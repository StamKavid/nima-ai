# Supported METLEN buyer/day capture — 2026-11-27

**Verdict:** the existing supported collection, SQL and analytics paths work for
one declared buyer/day containing a reported METLEN supplier key. U1, U2 and U3
return `ready` for their declared uses. This is automated builder verification;
human review, metric certification, market coverage and analyst usefulness remain
open. No application, schema, dependency, metric definition or CI code changed.

Baseline: main `57ffdf9` after owner-merged #236, identical reviewed `3733d76`
tree; all three PR jobs passed in run 45971023612. This follows the
[retained-cohort verdict](retained-real-cohort.md) without altering its originals
or treating its historical unsupported supplier-filter query as a supported one.

Follow-up: #237 was owner-merged at `7e0586e` with the identical reviewed tree.
A separately approved [later same-query capture](same-query-change-pilot.md)
subsequently supplies U4 comparison proof; the U4 input boundary below describes
this earlier checkpoint.

## Acquisition and clocks

The owner explicitly approved the prepared managed-cloud proxy route, capped at
two requests. The existing collector used **one request**, returning HTTP 200 and
one complete page: **16 unique publications, zero quarantine**, one matching the
selected reported company key and 15 other publications. All original buyer/day
fields match the declared one-buyer query for **2026-07-06**. This convenience
selection came from the earlier archive; it is not a representative market sample.

The request used an explicit proxy, normal certificate/hostname verification,
no redirects or direct fallback, a persistent attempt guard and bounded pages,
body size and duration. Collection received no application database credentials.
These application checks do not attest kernel isolation, a verified VPN/worker,
upstream forwarding behavior or anonymity. Collection stopped on completion;
the second request slot remains unused and is not a new source budget.

Actual receipt observation was **2026-11-27 13:19:59 UTC**. The response's HTTP
`Date` was **2026-11-03 16:21:55 UTC**, earlier than observation. Both values are
preserved. Their discrepancy's cause and current publisher/source freshness are
**not established**; neither successful collection nor `ready` resolves that gap.
The July query date, November observation and later offline processing are
separate clocks.

Source attribution: KIMDIS open-data API, [official documentation](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help);
the recorded source contract declares [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
This note reports derived aggregate checks; originals remain private.

## Actual analytics and independent reconciliation

Frozen originals were copied into an owned PostgreSQL 17 scratch reconstruction
at schema 15, retaining the actual receipt observation time. New processing times
are reconstruction times. Existing readouts and acceptance consumers ran under a
restricted reader; there was no operational migration or source request in this
offline validation.

| Use | Fitness | Scope and result |
|---|---|---|
| U1 supplier/buyer participation | ready | One publication matching the reported company key, one buyer, within the 16-publication capture |
| U2 reported CPV/month | ready | Whole buyer/day cohort: 32 cells, 74 memberships, 16 publications |
| U3 buyer participation concentration | ready | Whole cohort: 16 resolved/zero unresolved publications, 16 supplier keys, six joint records, 24 participations; top share 4/16 |
| U4 observed change | not run | No independent complete same-query pair; no numeric-change claim |

U1's diagnostic cohort count is 16; its selected supplier result is one. U2 and
U3 describe the whole buyer/day cohort, not METLEN-only categories or its market
share. Overlapping CPV memberships and joint participations are not additional
contracts. No contract-value allocation, paid-spending or revenue total follows.
All four metric definitions remain **draft**; `ready` is scoped data fitness.

An independent checker importing no Nima code reconciled all 16 originals with
**160 field comparisons**, Decimal amounts, source/supplier membership sets,
CPV/month cells and exact denominators. It found **zero unexplained discrepancies**.
The selected company publication already occurs among the nine earlier archived
company publications; its normalized fields are unchanged. This is another
observation of an overlapping publication, not a tenth distinct company record or
a comparable two-capture U4 cohort.

Readouts repeated with identical bytes/mtimes and no source/processing SQL changes.
The separate legacy U1 journal passed byte-equivalence, retry and SELECT-only
inspection; only its journal rows were added in the disposable database. A trusted
native dump plus relocated archive restored into a second owned database and
reproduced **all three reports byte for byte**. This is same-host restore proof,
not operational off-host recovery. Scratch databases and roles were removed and
the owned validation PostgreSQL instance was stopped.

## Checkpoint and next action

The supported company-key checkpoint is complete as an automated evidence test.
It establishes a usable narrow path without new infrastructure. It does not
establish legal identity, national coverage, current freshness, a Diavgeia join,
human metric review, task speedup or release acceptance. No Diavgeia/GEMI request
or join was performed. Prior answer exposure and builder familiarity remain
disclosed limitations for subsequent human tasks.

Next, review metric definitions and the actual scoped evidence with a human;
prepare missing positive two-source and complete same-query cases under separate
explicit acquisition scope. Keep other history adapters and new infrastructure
behind that product-evidence work. Release gates and package `0.0.1` are unchanged.

Private reproducibility pack: `/workspace/work/nima-metlen-capture-20261127`.
It preserves the original archive/receipts, route authorization and attempt ledger,
SQL reconstruction and independent checkers, private requests/readouts/sidecars,
trusted native dump, relocated restore inputs, verdict and hash inventory. It is
outside Git; its local persistence is not an off-host backup guarantee.
