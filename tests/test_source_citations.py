"""Hand-computed citation outcomes; synthetic records, never publisher claims."""

import ast
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from importlib.resources import files
from typing import Any, cast

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.semantics import citations
from nima.semantics.citations import (
    CitationError,
    ContractObservation,
    DecisionObservation,
    definition,
    definition_sha256,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.lifecycle import Reference

CUTOFF = datetime(2026, 1, 10, tzinfo=UTC)


def payload(
    rows: tuple[ContractObservation, ...],
    targets: tuple[DecisionObservation, ...],
    cutoff: datetime = CUTOFF,
) -> dict[str, Any]:
    return cast(dict[str, Any], evaluate(rows, targets, cutoff=cutoff).payload())


def parity(
    dsn: str,
    rows: tuple[ContractObservation, ...],
    targets: tuple[DecisionObservation, ...],
    cutoff: datetime = CUTOFF,
) -> dict[str, Any]:
    result = payload(rows, targets, cutoff)
    with psycopg.connect(dsn) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        sql = connection.execute(
            reference_sql(), (Jsonb(sql_rows(rows, targets)), cutoff)
        ).fetchone()
    assert sql is not None
    assert sql[0] == result
    return result


def contract(
    number: int, name: str = "C", targets: tuple[str, ...] | None = ("A",), day: int = 1
) -> ContractObservation:
    refs = (
        None
        if targets is None
        else tuple(
            Reference("commitment_decision", f"diavgeia:{t}", "diavgeiaADA") for t in targets
        )
    )
    return ContractObservation(
        number,
        f"kimdis:{name}",
        "kimdis-normalized-v1",
        hashlib.sha256(name.encode()).hexdigest(),
        datetime(2026, 1, day, tzinfo=UTC),
        refs,
        False,
    )


def decision(
    number: int = 100, ada: str = "A", kind: str | None = "Β.1.3", day: int = 1
) -> DecisionObservation:
    return DecisionObservation(
        number,
        f"diavgeia:{ada}",
        "diavgeia-commitment-v1",
        hashlib.sha256(ada.encode()).hexdigest(),
        datetime(2026, 1, day, tzinfo=UTC),
        ada,
        kind,
        "PUBLISHED",
    )


def test_known_outcomes_and_denominators(pg_dsn: str) -> None:
    rows = tuple(contract(n, str(n), (ada,)) for n, ada in enumerate("ABCDE", 1))
    targets = (
        decision(),
        decision(101, "B", "Δ.2.2"),
        decision(102, "C", None),
        decision(103, "D"),
        replace(decision(104, "D"), content_sha256="f" * 64),
    )
    result = parity(pg_dsn, rows, targets)
    assert [e["outcome"] for e in result["edges"]] == [
        "resolved",
        "target_type_mismatch",
        "target_type_unknown",
        "target_ambiguous",
        "unresolved",
    ]
    assert result["records"] == 5
    assert result["distinct_targets"] == 5
    assert result["outcome_counts"] == {
        "resolved": 1,
        "unresolved": 1,
        "target_ambiguous": 1,
        "target_type_unknown": 1,
        "target_type_mismatch": 1,
    }


def test_latest_target_is_classified_after_selection(pg_dsn: str) -> None:
    old = decision()
    new = replace(decision(101, kind="Δ.2.2", day=2), content_sha256="f" * 64)
    edge = parity(pg_dsn, (contract(1),), (old, new))["edges"][0]
    assert edge["outcome"] == "target_type_mismatch"
    assert edge["target_versions"][0]["decision_type"] == "Δ.2.2"


def test_unknown_empty_and_ambiguous_sources_are_separate(pg_dsn: str) -> None:
    rows = (contract(1, "unknown", None), contract(2, "empty", ()), contract(3, "conflict"))
    conflict = replace(rows[2], observation_id=4, content_sha256="e" * 64)
    result = parity(pg_dsn, (*rows, conflict), (decision(),))
    assert result["edges"] == []
    assert result["source_ambiguous_ids"] == ["kimdis:conflict"]
    assert result["unknown_reference_ids"] == ["kimdis:unknown"]
    assert result["no_citation_ids"] == ["kimdis:empty"]


def test_reobservation_and_a_b_a_keep_lineage_without_multiplying_edges(pg_dsn: str) -> None:
    a = contract(1)
    b = replace(contract(2, targets=("B",), day=2), content_sha256="b" * 64)
    again = replace(a, observation_id=3, observed_at=datetime(2026, 1, 3, tzinfo=UTC))
    target = decision()
    seen_again = replace(target, observation_id=101, observed_at=again.observed_at)
    rows, targets = (a, b, again), (target, seen_again)
    result = parity(pg_dsn, rows, targets)
    assert len(result["edges"]) == 1
    edge = result["edges"][0]
    assert edge["target_id"] == "diavgeia:A"
    assert edge["source_version"]["observations"] == [
        [1, a.observed_at.isoformat()],
        [3, again.observed_at.isoformat()],
    ]
    assert [o[0] for o in edge["target_versions"][0]["observations"]] == [100, 101]
    assert parity(pg_dsn, tuple(reversed(rows)), tuple(reversed(targets))) == result


def test_cutoff_is_inclusive_and_applies_before_selection(pg_dsn: str) -> None:
    row = contract(1, day=2)
    target = decision(day=2)
    late = replace(decision(101, day=3), content_sha256="c" * 64, decision_type=None)
    assert (
        parity(pg_dsn, (row,), (target, late), target.observed_at)["edges"][0]["outcome"]
        == "resolved"
    )
    early = target.observed_at - timedelta(microseconds=1)
    assert (
        parity(pg_dsn, (row,), (target, late), early)["status"] == "no_observations_before_cutoff"
    )
    assert parity(pg_dsn, (contract(1),), (target,), early)["edges"][0]["outcome"] == "unresolved"


@pytest.mark.parametrize("state", ["PUBLISHED", "REVOKED", "PENDING_REVOCATION"])
@pytest.mark.parametrize("cancelled", [True, False, None])
def test_status_and_cancellation_are_disclosed_not_filtered(
    pg_dsn: str, state: str, cancelled: bool | None
) -> None:
    result = parity(
        pg_dsn,
        (replace(contract(1), cancelled=cancelled),),
        (replace(decision(), decision_status=state),),
    )
    edge = result["edges"][0]
    assert edge["outcome"] == "resolved"
    assert edge["source_version"]["cancelled"] is cancelled
    assert edge["target_versions"][0]["decision_status"] == state


def test_duplicates_sharing_and_non_diavgeia_relations(pg_dsn: str) -> None:
    a = contract(1, "α", ("A", "A"))
    a = replace(
        a,
        references=(
            *cast(tuple[Reference, ...], a.references),
            Reference("award", "kimdis:A", "auctionRefNo"),
        ),
    )
    b = contract(2, "Z")
    other = replace(
        contract(3, "other", ()),
        references=(Reference("payment_order", "kimdis:P", "paymentRefNo"),),
    )
    result = parity(pg_dsn, (a, b, other), (decision(),))
    assert [(e["source_id"], e["target_id"]) for e in result["edges"]] == [
        ("kimdis:Z", "diavgeia:A"),
        ("kimdis:α", "diavgeia:A"),
    ]
    assert result["shared_targets"] == [
        {"target_id": "diavgeia:A", "citing_records": 2, "source_ids": ["kimdis:Z", "kimdis:α"]}
    ]
    assert result["distinct_targets"] == 1
    assert result["no_citation_ids"] == ["kimdis:other"]


@pytest.mark.parametrize("different", ["a", "Α", "A ", " A", "é", "e\u0301"])
def test_reference_matching_never_normalizes_text(pg_dsn: str, different: str) -> None:
    result = parity(pg_dsn, (contract(1, targets=(different,)),), (decision(),))
    assert result["edges"][0]["outcome"] == "unresolved"
    assert result["edges"][0]["target_id"] == "diavgeia:" + different


def test_latest_source_unknown_does_not_fall_back_to_old_citation(pg_dsn: str) -> None:
    old = contract(1)
    new = replace(contract(2, targets=None, day=2), content_sha256="b" * 64)
    assert parity(pg_dsn, (old, new), (decision(),))["unknown_reference_ids"] == ["kimdis:C"]
    assert payload((old, new), (decision(),))["edges"] == []


def test_empty_and_no_citation_captures(pg_dsn: str) -> None:
    assert parity(pg_dsn, (), ())["status"] == "empty_capture"
    assert parity(pg_dsn, (), (decision(),))["status"] == "empty_capture"
    assert parity(pg_dsn, (contract(1, targets=()),), ())["status"] == "no_observed_citations"


def test_microsecond_lineage_and_target_hash_order(pg_dsn: str) -> None:
    a = replace(decision(), observed_at=CUTOFF.replace(microsecond=1200))
    b = replace(a, observation_id=101, content_sha256="0" * 64)
    result = parity(pg_dsn, (contract(1),), (a, b), a.observed_at)
    versions = result["edges"][0]["target_versions"]
    assert [v["content_sha256"] for v in versions] == sorted([a.content_sha256, b.content_sha256])
    assert versions[0]["observations"][0][1].endswith(".001200+00:00")


@pytest.mark.parametrize(
    "change",
    [
        {"observation_id": True},
        {"observation_id": 0},
        {"observation_id": "1"},
        {"source_id": None},
        {"source_id": "diavgeia:A"},
        {"source_id": "kimdis: "},
        {"source_id": "kimdis:\ud800"},
        {"content_sha256": None},
        {"content_sha256": "A" * 64},
        {"observed_at": None},
        {"observed_at": datetime(2026, 1, 1)},
        {"observed_at": datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))},
    ],
)
def test_bad_common_input_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(CitationError, match="^citation_input$"):
        evaluate((replace(contract(1), **change),), (), cutoff=CUTOFF)


@pytest.mark.parametrize(
    "change",
    [
        {"normalizer_version": "kimdis-normalized-v2"},
        {"cancelled": 1},
        {"references": []},
        {"references": ("A",)},
        {"references": (Reference(cast(str, []), "diavgeia:A", "diavgeiaADA"),)},
        {"references": (Reference("unsupported", "kimdis:A", cast(str, None)),)},
        {"references": (Reference("payment_order", "diavgeia:A", "paymentRefNo"),)},
        {"references": (Reference("commitment_decision", "diavgeia:A", "ada"),)},
        {"references": (Reference("commitment_decision", "diavgeia:", "diavgeiaADA"),)},
        {"references": (Reference("commitment_decision", cast(str, None), "diavgeiaADA"),)},
    ],
)
def test_bad_contract_facts_are_refused(change: dict[str, Any]) -> None:
    with pytest.raises(CitationError, match="^citation_contract$"):
        evaluate((replace(contract(1), **change),), (), cutoff=CUTOFF)


@pytest.mark.parametrize(
    "change",
    [
        {"normalizer_version": []},
        {"normalizer_version": "diavgeia-v99"},
        {"ada": None},
        {"ada": "other"},
        {"decision_type": []},
        {"decision_type": " "},
        {"decision_status": []},
        {"decision_status": "unknown"},
    ],
)
def test_bad_target_facts_are_not_hidden_by_absent_citations(change: dict[str, Any]) -> None:
    with pytest.raises(CitationError, match="^citation_contract$"):
        evaluate((), (replace(decision(), **change),), cutoff=CUTOFF)


@pytest.mark.parametrize("cutoff", [None, "2026-01-01", datetime(2026, 1, 1)])
def test_invalid_selection_is_fixed_reason(cutoff: Any) -> None:
    with pytest.raises(CitationError, match="^citation_input$"):
        evaluate((), (), cutoff=cutoff)


def test_duplicate_ids_wrong_containers_and_inconsistent_versions() -> None:
    bad_pairs: list[tuple[Any, Any]] = [
        ([], ()),
        ((), []),
        ((None,), ()),
        ((decision(),), ()),
        ((), (contract(1),)),
        ((contract(1), contract(1)), ()),
        ((contract(1),), (decision(1),)),
    ]
    for rows, targets in bad_pairs:
        with pytest.raises(CitationError, match="^citation_input$"):
            evaluate(rows, targets, cutoff=CUTOFF)
    for rows, targets in [
        ((contract(1), replace(contract(2), cancelled=True)), ()),
        ((), (decision(), replace(decision(101), decision_type=None))),
    ]:
        with pytest.raises(CitationError, match="^citation_contract$"):
            evaluate(rows, targets, cutoff=CUTOFF)


def test_observation_and_reference_bounds() -> None:
    rows = tuple(contract(i, str(i), ()) for i in range(1, 5001))
    assert evaluate(rows, (), cutoff=CUTOFF).records == 5000
    with pytest.raises(CitationError, match="^citation_limit$"):
        evaluate(rows, (decision(5001),), cutoff=CUTOFF)
    refs = cast(tuple[Reference, ...], contract(1).references)
    assert (
        len(evaluate((replace(contract(1), references=refs * 1000),), (), cutoff=CUTOFF).edges) == 1
    )
    with pytest.raises(CitationError, match="^citation_contract$"):
        evaluate((replace(contract(1), references=refs * 1001),), (), cutoff=CUTOFF)


def test_edge_and_serialized_output_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(citations, "MAX_EDGES", 2)
    assert len(evaluate((contract(1, targets=("A", "B")),), (), cutoff=CUTOFF).edges) == 2
    with pytest.raises(CitationError, match="^citation_limit$"):
        evaluate((contract(1, targets=("A", "B", "C")),), (), cutoff=CUTOFF)
    result = payload((contract(1),), ())
    size = len(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    monkeypatch.setattr(citations, "MAX_OUTPUT_BYTES", size)
    assert payload((contract(1),), ()) == result
    monkeypatch.setattr(citations, "MAX_OUTPUT_BYTES", size - 1)
    with pytest.raises(CitationError, match="^citation_limit$"):
        evaluate((contract(1),), (), cutoff=CUTOFF)


def test_definition_hash_covers_sql_and_model_stays_pure(monkeypatch: pytest.MonkeyPatch) -> None:
    assert reference_sql() == files("nima.semantics").joinpath("citations.sql").read_text()
    assert definition()["status"] == "draft"
    assert definition()["model"] == "explicit_procurement_citations.v1"
    before = definition_sha256()
    sql = reference_sql()
    monkeypatch.setattr(citations, "reference_sql", lambda: sql + "\n-- changed\n")
    assert definition_sha256() != before
    imports = set()
    for node in ast.walk(ast.parse(files("nima.semantics").joinpath("citations.py").read_text())):
        if isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    assert {i for i in imports if i.startswith("nima.")} == {
        "nima.semantics.lifecycle",
        "nima.semantics.selection",
    }
    assert not imports & {"psycopg", "httpx", "prefect"}
