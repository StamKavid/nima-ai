# Durable collection and inspection verification

Date: 2026-11-09. Base: merged PR #11 (`65b08ea`). Scope is fresh PostgreSQL-backed
HTTP collection and read-only run inspection, under SPEC-source-ingestion.md.

172 tests pass; 97.42% combined Python line/branch coverage. Formatting/lint,
strict types, build, Bandit, Gitleaks, skill integrity, and locked-dependency audit
pass locally. The 90% coverage floor and existing CI job/service are unchanged.
Both migration resources in the built wheel match their original files.

## Behavioral evidence

- Database collection/inspection and CLI tests failed before implementation.
- Migration 0002 upgrades a populated v1 schema; 0001 and its checksum remain
  unchanged. Missing/outdated schemas are rejected before source HTTP access.
- HTTPX fixtures plus real PostgreSQL verify retry/error evidence, page commits,
  unknown IDs, quarantine, incomplete runs, explicit migration, read-only CLI,
  redacted driver errors, and failure outputs that retain an inspectable run ID.
- Real SIGKILL tests stop a collector inside a mocked HTTP transport at the first
  request or the request after a committed page. Fresh SQL inspection reconstructs
  correct counts/checkpoints and one unknown started attempt despite a deliberately
  corrupted filesystem progress manifest. Neither case claims completeness.
- Failed attempt INSERT prevents HTTP access. Failed receipt UPDATE prevents a
  page commit or successful run. Archive corruption and failed derived-output
  writes retain inspectable SQL state; archive errors have sanitized receipt codes.
- Removing the managed-page ownership guard caused the durability test to fail.
  The original file was restored byte-for-byte with isolated bytecode caches.
- An offline replay of the retained one-day sample completed 23 pages / 1,118
  normalized records and 24 attempt receipts, including a recorded 429. SQL
  inspection reported checkpoint 23 and zero pending attempts. Disposable replay
  files/database were removed; the original source archive was unchanged.

## Review and boundaries

Review covered schema compatibility, immutable source evidence, transaction
ownership, before-HTTP attempt persistence, source ID reconciliation, SQL snapshot
counts, rate/budget behavior, and error redaction. PostgreSQL aggregate/JSON/array
semantics follow the official documentation linked in `storage/runs.py`.

A stored running status is not proof of worker liveness. A started attempt can
have an unknown outcome after abrupt exit. Inspection does not validate archive
files or refresh source data. SQL and filesystem writes are not a distributed
transaction; finalization or derived-output failures may leave committed pages
with a running status, and inspection reports these conservatively.

No HTTP resume is exposed. Safe takeover, pending-response replay, source-drift
verification, and multi-page restart remain the next increment. Outbox delivery,
party projections, graph/model work, production migration/hosting and database-server
or storage-device crash guarantees are outside this PR. Hosted checks are recorded
in the PR after checking the final head; no merge/deployment is automatic.
