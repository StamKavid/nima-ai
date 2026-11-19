# Spec: source boundaries for a second feed — V1-04

Status: **proposed; awaiting owner approval before any plan or code.** Follows #152
(`7dfc7b1`). This is backlog package V1-04 (`docs/roadmap/agent-backlog.md`), the first
step of v0.2. It prepares a second source (Diavgeia decisions, V1-06) without copying the
KIMDIS stack, and does not fetch, parse or activate any new source.

## Objective

Let the shared acquisition engine (page store, collector, replay, projection) work with any
source through one small Python protocol, with KIMDIS as the first adapter, while keeping
every existing guarantee: archive before parsing, checkpoint and resume, advisory-lease
ownership, outbox, quarantine, namespaced source IDs and exact money. Success means a second
adapter can be added by writing source-specific code only, proven by a conformance suite
that runs against KIMDIS and a synthetic test adapter. Users of the product see no change.

## Measured starting point

Measured with a real import graph over `src/nima` (18 packages) on main `7dfc7b1`:

- KIMDIS-specific code lives in `nima.sources.kimdis` and `nima.sources.kimdis_contracts`.
- Seven modules outside it import it: `ingestion.collector`, `storage.postgres` (the shared
  `PageStore`, imported by 26 modules), `dataops.replay`, `analytics.reconcile` and three
  `metadata` modules. The engine's own storage layer is therefore coupled to one source.
- Shared engine modules also carry KIMDIS literals (for example `ingestion.config.Query` is
  a KIMDIS date/buyer query, and `NORMALIZER_VERSION` is a single global).
- Three package-level import cycles already exist (`ingestion`, `orchestration`, `storage`;
  `orchestration`, `projections`, `storage`; `orchestration`, `storage`), plus two
  module-level ones (`egress.bootstrap`/`gateway`, `kimdis`/`kimdis_contracts`). A dependency
  test that demands "no cycles" would fail today.

## Assumptions (correct before approval)

1. No database migration is needed: `record_versions.normalized` is JSON, `source_id` is
   already namespaced text and `ingest_runs.query` is JSON. Per-source `connector_version`
   and `normalizer_version` are the only values that stop being process-wide constants.
2. The second adapter in this package is a **synthetic test adapter**, not Diavgeia. A real
   second source needs its own access and reuse acceptance first (V1-06).
3. `ingestion.config.Query` stays KIMDIS-shaped for now; the engine treats a run's query as an
   opaque JSON payload supplied by the adapter.
4. Existing import cycles are recorded and not fixed here; the dependency test only forbids
   new ones and new forbidden edges.
5. No new dependency, no CI edit, no live request.

## The boundary

A source adapter provides four things and nothing else:

```python
class SourceAdapter(Protocol):
    name: str  # namespace prefix, e.g. "kimdis"
    connector_version: str
    normalizer_version: str

    def query_payload(self) -> dict[str, object]: ...
    def normalize_page(self, raw: bytes, *, max_bytes: int) -> NormalizedPage: ...
```

`NormalizedPage` is a frozen dataclass in a neutral module (`nima/sources/base.py`) holding
page number, size, totals, per-record contracts with their evidence pointer, source IDs,
record hashes and quarantine issues; it is today's `Page` made source-neutral. Transport
(HTTP, retries, rate limits) stays in `ingestion.transport`; storage stays in `storage`. The
engine imports the protocol and `NormalizedPage`, never a concrete adapter.

## Commands

```
uv run --frozen pytest tests/test_source_conformance.py tests/test_dependency_graph.py -q
uv run --frozen pytest tests/test_collection.py tests/test_resume.py tests/test_page_store.py \
    tests/test_access_collector.py tests/test_durable_crash.py -q   # existing guarantees
uv run --frozen mypy && just check && just audit
```

## Project structure

- `src/nima/sources/base.py`: protocol and `NormalizedPage` (new, neutral, no source imports).
- `src/nima/sources/kimdis.py`: gains a thin `KimdisAdapter`; parsing behavior is unchanged.
- `src/nima/storage/postgres.py`, `ingestion/collector.py`, `dataops/replay.py`: take an
  adapter (default KIMDIS) instead of importing `nima.sources.kimdis`.
- `tests/test_source_conformance.py`: one parametrized suite run against every adapter.
- `tests/test_dependency_graph.py` plus a committed baseline file listing today's cycles.
- A synthetic adapter lives in `tests/` only.

## Testing strategy

- **Conformance suite** (the heart of this package), parametrized over KIMDIS and the
  synthetic adapter: the raw page is archived before parsing; identical replay is idempotent
  and changed bytes for a committed page are refused; a gap or changed pagination is refused;
  resume continues from the committed prefix; bad records are quarantined without losing the
  raw bytes; money round-trips as `Decimal` with unknowns preserved; source IDs carry the
  adapter namespace and two adapters cannot collide.
- **Byte-for-byte regression:** a recorded KIMDIS page run before and after the change
  produces identical `raw_objects`, `record_versions`, `observations`, outbox and archive
  bytes, and the existing replay, crash and resume tests pass unchanged.
- **Access profiles stay valid:** the collector and projector necessity tests from #150 and
  #152 must pass unchanged, which proves no new database privilege crept in.
- **Dependency tests:** the import graph is rebuilt in the test; a forbidden edge
  (`nima.storage.*` or `nima.ingestion.*` importing a concrete `nima.sources.<name>`) fails;
  any import cycle not in the committed baseline fails; the baseline may only shrink.

## Boundaries

- Always: archive before parse; fail closed; keep evidence bytes identical; test with the
  real store, not mocks.
- Ask first: any migration, dependency or CI change; changing a persisted identifier or
  version string; fixing the existing import cycles.
- Never: add a second live source, request any network resource, or let the engine branch on
  a source name.

## Slices and finite acceptance

1. **S1 freeze:** the import-graph test and cycle baseline, no behavior change.
2. **S2 protocol:** `base.py` and `KimdisAdapter` wrapping the existing functions; no engine
   change; KIMDIS conformance passes.
3. **S3 engine on the protocol:** page store, collector and replay take the adapter with
   KIMDIS as the default; all existing tests and the byte-for-byte check pass.
4. **S4 second adapter:** synthetic adapter and the full conformance suite on both.

Each slice ends in one review-ready PR with full gates and hosted exact-head jobs.

## Success criteria

- Zero engine imports of a concrete source module (today: seven importers, of which three
  are engine modules).
- The synthetic adapter runs collect, resume, replay and quarantine with **no engine change**.
- Existing crash, resume, replay and access tests pass unchanged; evidence bytes identical.
- The dependency test rejects a new cycle and a new forbidden edge.

## Open questions

1. Is a test-only synthetic second adapter the right exit proof now (recommended), or do you
   want a real small public dataset before V1-06's access review?
2. Record the three existing package cycles as a shrink-only baseline (recommended), or fix
   them first? Fixing them touches orchestration and is a separate, larger package.
3. May the engine's `connector_version` and `normalizer_version` become per-adapter values
   (assumption 1), given they are stored in evidence tables and used in processing identity?
   KIMDIS keeps today's exact strings, so existing rows stay valid.
