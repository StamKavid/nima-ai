# Offline GEMI persistence verification

2026-11-10. Implements the user-approved docs/sources/gemi-persistence.md after
the independent archive-verification slice. No new dependency, provider request,
credential, CI control, identity decision or graph write is included.

Local `make check`: **411 tests, 98.05% combined line/branch coverage**. Storage
orchestration has 100% coverage and the archive verifier 99%. Formatting/lint,
strict types, package build, skill integrity, Bandit and Gitleaks passed. The
hash-locked dependency audit passed against the unchanged uv.lock. Final-head
hosted results are recorded in the delivery PRs.

## Evidence and recovery

Tests use the real collector with synthetic HTTPX responses to create archives,
then real disposable PostgreSQL 17 databases. Parser/verification, SQL and CLI
tests failed before their implementations. No production registry payload is
committed or used to claim provider compatibility.

Mixed 200/404 and retry evidence imports reconcile IDs, bodies, assertions and
original observation times. Immutable SQL relations retain exact manifest bytes,
per-attempt metadata, response versions and observations. A→B→A preserves all
three observations and reuses the two response versions. Formatting changes can
produce another byte version without implying a legal/business change.

Identical concurrent imports converge on one result; replay rechecks the archive,
body metadata, stored assertions and all run relations. Changed manifests,
relocated archives, removed bodies and administrator-corrupted assertions fail
without replacing history. A failed SQL trigger rolls back every new registry
and raw-metadata row. Evidence UPDATE/DELETE attempts are rejected.

Actual child-process SIGKILL tests stop the importer before commit, after profile
and response inserts at its last observation, and after commit. A fresh connection
proves zero partial import before commit, complete durable evidence after commit,
and successful idempotent replay in both cases. Archive bytes/modes/mtime remain
unchanged. These tests do not simulate machine power loss, server recovery,
network storage or later loss of the external archive.

A populated v3 KIMDIS database refuses registry import until explicit migration
0004. After upgrading, previous page replay and outbox projection still work;
registry imports enqueue no procurement events. Other KIMDIS collection, resume,
projection, identity and real crash tests pass in the full suite.

The CLI succeeds without NIMA_GEMI_API_KEY and with HTTPX client construction
forbidden. It returns fixed redacted configuration, source-validation, database
and interruption outcomes. Missing configuration never initializes an archive.
The prior hash-guard mutation was killed and restored before final checks; see
gemi-archive.md. Earlier manifests do not retain Content-Type, which remains
explicitly unverified during offline replay.

## Review and delivery

Five-axis review covers atomicity/evidence/coverage, typed values and small source
boundaries, separation from procurement checkpoints and event dispatch, bounded
no-follow file reads plus parameterized/redacted SQL, and sequential bounded
work with per-run transaction locks. The source archive remains single-owner;
DB rows cannot make an external body immune to future deletion or modification.

Deliver archive verification to main first, then its dependent storage/CLI PR.
The dependent PR is retargeted to main after its predecessor merges. Both remain
private and attributed to StamKavid; hosted push CI validates each branch. PR CI
targets main under the unchanged workflow, so the dependent PR receives that
additional event only after retargeting. No automatic merge/deployment occurs.
Personal-key acceptance, real-profile schema compatibility, freshness, reviewed
identity links and a company graph remain later validation gates.
