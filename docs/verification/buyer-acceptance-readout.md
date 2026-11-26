# U3 acceptance consumer checkpoint

Date: 2026-11-26 (Europe/Athens). Owner approved E1–E3 of the
[contract](../specs/SPEC-buyer-acceptance-readout.md), including implementation.
Contract #230 is merged at `0665eb7`; reviewed `ff5f6b5` is reachable with
identical tree `17c4b7f4ee91a19b83cc9e58784640e72f8a8e15`.
This records focused proof for the implementation candidate. Final local,
package/audit and exact-head hosted results are recorded on its delivery PR.

## Boundary and meaning

The additive `prepare_buyer_result` returns the already-verified body, typed metric,
frozen cohort JSON/observations and verified pages. The old tuple API/report bytes
remain unchanged. The existing sequence owns one bounded cohort read, original/
projection reconciliation and Python/SQL parity; its two sequential read-only
connections close before sidecar publication. No source HTTP, SQL writes, second
verifier, per-buyer metric evaluation or new orchestration layer is added.

The consumer inspects a private hash-named report (1 MiB), prepares once afresh,
requires full byte equality and validates frozen/typed/serialized bindings. It
uses the existing shared selector once to measure whole-cohort selection while
reconciling buyer-specific diagnostics, sparse evidence and exact share/participation
accounting. The unchanged policy decides fitness; monetary eligibility is not
applicable. The private sidecar (64 KiB) hash-binds selection without copying
buyer/supplier/tax IDs, names, source IDs, rankings, shares, amounts or paths.

Policy SHA-256 remains
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
Semantic/SQL/source definitions, old artifact formats, ODCS contracts, journal,
schema/grants, dependencies and CI are unchanged.

## Focused proof

**236 cases pass**, including 167 new preparation/consumer cases and the existing
buyer readout/three neighboring acceptance CLI suites. Line and branch coverage:

| Module | Statements | Branches | Coverage |
|---|---:|---:|---:|
| U3 acceptance adapter | 219 | 92 | 100% |
| Changed buyer producer | 76 | 4 | 100% |
| Shared acceptance CLI | 44 | 2 | 100% |

Missing API/consumer/command tests failed before implementation. Cases cover all
fourteen counters, full-cohort versus buyer scope, global ambiguity, changed buyer
after latest selection, A→B→A, re-observation, future-only observations, sparse
evidence, unknown/empty/ineligible/partial/joint/duplicate/alias suppliers,
cancellation in unresolved/joint records, tied leaders and exact share denominators.
An empty denominator carrying a share refuses explicitly. Strict mypy passes
419 first-party files; lint, Bandit and Gitleaks pass without threshold changes.

Twenty U3 native/process cases use owned PostgreSQL 17, restricted readers and
actual synthetic original bytes. Another native preparation case proves frozen
facts/tuple compatibility and closed connections. A hand-computed native cohort
has thirteen observations/six pages/eight unambiguous source records plus one
ambiguous source. For B1: six buyer records, four resolved/two unresolved, one
partial, one joint and five participations; cancellation and unknown cancellation
each count once. Its partial record has two ineligible occurrences and its joint
record contributes two supplier-cell cancellations. Top share stays 3/4 and
unresolved share 2/6. The report cites ten/three/two observations for the tested
buyer selections, while acceptance always measures thirteen original observations.

Native refusal covers incomplete/quarantined/no-page captures, damaged/missing
originals, SQL/projection/page/membership disagreement and owner-principal access,
with no sidecar. Complete-empty requires an original empty page. Retry/relocation
reconstructs once through two connections without HTTP or source writes; removing
an original after prior publication invalidates the next attempt. Four SIGKILL/
SIGINT cases stop before/after the final link, prove closed SQL and retry identical
bytes through the normal CLI without modifying evidence or an existing final mtime.

Controlled producer frames separately test negative policy publication and measured
nonzero quarantine. They do not claim real quarantined/partial captures passed
the existing strict verifier.

All **28 behavior mutations are rejected**: every counter, whole versus buyer/
sparse-evidence scope, partial occurrences, overlapping participation/cancellation,
top-share denominator and empty-share handling, single preparation/selection,
byte equality, privacy, subject/sidecar bounds, publication/error handling and
cohort/assessment/evidence bindings. Source is restored byte-for-byte and SHA-256
checked; these are behavior failures, not changed-definition-pin failures.

## Delivery and remaining work

Require full `just check`/`just audit`, isolated built-wheel/native CLI and
independent pre-change report-byte/tuple proof plus all exact-head hosted jobs
before review readiness. Keep source stable during verification; record late
results on the PR without another documentation-only full run. Private logs,
owned fixtures and mutation proofs remain outside Git at
`/workspace/work/nima-buyer-acceptance-proof`.

Software proof uses synthetic originals. Actual cohort reconciliation, metric
review/certification and investigator task proof remain open, as do U4 and durable
acceptance history. No source activation, deployment or release is included.
[Operator command](../runbooks/buyer-acceptance.md).
