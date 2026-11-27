# Citation pilot: real HTTP 503 and limited inspection — 2026-11-27

**Verdict:** acquisition stopped after its first request returned HTTP 503.
Positive two-source reconciliation remains open. The existing readout, per-use
acceptance and journal successfully preserve a **limited** citation inspection,
with partial-capture, unresolved-citation and cancellation warnings. No application,
schema, policy, dependency, test or CI code changed.

Baseline: main `d1188e8` after owner-merged #238, identical reviewed `6d98c67`
tree. All three jobs passed in run 46021474302: 5,375 timed cases, zero
failures/errors/skips, 95.49% hosted coverage; downloaded artifact verified.

## Actual acquisition and preserved inputs

The owner approved three exact Diavgeia commitment windows through the selected
managed-cloud proxy, one page/attempt each, no direct fallback or redirects and
a 120-second budget per query. The **first request returned HTTP 503**; its
complete 2,382-byte response was archived before interpretation. The whole pilot
stopped as agreed: **one request used, two queries not sent, no retry**. The
allowance is closed. This establishes neither a publisher-wide outage nor whether
the response originated at the publisher or an intermediary.

No database/API credentials were supplied to collection. The route has normal
TLS/hostname verification but is not a verified VPN, isolated worker or anonymity
attestation. No fresh KIMDIS request was needed: its complete retained run has
1,118 distinct publication IDs, 23 data pages and 24 preserved attempt bodies,
including one historical 429 that was not retried. Current normalization has
zero quarantine. The citation reader's existing 5,000-observation/500-page/8 MiB
limits admitted this actual reconstructed cohort; no limit was raised.

KIMDIS data observations remain **2026-11-08**. The failed Diavgeia HTTP attempt
was recorded at **2026-11-27 18:51:29 UTC**; it produced no admitted decision
page. Its source totals and data-observation span remain unknown, with no
decision-retrieval attribution. Zero admitted decisions is not an empty publisher.
New offline processing times are separate from these recorded source clocks.

## Observed readout and policy result

| Measurement | Actual result |
|---|---|
| KIMDIS publications / admitted data pages | 1,118 / 23 |
| Explicit citation edges / resolved / unresolved | 4 / 0 / 4 |
| Reported cancelled source records | 4; none is among the four citing records |
| Provider / coverage | `observed_citations` / `partial_capture` |
| Per-use fitness | `limited` |
| Limitations | `cancelled_records`, `partial_capture`, `unresolved_citations` |

The reviewed citations policy deliberately permits limited inspection of reported
references from a partial capture. The completeness check is explicitly failed;
the data is not `ready` for confirmed targets. Missing targets mean absent from
this selected cohort, not absent from Diavgeia. Cancellation flags and citation
edges have different grains. No identity, payment, legal-validity or misconduct
claim follows, and contract/commitment values are not added.

Independent reconciliation importing no Nima code verified **1,118 original
content digests**, **1,118 explicit-reference fields**, all edge/membership/counter
sets, 23 admitted data-page hashes and all **25 attempt-body hashes**. It found
zero unexplained discrepancies. The HTTP 503 body is preserved as failure evidence;
it is not treated as a decision or included among verified data pages.

## SQL, history and restore

Owned PostgreSQL 17 reconstruction preserved actual receipt times and schema 15.
The existing projector processed 1,118 KIMDIS events in supported bounded batches.
Restricted readouts/acceptance left SQL unchanged and reproduced report/sidecar
bytes and mtimes on retry. Only the dedicated journal rows were added during
recording; source and processing rows stayed exact.

The real journal outcome is **`assessed` / `limited`**, not refusal, certification
or a positive target match. Completed-ID reuse and SELECT-only inspection preserve
the original result/body. A trusted native dump and relocated archives reproduced
the report, sidecar and journal record/body exactly in a second owned database.
Scratch databases/roles were removed and the owned validation instance stopped.
This is same-host proof, not operational off-host recovery or analyst validation.

## Boundary and next action

The real source-failure/inspection/history checkpoint is complete. The positive
pair, human review, certification, daily operation and current publisher freshness
remain open. Arrange a separately scoped future acquisition attempt; this failure
does not justify a new service, library, source-budget extension or deployment.
All metrics/models remain draft and the package stays `0.0.1`.

Sources: KIMDIS and Diavgeia. Recorded contracts cite [KIMDIS documentation](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help)
and [Diavgeia documentation](https://diavgeia.gov.gr/api/help), with CC BY 4.0 reuse
attribution. Originals, names and identifiers remain outside Git in
`/workspace/work/nima-citation-pilot-20261127`: actual authorization/attempts,
archives, private requests/report/sidecar/history, native dump, independent
checker and verdict. Local persistence is not an off-host backup guarantee.
