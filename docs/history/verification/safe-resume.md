# Safe managed-run resume verification

Date: 2026-11-09. Base: merged PR #12 (`c80efc5`). Scope: explicit managed-run
resume under SPEC-source-ingestion.md. No dependency, schema, CI or quality-floor change.

187 tests pass; measured local combined Python line/branch coverage is 96.64%.
Formatting/lint, strict types, build, Bandit, Gitleaks, skill integrity and the
hash-locked dependency audit pass. Hosted results are recorded in the PR.

## Evidence and review

- Recovery/archive tests and CLI tests failed before implementation. A committed
  prefix is revalidated before continuation; changed source content stops the run
  before accepting new pages. Benign JSON formatting changes are allowed.
- A complete saved response for an uncommitted page replays with original hash,
  bytes and observation time. Changed pending content is rejected. Repeat resume
  of fully committed data verifies archives without source HTTP or duplicate events.
- Missing/corrupt/oversized evidence and invalid saved options are rejected. A
  missing archive root is not recreated. Query/limits/versions stay fixed.
- Real SIGKILL tests cover an HTTP request, a later request after one committed
  page, and a blocked checkpoint transaction after its HTTP receipt was saved.
  Fresh recovery reaches the full dataset exactly once despite corrupted progress
  files. Historical unknown attempts stay unknown; current-owner counts are separate.
- An active child worker rejects a competing resume. Lease-loss testing exposed
  an unsafe claim through a second connection; ownership claims now use the exact
  advisory-lock connection. Old-token page/attempt writes and old-lease reclaim fail.
- Disabling prefix validation made the drift test request a continuation page;
  the test failed. Source was restored byte-for-byte with isolated bytecode caches.
- Offline cached sample: interrupt after 5 pages / 250 records, then revalidate
  pages 0–4 and continue to 23 pages / 1,118 records, observations and pending events.
  Total attempts: 29. Repeating completed resume made zero source requests. All
  disposable probe data was removed and original cached evidence stayed unchanged.

Review covers lease/claim atomicity, row-token fencing, verified bounded reads,
shared retry/acceptance/reconciliation paths, pending-body selection, observation
timestamps and failure redaction. PostgreSQL advisory-lock documentation is linked
in storage/runs.py. Original migrations and source records are unchanged.

## Boundaries

Drain older pre-lease workers before upgrading. Offset revalidation is not snapshot
isolation, a source freshness guarantee or exactly-once HTTP. Original manifests
and JSONL are initial-invocation projections; use SQL for resumed state. Each user
invocation has the original budgets and total page cap; no automatic scheduler.
Database-server/storage-device crash recovery, outbox delivery, party projections,
graph/model work and production deployment are outside this change.
