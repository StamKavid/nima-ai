# Same-query observed-change pilot — 2026-11-27

**Verdict:** two complete, independently observed captures now exercise the real
U4 comparison. It returns `observed_changes` with data fitness `ready`: **nine
source-content changes, seven unchanged, none added or missing**. All nine
differences are array ordering under the diagnostic below; no business or legal
event is established. All four metric definitions remain **draft**.

Baseline: main `7e0586e` after owner-merged #237, identical reviewed `213e7b5`
tree. All three PR jobs passed in run 46008277708, with 5,375 timed cases,
zero failures/errors/skips and 95.49% hosted coverage; downloaded artifact verified.
This follows the [supported company-key checkpoint](metlen-buyer-day-capture.md).
No application, schema, metric, normalizer, dependency, test or CI code changed.

## Capture and time scope

The retained inventory screened 31 manifest paths representing seven distinct
captures and 24 copies; it supplied no complete supported same-query pair.
The owner then explicitly approved one later capture of the exact earlier
buyer/day query: **2026-07-06**, one buyer, two pages/HTTP requests maximum,
one attempt per page and 120 seconds. This is a convenience cohort, not a
representative company or market sample.

Collection used **one request**, returning one complete page with **16 publications
and zero quarantine**. It received no database credentials. The explicit proxy,
TLS/hostname verification, no-direct-fallback and no-redirect guards
were retained. This is not a verified VPN, isolated worker or anonymity claim.
Collection stopped on completion; the unused slot does not fund another capture.

| Clock, UTC | Earlier capture | Later capture |
|---|---|---|
| Stored observation | 2026-11-27 13:19:59 | 2026-11-27 14:53:16 |
| Response HTTP Date | 2026-11-03 16:21:55 | 2026-11-27 14:53:18 |

The actual stored timestamps and response headers are preserved, not adjusted.
The earlier HTTP Date discrepancy remains unexplained. A later response and
strictly ordered observations do not establish current publisher freshness or
when a source-side change occurred. Offline reconstruction times are separate.

Source attribution: KIMDIS open-data API, [official documentation](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help);
the recorded contract declares [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Only aggregate verification findings enter Git; originals remain private.

## What changed, and what did not

U4 compares source-content hashes and retains array order by design. Independent
checking of all **32 record occurrences**, both original page hashes, source-ID
sets, run roles and six acceptance counters agrees with the actual readout:

| Measured grain | Result |
|---|---|
| Complete captures / original pages | Two / two |
| Observations / reported page records | 32 / 32 |
| Distinct comparison-eligible source records | 16 |
| Ambiguous / quarantined records | Zero / zero |
| Added / changed / missing / unchanged | 0 / 9 / 0 / 7 |

Every changed record differs in CPV-list ordering; two also differ in supplier-list
ordering. A separate recursive multiset diagnostic ignores array order while
retaining duplicates, scalar types/precision and object structure. All nine
differences disappear under that diagnostic; no remaining value or membership
difference was found. It does not change U4's definition or justify changing
immutable source hashes. Array order is still preserved in original evidence.

The later U1–U3 readouts and acceptance consumers also ran. All are `ready` for
their declared uses, with the same analytical payloads as the earlier capture:

- U1: one publication matching the reported METLEN key, one buyer.
- U2: whole buyer/day cohort, 32 CPV/month cells and 74 memberships.
- U3: whole cohort, 16 resolved/zero unresolved records, 16 supplier keys,
  six joint records, 24 participations and top share 4/16.

Cross-capture analytical equality excludes exactly `observation_ids` and
`version_hashes`; their expected differences remain in full provenance. It does
not mean full reports from different captures are byte-identical. A further
independent check reconciled **160 later-source fields**, exact Decimal values,
memberships and denominators with zero unexplained discrepancies. Neither joint
participations nor overlapping CPV memberships are extra contracts or spending.

## SQL, retry and restore proof

Restored the trusted earlier native dump into an owned PostgreSQL 17 scratch
database, verified schema 15 and appended the actual later receipt/observations.
Every earlier SQL row was preserved. Existing readouts and acceptance used a
restricted reader; all SQL rows stayed unchanged during those operations. Exact
retries preserved report and sidecar bytes/mtimes. No U4 history adapter was added.

A new trusted native dump and relocated earlier/later archives reproduced **all
four reports and all four acceptance sidecars byte for byte** in a second owned
database. Scratch databases and roles were removed, and the owned validation
instance stopped. This proves same-host reproduction, not off-host operations.
Private scripts import no Nima code for independent source reconciliation; this
is automated builder verification, not independent human review.

## Checkpoint and next action

The automated real U4 comparison checkpoint is complete. The older retained
incomparable pair remains a separate negative control; no historical evidence
was overwritten. Metric certification, missing real-case coverage, human task
usefulness, current freshness and positive two-source acceptance remain open.

Offline source preparation recovered four explicit Diavgeia reference candidates
from 23 hash-verified pages of an older 1,118-record KIMDIS capture. The loose
retained Diavgeia probe matches none. These are candidate inputs, not joined
source facts or positive acceptance; no Diavgeia request was made here.

Next: human definition/source review and a separately scoped positive two-source
pilot. Do not add change alerts that label these nine content differences as
amendments or economic events. Keep further history adapters and infrastructure
behind the remaining product evidence. Release gates and package `0.0.1` stay
unchanged; no certification, schedule or release is activated.

Private handoff: `/workspace/work/nima-change-pilot-20261127` retains actual
authorization/attempt records, original receipts, requests, four reports and
sidecars, native dump/restore inputs, independent checkers, diagnostics and verdict.
Local retention is not an off-host backup guarantee.
