# Spec: source-neutral collection — V1-04 follow-up (N1, N2)

Status: **draft, awaiting owner approval.** Extends `SPEC-source-boundaries.md` (S1-S4 delivered
in #154-#157). It closes the gaps that stop a real second source (S5) from running through the
acquisition engine. It does not add a source, fetch anything or touch the downstream graph,
metadata or analytics code.

## Objective

After S3/S4 the engine parses, stores and replays any adapter's pages. It still **collects** as
KIMDIS: it sends every request to the KIMDIS endpoint, writes KIMDIS provenance into every
archive manifest, and can only store and reload a KIMDIS-shaped run query. A real second source
would archive false provenance, and an adapter wired to it would send its requests to the wrong
host. Success means a second adapter supplies its own request, provenance and run options, the
engine uses exactly those, and **every KIMDIS byte stays identical** (wire request, manifest,
database rows, sidecars).

## Correction to the S4 claim

S4 reported that collect, resume and replay "pass unchanged" for the synthetic sources. That is
true only for parsing, storage, replay and identity. The synthetic tests passed KIMDIS's own
`Query` to every source, so the run-options round trip was never exercised with a non-KIMDIS
query. It would fail: `storage.runs.load_options` rebuilds a KIMDIS `Query` from the keys
`dateFrom`, `dateTo` and `organizations`. The earlier statement is corrected in the V1-04 spec,
todo and progress documents in the same change as this spec.

## Measured starting point (main `0945918`)

Three KIMDIS constants or types are hardwired into engine modules:

1. **Request.** `ingestion.transport.Session.request` sends `POST ENDPOINT?page=N` with
   `json=query.payload()` and `Accept: application/json`. `ENDPOINT` lives in
   `ingestion.config`.
2. **Provenance.** `ingestion.collector` writes `endpoint`, `source` (the documentation URL) and
   `license` ("CC BY 4.0") into `manifest.json` from `ingestion.config` constants. Confirmed by
   running a synthetic `ledger` collection: its manifest claimed the KIMDIS endpoint, source and
   licence. Nothing in code reads this file back; tests, the restore drill and evidence
   bundles do. Existing runs on disk stay valid because nothing re-parses them.
3. **Run options.** `collect()`, `RunStore.begin/takeover`, `PageStore.start_run` and
   `load_options` take or rebuild a KIMDIS `Query`. `resume()` therefore cannot reload another
   source's options.

## Assumptions (correct before approval)

1. No database migration. Adapter identity for a resumed run comes from the stored
   `connector_version` through the registry; no `source` column is added. (Alternative below.)
2. The adapter protocol grows by two members and nothing else: `provenance` and
   `request_for(page)`. Run options move to `query_payload()`, which already exists.
3. Requests stay **page-number addressed**, as the engine's checkpointing is. Cursor continuation
   is not built (see the register).
4. The engine owns how a request is made (timeouts, size limit, identity encoding, user agent,
   retry, rate limit, archive-before-parse, receipts). The adapter owns what is asked.
5. KIMDIS, the two synthetic sources and the seam stub are the only adapters; no live request.

## The change

```python
@dataclass(frozen=True)
class SourceProvenance:
    endpoint: str  # base URL every request goes to; https only
    documentation_url: str  # recorded in the manifest as "source"
    license: str  # as the publisher states it; KIMDIS keeps "CC BY 4.0"


@dataclass(frozen=True)
class SourceRequest:
    method: Literal["GET", "POST"]
    url: str  # must equal the adapter's provenance.endpoint
    params: Mapping[str, str | int]
    json: Mapping[str, object] | None
    accept: str  # e.g. "application/json" or "text/csv"


class SourceAdapter(Protocol):  # existing members unchanged
    @property
    def provenance(self) -> SourceProvenance: ...
    def request_for(self, page: int) -> SourceRequest: ...
```

- **N1: request and provenance.** `Session.request` takes a `SourceRequest`. The collector
  builds it with `source.request_for(page)` and writes the manifest from `source.provenance`.
  A request whose URL is not `https` or differs from the declared endpoint is refused **before
  any network call** as a programming error, not a run failure, so no new failure code or
  stored value appears. `ENDPOINT` and `SOURCE` leave the engine and live with KIMDIS.
- **N2: run options.** The engine stores `adapter.query_payload()` (identical bytes for KIMDIS)
  and compares against it on takeover. `load_options` returns the saved payload, the saved
  `connector_version`, the limits and the archive root, and no longer builds a `Query`.
  `resume()` uses an explicit adapter if given; otherwise `registry.adapter_from_run(
  connector_version, payload)` builds the registered adapter, and an unknown version stops the
  run before any network call. `collect()` keeps accepting a query-like object, so existing
  callers and tests do not change.

## Testing strategy

Tests first, red before green, mutation-checked, as in S3.

1. **Pins from the unmodified engine, committed before the change** (recorded from `main`, volatile
   fields removed): the exact KIMDIS wire request (method, URL, params, body, headers) for a
   multi-page run; the manifest minus `started_at`, `finished_at`, run id and observation times;
   and a KIMDIS resume round trip. They must pass unchanged after each slice.
2. **Conformance (all three sources):** `request_for` is deterministic, its URL equals
   `provenance.endpoint`, it is `https`, different pages give different requests, fields are
   single-line text without control characters, and a request that disagrees with its
   provenance is refused.
3. **Engine suite (all three sources):** every request the mock transport sees goes to that
   source's own endpoint and nowhere else; the manifest records that source's endpoint, source
   URL and licence; N2 resumes a run whose stored query is **not** KIMDIS-shaped, rejects an
   unknown connector version before the network, and still refuses a payload mismatch.
4. **Mutations:** engine ignoring the adapter's endpoint, manifest reading the old constants,
   `Accept` hardcoded, resume rebuilding a KIMDIS query, identity comparison dropped. Each must
   fail a test and be restored.
5. Full gates and hosted exact-head jobs per slice, as before. No CI, dependency or migration
   change. The new request guard is covered to the project's 100% line and branch standard.

## Boundaries

- **Always:** tests first; KIMDIS wire, manifest, database and sidecar bytes identical; one PR per
  slice; draft PR, hosted CI proof, owner merges.
- **Ask first:** a database migration (a `source` column is the alternative to assumption 1),
  any CI or dependency change, any change to graph, metadata or analytics code, any
  network-allowlist change.
- **Never:** a live request, a second real source, a change to stored KIMDIS bytes, a weakened or
  skipped test.

## Success criteria

- No engine module imports a KIMDIS constant (`ENDPOINT`, `SOURCE`) and none builds a KIMDIS
  `Query` from stored options. The dependency baseline does not grow.
- Each of the three sources collects, resumes and replays through the same engine, sending
  requests only to its own endpoint and archiving its own provenance.
- The pinned KIMDIS wire request, manifest, rows and sidecars are byte-identical to `main`.
- Existing crash, resume, replay and access tests pass unchanged.

## What this does not fix, and when it must be revisited

Nothing below is hidden debt; each item has a named trigger.

| Item | Why it stays | Revisit when |
|---|---|---|
| Downstream code accepts only `kimdis` and `gemi`: `graph.pilot_archive`, `metadata` (CLI, export, store with `kimdis_run_id`/`gemi_run_id` columns), analytics, `dataops.archive`, and the replay `PAGE_ARCHIVE` label. | Widening it changes stored schemas (a migration) and several packages, and AGENTS.md puts graph, models and UI after ingestion. A third source ingests and replays but cannot flow downstream yet. | The owner names a dataset and wants it consumed downstream; spec against that dataset. |
| Cursor-continued requests (the next request depends on the last response). | No real source needs it; designing it now would be a guess. The page-number contract is the one the checkpoint uses. | The first real cursor-paged source is chosen. |
| `Query` and its date/buyer rules sit in `ingestion.config`. | It is KIMDIS's query, used by the CLI and intent code in many modules; moving it is mechanical and wide. | A second source needs its own CLI, or the intent layer becomes per-source. |
| Licence is recorded as the publisher's own string (KIMDIS "CC BY 4.0", GEMI "ODC-BY-1.0"). | KIMDIS bytes must not change. | Evidence export needs machine-comparable licences. |
| GEMI keeps its own transport and manifest. | Separate flow, already tracked in the dependency baseline. | GEMI is moved onto the protocol. |

## Open questions

1. **Two PRs or one?** Recommended: N1 then N2, each reviewable on its own. N1 is small and
   removes the false-provenance and wrong-host risks; N2 is the wider change.
2. **Resume identity without a migration** (assumption 1) or a new `ingest_runs.source` column?
   Recommended: no migration. `connector_version` already uniquely identifies the adapter, and a
   column would need an owner-applied migration on the pilot database for no behavioural gain.
3. **Accept the five deferred items above** with their triggers?
