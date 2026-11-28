# Buyer-participation insight verification

Date: 2026-11-28. The implementation is delivered in #242 on main `0c03404`,
with the identical reviewed `6bb7e14` tree, for the approved
[I1–I3 contract](../specs/SPEC-buyer-participation-insight.md) and
[BI1–BI4 plan](../../tasks/plan.md).

## Result and scope

The library and `insights buyer-participation` command export one private,
content-named artifact over a freshly verified U3 report and embedded assessment.
The insight calls the existing acceptance consumer once; its existing two SQL
connections remain the only database reads. It adds no source requests, SQL
query, migration, dependency, metric definition or acceptance-policy promotion.

Current real metric definitions remain draft. Ready data returns
`review_required`; limited/empty data returns `insufficient_evidence`.
Both carry `answer: null`. Operational failures produce no new artifact.
The numerical `answered` composition is exercised with explicitly fictional
certified/compatible-profile fixtures only. Certified production admission is
unproven and requires the separate human review and policy evolution already
identified in the spec. This checkpoint does not complete R6.

## Focused and adversarial proof

96 focused cases pass with 100% line and branch coverage in both new modules.
Checkpoint A also passed 247 cases across the initial insight library and existing
U3 consumer/readout tests, strict types and package build. Later CLI and evidence
cases extend that checkpoint; these counts describe their actual separate runs.

- The hand-calculated fixture retains both leaders at 2/3 over three records,
  four overlapping participations and one joint record. Unknown D remains 1/4
  of buyer records and causes no answer under the actual limiting policy.
- Sparse parent evidence maps the chosen observation and its page; older,
  after-cutoff, wrong-buyer/source/version/normalizer and missing/duplicate witness
  cases fail rather than produce misleading citations. Denominator witnesses
  include every resolved record, preserving overlapping numerator membership.
- Hash/request/metric/profile/assessment disagreement, malformed JSON, duplicate
  keys, non-finite values, input/output limits and changed subjects fail closed.
  Output overflow does not truncate ties, evidence or interpretation limits.
- Restricted-role native tests verify one consumer call/two closed connections,
  exact retry bytes and mtime, 0700/0600 output, archive relocation, no SQL/archive
  changes and failure after removing an original. Owner-role access, forged
  certification, unsafe symlink/hardlink/permissions and empty capture are checked.
- CLI tests cover delegated arguments, environment-only DSN, help, actual status,
  refusal/input/operational/interruption exits and private-safe stdout/stderr.

24 targeted, reversible mutations were rejected by actual test failures. They
cover certification/refusal state, limitation preservation, definition/fitness
hashes, non-answer handling, share/overlap/tie/denominator mapping, selected evidence,
each witness constraint, closed errors, profile bindings, CLI exits and output
size. The original module bytes were restored and checked before further proof.

## Retained real data and installed wheel

Trusted private PostgreSQL dumps were checked against their prior recorded hashes,
restored into owned scratch databases and explicitly migrated where required.
The installed wheel was loaded under isolated Python with its package path
verified. HTTP was forbidden in both library and CLI proof processes.

| Preserved cohort | Fresh U3 fitness | Insight status | Numerical answer |
|---|---|---|---|
| 16 captured buyer/day publications | ready | review_required | null |
| 77 captured buyer/day publications | limited | insufficient_evidence | null |

Both prior parent reports and acceptance sidecars reproduce byte-for-byte. The
installed CLI and library, repeated export and relocated archive produce the
same insight bytes. A fresh native dump/second restore reproduces them too.
SQL table snapshots and original-file digests/mtimes remain equal. Removing a
page from the private relocated copy causes `insight_evidence`; an older output
remains unchanged and is not reused as a fresh pass. Owned scratch databases and
roles were removed. No government request occurred.

Original private evidence, requests, dumps, reports and proof scripts remain
outside Git. No company identity, national coverage, current source freshness,
spending, market share, misconduct or analyst certification is inferred.

## Delivery gates

Full local `just check`: 5,471 cases / 95.52%; dependency audit clean. All three
exact-head jobs in run 46125074963 passed for `6bb7e14`: 5,471 timed cases,
zero failures/errors/skips, 95.51% combined coverage and 100% line/branch in the
two new modules. Downloaded artifact 15255862406, digest
`d19de8e00091bea0d92f53c005e36d6b910b8656d5f048a3799caebdb795bbdd`,
and both XML contents were checked. An initial local disk-full attempt is retained;
after generated-file/environment cleanup the unchanged-code full rerun passed.
The existing local Prefect home-directory warning is recorded on the delivery PR;
no suppression was added. All five commits resolve to StamKavid as author/committer.
Owned scratch resources were removed and the test cluster stopped.

Owner merge and identical-tree reachability were verified. Metric certification,
positive two-source proof, other insight families and the remaining operations,
product and release gates stay open. The next
[U3 human review packet](u3-owner-review-packet.md) is prepared, unsigned.
