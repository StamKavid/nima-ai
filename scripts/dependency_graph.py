"""Import-graph checks that keep the shared engine independent of concrete sources.

Two rules, both measured from source with ``ast`` and compared with a committed baseline:

* no import cycle may appear or grow (modules, and two-level packages);
* engine modules must not import a concrete source adapter.

Existing violations are recorded in ``tests/dependency_baseline.json``. The baseline may
only shrink: a check fails on any new violation and also on a baseline entry that no longer
exists, so progress has to be recorded in the same change that makes it.
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO / "src"
DEFAULT_BASELINE = REPO / "tests" / "dependency_baseline.json"
ENGINE_PREFIXES = (
    "nima.storage",
    "nima.ingestion",
    "nima.dataops.replay",
    "nima.projections",
)
SOURCE_PREFIX = "nima.sources."
ALLOWED_SOURCE_MODULES = frozenset({"nima.sources.base", "nima.sources.registry"})
KINDS = ("package_cycles", "module_cycles", "forbidden_edges")

type Graph = Mapping[str, frozenset[str]]


class DependencyError(ValueError):
    """The graph or the baseline cannot be trusted; never treated as a pass."""


def _module_name(path: Path, src: Path) -> str:
    parts = list(path.relative_to(src).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported(tree: ast.AST, known: frozenset[str], path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names if a.name in known}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise DependencyError(f"relative import is not supported: {path.name}")
            base = node.module or ""
            for alias in node.names:
                submodule = f"{base}.{alias.name}"
                if submodule in known:
                    found.add(submodule)
                elif base in known:
                    found.add(base)
    return found


def build_graph(src: Path, package: str = "nima") -> dict[str, frozenset[str]]:
    files = sorted((src / package).rglob("*.py"))
    modules = {_module_name(p, src): p for p in files}
    known = frozenset(modules)
    graph: dict[str, frozenset[str]] = {}
    for name, path in modules.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            raise DependencyError(f"cannot parse {path.name}") from None
        graph[name] = frozenset(_imported(tree, known, path) - {name})
    return graph


def cycles(graph: Graph) -> list[tuple[str, ...]]:
    """Strongly connected groups of two or more nodes, as sorted tuples (Tarjan, iterative)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[tuple[str, ...]] = []
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work: list[tuple[str, list[str]]] = [(root, sorted(graph[root] - {root}))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, pending = work[-1]
            if pending:
                child = pending.pop()
                if child not in graph:
                    continue
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, sorted(graph[child] - {child})))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                if len(group) > 1:
                    groups.append(tuple(sorted(group)))
    return sorted(groups)


def package_of(module: str) -> str:
    return ".".join(module.split(".")[:2])


def package_graph(graph: Graph) -> dict[str, frozenset[str]]:
    edges: dict[str, set[str]] = defaultdict(set)
    for module, deps in graph.items():
        edges[package_of(module)] |= {package_of(d) for d in deps} - {package_of(module)}
    return {package: frozenset(deps) for package, deps in edges.items()}


def forbidden_edges(graph: Graph, engine: Iterable[str] = ENGINE_PREFIXES) -> list[tuple[str, str]]:
    prefixes = tuple(engine)
    found = [
        (importer, target)
        for importer, deps in graph.items()
        if any(importer == p or importer.startswith(p + ".") for p in prefixes)
        for target in deps
        if target.startswith(SOURCE_PREFIX) and target not in ALLOWED_SOURCE_MODULES
    ]
    return sorted(found)


def snapshot(src: Path, package: str = "nima") -> dict[str, object]:
    graph = build_graph(src, package)
    return {
        "package_cycles": [list(g) for g in cycles(package_graph(graph))],
        "module_cycles": [list(g) for g in cycles(graph)],
        "forbidden_edges": [list(e) for e in forbidden_edges(graph)],
    }


def _entries(value: object, kind: str, width: int | None) -> set[tuple[str, ...]]:
    if not isinstance(value, list):
        raise DependencyError(f"baseline {kind} must be a list")
    out: set[tuple[str, ...]] = set()
    for item in value:
        if (
            not isinstance(item, list)
            or not item
            or not all(isinstance(x, str) for x in item)
            or (width is not None and len(item) != width)
        ):
            raise DependencyError(f"baseline {kind} entry is malformed")
        out.add(tuple(item))
    return out


def compare(current: Mapping[str, object], baseline: Mapping[str, object]) -> list[str]:
    """Human-readable problems; empty means the graph matches the committed baseline."""
    problems: list[str] = []
    for kind in KINDS:
        if kind not in baseline:
            raise DependencyError(f"baseline is missing {kind}")
        width = 2 if kind == "forbidden_edges" else None
        now = _entries(current[kind], kind, width)
        recorded = _entries(baseline[kind], kind, width)
        label = "forbidden engine import" if kind == "forbidden_edges" else kind.replace("_", " ")
        joiner = " -> " if kind == "forbidden_edges" else ", "
        problems += [f"new or grown {label}: {joiner.join(e)}" for e in sorted(now - recorded)]
        problems += [
            f"stale baseline {label} (remove or narrow it): {joiner.join(e)}"
            for e in sorted(recorded - now)
        ]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.dependency_graph")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write", action="store_true", help="rewrite the baseline")
    args = parser.parse_args(argv)
    try:
        if not args.src.is_dir():
            raise DependencyError("source directory not found")
        current = snapshot(args.src)
        if args.write:
            args.baseline.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
            return 0
        baseline = json.loads(args.baseline.read_text())
        if not isinstance(baseline, dict):
            raise DependencyError("baseline must be an object")
        problems = compare(current, baseline)
    except (DependencyError, OSError, ValueError) as error:
        print(f"dependency check could not run: {error}")
        return 2
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
