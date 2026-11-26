# U2 acceptance consumer checkpoint

Date: 2026-11-26 (Europe/Athens). Owner approved D1–D3 of the
[contract](../specs/SPEC-cpv-acceptance-readout.md), including implementation.
Baseline #228 is merged at `e6f48b4`; all three main jobs passed in run 45812543064.
This records focused proof for the implementation candidate. Final full local,
package/audit and exact-head hosted results are recorded on its delivery PR.

## Boundary

The public `prepare_cpv_result` exposes the existing verified report with a frozen
cohort JSON string, typed metric/observations and verified pages. The old
`prepare_cpv_readout` tuple API and existing report bytes stay unchanged. The
preparation sequence still reads one source cohort, verifies originals/re-extracts
CPV and checks reference SQL against frozen JSON. It uses two sequential read-only
connections, both closed before sidecar publication. The acceptance adapter adds
no verifier, source fetch, schema, dependency or orchestration layer.

The adapter inspects a private hash-named report (1 MiB), prepares once afresh,
requires full byte equality and validates typed/frozen/serialized bindings. Ten
explicit measured counters feed unchanged `nima.dataset-acceptance` 1.0.0, SHA-256
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
Coverage diagnostics precede CPV/month filters; record cancellations are counted
once regardless of overlapping cells. A private sidecar (64 KiB) binds hashes,
cutoff, profiles and policy without copying selections or source detail.

## Focused and adversarial proof

**211 cases pass**, including 143 new preparation/consumer cases and existing
CPV/acceptance CLI compatibility cases. Line and branch coverage is 100% for:

| Module | Statements | Branches |
|---|---:|---:|
| U2 acceptance adapter | 175 | 64 |
| CPV producer including new preparation API | 91 | 6 |
| Shared acceptance CLI | 42 | 2 |

Initial tests failed for the missing API/consumer/command. A later failing
record-pointer disagreement test drove the corresponding binding check. Strict
mypy passes 411 first-party files; lint, Bandit and Gitleaks pass. Existing tests,
policy/semantic/SQL definitions, artifact formats and ODCS contracts are retained.

Twenty U2 native/process cases use owned PostgreSQL 17, restricted readers and
actual synthetic original bytes. Another native preparation case checks the
frozen facts/old tuple API and closed connections. Tests prohibit source HTTP and
compare SQL/archive/input state before and after inspection. Native known answers
include eight observations/five pages, four unambiguous records, one ambiguous
record and one each unknown date, unclassified CPV, unknown cancellation and
cancellation. Five cell contributions and two cell cancellation contributions do
not change those four/one distinct-record counts. The same diagnostics persist
under unmatched code/month filters with `selection_unresolved`.

Actual incomplete/quarantined/no-page captures, broken/missing originals,
SQL/projection/membership/page disagreement and owner-principal access refuse
without publishing. Genuine complete-empty includes its original empty page.
Every successful retry/relocation uses two connections; deleting an original after
prior publication invalidates the next attempt. Four SIGKILL/SIGINT cases stop
before/after the final link, prove closed SQL, then retry identical bytes through
the normal CLI without changing originals or an existing artifact's mtime.

Controlled producer frames separately test published negative policy decisions,
nonzero quarantine measurement and unsupported definitions. They do not claim
that real partial/quarantined captures pass the strict native verifier.

All **22 behavior mutations are rejected**: every counter, overlap/filter scope,
single preparation, saved-byte equality, selection privacy, subject/sidecar bounds,
publication/error handling, cohort/assessment bindings, typed coverage and evidence
pointers. Source is restored byte-for-byte and SHA-256 checked. These are behavior
failures, not changed-definition-pin failures.

## Delivery and remaining scope

Require full `just check`/`just audit`, isolated built-wheel/native CLI proof and
all three exact-head hosted jobs before merge readiness. Source stays frozen during
these gates; post-push results go on the PR without another documentation-only
full run. Private logs/fixtures/mutation proofs stay outside Git under
`/workspace/work/nima-cpv-acceptance-proof`.

This is software verification using synthetic originals, not actual market-data
acceptance, metric certification, observed investigator value or a release.
U3/U4, durable history and real-cohort reconciliation remain open.
[Operator command](../runbooks/cpv-acceptance.md).
