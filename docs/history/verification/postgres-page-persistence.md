# PostgreSQL page persistence verification

Date: 2026-11-09. Base: merged PR #10 on main (`e2314cd`). Scope is the
archived-page transaction in SPEC-source-ingestion.md; HTTP resume stays deferred.

## Evidence

- 151 tests pass; 98.23% combined line/branch coverage. The existing 90% floor
  remains unchanged. New database tests use real PostgreSQL 17.11 and Psycopg
  3.3.8, with a separate UUID-named disposable database per test, never mocks/skips.
- Migration, fingerprint, and page API tests failed before their implementation.
  Migration replay/checksum checks and failed-DDL rollback pass; the built wheel
  contains the exact SQL resource used by migration.
- Repeated committed-page replay adds no observations or outbox work. A→B→A→A
  across fresh runs produces two versions and four observations/events. Exact
  amounts/timestamps survive storage. Object-key order and changed neighboring
  records do not duplicate unchanged versions; unprojected fields affect hashes.
- Quarantine preserves original row indexes. Invalid run identity, naive times,
  page gaps, changed committed bytes, and changed page shape fail visibly.
  A duplicate source ID rolls back all page effects and leaves the checkpoint.
- SIGKILL before commit: a test-only database trigger holds a real child worker
  at the final checkpoint UPDATE after records/outbox insertion. Killing it rolls
  back the transaction. A new connection replays the hash-verified archived body.
- SIGKILL after commit: a real child signals local commit and waits before its
  supervisor proceeds. Killing it leaves a durable page. Replaying the archived
  body returns false and leaves exactly one observation and pending event.
- Two concurrent callers of the same page produce one commit and one replay.
- A targeted mutation disabled changed-page rejection; the checkpoint test failed.
  Source was restored byte-for-byte, using isolated bytecode caches.

Formatting/lint, strict types, build, Bandit, Gitleaks, skill integrity, and the
hash-locked dependency advisory audit pass locally. CI adds a digest-pinned
PostgreSQL service and runs the same suite; no existing check is removed or relaxed.
Hosted run evidence is recorded in the PR after checking its final commit.

## Review and limits

Review covers transaction ownership, row locking, parameterized SQL, FK/unique
constraints, evidence immutability, full-source hashing, bounded connection/query
waits, and private filesystem evidence. Source fingerprinting rejects depth above
128. Migration is explicit and atomic; unknown history/checksum drift is rejected.

These are worker-process tests with a running database, not database-server,
storage-device, or multi-page HTTP recovery tests. Raw files precede SQL and may
remain unreferenced after rollback; no distributed transaction or automatic blob
garbage collection is claimed. Archive roots are fixed per run. The API assumes
a trusted local archive owner and a compatible explicitly migrated schema.

The HTTP CLI remains archive-only. Attempt persistence, run show/resume, final
coverage reconstruction, supplier/buyer relational projections, outbox delivery,
and production roles/backups/retention remain open. Observation IDs identify events;
their allocation order is not a cross-run commit-order or source-event-time proof.
No live source collection, deployed schema, graph inference, or model training is
part of this increment. Connection strings and raw data remain outside Git.
