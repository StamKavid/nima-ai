# Dataset-acceptance pure-policy checkpoint

Date: 2026-11-25. Owner approved A1–A3 of the
[spec](../specs/SPEC-dataset-acceptance.md), including implementation of the first
pure-policy slice. Delivered: [PR #223](https://github.com/StamKavid/nima-ai/pull/223),
main `a4eb99d`, with tested `d2d94db` reachable and an identical tree. The final
local gate passes all 4,463 tests at 95.03% overall coverage; audit, security and
installed-wheel proof pass. All three jobs passed on main in
[CI run 45639919348](https://github.com/StamKavid/nima-ai/actions/runs/45639919348).
The focused proof and corrections below describe that delivered slice.

## Implemented boundary

`contracts/acceptance.py` evaluates typed internal verification outcomes for
U1–U4 and exact citation inspection. It imports only stdlib. It neither reads
originals nor independently proves that a caller ran a check. Existing verified
readers retain that responsibility. There is no JSON intake, product adapter,
command, SQL write, journal extension, new dependency or activation.

Immutable input binds request/cohort hashes, cutoff, selected run profiles,
definition/SQL hashes, fixed check outcomes and bounded counts with named grains.
The supported profiles are the current four draft metrics and draft citation
model. Policy `nima.dataset-acceptance` version `1.0.0` has definition hash:

```text
f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06
```

Definitions and SQL hashes are explicitly pinned; an installed new version or
changed metric definition is not admitted automatically. A later semantic review
that changes a definition hash needs a deliberate acceptance-policy update too.
This does not change existing readouts or their immutable artifacts.

`ready`, `limited`, `blocked` and `not_assessed` describe data fitness for one
declared use, never metric certification. Known required failure outranks absent
proof. Missing required checks cannot pass; monetary eligibility is explicitly
not applicable to these record-count uses. Honest incomplete/quarantined captures
can support limited citation inspection while blocking numeric uses. Provider
empty/unresolved/incomparable statuses remain explicit; no unknown becomes zero.

## Focused proof

| Check | Observed result |
|---|---|
| Pure known answers and adversarial input cases | 134 passed |
| New policy line and branch coverage | 100%, 177 statements and 72 branches |
| Native PostgreSQL 17 integration | 15 passed using existing verified readers and restricted source roles |
| Targeted behavior mutations | 22 rejected; source restored byte-for-byte, SHA-256 checked |
| Existing request cardinality | Ten selected runs total, including both sides of a comparison/citation request |

The SQL tests use synthetic captures and invoke actual public preparation paths
before building policy facts through a **test-only bridge**. Complete, partial,
quarantined, empty and no-page captures, missing/type-unknown/mismatched targets,
and a real U1 fixture are exercised. Corrupt/missing raw bytes, altered normalized
SQL facts, incorrect record positions and omitted observations never reach a
successful policy evaluation. HTTP is forbidden in the two-source checks. SQL
table hashes and original file bytes/metadata remain unchanged by the checks.

Mutation checks alter required-check precedence, missing-proof handling, citation
partial scope, date relevance, page/selection/buyer partitions, quarantine,
zero-page completeness, membership, unsupported definitions, Boolean counters,
known-failure preservation, unresolved-citation disclosure and canonical order.
The final mutation run excludes the policy-definition hash pin, so rejected
changes must fail behavioral assertions. An initial surviving disclosure mutation
exposed a missing assertion; explicit tests for each citation limitation close it.

Review also corrected an overly broad draft run bound. The old implementation
fails the new eleven-run rejection test; the corrected policy matches all five
existing readout interfaces. The initial full gate was interrupted for this
correction and is not a claimed pass; the final gate is a fresh full run.
Later review reproduced another gap: omitted applicable counters could look like
zero. Each use now requires its diagnostic counters explicitly, with U3's
denominator/joint/partial relationships checked. Missing counts do not hide a
known partition failure. Regression tests fail against the earlier implementation;
the final full gate is restarted after this correction too.
The counter-corrected full run passed all 4,463 tests at 95.03% overall coverage,
then Bandit interpreted the metadata key `pass_reason: "ok"` as a password.
Renaming it `successful_check_reason` makes the meaning explicit; the unchanged
security and secret scans pass. No security rule or threshold is suppressed.
The candidate's final full-gate results remain on the PR.

## Remaining work

- The pure policy is delivered. The first consumer's
  [citation-acceptance contract](../specs/SPEC-citation-acceptance-readout.md) is a
  separate draft; existing metric definitions and artifact contracts are unchanged.
- Specify and build the verified acceptance readout adapter. A cached JSON
  artifact with a success flag must never substitute for reconstruction.
- Review an additive durable journal contract. V1-01's current Python and SQL
  contracts admit only the original supplier–buyer verification operation.
- Reconcile the owner's actual four-positive two-source cohort when its original
  archives and SQL inputs are available. Synthetic tests and the separate
  77-record metric cohort cannot close that acceptance.

V1-08, metric review/certification and real-data acceptance remain open. No source
request, government-IP waiver, production migration, schedule or release is implied.
