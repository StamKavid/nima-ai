# Real-data readout pilot: readiness and protocol

Assessment date: 2026-11-17. Current result: **blocked_inputs**. This implements
the readiness/result record for PV10 in the approved [plan](../../tasks/plan.md)
and [consumer scope](../../SPEC-market-analytics.md). It is not a completed
real-company audit or an observed analyst study. No capability-progress credit
follows from preparing this document.

The owner merged #119/#120 into main at `3cd4f77` and requested continuation.
All three exact-head jobs for #120 passed in run 44053781048. That completes V-D
review of the recommendation to retain packaged SQL and Prefect; dbt remains an
isolated experiment. The metric definition remains draft.

## Observed input status

Read-only inventory found zero `.body` objects and zero managed-run manifests in
the main project's `data`/`work` locations and the existing ingestion/archive
companion checkouts' `data`/`work` locations. `NIMA_DATABASE_URL` is not configured
in this workspace. This describes the
checked locations/environment, not every possible owner-managed host or archive.

The retained dbt capture is explicitly synthetic and cannot fill this gate. The
historical source feasibility sample described in `SPEC-source-ingestion.md`
does not supply the complete managed SQL/original cohort required here.

| Requirement | Observed status |
|---|---|
| Explicit real KIMDIS run selection and private request | Not available |
| Matching original bytes and complete projections | Not available for an admitted real cohort |
| Dedicated SELECT-only application configuration | Not configured |
| Source-supported reported supplier key | Not selected |
| Accountable analyst and task observation | Not performed |
| Real records manually audited / tasks observed | 0 / 0; no accuracy or speedup estimate |

No source request, archive repair, role/schema change, deployment or contact with
another person was performed for this assessment. No absence of contracts or
company activity is inferred from these missing inputs.

## Minimum input handoff

For existing captures, provide the local path to a private readout request and
the name of its privately configured database environment variable. Do not paste
credentials, source records or company/person details into an issue or PR. Use the
[runbook](../analytics/supplier-buyers.md) for exact request fields and read grants.
The existing CLI reads `NIMA_DATABASE_URL`; configuring an alternate private
environment name does not add a command-line connection-string option.

The request must bind 1–10 complete supported managed KIMDIS runs, their private
archive locations, one inclusive UTC cutoff and one eligible reported Greek tax
identifier. The whole selected cohort must fit the existing 500-observation,
32-page/object-location, 8 MiB/object, 64 MiB recovered-byte and 1 MiB result limits.
Do not select only matching records or silently truncate a larger run.

METLEN remains an optional owner-preferred label from earlier work. Its brand
does not identify a single legal entity or establish an AFM. This first market
pilot tests a **reported identifier grouping**; it needs no GEMI key or reviewed
legal-identity claim. If the owner chooses a company label, retain its evidentiary
basis and unresolved ambiguity privately. Never infer an identifier from name
similarity or substitute a group/subsidiary record without an explicit selection.

If no capture exists, a separate protected acquisition step is required. Specify
its source endpoint, exact date/buyer query, host and egress configuration,
request/page/time budgets, private archive/database destinations and stop rules
before execution. The KIMDIS collector filters by dates and optional buyer IDs;
the present contract supplies no supplier-name search. No Publicity scraping,
direct missing-original fetch or source-worker activation is implied by PV10.
Fixture-only egress checks do not establish deployed investigator IP protection.

### Bounded capture proposal if no existing inputs are available

This is preparation for a separate source-access decision, not an executable
authorization or a deployed worker. Use only the existing fixed KIMDIS contract
endpoint and a closed date window `2026-11-06` to `2026-11-06`, which was used in
the documented feasibility probe. Do not search GEMI or Publicity for this step.

- Discovery: one page, one attempt. Retain it as a discovery capture; an incomplete
  all-buyers run cannot be admitted to the readout. Select the smallest positive
  ASCII numeric buyer key present in that page, using numeric order and then
  original text as the tie-break; preserve the original key text. Stop if discovery
  fails, has quarantined records or supplies no eligible buyer key.
- Cohort: the same one-day query for that buyer, at most two pages and one attempt
  per page. Require complete pagination and no quarantine. If it exceeds bounds,
  fails or is empty, stop and record the result rather than selecting another buyer.
- Budget: at most three HTTP attempts overall, 20 requests/minute, 20-second HTTP
  inactivity timeout, 120-second cooperative budget per run and 8 MiB/body.
  The resulting readout must still satisfy every existing bound; never truncate it.
- Supplier: from the complete cohort, select an eligible reported Greek tax key
  with the most distinct latest-captured matching source IDs, breaking ties by
  exact key text. Record this deliberate convenience selection; it is not a
  representative company sample or a METLEN/legal-entity lookup. If no eligible
  supplier exists, record insufficient inputs and stop.

Before activation, resolve and record the approved execution host/egress route,
private destinations and database configuration. Do not assume this workspace has
a verified VPN/proxy. Use source-access approval under the consumer scope; no
purchase, provisioning, schedule or new privacy guarantee is implicit. A new
capture would establish inputs only: the human evidence/task gates still apply.

## Freeze and verify before timing

1. Record the selection rationale, exact request hash, run IDs/query windows,
   cutoff, reported supplier key, omissions and known limitations in a private
   0700 case directory with 0600 files. Keep all original evidence outside Git.
2. Run the existing offline command under the dedicated reader. Record its exit,
   fixed outcome and artifact hash. Freeze the metric definition/hash, source/
   normalizer/projection versions and snapshot identity from that artifact.
3. Require successful original-byte and full projection reconciliation for every
   selected page, including empty, nonmatching and after-cutoff records. Missing
   originals or inconsistent SQL block the pilot; they do not become zero counts.
4. Preserve the artifact unchanged and confirm identical replay. A genuinely empty,
   unresolved or no-participation result is valid command behavior, but is not a
   nonempty supplier–buyer demonstration. Record it without expanding the cohort
   after seeing results.

No new evaluator, library, table or CLI is introduced. Existing resource bounds
and five consumer outcomes remain those of the approved readout contract.

## Manual evidence audit

For a deliberately small first case, aim for at most ten counted source IDs so
each contribution can be inspected. Larger complete runs remain valid within
the existing hard limits; record any manual-review sampling limitation explicitly.
Do not drop records from the command to make auditing easier.

Freeze the audit selection rule before inspecting expected/observed values.
Inspect all counted IDs when feasible, plus a declared sample of noncontributing
and unresolved IDs. Include revisions removing the supplier, ties, duplicate
matching ordinals, cancellations, missing buyer keys and unassessed countries
where actually present. Record absent edge-case categories; do not insert fixtures
or silently choose a different cohort. Reuse of one ID across categories is explicit.

For each reviewed source ID, retain every relevant observation/revision and record:

| Check | Private evidence and expected comparison |
|---|---|
| Original locator | Raw SHA-256, `/content/<index>`, run/page/index, source/version key |
| Reported grouping | Original country/tax text, GR/EL and ASCII-trimming rules, matching ordinals |
| Revision selection | Latest captured observation before cutoff; contrary/earlier/tied evidence |
| Buyer | Original organization key/Greek label or explicit unassigned bucket |
| Count grain | One eligible contribution per source ID; ordinals/re-observations do not multiply it |
| Cancellation and values | True/false/unknown; exact source money/currency retained without spending allocation |
| Time | Source date text distinguished from recorded UTC observation time |
| Attribution | Reviewer, expected/observed value, pass/fail/unknown/not-applicable and reason |

Reconcile buyer record counts plus unassigned IDs to the full reported total.
Record the checked numerator and eligible denominator, the manually unreviewed
remainder and all discrepancies. Hash agreement establishes consistency with
captured bytes, not publisher truth. A critical grouping, pointer, revision, count
or amount/date discrepancy blocks a verified-cohort claim until resolved in a
separate recorded assessment; never edit history to force success.

## Observe one analyst task

The owner may be the first consenting analyst. Do not contact anyone automatically.
Use the same frozen cohort, key, cutoff, definitions and original files for both
conditions. The task is to identify covered buyers for the selected reported
supplier, their distinct publication counts and a citation supporting each answer,
while explaining revisions, unassigned records and unresolved cases.

Record a manual condition using originals and an assisted condition using the
readout, then adjudicate both against the evidence audit. Separate initial setup,
active task time, interruptions and verification time. Record completion, wrong
or missing answers, citation errors, missing information, interpretation mistakes
and whether the analyst can explain the result/coverage. Disclose self-review,
builder familiarity, task order and learning effects. A single paired observation
does not estimate performance for other users or the Greek market.

If an agreed session timebox expires, record the condition as unfinished; do not
convert a timeout into a measured speedup. Calculate a time difference only for
comparable completed conditions, alongside correctness and verification effort.
No target improvement is assumed in advance.

## Assessment and publication

Keep the request, original bytes, artifacts, timings, audit matrix and analyst
notes private. Publish only an owner-reviewed redacted aggregate result. Hashes
are not anonymization. Report source/window coverage, checked denominators,
unknowns, discrepancies and whether the task saved work or failed to do so.

The current `blocked_inputs` label belongs to this assessment, not the CLI's
outcome vocabulary. Once inputs exist, readiness, evidence-audit completion and
task observation remain separate milestones. Do not mark PV10 complete merely
because the command exits 0 or a company has no matching records. A real audited
cohort plus an actually observed task is required for the product-usefulness claim.

Backup/restore, historical correction sweeps, normalizer-version replay, refresh
recovery, broader database roles and deployed monitoring retain their separate
reliability scopes. This pilot does not certify those capabilities or activate AI.
