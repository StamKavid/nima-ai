"""One GEMI company-search response becomes one outcome per queried AFM, never a chosen company.

The search returns complete Company objects, answers 404 (not an empty list) when nothing matches
and may describe a larger result than it returned. Every returned company is kept; none is selected,
and a queried AFM is never treated as a verified identity. Only a controlled field path, never a
source value, appears in a quarantine reason.

https://opendata-api.businessportal.gr/api-docs
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from nima.sources.gemi import (
    InvalidProfile,
    RegistryCompany,
    decode_body,
    normalize_company,
)

MAX_HITS = 20
ASCII_TRIM = " \t\r\n"

type Outcome = Literal[
    "hit_single",
    "hit_multiple",
    "truncated",
    "afm_mismatch",
    "not_found_at_observation",
    "quarantined",
]


@dataclass(frozen=True)
class Hit:
    company: RegistryCompany
    afm_matches: bool


@dataclass(frozen=True)
class SearchResult:
    queried_afm: str
    http_status: int
    outcome: Outcome
    truncated: bool
    total_count: int | None
    hits: tuple[Hit, ...]
    response_sha256: str
    quarantine_path: str | None


def queryable_afm(value: object) -> str:
    """Only a nine-ASCII-digit text that is not the all-zero placeholder may be sent."""
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9]{9}", value) is None
        or value == "000000000"
    ):
        raise ValueError("afm")
    return value


def _count(value: object, path: str) -> int:
    if type(value) is not int or value < 0:
        raise InvalidProfile(path)
    return value


def _size(value: object, path: str) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 6:
        return int(value)
    raise InvalidProfile(path)


def _quarantined(base: SearchResult, path: str) -> SearchResult:
    return SearchResult(
        base.queried_afm,
        base.http_status,
        "quarantined",
        False,
        None,
        (),
        base.response_sha256,
        path,
    )


def _hits(results: list[object], queried: str, digest: str) -> tuple[Hit, ...]:
    hits = []
    for index, item in enumerate(results):
        path = f"/searchResults/{index}"
        if not isinstance(item, dict):
            raise InvalidProfile(path)
        company = normalize_company(item, digest, expected=None, prefix=path)
        reported = company.fields["reported_afm"].value
        matches = isinstance(reported, str) and reported.strip(ASCII_TRIM) == queried
        hits.append(Hit(company, matches))
    return tuple(hits)


def parse_search(raw: bytes, *, queried_afm: str, http_status: int) -> SearchResult:
    """Parse the answer to one ``afm`` query; only HTTP 200 and 404 belong here."""
    queried = queryable_afm(queried_afm)
    if type(http_status) is not int or http_status not in (200, 404):
        raise ValueError("status")
    digest = hashlib.sha256(raw).hexdigest()
    base = SearchResult(queried, http_status, "quarantined", False, None, (), digest, None)
    if http_status == 404:
        return SearchResult(queried, 404, "not_found_at_observation", False, None, (), digest, None)
    try:
        document = decode_body(raw)
        metadata = document.get("searchMetadata")
        if not isinstance(metadata, dict):
            raise InvalidProfile("/searchMetadata")
        total = _count(metadata.get("totalCount"), "/searchMetadata/totalCount")
        if _count(metadata.get("resultsOffset"), "/searchMetadata/resultsOffset") != 0:
            raise InvalidProfile("/searchMetadata/resultsOffset")
        size = _size(metadata.get("resultsSize"), "/searchMetadata/resultsSize")
        results = document.get("searchResults")
        if not isinstance(results, list) or len(results) > MAX_HITS:
            raise InvalidProfile("/searchResults")
        if not results:
            raise InvalidProfile("empty_results")
        if total < len(results):
            raise InvalidProfile("/searchMetadata/totalCount")
        if size != len(results):
            raise InvalidProfile("/searchMetadata/resultsSize")
        hits = _hits(results, queried, digest)
    except InvalidProfile as error:
        return _quarantined(base, str(error))
    truncated = total > len(hits)
    outcome: Outcome
    if any(not hit.afm_matches for hit in hits):
        outcome = "afm_mismatch"
    elif truncated:
        outcome = "truncated"
    elif len(hits) > 1:
        outcome = "hit_multiple"
    else:
        outcome = "hit_single"
    return SearchResult(queried, 200, outcome, truncated, total, hits, digest, None)
