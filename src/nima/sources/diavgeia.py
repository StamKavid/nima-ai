"""Diavgeia award decisions (type Δ.2.2) as a source adapter.

The request and field names follow the official API documentation read on 2026-11-20
(``docs/sources/diavgeia-acceptance.md``). No live response has been recorded yet, so every
shape here is **unverified** until the first approved real run; a response that does not match
stops the page (envelope) or is quarantined (record) and never reaches a metric.

Only a closed set of metadata is kept. A decision's persons are reduced to a count and the
distinct tax-number types. The documented main Greek type covers natural and legal persons
together, and the first real run showed short codes whose meaning is unverified, so no tax
number or name is projected (``SPEC-diavgeia-pilot.md``).
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Never, cast

from nima.sources.base import (
    DEFAULT_MAX_BYTES,
    NormalizedPage,
    NormalizedRecord,
    PageIssue,
    PayloadSource,
    QueryPayload,
    SourcePageError,
    SourceProvenance,
    SourceRequest,
)

ENDPOINT = "https://diavgeia.gov.gr/opendata/search.json"
DOCUMENTATION_URL = "https://diavgeia.gov.gr/api/help"
LICENSE = "CC BY 4.0 (Law 3448/2006)"
CONNECTOR_VERSION = "diavgeia-search-v1"
NORMALIZER_VERSION = "diavgeia-decision-v1"
DECISION_TYPE = "Δ.2.2"
PAGE_SIZE = 100
MAX_WINDOW_DAYS = 30
MAX_EXPONENT = 30
STATUSES = frozenset({"PUBLISHED", "PENDING_REVOCATION", "REVOKED"})
_ORGANIZATION = re.compile(r"[A-Za-z0-9_-]{1,32}")
_ADA = re.compile(r"[^\W_]+(?:-[^\W_]+)*")


@dataclass(frozen=True)
class DiavgeiaQuery:
    """One organisation, one issue-date window of at most 30 days, awards only."""

    organization: str
    from_issue_date: str
    to_issue_date: str

    def __post_init__(self) -> None:
        if not isinstance(self.organization, str) or not _ORGANIZATION.fullmatch(self.organization):
            raise ValueError("Invalid organization")
        start, end = _day(self.from_issue_date), _day(self.to_issue_date)
        if not 0 <= (end - start).days < MAX_WINDOW_DAYS:
            raise ValueError("Invalid issue-date window")

    def payload(self) -> dict[str, object]:
        return {
            "organization": self.organization,
            "decisionType": DECISION_TYPE,
            "fromIssueDate": self.from_issue_date,
            "toIssueDate": self.to_issue_date,
            "status": "all",
            "size": PAGE_SIZE,
        }


def _day(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Invalid date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid date") from None
    if parsed.isoformat() != value:
        raise ValueError("Invalid date")
    return parsed


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourcePageError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(name: str) -> Never:
    raise SourcePageError("Non-finite JSON number")


def _decode(raw: bytes, max_bytes: int) -> dict[str, object]:
    if len(raw) > max_bytes:
        raise SourcePageError("Response exceeds the size limit")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, RecursionError):
        raise SourcePageError("Response is not valid JSON") from None
    if not isinstance(value, dict):
        raise SourcePageError("Response is not a JSON object")
    return value


def _integer(value: object, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SourcePageError(f"Invalid pagination at {field}")
    return value


def _source_hash(value: object) -> str:
    """Hash parsed source content; exact decimals are tagged so precision is part of the hash."""

    def tagged(item: object, depth: int = 0) -> object:
        if depth > 64:
            raise SourcePageError("Source content exceeds canonical depth limit")
        if isinstance(item, Decimal):
            return ["decimal", str(item)]
        if isinstance(item, dict):
            return ["object", [[k, tagged(v, depth + 1)] for k, v in sorted(item.items())]]
        if isinstance(item, list):
            return ["array", [tagged(v, depth + 1) for v in item]]
        return ["scalar", item]

    canonical = json.dumps(tagged(value), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class _BadRecord(ValueError):
    """A source defect in one record; the reason is fixed text, never the source value."""


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _BadRecord("invalid_text_field")
    return value


def _optional_timestamp(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _BadRecord("invalid_timestamp")
    return value


def _ada(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64 or not _ADA.fullmatch(value):
        raise _BadRecord("invalid_ada")
    return value


def _amount(extra: dict[str, object]) -> tuple[str | None, str | None]:
    award = extra.get("awardAmount")
    if award is None:
        return None, None
    if not isinstance(award, dict):
        raise _BadRecord("invalid_award_amount")
    amount, currency = award.get("amount"), award.get("currency")
    if amount is None:
        return None, _optional_text(currency)
    if isinstance(amount, bool) or not isinstance(amount, (int, Decimal)):
        raise _BadRecord("invalid_award_amount")
    number = Decimal(amount)
    if abs(number.adjusted()) > MAX_EXPONENT:
        raise _BadRecord("invalid_award_amount")
    return format(number, "f"), _optional_text(currency)


def _persons(extra: dict[str, object]) -> tuple[int, list[str]]:
    persons = extra.get("person")
    if persons is None:
        return 0, []
    if not isinstance(persons, list) or not all(isinstance(p, dict) for p in persons):
        raise _BadRecord("invalid_persons")
    types = {
        t
        for t in (cast(dict[str, object], p).get("afmType") for p in persons)
        if isinstance(t, str)
    }
    return len(persons), sorted(types)


def _record(value: object) -> tuple[str, dict[str, object]]:
    if not isinstance(value, dict):
        raise _BadRecord("record_not_an_object")
    ada = _ada(value.get("ada"))
    status, version = value.get("status"), value.get("versionId")
    if status not in STATUSES:
        raise _BadRecord("unsupported_status")
    if not isinstance(version, str) or not version.strip():
        raise _BadRecord("invalid_version_id")
    private = value.get("privateData")
    if private is not None and type(private) is not bool:
        raise _BadRecord("invalid_private_data")
    extra = value.get("extraFieldValues")
    if extra is None:
        extra = {}
    if not isinstance(extra, dict):
        raise _BadRecord("invalid_extra_fields")
    related = extra.get("textRelatedADA")
    amount, currency = _amount(extra)
    person_count, person_types = _persons(extra)
    return f"diavgeia:{ada}", {
        "ada": ada,
        "decision_type": _optional_text(value.get("decisionTypeId")),
        "organization_id": _optional_text(value.get("organizationId")),
        "issue_timestamp_ms": _optional_timestamp(value.get("issueDate")),
        "submission_timestamp_ms": _optional_timestamp(value.get("submissionTimestamp")),
        "version_id": version,
        "status": status,
        "corrected_version_id": _optional_text(value.get("correctedVersionId")),
        "private_data": private,
        "related_ada": None if related in (None, "") else _ada(related),
        "award_amount": amount,
        "award_currency": currency,
        "person_count": person_count,
        "person_types": person_types,
    }


DECISION_ENDPOINT = "https://diavgeia.gov.gr/opendata/decisions"


class InvalidDecision(ValueError):
    """A single-decision response that cannot be used; the reason is fixed text."""


def decision_url(ada: str) -> str:
    """The documented single-decision path (``GET /decisions/<ADA>``, JSON by suffix)."""
    if not isinstance(ada, str) or len(ada) > 64 or not _ADA.fullmatch(ada):
        raise ValueError("Invalid ADA")
    return f"{DECISION_ENDPOINT}/{ada}.json"


def decision_summary(raw: bytes, ada: str, max_bytes: int) -> dict[str, str | None]:
    """Only the type, organisation and status of one decision; nothing else is read."""
    try:
        value = _decode(raw, max_bytes)
    except SourcePageError as error:
        text = str(error)
        if "size" in text:
            raise InvalidDecision("size") from None
        raise InvalidDecision("object" if "object" in text else "json") from None
    if value.get("ada") != ada:
        raise InvalidDecision("ada_mismatch")
    if value.get("status") not in STATUSES:
        raise InvalidDecision("status")
    kind, organization = value.get("decisionTypeId"), value.get("organizationId")
    if not isinstance(kind, str) or not kind.strip():
        raise InvalidDecision("decision_type")
    if organization is not None and (not isinstance(organization, str) or not organization.strip()):
        raise InvalidDecision("organization")
    return {
        "decision_type": kind,
        "organization_id": organization,
        "status": cast(str, value["status"]),
    }


class DiavgeiaAdapter:
    name = "diavgeia"
    connector_version = CONNECTOR_VERSION
    normalizer_version = NORMALIZER_VERSION
    provenance = SourceProvenance(
        endpoint=ENDPOINT, documentation_url=DOCUMENTATION_URL, license=LICENSE
    )

    def __init__(self, query: PayloadSource | None = None) -> None:
        self._query = query

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "DiavgeiaAdapter":
        """Rebuild the adapter for a saved run; the payload must be exactly what was written."""
        organization = payload.get("organization")
        first, last = payload.get("fromIssueDate"), payload.get("toIssueDate")
        if not isinstance(organization, str) or not isinstance(first, str):
            raise ValueError("Invalid saved query")
        if not isinstance(last, str):
            raise ValueError("Invalid saved query")
        canonical = DiavgeiaQuery(organization, first, last).payload()
        if canonical != dict(payload):
            raise ValueError("Saved query is not in canonical form")
        return cls(QueryPayload(canonical))

    def query_payload(self) -> dict[str, object]:
        if self._query is None:
            raise ValueError("this adapter was created without a query")
        return self._query.payload()

    def request_for(self, page: int) -> SourceRequest:
        """The documented search: GET, 0-based page, awards for one organisation and window."""
        query = self.query_payload()
        return SourceRequest(
            method="GET",
            url=ENDPOINT,
            params={
                "org": cast(str, query["organization"]),
                "type": cast(str, query["decisionType"]),
                "from_issue_date": cast(str, query["fromIssueDate"]),
                "to_issue_date": cast(str, query["toIssueDate"]),
                "status": cast(str, query["status"]),
                "page": page,
                "size": cast(int, query["size"]),
            },
            json=None,
            accept="application/json",
        )

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        response = _decode(raw, max_bytes)
        info, decisions = response.get("info"), response.get("decisions")
        if not isinstance(info, dict) or not isinstance(decisions, list):
            raise SourcePageError("Missing info or decisions")
        number = _integer(info.get("page"), "page")
        size = _integer(info.get("size"), "size", 1)
        total = _integer(info.get("total"), "total")
        pages = math.ceil(total / size)
        if number >= max(1, pages) or len(decisions) != min(size, max(0, total - number * size)):
            raise SourcePageError("Inconsistent pagination")
        digest = hashlib.sha256(raw).hexdigest()
        records: list[NormalizedRecord] = []
        issues: list[PageIssue] = []
        source_ids: list[str] = []
        for index, value in enumerate(decisions):
            pointer = f"/decisions/{index}"
            try:
                source_id, normalized = _record(value)
            except _BadRecord as error:
                issues.append(PageIssue(index, pointer, str(error)))
                ada = value.get("ada") if isinstance(value, dict) else None
                if isinstance(ada, str) and len(ada) <= 64 and _ADA.fullmatch(ada):
                    source_ids.append(f"diavgeia:{ada}")
            else:
                source_ids.append(source_id)
                records.append(
                    NormalizedRecord(index, pointer, source_id, _source_hash(value), normalized)
                )
        return NormalizedPage(
            number=number,
            size=size,
            total_records=total,
            total_pages=pages,
            last=number == max(0, pages - 1),
            record_count=len(decisions),
            response_sha256=digest,
            records=tuple(records),
            issues=tuple(issues),
            source_ids=tuple(source_ids),
            record_hashes=tuple(_source_hash(value) for value in decisions),
        )
