# ADR-0003: Collect bounded evidence before database checkpointing

## Status

Implemented for review as the next slice of the accepted ingestion direction.

## Date

2026-11-08

## Context

The normalizer needs reproducible source bodies and visible collection coverage
before later graph/model work can use its output. Combining HTTP, storage,
PostgreSQL transactions, outbox workers, and crash recovery in one increment
would make each guarantee harder to assess.

## Decision

Use pinned HTTPX 0.28.1 for streaming read-only POST requests to the fixed
official KIMDIS endpoint. Preserve inherited proxy/CA settings and verified TLS;
disable redirects. Bound dates, attempts, rate, body size, pages, and run time.
HTTPX timeouts bound inactivity, so check a separate monotonic run budget and
document its cooperative limits.

Archive completed identity-encoded response bodies by SHA-256 before parsing or
HTTP status handling. Use private local directories/files, immutable blob
creation, and fsynced atomic run manifests. Preserve separate raw/normalization
completeness and per-row quarantine. Start a fresh run on each invocation.

Keep the implementation in three reviewable dependent changes: page/archive,
HTTP collection, and CLI/documentation. Do not expose database inspection or
resume commands before transactional history/checkpoints are implemented.

## Alternatives

`urllib` would avoid a runtime dependency but requires more manual streaming,
timeout, and transport-test plumbing. A general scraping/agent framework adds
unneeded abstractions for one structured endpoint. A manifest-only resume scheme
would imply transactional recovery guarantees it cannot currently provide.

## Consequences

Local evidence can be inspected and reparsed independently of a database. Raw
data and derived artifacts stay outside Git. This is a single-owner local archive,
not a concurrent object-storage service. Compressed responses are rejected rather
than risking unbounded decompressor allocation. SIGKILL can leave a running
manifest or incomplete derived JSONL; these are not eligible for automatic resume.
The next increment adds PostgreSQL observations/versions/outbox and real
process-crash/reconciliation tests. Offset-page reconciliation cannot prove a
consistent source snapshot.

## Sources

- https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help
- https://www.python-httpx.org/quickstart/#streaming-responses
- https://www.python-httpx.org/advanced/timeouts/
