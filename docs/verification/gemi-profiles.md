# Bounded GEMI profile verification

2026-11-10. Base: approved PR #17 (`1f45c70`). No schema, dependency or CI change.
Local checks pass with 322 tests and 97.85% combined Python line/branch coverage.
Parser coverage is 100%; collector is 99%. Formatting/lint, strict types, build,
skill integrity, Bandit, Gitleaks and dependency audit pass.

Parser/collector/CLI tests failed before implementation. Fixtures are synthetic;
there are no production GEMI profiles or personal keys in this change. Tests cover
exact requested identity, Greek/leading-zero text, partial/unknown/empty fields,
KAD version/date pointers, malformed/duplicate/nonfinite JSON and resource bounds.
Arrays exceeding the client cap are quarantined, never truncated.

Real HTTPX plus MockTransport exercises GET/header behavior, pre-request pending
manifests, pacing, 404 accounting, retry exhaustion/defer, auth/redirect stops,
unsupported compression/media, partial streams, cooperative budgets and key/error
redaction. Forced raw-storage failure prevents normalization. All legacy database
tests still use disposable PostgreSQL 17; the GEMI path writes no SQL/outbox rows.

Real SIGKILL tests stop a child inside a MockTransport request and before terminal
manifest publication. Neither leaves false complete flags; complete body evidence
is preserved where available. A fresh lookup uses a new run, reuses immutable blobs
and does not rewrite old manifest bytes. This is not automatic HTTP resume or proof
of real-provider/server/storage recovery.

Mutation experiment: disabling requested registry-ID matching made its regression
test fail (DID NOT RAISE). The clean baseline passed; original bytes were restored
using an isolated bytecode cache before final checks.

Five-axis review covers evidence/completeness correctness, typed immutable assertions,
separation from KIMDIS SQL/identity logic, fixed HTTPS/no-redirect and credential
handling, and bounded request/body/array work. Raw JSON pointers are absent when
the source field is absent; observation time never replaces unknown event dates.
Archive primitives retain their existing single-owner local-filesystem boundary.

No authenticated live pilot ran: provider payload types, coverage, freshness and
credential acceptance remain unverified. Configure a personal key in environment
settings and explicitly choose pilot IDs to establish that evidence. Do not share
keys in chat. Hosted final-head checks are recorded in the delivery PR.
