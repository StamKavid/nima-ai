"""The metric catalogue: every metric listed once, with hashes the published page must match.

Promotion is an owner decision. A metric may be `reviewed` only if the catalogue page carries a
dated review record for it, and `certified` only if a recorded real-data reconciliation exists.
These tests make a silent promotion fail instead of passing.
"""

import ast
import hashlib
import re
from importlib.resources import files
from pathlib import Path

import pytest

from nima.semantics.catalogue import CatalogueEntry, entries
from nima.semantics.citations import definition as citation_definition

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "semantics" / "metric-catalogue.md"
ROW = re.compile(
    r"^\| (U\d) \| `([a-z_0-9.]+)` \| ([a-z]+) \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|$",
    re.MULTILINE,
)


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_the_four_scenarios_have_one_metric_each_in_order() -> None:
    rows = entries()
    assert [row.scenario for row in rows] == ["U1", "U2", "U3", "U4"]
    assert len({row.metric_id for row in rows}) == 4
    assert all(re.fullmatch(r"[a-z_]+\.v[0-9]+", row.metric_id) for row in rows)


def test_each_entry_names_an_existing_provider_and_document() -> None:
    for row in entries():
        module = files("nima.semantics").joinpath(row.provider.rsplit(".", 1)[1] + ".py")
        assert module.is_file(), row.provider
        assert (ROOT / row.document).is_file(), row.document


def test_the_hashes_are_sha256_and_the_sql_hash_is_the_packaged_files_hash() -> None:
    for row in entries():
        assert re.fullmatch(r"[0-9a-f]{64}", row.definition_sha256)
        sql_name = row.provider.rsplit(".", 1)[1] + ".sql"
        packaged = files("nima.semantics").joinpath(sql_name).read_text()
        assert row.sql_sha256 == hashlib.sha256(packaged.encode()).hexdigest()


def test_the_published_page_matches_the_code_exactly() -> None:
    published = ROW.findall(page())
    computed = [
        (r.scenario, r.metric_id, r.status, r.definition_sha256, r.sql_sha256) for r in entries()
    ]
    assert published == computed


def test_every_packaged_reference_sql_has_a_declared_metric_or_model_owner() -> None:
    packaged = {p.name for p in files("nima.semantics").iterdir() if p.name.endswith(".sql")}
    listed = {row.provider.rsplit(".", 1)[1] + ".sql" for row in entries()}
    # Citations are a model, not a fifth metric; unknown SQL still fails this closed set.
    model = citation_definition()
    assert model["model"] == "explicit_procurement_citations.v1"
    assert "metric" not in model
    sql = files("nima.semantics").joinpath("citations.sql").read_text()
    assert model["sql_sha256"] == hashlib.sha256(sql.encode()).hexdigest()
    assert packaged == listed | {"citations.sql"}


def test_every_semantic_module_that_defines_a_metric_is_listed() -> None:
    listed = {row.provider.rsplit(".", 1)[1] for row in entries()}
    defining = set()
    for path in (ROOT / "src" / "nima" / "semantics").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict) and any(
                isinstance(key, ast.Constant) and key.value == "metric" for key in node.keys
            ):
                defining.add(path.stem)
    assert defining == listed


def test_a_status_is_one_of_the_three_and_promotion_leaves_a_record() -> None:
    text = page()
    for row in entries():
        assert row.status in {"draft", "reviewed", "certified"}
        if row.status in {"reviewed", "certified"}:
            assert f"Review record: `{row.metric_id}`" in text, row.metric_id
        if row.status == "certified":
            record = ROOT / "docs" / "verification" / f"reconciliation-{row.metric_id}.md"
            assert record.is_file(), record


def test_the_catalogue_is_read_only_and_imports_only_semantic_modules() -> None:
    source = files("nima.semantics").joinpath("catalogue.py").read_text()
    for node in ast.walk(ast.parse(source)):
        names = (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        for name in names:
            assert not name.startswith(
                ("psycopg", "prefect", "httpx", "nima.storage", "nima.ingestion")
            )


def test_the_entry_type_is_a_plain_frozen_record() -> None:
    row = entries()[0]
    assert isinstance(row, CatalogueEntry)
    with pytest.raises(AttributeError):
        row.status = "certified"  # type: ignore[misc]
