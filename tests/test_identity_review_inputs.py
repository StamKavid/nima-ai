"""Private review requests are untrusted, bounded inputs, never accepted identities."""

import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from nima.identity import review_inputs
from nima.identity.artifacts import encode
from nima.identity.review_types import ReviewError
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import NORMALIZER_VERSION


def request(operation: str = "accept") -> dict[str, object]:
    value: dict[str, object] = {
        "request_format": "nima-identity-review-request-v1",
        "operation": operation,
        "subject": {
            "run_id": str(UUID(int=1)),
            "observation_id": 1,
            "projection_version": PROJECTION_VERSION,
            "source_id": "kimdis:1",
            "normalizer_version": NORMALIZER_VERSION,
            "content_sha256": "a" * 64,
            "role": "supplier",
            "ordinal": 0,
        },
        "candidate": {"import_id": str(UUID(int=2)), "registry_number": "1"},
        "expected_revision": 0,
        "rationale": "  Ελληνικό τεκμήριο\n",
    }
    if operation in ("accept", "reject"):
        value["report_sha256"] = "b" * 64
    if operation == "accept":
        value.update(entity_id=str(UUID(int=3)), acknowledged_issues=[])
    if operation == "revoke":
        value["reverses_event_id"] = str(UUID(int=4))
    return value


def private_file(tmp_path: Path, name: str, body: bytes) -> Path:
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700, exist_ok=True)
    path = folder / name
    path.write_bytes(body)
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("operation", ["accept", "reject", "revoke"])
def test_private_request_types_identity_and_original_unicode(
    tmp_path: Path, operation: str
) -> None:
    raw = json.dumps(request(operation), ensure_ascii=False).encode()
    path = private_file(tmp_path, "request.json", raw)
    parsed = review_inputs.read_request(UUID(int=9), path)
    assert parsed.request_id == UUID(int=9) and parsed.operation == operation
    assert parsed.subject.run_id == UUID(int=1) and parsed.candidate.import_id == UUID(int=2)
    assert parsed.rationale == "  Ελληνικό τεκμήριο\n"
    assert parsed.payload() == request(operation)
    assert parsed.digest == hashlib.sha256(encode(parsed.payload())).hexdigest()
    another = private_file(
        tmp_path, "other.json", json.dumps(request(operation), indent=2).encode()
    )
    assert review_inputs.read_request(UUID(int=9), another) == parsed
    for attribute in ("expected_revision", "rationale"):
        with pytest.raises(AttributeError):
            setattr(parsed, attribute, 2)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "body",
    [
        b'{"operation":"accept","operation":"reject"}',
        b'{"private-sentinel":NaN}',
        b"[]",
        b"null",
        b"\xff",
        b"{",
    ],
)
def test_malformed_json_has_only_fixed_diagnostic(body: bytes) -> None:
    with pytest.raises(ReviewError, match="^review_input$") as error:
        review_inputs.decode_request(UUID(int=9), body)
    assert "private-sentinel" not in str(error.value)


def report_body() -> bytes:
    from dataclasses import replace
    from types import MappingProxyType

    from nima.identity.registry_report import build_report
    from nima.ingestion.config import CONNECTOR_VERSION
    from tests.test_registry_report import cohort

    data = cohort()
    coverage = {
        "stored_run_status": "unmanaged",
        "checkpoint_next_page": 1,
        "reported_total_records": 2,
        "reported_total_pages": 1,
        "normalizer_version": NORMALIZER_VERSION,
        "connector_version": CONNECTOR_VERSION,
        "page_count": 1,
        "quarantine_count": 0,
        "observation_count": 2,
        "expected_mentions": 2,
        "unknown_supplier_lists": 0,
        "empty_supplier_lists": 0,
        "collection_completeness": "not_certified",
    }
    data = replace(
        data,
        coverage=MappingProxyType(coverage),
        parties=tuple(
            replace(party, normalizer_version=NORMALIZER_VERSION) for party in data.parties
        ),
    )
    return encode(build_report(data))


def test_comparison_report_is_immutable_unverified_input_not_a_trusted_match(
    tmp_path: Path,
) -> None:
    body = report_body()
    path = private_file(tmp_path, "comparison.json", body)
    parsed = review_inputs.read_report(path, expected_sha256=hashlib.sha256(body).hexdigest())
    assert parsed.sha256 == hashlib.sha256(body).hexdigest()
    assert len(parsed.cohort.parties) == 2 and len(parsed.cohort.registry) == 3
    assert parsed.cohort.parties[0].name == " Άλφα ΑΕ "
    assert parsed.cohort.registry[0].fields["reported_afm"].value == "001234567"
    assert parsed.cohort.coverage["stored_run_status"] == "unmanaged"
    with pytest.raises(TypeError):
        cast(dict[str, object], parsed.cohort.coverage)["stored_run_status"] = "complete"
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_inputs.read_report(path, expected_sha256="0" * 64)
    assert path.read_bytes() == body


@pytest.mark.parametrize(
    "part",
    ["automatic", "policy", "unknown", "assessment", "outcome", "duplicate", "missing", "pointer"],
)
def test_report_mutations_cannot_change_derived_policy_or_structure(part: str) -> None:
    value = json.loads(report_body())
    if part == "automatic":
        value["automatic_identity_links"] = 1
    elif part == "policy":
        value["policy_version"] = "private-sentinel"
    elif part == "unknown":
        value["private-sentinel"] = "source text"
    elif part == "assessment":
        value["occurrences"][0]["assessment"]["identity_status"] = "accepted"
    elif part == "outcome":
        value["occurrences"][0]["comparison"]["outcome"] = "no_candidate_in_selected_imports"
    elif part == "duplicate":
        value["occurrences"].append(value["occurrences"][0])
    elif part == "missing":
        value["registry_observations"].pop()
    else:
        value["registry_observations"][0]["fields"]["reported_afm"]["json_pointer"] = (
            "/private-sentinel"
        )
    with pytest.raises(ReviewError) as error:
        review_inputs.decode_report(encode(value))
    assert "private-sentinel" not in str(error.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("request_format", "private-sentinel"),
        ("operation", "unknown"),
        ("reviewer", "private-sentinel"),
        ("expected_revision", True),
        ("expected_revision", -1),
        ("expected_revision", 2**63),
        ("report_sha256", "x" * 64),
        ("entity_id", "private-sentinel"),
        ("rationale", " \t\r\n"),
        ("rationale", "\ud800"),
        ("rationale", "\x00"),
        ("subject.observation_id", 0),
        ("subject.observation_id", False),
        ("subject.run_id", 3),
        ("subject.projection_version", "private-sentinel"),
        ("subject.source_id", "gemi:1"),
        ("subject.source_id", "kimdis:"),
        ("subject.normalizer_version", "unsupported"),
        ("subject.content_sha256", None),
        ("subject.role", "owner"),
        ("subject.ordinal", 1000),
        ("candidate.registry_number", "0001"),
        ("candidate.registry_number", "not-a-number"),
        ("candidate.extra", 1),
        ("acknowledged_issues", ["private-sentinel"]),
        ("acknowledged_issues", [3]),
        ("acknowledged_issues", {}),
        ("acknowledged_issues", ["reported_afm_changed_for_registry_number"] * 2),
    ],
)
def test_request_fields_cannot_supply_an_actor_or_bypass_types(key: str, value: object) -> None:
    data = request()
    parts = key.split(".")
    target = data if len(parts) == 1 else cast(dict[str, object], data[parts[0]])
    target[parts[-1]] = value
    with pytest.raises(ReviewError, match="^review_input$"):
        review_inputs.decode_request(UUID(int=9), json.dumps(data).encode())


def test_operation_specific_fields_and_conflict_ordering() -> None:
    for operation, forbidden in [("reject", "entity_id"), ("revoke", "report_sha256")]:
        data = request(operation)
        data[forbidden] = str(UUID(int=2))
        with pytest.raises(ReviewError, match="^review_input$"):
            review_inputs.decode_request(UUID(int=9), json.dumps(data).encode())
    data = request()
    data["acknowledged_issues"] = [
        "reported_afm_changed_for_registry_number",
        "multiple_registry_numbers_for_reported_afm",
    ]
    one = review_inputs.decode_request(UUID(int=9), json.dumps(data).encode())
    data["acknowledged_issues"] = list(reversed(cast(list[str], data["acknowledged_issues"])))
    assert one == review_inputs.decode_request(UUID(int=9), json.dumps(data).encode())
    subject = cast(dict[str, object], data["subject"])
    subject["role"], subject["ordinal"] = "buyer", 1
    with pytest.raises(ReviewError):
        review_inputs.decode_request(UUID(int=9), json.dumps(data).encode())
    with pytest.raises(ReviewError):
        review_inputs.decode_request(cast(UUID, "private-sentinel"), b"{}")


def test_exact_request_and_unicode_rationale_byte_bounds() -> None:
    from nima.identity.review_types import MAX_RATIONALE_BYTES, MAX_REQUEST_BYTES

    data = request()
    data["rationale"] = "α" * (MAX_RATIONALE_BYTES // 2)
    raw = json.dumps(data, ensure_ascii=False).encode()
    padded = raw + b" " * (MAX_REQUEST_BYTES - len(raw))
    assert review_inputs.decode_request(UUID(int=9), padded).rationale == data["rationale"]
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_inputs.decode_request(UUID(int=9), padded + b" ")
    data["rationale"] = str(data["rationale"]) + "α"
    with pytest.raises(ReviewError, match="^review_input$"):
        review_inputs.decode_request(UUID(int=9), json.dumps(data, ensure_ascii=False).encode())
    for raw in (b"[" * 1500 + b"0" + b"]" * 1500, b'{"x":' + b"9" * 5000 + b"}"):
        with pytest.raises(ReviewError, match="^review_input$"):
            review_inputs.decode_request(UUID(int=9), raw)


@pytest.mark.parametrize(
    "hazard",
    [
        "parent_symlink",
        "file_symlink",
        "public_folder",
        "public_file",
        "missing",
        "traversal",
        "git",
        "nul",
        "oversize",
    ],
)
def test_private_reader_rejects_unsafe_inputs_without_writes(tmp_path: Path, hazard: str) -> None:
    path = private_file(tmp_path, "request.json", json.dumps(request()).encode())
    original = path.read_bytes()
    selected = path
    if hazard == "parent_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(path.parent, target_is_directory=True)
        selected = alias / path.name
    elif hazard == "file_symlink":
        selected = path.parent / "alias.json"
        selected.symlink_to(path)
    elif hazard == "public_folder":
        path.parent.chmod(0o755)
    elif hazard == "public_file":
        path.chmod(0o644)
    elif hazard == "missing":
        selected = path.parent / "private-sentinel.json"
    elif hazard == "traversal":
        selected = path.parent / ".." / "private" / path.name
    elif hazard == "git":
        selected = tmp_path / ".git" / path.name
    elif hazard == "nul":
        selected = path.parent / "private-sentinel\x00"
    else:
        selected = private_file(tmp_path, "oversize.json", b" " * (16 * 1024 + 1))
    with pytest.raises(ReviewError) as error:
        review_inputs.read_request(UUID(int=9), selected)
    assert "private-sentinel" not in str(error.value)
    assert path.read_bytes() == original
    assert not list(tmp_path.rglob(".tmp-*"))


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("root", "projection_version", "private-sentinel"),
        ("root", "run_id", None),
        ("root", "registry_imports", {}),
        ("root", "registry_imports", []),
        ("imports", "import_version", "unsupported"),
        ("imports", "profile_count", True),
        ("imports", "profile_count", 0),
        ("imports", "response_count", 0),
        ("imports", "imported_at", "not-a-date"),
        ("imports", "manifest_sha256", "x"),
        ("registry", "status", 201),
        ("registry", "outcome", "private-sentinel"),
        ("registry", "source_id", "gemi:99"),
        ("registry", "normalizer_version", "unsupported"),
        ("registry", "attempt", False),
        ("registry", "registry_number", "0001"),
        ("parties", "tax_id", True),
        ("parties", "json_pointer", "/private-sentinel"),
        ("parties", "observed_at", "2026-11-01"),
        ("coverage", "expected_mentions", False),
        ("coverage", "collection_completeness", "certified"),
        ("coverage", "connector_version", "bad"),
    ],
)
def test_report_versions_types_counts_and_provenance(section: str, key: str, value: object) -> None:
    data = json.loads(report_body())
    target = {
        "root": data,
        "imports": data["registry_imports"][0],
        "registry": data["registry_observations"][0],
        "parties": data["occurrences"][0],
        "coverage": data["coverage"],
    }[section]
    target[key] = value
    with pytest.raises(ReviewError) as error:
        review_inputs.decode_report(encode(data))
    assert "private-sentinel" not in str(error.value)


def test_report_empty_all_404_and_internally_consistent_forgery_remain_unverified() -> None:
    from dataclasses import replace
    from types import MappingProxyType

    from nima.identity.registry_policy import RegistryObservation
    from nima.identity.registry_report import build_report

    data = review_inputs.decode_report(report_body()).cohort
    forged = replace(
        data, parties=tuple(replace(row, name="Unverified claim") for row in data.parties)
    )
    assert (
        review_inputs.decode_report(encode(build_report(forged))).cohort.parties[0].name
        == "Unverified claim"
    )
    missing = tuple(
        replace(
            row,
            claim=RegistryObservation(row.claim.import_id, "1", "not_found_at_observation", None),
            status=404,
            fields=MappingProxyType({}),
            source_id=None,
            normalizer_version=None,
        )
        for row in data.registry
    )
    data = replace(
        data,
        parties=(),
        registry=missing,
        imports=tuple(replace(row, profile_count=0, not_found_count=1) for row in data.imports),
    )
    parsed = review_inputs.decode_report(encode(build_report(data)))
    assert parsed.cohort.parties == () and len(parsed.cohort.registry) == 3
    assert all(row.claim.outcome == "not_found_at_observation" for row in parsed.cohort.registry)


def test_report_order_uniqueness_and_exact_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    body = report_body()
    with pytest.raises(ReviewError):
        review_inputs.decode_report(json.dumps(json.loads(body), indent=2).encode())
    for section in ("registry_imports", "registry_observations"):
        data = json.loads(body)
        data[section].append(data[section][0])
        with pytest.raises(ReviewError):
            review_inputs.decode_report(encode(data))
    for constant, maximum in [
        ("MAX_COMPARISON_MENTIONS", 1),
        ("MAX_REGISTRY_OBSERVATIONS", 2),
        ("MAX_REPORT_BYTES", len(body) - 1),
    ]:
        with monkeypatch.context() as scoped:
            scoped.setattr(review_inputs, constant, maximum)
            with pytest.raises(ReviewError, match="^review_limit$"):
                review_inputs.decode_report(body)
    monkeypatch.setattr(review_inputs, "MAX_REPORT_BYTES", len(body))
    assert review_inputs.decode_report(body).sha256 == hashlib.sha256(body).hexdigest()
    with pytest.raises(ReviewError):
        review_inputs.decode_report(b"{}")


def test_codec_accepts_real_stored_comparison_without_opening_sql_or_http(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.identity.registry_report import compare_run
    from tests.test_identity_report import seed
    from tests.test_kimdis_pages import record
    from tests.test_registry_cohort import registry_import

    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    output = tmp_path / "reports"
    compare_run(pg_dsn, run, (selected,), PROJECTION_VERSION, output)
    monkeypatch.setattr(
        "nima.identity.registry_cohort._connect", lambda *a: pytest.fail("codec opened SQL")
    )
    monkeypatch.setattr("httpx.Client", lambda **kw: pytest.fail("codec opened HTTP"))
    parsed = review_inputs.read_report(next(output.glob("*.json")))
    assert parsed.cohort.run_id == run and len(parsed.cohort.parties) == 1
    assert len(parsed.cohort.registry) == 2
