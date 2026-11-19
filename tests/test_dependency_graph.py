"""Import-graph checks: no new cycles, no engine import of a concrete source, shrink-only."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts import dependency_graph as dg

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "tests" / "dependency_baseline.json"


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, body in files.items():
        path = root / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root / "src"


def test_graph_resolves_imports_and_from_imports_to_known_modules(tmp_path: Path) -> None:
    src = tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "import pkg.b\nfrom pkg import c\nimport os\nimport pkg.missing\n",
            "pkg/b.py": "from pkg.c import thing\n",
            "pkg/c.py": "thing = 1\n",
        },
    )
    graph = dg.build_graph(src, "pkg")
    assert graph["pkg.a"] == frozenset({"pkg.b", "pkg.c"})
    assert graph["pkg.b"] == frozenset({"pkg.c"})
    assert graph["pkg.c"] == frozenset()


def test_lazy_imports_inside_functions_count(tmp_path: Path) -> None:
    src = tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "def f():\n    from pkg import b\n",
            "pkg/b.py": "",
        },
    )
    assert dg.build_graph(src, "pkg")["pkg.a"] == frozenset({"pkg.b"})


def test_relative_imports_are_refused_not_ignored(tmp_path: Path) -> None:
    src = tree(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from . import b\n", "pkg/b.py": ""})
    with pytest.raises(dg.DependencyError, match="relative"):
        dg.build_graph(src, "pkg")


def test_unparseable_source_is_an_error_not_an_empty_graph(tmp_path: Path) -> None:
    src = tree(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "def (:\n"})
    with pytest.raises(dg.DependencyError, match="parse"):
        dg.build_graph(src, "pkg")


def test_cycles_are_strongly_connected_groups_and_self_imports_are_ignored() -> None:
    graph = {
        "a": frozenset({"b", "a"}),
        "b": frozenset({"c"}),
        "c": frozenset({"a"}),
        "d": frozenset({"a"}),
        "e": frozenset(),
    }
    assert dg.cycles(graph) == [("a", "b", "c")]
    assert dg.cycles({"x": frozenset({"y"}), "y": frozenset()}) == []


def test_two_separate_cycles_are_reported_separately_and_sorted() -> None:
    graph = {
        "q": frozenset({"r"}),
        "r": frozenset({"q"}),
        "a": frozenset({"b"}),
        "b": frozenset({"a"}),
    }
    assert dg.cycles(graph) == [("a", "b"), ("q", "r")]


def test_package_graph_collapses_modules_to_two_level_packages() -> None:
    graph = {
        "nima.storage.postgres": frozenset({"nima.ingestion.config"}),
        "nima.ingestion.config": frozenset({"nima.storage.runs"}),
        "nima.storage.runs": frozenset(),
        "nima": frozenset(),
    }
    assert dg.package_graph(graph) == {
        "nima": frozenset(),
        "nima.storage": frozenset({"nima.ingestion"}),
        "nima.ingestion": frozenset({"nima.storage"}),
    }


def test_forbidden_edges_are_engine_modules_importing_a_concrete_source() -> None:
    graph = {
        "nima.storage.postgres": frozenset({"nima.sources.kimdis", "nima.sources.base"}),
        "nima.ingestion.collector": frozenset({"nima.sources.gemi"}),
        "nima.analytics.reconcile": frozenset({"nima.sources.kimdis"}),
        "nima.sources.kimdis": frozenset({"nima.sources.kimdis_contracts"}),
    }
    assert dg.forbidden_edges(graph) == [
        ("nima.ingestion.collector", "nima.sources.gemi"),
        ("nima.storage.postgres", "nima.sources.kimdis"),
    ]


def snapshot(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "package_cycles": [["nima.a", "nima.b"]],
        "module_cycles": [["nima.x", "nima.y"]],
        "forbidden_edges": [["nima.storage.postgres", "nima.sources.kimdis"]],
    }
    return {**base, **changes}


def test_matching_snapshot_has_no_problems() -> None:
    assert dg.compare(snapshot(), snapshot()) == []


def test_a_new_or_grown_cycle_is_a_problem() -> None:
    new = snapshot(package_cycles=[["nima.a", "nima.b"], ["nima.c", "nima.d"]])
    assert any("new" in p and "nima.c" in p for p in dg.compare(new, snapshot()))
    grown = snapshot(package_cycles=[["nima.a", "nima.b", "nima.c"]])
    assert any("nima.c" in p for p in dg.compare(grown, snapshot()))


def test_a_new_forbidden_edge_is_a_problem() -> None:
    now = snapshot(
        forbidden_edges=[
            ["nima.storage.postgres", "nima.sources.kimdis"],
            ["nima.ingestion.collector", "nima.sources.gemi"],
        ]
    )
    problems = dg.compare(now, snapshot())
    assert len(problems) == 1 and "nima.ingestion.collector" in problems[0]


def test_a_shrunk_graph_must_update_the_baseline() -> None:
    problems = dg.compare(snapshot(forbidden_edges=[]), snapshot())
    assert len(problems) == 1 and "stale" in problems[0] and "remove" in problems[0]
    problems = dg.compare(snapshot(package_cycles=[]), snapshot())
    assert len(problems) == 1 and "stale" in problems[0]


def test_malformed_baseline_is_refused() -> None:
    with pytest.raises(dg.DependencyError, match="baseline"):
        dg.compare(snapshot(), {"package_cycles": []})
    with pytest.raises(dg.DependencyError, match="baseline"):
        dg.compare(snapshot(), snapshot(forbidden_edges="nope"))


def test_snapshot_is_sorted_and_deterministic(tmp_path: Path) -> None:
    src = tree(
        tmp_path,
        {
            "nima/__init__.py": "",
            "nima/storage/__init__.py": "",
            "nima/storage/postgres.py": "import nima.sources.kimdis\n",
            "nima/sources/__init__.py": "",
            "nima/sources/kimdis.py": "",
        },
    )
    first = dg.snapshot(src)
    assert first == dg.snapshot(src)
    assert first["forbidden_edges"] == [["nima.storage.postgres", "nima.sources.kimdis"]]


def test_cli_writes_then_checks_a_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tree(
        tmp_path,
        {
            "nima/__init__.py": "",
            "nima/storage/__init__.py": "",
            "nima/storage/postgres.py": "import nima.sources.kimdis\n",
            "nima/sources/__init__.py": "",
            "nima/sources/kimdis.py": "",
        },
    )
    baseline = tmp_path / "baseline.json"
    args = ["--src", str(src), "--baseline", str(baseline)]
    assert dg.main([*args, "--write"]) == 0
    text = baseline.read_text()
    assert text.endswith("\n") and json.loads(text)["forbidden_edges"]
    assert dg.main(args) == 0
    (src / "nima" / "storage" / "extra.py").write_text("import nima.sources.kimdis\n")
    assert dg.main(args) == 1
    assert "nima.storage.extra" in capsys.readouterr().out


def test_cli_fails_closed_without_a_baseline_or_on_bad_arguments(tmp_path: Path) -> None:
    src = tree(tmp_path, {"nima/__init__.py": ""})
    assert dg.main(["--src", str(src), "--baseline", str(tmp_path / "missing.json")]) == 2
    assert dg.main(["--src", str(tmp_path / "nowhere")]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert dg.main(["--src", str(src), "--baseline", str(broken)]) == 2


def test_the_real_repository_matches_its_committed_baseline() -> None:
    """New cycles and new engine-to-source imports fail here; shrinking requires editing the
    baseline file in the same change (run `uv run python -m scripts.dependency_graph --write`)."""
    baseline = json.loads(BASELINE.read_text())
    problems = dg.compare(dg.snapshot(REPO / "src"), baseline)
    assert problems == [], "\n".join(problems)


def test_edges_to_unknown_nodes_are_ignored_by_cycle_detection() -> None:
    graph = {"a": frozenset({"b", "ghost"}), "b": frozenset({"a"})}
    assert dg.cycles(graph) == [("a", "b")]


def test_malformed_baseline_entries_are_refused() -> None:
    wrong_width = snapshot(forbidden_edges=[["only-one"]])
    with pytest.raises(dg.DependencyError, match="entry is malformed"):
        dg.compare(snapshot(), wrong_width)
    with pytest.raises(dg.DependencyError, match="entry is malformed"):
        dg.compare(snapshot(), snapshot(package_cycles=[[1, 2]]))
    with pytest.raises(dg.DependencyError, match="entry is malformed"):
        dg.compare(snapshot(), snapshot(module_cycles=[[]]))


def test_cli_rejects_a_baseline_that_is_not_an_object(tmp_path: Path) -> None:
    src = tree(tmp_path, {"nima/__init__.py": ""})
    listing = tmp_path / "list.json"
    listing.write_text("[]")
    assert dg.main(["--src", str(src), "--baseline", str(listing)]) == 2


def test_module_entry_point_exits_with_the_check_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tree(tmp_path, {"nima/__init__.py": ""})
    baseline = tmp_path / "baseline.json"
    monkeypatch.delitem(sys.modules, "scripts.dependency_graph", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["dependency_graph", "--src", str(src), "--baseline", str(baseline), "--write"]
    )
    with pytest.raises(SystemExit) as written:
        runpy.run_module("scripts.dependency_graph", run_name="__main__")
    assert written.value.code == 0
    monkeypatch.setattr(
        sys, "argv", ["dependency_graph", "--src", str(src), "--baseline", str(baseline)]
    )
    with pytest.raises(SystemExit) as checked:
        runpy.run_module("scripts.dependency_graph", run_name="__main__")
    assert checked.value.code == 0
