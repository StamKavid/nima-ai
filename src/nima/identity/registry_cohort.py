"""Bounded procurement/registry evidence from one read-only PostgreSQL snapshot.

https://www.postgresql.org/docs/17/transaction-iso.html#XACT-REPEATABLE-READ
https://www.postgresql.org/docs/17/functions-json.html
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Literal, cast
from uuid import UUID

from psycopg import sql

from nima.identity import MAX_COMPARISON_MENTIONS, MAX_REGISTRY_OBSERVATIONS, ComparisonError
from nima.identity.cohort import read_cohort_in_transaction
from nima.identity.policy import Occurrence, PartyClaim
from nima.identity.registry_policy import RegistryObservation, SearchOutcome
from nima.projections.worker import PROJECTION_VERSION
from nima.sources.gemi import NORMALIZER_VERSION as GEMI_VERSION
from nima.sources.gemi import Assertion
from nima.storage.gemi import IMPORT_VERSION, SEARCH_IMPORT_VERSION
from nima.storage.gemi_archive import CONTRACT, SEARCH_CONTRACT
from nima.storage.postgres import Connection, _connect, check_schema

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_IMPORTS = 10
# Current coverage contains only bounded versions, statuses and SQL integer counts.
_COVERAGE_RESERVE = 4096

_IMPORT_ROWS = """SELECT jsonb_build_object(
    'import_id', i.run_id, 'import_version', i.import_version,
    'normalizer_version', i.normalizer_version, 'manifest_sha256', i.manifest_sha256,
    'source_url', i.source_url, 'license', i.license, 'publisher', i.publisher,
    'imported_at', i.imported_at, 'profile_count', i.profile_count,
    'not_found_count', i.not_found_count, 'response_count', i.response_count) AS payload,
    i.import_version=%s AND i.normalizer_version=%s AND i.source_url=%s
        AND i.license=%s AND i.publisher=%s AS supported,
    i.profile_count=(SELECT count(*) FROM nima.gemi_observations o
        WHERE o.run_id=i.run_id AND o.outcome='found')
    AND i.not_found_count=(SELECT count(*) FROM nima.gemi_observations o
        WHERE o.run_id=i.run_id AND o.outcome='not_found_at_observation')
    AND i.response_count=(SELECT count(*) FROM nima.gemi_responses r WHERE r.run_id=i.run_id)
        AS complete,
    i.profile_count+i.not_found_count AS observations
    FROM nima.gemi_imports i WHERE i.run_id=ANY(%s)"""
_IMPORT_PARAMETERS = (
    IMPORT_VERSION,
    GEMI_VERSION,
    CONTRACT["source"],
    CONTRACT["license"],
    CONTRACT["publisher"],
)

_REGISTRY_ROWS = """SELECT jsonb_build_object(
    'import_id', o.run_id, 'registry_number', o.registry_number,
    'outcome', o.outcome, 'attempt', o.attempt, 'status', o.status,
    'raw_sha256', o.raw_sha256, 'observed_at', o.observed_at,
    'source_id', o.source_id, 'normalizer_version', o.normalizer_version,
    'fields', CASE WHEN o.outcome='found' THEN jsonb_build_object(
        'registry_number', v.normalized->'fields'->'registry_number',
        'reported_afm', v.normalized->'fields'->'reported_afm',
        'name_el', v.normalized->'fields'->'name_el',
        'legal_type_id', v.normalized->'fields'->'legal_type_id',
        'legal_type_label', v.normalized->'fields'->'legal_type_label',
        'status_id', v.normalized->'fields'->'status_id',
        'status_label', v.normalized->'fields'->'status_label',
        'is_branch', v.normalized->'fields'->'is_branch',
        'auto_registered', v.normalized->'fields'->'auto_registered',
        'incorporation_date', v.normalized->'fields'->'incorporation_date',
        'last_status_change', v.normalized->'fields'->'last_status_change') END) AS payload,
    r.run_id IS NOT NULL AND b.sha256 IS NOT NULL AND r.failure IS NULL AND (
        (o.outcome='found' AND o.status=200 AND o.source_id='gemi:' || o.registry_number
         AND o.normalizer_version=%s AND v.source_id IS NOT NULL
         AND v.normalized->>'source_id'=v.source_id
         AND v.normalized->>'normalizer_version'=v.normalizer_version
         AND v.normalized->>'response_sha256'=v.raw_sha256)
        OR (o.outcome='not_found_at_observation' AND o.status=404
            AND o.source_id IS NULL AND o.normalizer_version IS NULL)) AS valid
    FROM nima.gemi_observations o
    LEFT JOIN nima.gemi_responses r ON r.run_id=o.run_id AND r.registry_number=o.registry_number
        AND r.attempt=o.attempt AND r.status=o.status AND r.raw_sha256=o.raw_sha256
        AND r.observed_at=o.observed_at
    LEFT JOIN nima.raw_objects b ON b.sha256=o.raw_sha256 AND b.byte_length=r.byte_length
    LEFT JOIN nima.gemi_profile_versions v ON v.source_id=o.source_id
        AND v.normalizer_version=o.normalizer_version AND v.raw_sha256=o.raw_sha256
    WHERE o.run_id=ANY(%s)"""

_DATE_ROWS = """SELECT jsonb_build_object(
    'source_id', f.source_id, 'normalizer_version', f.normalizer_version,
    'content_sha256', f.content_sha256, 'source_submitted_at', f.source_submitted_at,
    'source_updated_at', f.source_updated_at) AS payload
    FROM nima.projection_contracts f WHERE f.projection_version=%s
    AND EXISTS (SELECT 1 FROM nima.observations o WHERE o.run_id=%s
        AND o.source_id=f.source_id AND o.normalizer_version=f.normalizer_version
        AND o.content_sha256=f.content_sha256)"""

_FIELD_SPECS = (
    ("registry_number", "/arGemi", "integer"),
    ("reported_afm", "/afm", "text"),
    ("name_el", "/coNameEl", "text"),
    ("legal_type_id", "/legalType/id", "integer"),
    ("legal_type_label", "/legalType/descr", "text"),
    ("status_id", "/status/id", "integer"),
    ("status_label", "/status/descr", "text"),
    ("is_branch", "/isBranch", "boolean"),
    ("auto_registered", "/autoRegistered", "boolean"),
    ("incorporation_date", "/incorporationDate", "date"),
    ("last_status_change", "/lastStatusChange", "date"),
)


_SEARCH_IMPORT_ROWS = """SELECT jsonb_build_object(
    'import_id', i.run_id, 'import_version', i.import_version,
    'connector_version', i.connector_version, 'normalizer_version', i.normalizer_version,
    'manifest_sha256', i.manifest_sha256, 'source_url', i.source_url, 'license', i.license,
    'publisher', i.publisher, 'imported_at', i.imported_at, 'afm_count', i.afm_count,
    'request_count', i.request_count, 'hit_count', i.hit_count,
    'unconfirmed_quarantine_count', i.unconfirmed_quarantine_count) AS payload,
    i.import_version=%s AND i.connector_version=%s AND i.normalizer_version=%s
        AND i.source_url=%s AND i.license=%s AND i.publisher=%s AS supported,
    i.afm_count=(SELECT count(*) FROM nima.gemi_search_outcomes o WHERE o.run_id=i.run_id)
    AND i.request_count=(SELECT count(*) FROM nima.gemi_search_requests r WHERE r.run_id=i.run_id)
    AND i.hit_count=(SELECT count(*) FROM nima.gemi_search_hits h WHERE h.run_id=i.run_id)
    AND i.unconfirmed_quarantine_count=(SELECT count(*) FROM nima.gemi_search_outcomes o
        WHERE o.run_id=i.run_id AND o.unconfirmed_quarantine) AS complete,
    i.hit_count AS observations
    FROM nima.gemi_search_imports i WHERE i.run_id=ANY(%s)"""
_SEARCH_PARAMETERS = (
    SEARCH_IMPORT_VERSION,
    SEARCH_CONTRACT["connector_version"],
    GEMI_VERSION,
    CONTRACT["source"],
    CONTRACT["license"],
    CONTRACT["publisher"],
)

_SEARCH_QUERY_ROWS = """SELECT jsonb_build_object(
    'import_id', o.run_id, 'afm', o.afm, 'outcome', o.outcome, 'truncated', o.truncated,
    'unconfirmed_quarantine', o.unconfirmed_quarantine, 'hit_count', o.hit_count,
    'attempt', o.attempt, 'status', o.status, 'raw_sha256', o.raw_sha256,
    'observed_at', o.observed_at) AS payload,
    r.run_id IS NOT NULL AND b.sha256 IS NOT NULL AND r.failure IS NULL
        AND r.status=o.status AND o.hit_count=(SELECT count(*) FROM nima.gemi_search_hits h
            WHERE h.run_id=o.run_id AND h.afm=o.afm) AS valid
    FROM nima.gemi_search_outcomes o
    LEFT JOIN nima.gemi_search_requests r ON r.run_id=o.run_id AND r.afm=o.afm
        AND r.attempt=o.attempt AND r.status=o.status AND r.raw_sha256=o.raw_sha256
        AND r.observed_at=o.observed_at
    LEFT JOIN nima.raw_objects b ON b.sha256=o.raw_sha256 AND b.byte_length=r.byte_length
    WHERE o.run_id=ANY(%s)"""

_SEARCH_HIT_ROWS = """SELECT jsonb_build_object(
    'import_id', h.run_id, 'queried_afm', h.afm, 'hit_index', h.hit_index,
    'registry_number', h.registry_number, 'afm_matches', h.afm_matches,
    'outcome', 'found', 'attempt', o.attempt, 'status', o.status, 'raw_sha256', h.raw_sha256,
    'observed_at', o.observed_at, 'source_id', h.source_id,
    'normalizer_version', h.normalizer_version,
    'fields', jsonb_build_object(
        'registry_number', v.normalized->'fields'->'registry_number',
        'reported_afm', v.normalized->'fields'->'reported_afm',
        'name_el', v.normalized->'fields'->'name_el',
        'legal_type_id', v.normalized->'fields'->'legal_type_id',
        'legal_type_label', v.normalized->'fields'->'legal_type_label',
        'status_id', v.normalized->'fields'->'status_id',
        'status_label', v.normalized->'fields'->'status_label',
        'is_branch', v.normalized->'fields'->'is_branch',
        'auto_registered', v.normalized->'fields'->'auto_registered',
        'incorporation_date', v.normalized->'fields'->'incorporation_date',
        'last_status_change', v.normalized->'fields'->'last_status_change')) AS payload,
    r.run_id IS NOT NULL AND b.sha256 IS NOT NULL AND r.failure IS NULL AND o.status=200
        AND o.outcome IN ('hit_single','hit_multiple','truncated','afm_mismatch')
        AND h.normalizer_version=%s AND v.source_id IS NOT NULL
        AND v.normalized->>'source_id'=v.source_id
        AND v.normalized->>'normalizer_version'=v.normalizer_version
        AND v.normalized->>'response_sha256'=v.raw_sha256 AS valid
    FROM nima.gemi_search_hits h
    JOIN nima.gemi_search_outcomes o ON o.run_id=h.run_id AND o.afm=h.afm
    LEFT JOIN nima.gemi_search_requests r ON r.run_id=o.run_id AND r.afm=o.afm
        AND r.attempt=o.attempt AND r.status=o.status AND r.raw_sha256=o.raw_sha256
        AND r.observed_at=o.observed_at
    LEFT JOIN nima.raw_objects b ON b.sha256=h.raw_sha256 AND b.byte_length=r.byte_length
    LEFT JOIN nima.gemi_profile_versions v ON v.source_id=h.source_id
        AND v.normalizer_version=h.normalizer_version AND v.raw_sha256=h.raw_sha256
    WHERE h.run_id=ANY(%s)"""


@dataclass(frozen=True)
class SearchImportEvidence:
    import_id: UUID
    import_version: str
    connector_version: str
    normalizer_version: str
    manifest_sha256: str
    source_url: str
    license: str
    publisher: str
    imported_at: str
    afm_count: int
    request_count: int
    hit_count: int
    unconfirmed_quarantine_count: int


@dataclass(frozen=True)
class SearchQueryEvidence:
    """What searching one AFM answered. A 404 is a statement about one observation."""

    import_id: UUID
    afm: str
    outcome: SearchOutcome
    truncated: bool
    unconfirmed_quarantine: bool
    hit_count: int
    attempt: int
    status: int
    raw_sha256: str
    observed_at: str


@dataclass(frozen=True)
class ImportEvidence:
    import_id: UUID
    import_version: str
    normalizer_version: str
    manifest_sha256: str
    source_url: str
    license: str
    publisher: str
    imported_at: str
    profile_count: int
    not_found_count: int
    response_count: int


@dataclass(frozen=True)
class RegistryEvidence:
    claim: RegistryObservation
    attempt: int
    status: int
    raw_sha256: str
    observed_at: str
    source_id: str | None
    normalizer_version: str | None
    fields: Mapping[str, Assertion]


@dataclass(frozen=True)
class PartyEvidence:
    source_id: str
    normalizer_version: str
    content_sha256: str
    observation_id: int
    role: Literal["buyer", "supplier"]
    ordinal: int
    name: str | None
    tax_id: str | None
    source_key: str | None
    country_code: str | None
    raw_sha256: str
    json_pointer: str
    observed_at: str
    source_submitted_at: str | None
    source_updated_at: str | None

    def claim(self) -> PartyClaim:
        return {
            "role": self.role,
            "ordinal": self.ordinal,
            "name": self.name,
            "tax_id": self.tax_id,
            "source_key": self.source_key,
            "country_code": self.country_code,
        }


@dataclass(frozen=True)
class ComparisonCohort:
    run_id: UUID
    projection_version: str
    coverage: Mapping[str, object]
    parties: tuple[PartyEvidence, ...]
    imports: tuple[ImportEvidence, ...]
    registry: tuple[RegistryEvidence, ...]
    search_imports: tuple[SearchImportEvidence, ...] = ()
    search_queries: tuple[SearchQueryEvidence, ...] = ()


def _configuration(run: UUID, imports: Sequence[UUID], version: str, max_mentions: int) -> None:
    if (
        not isinstance(run, UUID)
        or version != PROJECTION_VERSION
        or type(max_mentions) is not int
        or not 1 <= max_mentions <= MAX_COMPARISON_MENTIONS
        or not 1 <= len(imports) <= MAX_IMPORTS
        or any(not isinstance(selected, UUID) for selected in imports)
        or len(set(imports)) != len(imports)
    ):
        raise ValueError("comparison_configuration")


def read_comparison_cohort(
    dsn: str,
    run: UUID,
    gemi_imports: Sequence[UUID],
    version: str,
    *,
    max_mentions: int = MAX_COMPARISON_MENTIONS,
) -> ComparisonCohort:
    """Select profile imports and imported AFM searches by the same explicit UUIDs."""
    _configuration(run, gemi_imports, version, max_mentions)
    selected = tuple(sorted(gemi_imports, key=lambda item: item.int))
    check_schema(dsn)
    with _connect(dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        imports, searches = _kinds(connection, selected)
        reserved = _preflight(connection, run, imports, version) + _search_preflight(
            connection, searches
        )
        if reserved >= MAX_INPUT_BYTES:
            raise ComparisonError("comparison_limit")
        coverage, members = read_cohort_in_transaction(
            connection,
            run,
            version,
            max_mentions,
            max_input_bytes=MAX_INPUT_BYTES - reserved,
        )
        registry = _registry_evidence(connection, imports) + _search_hits(connection, searches)
        if len(registry) > MAX_REGISTRY_OBSERVATIONS:  # profile and search rows together
            raise ComparisonError("comparison_limit")
        result = ComparisonCohort(
            run,
            version,
            MappingProxyType(coverage),
            _parties(connection, run, version, members),
            _imports(connection, imports),
            tuple(sorted(registry, key=_registry_order)),
            _search_imports(connection, searches),
            _search_queries(connection, searches),
        )
    return result


def _registry_order(item: RegistryEvidence) -> tuple[int, str, str]:
    claim = item.claim
    return claim.import_id.int, claim.registry_number, claim.queried_afm or ""


def _kinds(
    connection: Connection, selected: tuple[UUID, ...]
) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
    """Split the selected ids into profile imports and search imports.

    An id that is a search import is read as one; every other id is left to the profile checks,
    which refuse an id that is not an import at all.
    """
    rows = connection.execute(
        "SELECT run_id FROM nima.gemi_search_imports WHERE run_id=ANY(%s)", (list(selected),)
    ).fetchall()
    searches = {cast(UUID, row[0]) for row in rows}
    return (
        tuple(item for item in selected if item not in searches),
        tuple(item for item in selected if item in searches),
    )


def _preflight(connection: Connection, run: UUID, imports: tuple[UUID, ...], version: str) -> int:
    """Check the selected profile imports; with none selected only the dates are measured."""
    expected = import_bytes = registry_bytes = 0
    if imports:
        count, supported, complete, expected, import_bytes = cast(
            tuple[int, bool, bool, int, int],
            connection.execute(
                sql.SQL(
                    "SELECT count(*), coalesce(bool_and(supported), false), "
                    "coalesce(bool_and(complete), false), coalesce(sum(observations), 0), "
                    "coalesce(sum(octet_length(payload::text)), 0) FROM ({}) selected"
                ).format(sql.SQL(_IMPORT_ROWS)),
                (*_IMPORT_PARAMETERS, list(imports)),
            ).fetchone(),
        )
        if count != len(imports):
            raise ComparisonError("registry_import_unavailable")
        if not supported:
            raise ComparisonError("registry_version")
        if not complete:
            raise ComparisonError("registry_incomplete")
        if expected > MAX_REGISTRY_OBSERVATIONS:
            raise ComparisonError("comparison_limit")
        observations, invalid, registry_bytes = cast(
            tuple[int, int, int],
            connection.execute(
                sql.SQL(
                    "SELECT count(*), count(*) FILTER (WHERE valid IS NOT TRUE), "
                    "coalesce(sum(octet_length(payload::text)), 0) FROM ({}) selected"
                ).format(sql.SQL(_REGISTRY_ROWS)),
                (GEMI_VERSION, list(imports)),
            ).fetchone(),
        )
        if observations != expected or invalid:
            raise ComparisonError("registry_incomplete")
    date_bytes = cast(
        tuple[int],
        connection.execute(
            sql.SQL(
                "SELECT coalesce(sum(octet_length(payload::text)), 0) FROM ({}) selected"
            ).format(sql.SQL(_DATE_ROWS)),
            (version, run),
        ).fetchone(),
    )[0]
    return import_bytes + registry_bytes + date_bytes + _COVERAGE_RESERVE


def _search_preflight(connection: Connection, searches: tuple[UUID, ...]) -> int:
    """Check the selected search imports the same way; returns the bytes they will add."""
    if not searches:
        return 0
    supported, complete, hits, size = cast(
        tuple[bool, bool, int, int],
        connection.execute(
            sql.SQL(
                "SELECT coalesce(bool_and(supported), false), "
                "coalesce(bool_and(complete), false), coalesce(sum(observations), 0), "
                "coalesce(sum(octet_length(payload::text)), 0) FROM ({}) selected"
            ).format(sql.SQL(_SEARCH_IMPORT_ROWS)),
            (*_SEARCH_PARAMETERS, list(searches)),
        ).fetchone(),
    )
    if not supported:
        raise ComparisonError("registry_version")
    if not complete:
        raise ComparisonError("registry_incomplete")
    if hits > MAX_REGISTRY_OBSERVATIONS:
        raise ComparisonError("comparison_limit")
    invalid, hit_bytes = cast(
        tuple[int, int],
        connection.execute(
            sql.SQL(
                "SELECT count(*) FILTER (WHERE valid IS NOT TRUE), "
                "coalesce(sum(octet_length(payload::text)), 0) FROM ({}) selected"
            ).format(sql.SQL(_SEARCH_HIT_ROWS)),
            (GEMI_VERSION, list(searches)),
        ).fetchone(),
    )
    bad_queries, query_bytes = cast(
        tuple[int, int],
        connection.execute(
            sql.SQL(
                "SELECT count(*) FILTER (WHERE valid IS NOT TRUE), "
                "coalesce(sum(octet_length(payload::text)), 0) FROM ({}) selected"
            ).format(sql.SQL(_SEARCH_QUERY_ROWS)),
            (list(searches),),
        ).fetchone(),
    )
    if invalid or bad_queries:
        raise ComparisonError("registry_incomplete")
    return size + hit_bytes + query_bytes


def _imports(connection: Connection, imports: tuple[UUID, ...]) -> tuple[ImportEvidence, ...]:
    if not imports:
        return ()
    rows = connection.execute(
        sql.SQL("SELECT payload FROM ({}) selected").format(sql.SQL(_IMPORT_ROWS)),
        (*_IMPORT_PARAMETERS, list(imports)),
    ).fetchall()
    result = []
    for row in rows:
        data = _object(row[0])
        result.append(
            ImportEvidence(
                _uuid(data["import_id"]),
                _required(data["import_version"]),
                _required(data["normalizer_version"]),
                _required(data["manifest_sha256"]),
                _required(data["source_url"]),
                _required(data["license"]),
                _required(data["publisher"]),
                _when(data["imported_at"]),
                _integer(data["profile_count"]),
                _integer(data["not_found_count"]),
                _integer(data["response_count"]),
            )
        )
    return tuple(sorted(result, key=lambda item: item.import_id.int))


def _registry_evidence(
    connection: Connection, imports: tuple[UUID, ...]
) -> tuple[RegistryEvidence, ...]:
    if not imports:
        return ()
    rows = connection.execute(
        sql.SQL("SELECT payload FROM ({}) selected").format(sql.SQL(_REGISTRY_ROWS)),
        (GEMI_VERSION, list(imports)),
    ).fetchall()
    result = []
    for row in rows:
        data = _object(row[0])
        import_id, number = _uuid(data["import_id"]), _required(data["registry_number"])
        fields: Mapping[str, Assertion]
        if data["outcome"] == "found":
            fields = _fields(data["fields"], number)
            claim = RegistryObservation(
                import_id,
                number,
                "found",
                _text(fields["reported_afm"].value),
                is_branch=_branch(fields),
            )
        elif data["outcome"] == "not_found_at_observation" and data["fields"] is None:
            fields = MappingProxyType({})
            claim = RegistryObservation(import_id, number, "not_found_at_observation", None)
        else:
            raise ComparisonError("registry_shape")
        result.append(
            RegistryEvidence(
                claim,
                _integer(data["attempt"]),
                _integer(data["status"]),
                _required(data["raw_sha256"]),
                _when(data["observed_at"]),
                _text(data["source_id"]),
                _text(data["normalizer_version"]),
                fields,
            )
        )
    return tuple(result)


def _search_imports(
    connection: Connection, searches: tuple[UUID, ...]
) -> tuple[SearchImportEvidence, ...]:
    if not searches:
        return ()
    rows = connection.execute(
        sql.SQL("SELECT payload FROM ({}) selected").format(sql.SQL(_SEARCH_IMPORT_ROWS)),
        (*_SEARCH_PARAMETERS, list(searches)),
    ).fetchall()
    result = []
    for row in rows:
        data = _object(row[0])
        result.append(
            SearchImportEvidence(
                _uuid(data["import_id"]),
                _required(data["import_version"]),
                _required(data["connector_version"]),
                _required(data["normalizer_version"]),
                _required(data["manifest_sha256"]),
                _required(data["source_url"]),
                _required(data["license"]),
                _required(data["publisher"]),
                _when(data["imported_at"]),
                _integer(data["afm_count"]),
                _integer(data["request_count"]),
                _integer(data["hit_count"]),
                _integer(data["unconfirmed_quarantine_count"]),
            )
        )
    return tuple(sorted(result, key=lambda item: item.import_id.int))


_SEARCH_OUTCOME_NAMES = frozenset(
    {
        "hit_single",
        "hit_multiple",
        "truncated",
        "afm_mismatch",
        "not_found_at_observation",
        "quarantined",
    }
)


def _branch(fields: Mapping[str, Assertion]) -> bool | None:
    """The registry's own is_branch flag; None means the profile did not say. The field reader has
    already refused anything that is neither a boolean nor null."""
    return cast(bool | None, fields["is_branch"].value)


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise ComparisonError("registry_shape")
    return value


def _search_queries(
    connection: Connection, searches: tuple[UUID, ...]
) -> tuple[SearchQueryEvidence, ...]:
    if not searches:
        return ()
    rows = connection.execute(
        sql.SQL("SELECT payload FROM ({}) selected").format(sql.SQL(_SEARCH_QUERY_ROWS)),
        (list(searches),),
    ).fetchall()
    result = []
    for row in rows:
        data = _object(row[0])
        outcome = _required(data["outcome"])
        if outcome not in _SEARCH_OUTCOME_NAMES:
            raise ComparisonError("registry_shape")
        result.append(
            SearchQueryEvidence(
                _uuid(data["import_id"]),
                _required(data["afm"]),
                cast(SearchOutcome, outcome),
                _flag(data["truncated"]),
                _flag(data["unconfirmed_quarantine"]),
                _integer(data["hit_count"]),
                _integer(data["attempt"]),
                _integer(data["status"]),
                _required(data["raw_sha256"]),
                _when(data["observed_at"]),
            )
        )
    return tuple(sorted(result, key=lambda item: (item.import_id.int, item.afm)))


def _search_hits(
    connection: Connection, searches: tuple[UUID, ...]
) -> tuple[RegistryEvidence, ...]:
    if not searches:
        return ()
    rows = connection.execute(
        sql.SQL("SELECT payload FROM ({}) selected").format(sql.SQL(_SEARCH_HIT_ROWS)),
        (GEMI_VERSION, list(searches)),
    ).fetchall()
    result = []
    for row in rows:
        data = _object(row[0])
        import_id, number = _uuid(data["import_id"]), _required(data["registry_number"])
        index = _integer(data["hit_index"])
        fields = _fields(data["fields"], number, f"/searchResults/{index}")
        claim = RegistryObservation(
            import_id,
            number,
            "found",
            _text(fields["reported_afm"].value),
            _required(data["queried_afm"]),
            _flag(data["afm_matches"]),
            _branch(fields),
        )
        result.append(
            RegistryEvidence(
                claim,
                _integer(data["attempt"]),
                _integer(data["status"]),
                _required(data["raw_sha256"]),
                _when(data["observed_at"]),
                _text(data["source_id"]),
                _text(data["normalizer_version"]),
                fields,
            )
        )
    return tuple(result)


def _parties(
    connection: Connection, run: UUID, version: str, members: list[Occurrence]
) -> tuple[PartyEvidence, ...]:
    rows = connection.execute(_DATE_ROWS, (version, run)).fetchall()
    dates = {}
    for row in rows:
        data = _object(row[0])
        key = (
            _required(data["source_id"]),
            _required(data["normalizer_version"]),
            _required(data["content_sha256"]),
        )
        dates[key] = (_text(data["source_submitted_at"]), _text(data["source_updated_at"]))
    result = []
    for member in members:
        key = member["source_id"], member["normalizer_version"], member["content_sha256"]
        if key not in dates:
            raise ComparisonError("registry_incomplete")
        submitted, updated = dates[key]
        evidence = member["evidence"]
        result.append(
            PartyEvidence(
                member["source_id"],
                member["normalizer_version"],
                member["content_sha256"],
                member["observation_id"],
                member["role"],
                member["ordinal"],
                member["name"],
                member["tax_id"],
                member["source_key"],
                member["country_code"],
                evidence["raw_sha256"],
                evidence["json_pointer"],
                _when(evidence["observed_at"]),
                submitted,
                updated,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.source_id,
                item.normalizer_version,
                item.content_sha256,
                item.observation_id,
                item.role,
                item.ordinal,
            ),
        )
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ComparisonError("registry_shape")
    return cast(dict[str, object], value)


def _text(value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ComparisonError("registry_shape")
    return value


def _required(value: object) -> str:
    text = _text(value)
    if text is None:
        raise ComparisonError("registry_shape")
    return text


def _uuid(value: object) -> UUID:
    try:
        return UUID(_required(value))
    except ValueError:
        raise ComparisonError("registry_shape") from None


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ComparisonError("registry_shape")
    return value


def _when(value: object) -> str:
    text = _text(value)
    try:
        if text is None or datetime.fromisoformat(text).utcoffset() is None:
            raise ValueError
    except ValueError:
        raise ComparisonError("registry_shape") from None
    return text


def _scalar(value: object, kind: str) -> str | int | bool | None:
    if value is None:
        return None
    if kind == "integer" and type(value) is int:
        return value
    if kind == "boolean" and type(value) is bool:
        return value
    if kind in {"text", "date"} and isinstance(value, str):
        if kind == "date":
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                raise ComparisonError("registry_shape") from None
        return value
    raise ComparisonError("registry_shape")


def _fields(value: object, number: str, prefix: str = "") -> Mapping[str, Assertion]:
    raw = _object(value)
    result = {}
    for name, pointer, kind in _FIELD_SPECS:
        item = _object(raw.get(name))
        if set(item) != {"value", "json_pointer"}:
            raise ComparisonError("registry_shape")
        parsed = _scalar(item["value"], kind)
        location = item["json_pointer"]
        if location is None:
            if parsed is not None:
                raise ComparisonError("registry_shape")
        elif location != prefix + pointer:
            raise ComparisonError("registry_shape")
        result[name] = Assertion(parsed, None if location is None else prefix + pointer)
    if str(result["registry_number"].value) != number:
        raise ComparisonError("registry_shape")
    return MappingProxyType(result)
