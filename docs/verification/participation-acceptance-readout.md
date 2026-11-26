# U1 acceptance consumer checkpoint

Date: 2026-11-26 (Europe/Athens). Owner approved C1–C3 of the
[contract](../specs/SPEC-participation-acceptance-readout.md), including implementation.
Contract #227 is merged at `e3839c0` and prerequisite #226 at `fcfa11d`. Both
reviewed heads are reachable from main and their combined tree matches the
composed prerequisite. Main baseline for this candidate is `e3839c0`; the prior
#225 baseline also has all three main jobs passed in run 45762240723. This record describes the candidate's local proof;
post-push exact-head results are recorded on its implementation PR.

## Boundary and meaning

The U1 adapter calls `analytics.export.prepare_readout` once per invocation,
requires complete byte equality with the inspected hash-named report and derives
all eleven counters from its fresh typed/frozen result. It neither recalculates
the metric nor opens another SQL snapshot. The existing API owns raw/SQL/
projection reconciliation, Python/SQL parity and original report validation.
SQL closes before archive reconciliation and publication.

A separate bounded private sidecar binds request/snapshot/cutoff/source profiles,
metric/SQL and the full unchanged policy definition to the assessment. Supplier
selection is hash-bound; no tax number, buyer key, name, normalized record, amount
or physical archive path is copied. Provider status is retained, including
unresolved and empty statuses; neither data fitness nor fixtures certify a metric.

Policy SHA-256 remains
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
All semantic/SQL hashes, original artifact formats and three ODCS contracts are
unchanged. The shared helper extracts only path/error/private subject handling,
retains the citation exception API and distinct 1/8 MiB subject limits, and uses
the existing descriptor-safe primitives and canonical publisher.

## Focused proof

**276 cases pass:** 125 U1 cases, 14 shared-file cases and all 137 existing citation
cases. U1 adapter: 181 statements / 70 branches, 100% line and branch coverage.
Shared helper: 31 statements / 10 branches, 100%; acceptance CLI: 40 statements /
2 branches, 100%. Strict mypy over 403 first-party files, lint, Bandit and Gitleaks
pass before the long gate. No skips, suppressions or threshold changes.

Hand-computed cases cover all eleven counters, tied unknown suppliers, list/country
unknowns unioned once, known-empty lists, A→B→A, re-observation, duplicate matching
supplier ordinals, invalid occurrences in ambiguous versions, buyer uncertainty,
cancellations and after-cutoff evidence. The native known cohort independently
checks eleven observations, four pages, seven unambiguous source records and all
diagnostic counts, with no copied supplier details.

Seventeen U1 native PostgreSQL/process cases use actual synthetic original bytes
and restricted readers. Complete/empty success, real partial/quarantined/no-page
refusal, damaged/missing originals, SQL/membership/page/projection disagreement
and owner-principal refusal produce the intended outcomes with no HTTP or source
writes. Retry/relocation tests count one connection per invocation and preserve
input/report bytes and metadata. Removing an original after successful publication
invalidates the next attempt; the prior sidecar cannot cache a pass.

Four SIGKILL/SIGINT cases stop before/after the real final publication link, with
no source SQL session at that boundary. Retry through the normal CLI produces
identical bytes and preserves an already completed artifact's mtime. A SIGKILL
may leave a private temporary file. Controlled producer frames exercise negative
policy publication separately; they do not claim a real partial U1 capture passed
its stricter existing verifier.

All **22 behavior mutations are rejected**, covering every counter, ambiguous
scope, country/list uncertainty, union versus addition, single preparation, byte
equality, tax-number privacy, subject/output bounds, publication/error handling
and assessment binding. Source is restored byte-for-byte and SHA-256 checked.
These tests fail on behavior, not a changed policy-definition pin.

## Delivery gates

Full `just check`, `just audit`, final isolated-wheel operation and all three
exact-head hosted jobs are required before review readiness. Their post-push
results are recorded on the implementation PR so this immutable pre-push record does not claim
its own future hosted outcome. Application code stays frozen during those runs;
no second full local suite is run solely to update documentation status.

Private logs, owned fixtures and mutation/wheel proofs remain outside Git in
`/workspace/work/nima-participation-acceptance-proof`. The checkpoint is software
verification, not actual source-cohort reconciliation or a v1.0 release.

## Remaining product work

U2–U4 consumers, additive durable-history contract, the owner's actual four-positive
citation reconciliation, metric review/certification and investigator task proof
remain open. No source activation, dependency, CI, schema/grant, journal or policy
change is included. [Operator command](../runbooks/participation-acceptance.md).
