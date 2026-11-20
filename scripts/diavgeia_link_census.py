"""Read-only census of how our own KIMDIS records cite Diavgeia decisions.

Run it before any Diavgeia request: it measures the explicit key (``diavgeiaADA``) in the data we
already hold. It answers two questions:

* how many KIMDIS records cite a Diavgeia decision at all;
* how many records share each cited decision. A decision cited by many records is an umbrella
  (for example an annual approval), not a one-to-one link between stages of one procurement.

The session is read-only and the report holds counts and public ADA identifiers only: no record
content, names, tax numbers or amounts. A record counts once however many versions it has.

    NIMA_DATABASE_URL=... uv run python -m scripts.diavgeia_link_census --top 20
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

# One row per cited decision: how many distinct KIMDIS records cite it.
PER_DECISION = """
SELECT r.ref ->> 'target_id' AS decision, count(DISTINCT v.source_id) AS records
FROM nima.record_versions v
CROSS JOIN LATERAL jsonb_array_elements(coalesce(v.normalized -> 'references', '[]'::jsonb))
  AS r(ref)
WHERE starts_with(v.source_id, 'kimdis:') AND r.ref ->> 'source_field' = 'diavgeiaADA'
GROUP BY 1
"""

RECORDS = """
SELECT count(DISTINCT source_id) FROM nima.record_versions WHERE starts_with(source_id, 'kimdis:')
"""

CITING = """
SELECT count(DISTINCT v.source_id)
FROM nima.record_versions v
CROSS JOIN LATERAL jsonb_array_elements(coalesce(v.normalized -> 'references', '[]'::jsonb))
  AS r(ref)
WHERE starts_with(v.source_id, 'kimdis:') AND r.ref ->> 'source_field' = 'diavgeiaADA'
"""

SUMMARY = (
    "WITH per AS ("
    + PER_DECISION
    + ") SELECT count(*), count(*) FILTER (WHERE records > 1), coalesce(max(records), 0) FROM per"
)

MOST_SHARED = (
    "WITH per AS ("
    + PER_DECISION
    + ") SELECT decision, records FROM per ORDER BY records DESC, decision ASC LIMIT %s"
)


def open_read_only(dsn: str) -> Connection:
    connection = psycopg.connect(dsn)
    connection.read_only = True
    return connection


def _one(connection: Connection, sql: str) -> tuple[int, ...]:
    # Every query here is an aggregate, so it always returns exactly one row.
    return tuple(int(value) for value in connection.execute(sql).fetchall()[0])


def census(dsn: str, *, top: int = DEFAULT_TOP) -> dict[str, object]:
    with open_read_only(dsn) as connection:
        (records,) = _one(connection, RECORDS)
        (citing,) = _one(connection, CITING)
        distinct, shared, widest = _one(connection, SUMMARY)
        rows = connection.execute(MOST_SHARED, (top,)).fetchall()
    return {
        "kimdis_records": records,
        "cite_a_diavgeia_ada": citing,
        "distinct_cited_decisions": distinct,
        "decisions_cited_by_more_than_one_record": shared,
        "max_records_citing_one_decision": widest,
        "most_shared": [{"decision": str(d), "kimdis_records": int(n)} for d, n in rows],
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
    parser = argparse.ArgumentParser(prog="python -m scripts.diavgeia_link_census")
    parser.add_argument(
        "--top", type=_top, default=DEFAULT_TOP, help="most-shared decisions to list"
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
