# ADR-0007: Sources plug into the engine through an adapter that owns the request

## Status

Accepted by the owner, 2026-11-20 (specs approved; delivered in #154-#159).

## Context

The acquisition engine parsed, stored and replayed pages as KIMDIS only. It sent every
request to the KIMDIS endpoint, wrote KIMDIS provenance into every manifest and could reload
only a KIMDIS-shaped run query. A second real source would have archived false provenance and
sent requests to the wrong host.

## Decision

A source is an adapter implementing `nima.sources.base.SourceAdapter`. The adapter owns what is
asked (`request_for`, `provenance`, `query_payload`, `normalize_page`); the engine owns how it
is asked and what happens to the answer (limits, retry, archive-before-parse, checkpoints,
resume, replay). Requests are refused before any run, file or network call unless `https`,
free of credentials/query/fragment, equal to the declared endpoint, and body-free for GET.
Resume rebuilds the adapter from the stored `connector_version` through the registry; there is
no migration. KIMDIS wire request, manifests, rows and sidecars stay byte-identical, pinned by
characterisation tests from unmodified main. Engine packages import no source constants; a
shrink-only dependency baseline enforces it.

## Consequences

A new source needs an adapter, a registry entry, synthetic fixtures and conformance tests, not
engine changes. Downstream code still enumerates `kimdis` and `gemi`; a third source ingests and
replays but does not flow onward until a spec names a dataset. Cursor-paged requests, a
per-source CLI and machine-comparable licences are deferred with triggers in
`docs/specs/SPEC-source-neutral-collection.md`. Alternative rejected: a `source` column on runs, which
needs a migration and gains nothing while `connector_version` identifies the adapter.
