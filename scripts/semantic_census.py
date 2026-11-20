"""Read-only census of date formats and supplier tax-ID classes in stored KIMDIS records.

Run it before writing the V1-05 time model: the model must parse the formats that really occur,
not a guess. It reports, per stored record version:

* for ``source_submitted_at`` and ``source_updated_at``: how many are missing or null or
  text, and the most common *shapes* of the text. A shape replaces each ASCII digit by ``9`` and
  every character outside ``9 / . : + , space -`` by ``A``, so it shows separators, a time part
  and a zone suffix, never a date;
* for supplier tax IDs: counts per class (nine digits, all zero, one repeated digit, a sequential
  run, leading zero, other lengths, non-ASCII, missing) and how many needed whitespace trimming;
* supplier country-code counts.

The session is read-only and the report holds counts and shapes only: no date, name, tax number,
amount or title. ``record_versions`` counts stored versions; ``kimdis_records`` counts distinct
source IDs.

    NIMA_DATABASE_URL=... uv run python -m scripts.semantic_census --top 20
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence

import psycopg
from psycopg import Connection

MAX_TOP = 100
DEFAULT_TOP = 20

TAX_CLASSES = (
    "missing_or_null",
    "non_ascii",
    "all_zero",
    "repeated_digit",
    "sequential_run",
    "leading_zero",
    "other_nine_digits",
    "nine_chars_not_all_digits",
    "shorter_than_nine",
    "longer_than_nine",
)

# Each query is written out in full (no string building). Only KIMDIS rows are read; a "version" is
# one stored row of ``nima.record_versions``.
RECORDS = r"""
SELECT count(DISTINCT source_id), count(*)
FROM nima.record_versions
WHERE starts_with(source_id, 'kimdis:')
"""

SUBMITTED_KINDS = r"""
SELECT CASE
         WHEN v.normalized -> 'source_submitted_at' IS NULL
           OR jsonb_typeof(v.normalized -> 'source_submitted_at') = 'null' THEN 'missing_or_null'
         ELSE 'text'
       END AS kind,
       count(*)
FROM nima.record_versions v
WHERE starts_with(v.source_id, 'kimdis:')
GROUP BY 1
"""

SUBMITTED_SHAPES = r"""
WITH shaped AS (
  SELECT left(
           regexp_replace(
             regexp_replace(v.normalized ->> 'source_submitted_at', '[0-9]', '9', 'g'),
             '[^9/.:+, -]', 'A', 'g'),
           40) AS shape
  FROM nima.record_versions v
  WHERE starts_with(v.source_id, 'kimdis:')
    AND jsonb_typeof(v.normalized -> 'source_submitted_at') IS DISTINCT FROM 'null'
), grouped AS (
  SELECT shape, count(*) AS versions FROM shaped GROUP BY shape
)
SELECT shape, versions, count(*) OVER () AS distinct_shapes
FROM grouped
ORDER BY versions DESC, shape COLLATE "C" ASC
LIMIT %s
"""

UPDATED_KINDS = r"""
SELECT CASE
         WHEN v.normalized -> 'source_updated_at' IS NULL
           OR jsonb_typeof(v.normalized -> 'source_updated_at') = 'null' THEN 'missing_or_null'
         ELSE 'text'
       END AS kind,
       count(*)
FROM nima.record_versions v
WHERE starts_with(v.source_id, 'kimdis:')
GROUP BY 1
"""

UPDATED_SHAPES = r"""
WITH shaped AS (
  SELECT left(
           regexp_replace(
             regexp_replace(v.normalized ->> 'source_updated_at', '[0-9]', '9', 'g'),
             '[^9/.:+, -]', 'A', 'g'),
           40) AS shape
  FROM nima.record_versions v
  WHERE starts_with(v.source_id, 'kimdis:')
    AND jsonb_typeof(v.normalized -> 'source_updated_at') IS DISTINCT FROM 'null'
), grouped AS (
  SELECT shape, count(*) AS versions FROM shaped GROUP BY shape
)
SELECT shape, versions, count(*) OVER () AS distinct_shapes
FROM grouped
ORDER BY versions DESC, shape COLLATE "C" ASC
LIMIT %s
"""

SUPPLIER_LISTS = r"""
SELECT CASE
         WHEN jsonb_typeof(v.normalized -> 'suppliers') <> 'array' THEN 'missing_or_null'
         WHEN jsonb_array_length(v.normalized -> 'suppliers') = 0 THEN 'empty'
         ELSE 'non_empty'
       END AS kind,
       count(*)
FROM nima.record_versions v
WHERE starts_with(v.source_id, 'kimdis:')
GROUP BY 1
"""

TAX_ID_CLASSES = r"""
WITH occurrences AS (
  SELECT s.supplier ->> 'tax_id' AS raw,
         btrim(s.supplier ->> 'tax_id', E' \t\r\n\f\v') AS trimmed
  FROM nima.record_versions v
  CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(v.normalized -> 'suppliers') = 'array'
         THEN v.normalized -> 'suppliers' ELSE '[]'::jsonb END
  ) AS s(supplier)
  WHERE starts_with(v.source_id, 'kimdis:')
)
SELECT CASE
         WHEN trimmed IS NULL THEN 'missing_or_null'
         WHEN octet_length(trimmed) <> char_length(trimmed) THEN 'non_ascii'
         WHEN trimmed ~ '^0{9}$' THEN 'all_zero'
         WHEN trimmed ~ '^([1-9])\1{8}$' THEN 'repeated_digit'
         WHEN trimmed IN ('123456789', '987654321') THEN 'sequential_run'
         WHEN trimmed ~ '^0[0-9]{8}$' THEN 'leading_zero'
         WHEN trimmed ~ '^[0-9]{9}$' THEN 'other_nine_digits'
         WHEN char_length(trimmed) = 9 THEN 'nine_chars_not_all_digits'
         WHEN char_length(trimmed) < 9 THEN 'shorter_than_nine'
         ELSE 'longer_than_nine'
       END AS class,
       count(*),
       count(*) FILTER (WHERE raw IS NOT NULL AND raw <> trimmed)
FROM occurrences
GROUP BY 1
"""

SUPPLIER_COUNTRIES = r"""
SELECT s.supplier ->> 'country_code' AS country, count(*) AS occurrences
FROM nima.record_versions v
CROSS JOIN LATERAL jsonb_array_elements(
  CASE WHEN jsonb_typeof(v.normalized -> 'suppliers') = 'array'
       THEN v.normalized -> 'suppliers' ELSE '[]'::jsonb END
) AS s(supplier)
WHERE starts_with(v.source_id, 'kimdis:')
GROUP BY 1
ORDER BY occurrences DESC, (s.supplier ->> 'country_code') COLLATE "C" ASC NULLS LAST
LIMIT %s
"""


def open_read_only(dsn: str) -> Connection:
    connection = psycopg.connect(dsn)
    connection.read_only = True
    return connection


def _kinds(connection: Connection, sql: str, names: Sequence[str]) -> dict[str, int]:
    result = dict.fromkeys(names, 0)
    for kind, count in connection.execute(sql).fetchall():
        result[str(kind)] = int(count)
    return result


def _date_field(
    connection: Connection, kinds_sql: str, shapes_sql: str, top: int
) -> dict[str, object]:
    kinds = _kinds(connection, kinds_sql, ("missing_or_null", "text"))
    rows = connection.execute(shapes_sql, (top,)).fetchall()
    return {
        **kinds,
        "distinct_shapes": int(rows[0][2]) if rows else 0,
        "shapes": [{"shape": str(shape), "versions": int(n)} for shape, n, _ in rows],
    }


def census(dsn: str, *, top: int = DEFAULT_TOP) -> dict[str, object]:
    with open_read_only(dsn) as connection:
        records, versions = (int(value) for value in connection.execute(RECORDS).fetchall()[0])
        submitted = _date_field(connection, SUBMITTED_KINDS, SUBMITTED_SHAPES, top)
        updated = _date_field(connection, UPDATED_KINDS, UPDATED_SHAPES, top)
        lists = _kinds(connection, SUPPLIER_LISTS, ("missing_or_null", "empty", "non_empty"))
        classes = dict.fromkeys(TAX_CLASSES, 0)
        trimmed = 0
        for name, count, needing_trim in connection.execute(TAX_ID_CLASSES).fetchall():
            classes[str(name)] = int(count)
            trimmed += int(needing_trim)
        countries = connection.execute(SUPPLIER_COUNTRIES, (top,)).fetchall()
    return {
        "kimdis_records": records,
        "record_versions": versions,
        "date_fields": {"source_submitted_at": submitted, "source_updated_at": updated},
        "supplier_lists": lists,
        "supplier_tax_ids": {
            "occurrences": sum(classes.values()),
            "needs_whitespace_trim": trimmed,
            **classes,
        },
        "supplier_countries": [
            {"country": None if code is None else str(code), "occurrences": int(n)}
            for code, n in countries
        ],
    }


def _top(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number") from None
    if not 1 <= number <= MAX_TOP:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_TOP}")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.semantic_census")
    parser.add_argument(
        "--top", type=_top, default=DEFAULT_TOP, help="most common shapes and countries to list"
    )
    args = parser.parse_args(argv)
    dsn = os.environ.get("NIMA_DATABASE_URL", "")
    if not dsn.strip():
        print(json.dumps({"status": "failed", "failure": "configuration"}))
        return 2
    try:
        report = census(dsn, top=args.top)
    except psycopg.Error:
        print(json.dumps({"status": "failed", "failure": "database"}))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
