# V1-07: verified two-source readout

Date: 2026-11-25. Base main `998f798`, after the owner merged #221 with the
approved citation model/SQL. Contract: [source citations](../specs/SPEC-cross-source-citations.md).
Operator instructions: [offline readout](../runbooks/source-citations.md).

The readout consumes explicitly selected ingest runs from the two sources, checks
stored ledger facts against every admitted original through supported adapters,
then compares model and reference SQL in one restricted repeatable-read session.
Publication happens after the session closes. No Diavgeia projection, source
request, repair, migration, dependency, CI or metric-definition change is included.

## Focused evidence

- 84 new request/cohort/readout/failure cases pass on native PostgreSQL 17.11;
  all four new modules have 100% line and branch coverage.
- Complete, interrupted, quarantined, complete-empty and no-page captures are
  accounted separately. Unknown fields, no matches, wrong types and ambiguous
  latest content remain inspectable. No-page runs fabricate no retrieval date.
- Original hashes, normalized forms, record positions, source IDs, quarantine
  entries, supported processing identities and field pointers are checked. Row
  limits precede payload-size serialization/fetch; byte/object/output bounds fail
  closed. Even a no-match or all-after-cutoff result checks every admitted page.
- A real restricted reader produces the hand-computed fixture answer with one
  serving connection, no application-table change and unchanged original-file
  bytes/stat metadata. HTTP is explicitly forbidden in that integration test.
- Repeated publication and copied/relocated archives reproduce identical artifact
  bytes. Artifacts are content-addressed, 0600 in 0700 directories. The fixture
  confirms names, subjects, supplier details, amounts and physical archive paths
  are absent from the exported result.
- Python and reference SQL agree; altered definitions, parity failures, malformed
  private requests, ineffective reader permissions, publication failures and
  unexpected adapter/boundary errors cannot produce a success result.
- The shared canonical encoder accepts a stricter per-call limit while preserving
  its existing default bound and bytes. Existing exact-size export tests and U1
  characterization pins pass unchanged. No metric is reviewed or certified here.

Targeted mutation results, full `just check`/`just audit`, package inspection and
hosted exact-head status are recorded in the delivery PR; focused checks are not
a substitute for those gates. Detailed private harnesses/logs stay outside Git.

All 22 targeted rule mutations were rejected and exact source restoration was
verified. They cover request identity/size, explicit profile approval, ledger
count/byte preflights, checkpoints, page/normalized/quarantine parity, field
pointers, orphan rows, unknown-field labels, SQL identity/parity, partial coverage,
canonical/output bounds, cutoff labels and source attribution. The locked
dependency audit reports no known vulnerabilities. These are targeted checks,
not an exhaustive mutation score or real-source reconciliation.

## Pending product acceptance

All positive evidence above uses synthetic fixtures. The original four-positive
KIMDIS/32-target Diavgeia cohort is documented in the earlier pilot records, but
its actual private originals and SQL snapshot are not present here. It has not
been reconciled by this readout. The separate retained 77-record metric pack does
not replace it. V1-05 human metric review/certification and V1-08 dataset acceptance
remain open; no national coverage, live freshness or v1.0 release is claimed.
