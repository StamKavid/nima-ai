# U1 acceptance consumer checkpoint

Date: 2026-11-26 (Europe/Athens). Owner approved C1–C3 of the
[contract](../specs/SPEC-participation-acceptance-readout.md), including implementation.
Contract #227 is merged at `e3839c0` and prerequisite #226 at `fcfa11d`. Both
reviewed heads are reachable from main and their combined tree matches the
composed prerequisite. Main baseline for this candidate is `e3839c0`; the prior
#225 baseline also has all three main jobs passed in run 45762240723.
#228 is now merged at `e6f48b4`; reviewed `f843f56` is reachable from main with
the identical tree `0ed559f3a0055062358a519ed45e7ee3680aa691`.

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

Full `just check` passed **4,739 tests**, 95.19% overall coverage; `just audit`
passed. Final isolated-wheel/native operation used wheel SHA-256
`debdc6b4b0740ead642f7121536c8073d9326a5489cd4d8d84bfb9ebc63c04d6`,
loaded outside the checkout, and proved the eleven counters, exact parent bytes,
identical retry, relative-path refusal and no copied tax number. All three
exact-head jobs passed in [run 45805461376](https://github.com/StamKavid/nima-ai/actions/runs/45805461376)
at `f843f567bd11b5ed82fd1e4f342dd3512e9092f7`: quality (4,739 tests),
orchestration-compose and source-worker-egress. Application code stayed frozen
during verification. No second full local suite was run solely to record delivery.

Private logs, owned fixtures and mutation/wheel proofs remain outside Git in
`/workspace/work/nima-participation-acceptance-proof`. The checkpoint is software
verification, not actual source-cohort reconciliation or a v1.0 release.

## Remaining product work

U2–U4 consumers, additive durable-history contract, the owner's actual four-positive
citation reconciliation, metric review/certification and investigator task proof
remain open. No source activation, dependency, CI, schema/grant, journal or policy
change is included. [Operator command](../runbooks/participation-acceptance.md).
