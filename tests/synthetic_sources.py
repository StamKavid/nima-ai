"""Two invented sources of deliberately different shape, used only to prove the adapter protocol.

Neither is a real feed and neither is registered: they live in the test tree so the product has no
dead source code. They differ from KIMDIS (and from each other) on every axis the engine could
have been fitted to:

* ``ledger``: semicolon-separated text, not JSON; page numbers in a comment header; money written
  with a decimal comma and dot grouping; identifiers like ``L-0001``; evidence located by physical
  line, not by a JSON pointer.
* ``events``: nested JSON paged by a cursor sequence (the last page has no next cursor); money as
  integer minor units with a currency-dependent exponent; composite identifiers ``namespace/n``.

Both keep the protocol's guarantees: a bad envelope raises ``SourcePageError``, a bad record
becomes a ``PageIssue`` with a fixed reason, every record is accounted for exactly once, and money
is exact decimal text, never a float.
"""

import csv
import hashlib
import json
import re
from decimal import Decimal

from nima.sources.base import (
    DEFAULT_MAX_BYTES,
    NormalizedPage,
    NormalizedRecord,
    PageIssue,
    SourcePageError,
    SourceProvenance,
    SourceRequest,
)

LEDGER_HEADER = re.compile(r"^#ledger page=(\d+) pages=(\d+) total=(\d+)$")
LEDGER_COLUMNS = ["id", "date", "amount", "memo"]
LEDGER_ID = re.compile(r"^L-\d{4,}$")
LEDGER_AMOUNT = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+),\d{2}$")
EVENT_NAMESPACE = re.compile(r"^[a-z0-9_-]+$")
EXPONENTS = {"EUR": 2, "USD": 2, "JPY": 0, "KWD": 3}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class LedgerAdapter:
    name = "ledger"
    connector_version = "ledger-connector-v2"
    normalizer_version = "ledger-normalized-v5"
    provenance = SourceProvenance(
        endpoint="https://ledger.example.invalid/api/entries",
        documentation_url="https://ledger.example.invalid/docs",
        license="Synthetic test data, no real licence",
    )

    def query_payload(self) -> dict[str, object]:
        return {"feed": "ledger", "account": "synthetic"}

    def request_for(self, page: int) -> SourceRequest:
        return SourceRequest("GET", self.provenance.endpoint, {"p": page}, None, "text/csv")

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        if len(raw) > max_bytes:
            raise SourcePageError("ledger page too large")
        try:
            lines = raw.decode("utf-8").split("\n")
        except UnicodeDecodeError:
            raise SourcePageError("ledger page is not text") from None
        header = LEDGER_HEADER.match(lines[0]) if lines else None
        if header is None or lines[1:2] != [";".join(LEDGER_COLUMNS)]:
            raise SourcePageError("ledger envelope is malformed")
        number, pages, total = (int(g) for g in header.groups())
        if not (pages >= 1 and number < pages):
            raise SourcePageError("ledger pagination is inconsistent")
        rows = [(position, line) for position, line in enumerate(lines[2:], start=3) if line]
        records: list[NormalizedRecord] = []
        issues: list[PageIssue] = []
        ids: list[str] = []
        hashes: list[str] = []
        for index, (position, line) in enumerate(rows):
            pointer = f"line:{position}"
            hashes.append(_sha(line))
            cells = next(csv.reader([line], delimiter=";"), [])
            if len(cells) != len(LEDGER_COLUMNS):
                issues.append(PageIssue(index, pointer, "bad_row"))
                continue
            row = dict(zip(LEDGER_COLUMNS, cells, strict=True))
            if not LEDGER_ID.match(row["id"]):
                issues.append(PageIssue(index, pointer, "bad_id"))
                continue
            ids.append(f"ledger:{row['id']}")
            if not LEDGER_AMOUNT.match(row["amount"]):
                issues.append(PageIssue(index, pointer, "bad_amount"))
            else:
                amount = Decimal(row["amount"].replace(".", "").replace(",", "."))
                records.append(
                    NormalizedRecord(
                        index=index,
                        evidence_pointer=pointer,
                        source_id=f"ledger:{row['id']}",
                        content_sha256=hashes[index],
                        normalized={
                            "id": row["id"],
                            "date": row["date"],
                            "amount": format(amount, "f"),
                            "memo": row["memo"],
                        },
                    )
                )
        return NormalizedPage(
            number=number,
            size=len(rows),
            total_records=total,
            total_pages=pages,
            last=number == pages - 1,
            record_count=len(rows),
            response_sha256=hashlib.sha256(raw).hexdigest(),
            records=tuple(records),
            issues=tuple(issues),
            source_ids=tuple(ids),
            record_hashes=tuple(hashes),
        )


def ledger_page(page: int, pages: int, total: int, rows: list[tuple[str, str, str]]) -> bytes:
    """Rows are (id, amount, memo); the date column is fixed so tests stay short."""
    lines = [f"#ledger page={page} pages={pages} total={total}", ";".join(LEDGER_COLUMNS)]
    lines += [f"{row_id};2026-11-06;{amount};{memo}" for row_id, amount, memo in rows]
    return ("\n".join(lines) + "\n").encode()


class EventsAdapter:
    name = "events"
    connector_version = "events-connector-v1"
    normalizer_version = "events-normalized-v9"
    provenance = SourceProvenance(
        endpoint="https://events.example.invalid/v1/stream",
        documentation_url="https://events.example.invalid/docs",
        license="Synthetic test data, no real licence",
    )

    def query_payload(self) -> dict[str, object]:
        return {"stream": "events", "since": "2026-11-06"}

    def request_for(self, page: int) -> SourceRequest:
        return SourceRequest(
            "POST",
            self.provenance.endpoint,
            {"seq": page},
            self.query_payload(),
            "application/json",
        )

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        if len(raw) > max_bytes:
            raise SourcePageError("events page too large")
        try:
            document = json.loads(raw)
            meta, data = document["meta"], document["data"]
            number, pages, total = int(meta["seq"]), int(meta["pages"]), int(meta["total"])
            cursor = meta["next"]
        except (ValueError, KeyError, TypeError):
            raise SourcePageError("events envelope is malformed") from None
        last = cursor is None
        if (
            not isinstance(data, list)
            or not (pages >= 1 and 0 <= number < pages)
            or last != (number == pages - 1)
        ):
            raise SourcePageError("events pagination is inconsistent")
        records: list[NormalizedRecord] = []
        issues: list[PageIssue] = []
        ids: list[str] = []
        hashes: list[str] = []
        for index, item in enumerate(data):
            pointer = f"/data/{index}"
            hashes.append(_sha(json.dumps(item, sort_keys=True, separators=(",", ":"))))
            key = item.get("key") if isinstance(item, dict) else None
            ident = _event_id(key)
            if ident is not None:
                ids.append(f"events:{ident}")
            value = item.get("value") if isinstance(item, dict) else None
            if ident is None:
                issues.append(PageIssue(index, pointer, "bad_key"))
            elif (reason := _event_money_problem(value)) is not None:
                issues.append(PageIssue(index, pointer, reason))
            else:
                assert isinstance(value, dict)
                currency = str(value["ccy"])
                amount = Decimal(f"{value['minor']}e-{EXPONENTS[currency]}")
                records.append(
                    NormalizedRecord(
                        index=index,
                        evidence_pointer=pointer,
                        source_id=f"events:{ident}",
                        content_sha256=hashes[index],
                        normalized={
                            "key": ident,
                            "amount": format(amount, "f"),
                            "currency": currency,
                        },
                    )
                )
        return NormalizedPage(
            number=number,
            size=len(data),
            total_records=total,
            total_pages=pages,
            last=last,
            record_count=len(data),
            response_sha256=hashlib.sha256(raw).hexdigest(),
            records=tuple(records),
            issues=tuple(issues),
            source_ids=tuple(ids),
            record_hashes=tuple(hashes),
        )


def _event_id(key: object) -> str | None:
    if not isinstance(key, dict):
        return None
    namespace, n = key.get("ns"), key.get("n")
    if not (isinstance(namespace, str) and EVENT_NAMESPACE.match(namespace)):
        return None
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        return None
    return f"{namespace}/{n}"


def _event_money_problem(value: object) -> str | None:
    if not isinstance(value, dict):
        return "bad_value"
    if value.get("ccy") not in EXPONENTS:
        return "unknown_currency"
    minor = value.get("minor")
    if isinstance(minor, bool) or not isinstance(minor, int):
        return "bad_minor"
    return None


def events_page(
    seq: int, pages: int, total: int, items: list[dict[str, object]], *, final: bool | None = None
) -> bytes:
    is_last = seq == pages - 1 if final is None else final
    meta = {"seq": seq, "pages": pages, "total": total, "next": None if is_last else f"c{seq + 1}"}
    return json.dumps({"meta": meta, "data": items}).encode()


def event(namespace: str, n: int, minor: object, currency: object = "EUR") -> dict[str, object]:
    return {"key": {"ns": namespace, "n": n}, "value": {"minor": minor, "ccy": currency}}
