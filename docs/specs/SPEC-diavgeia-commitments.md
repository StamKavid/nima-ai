# Spec: Diavgeia commitment decisions (Β.1.3), second pilot

Module ID: `diavgeia-commitments`. Status: **draft for owner review; no code, no request.** Builds on
[SPEC-diavgeia-pilot](SPEC-diavgeia-pilot.md) and its [run record](../verification/diavgeia-pilot-run.md), the
[acceptance dossier](../sources/diavgeia-acceptance.md) and the [source boundary](SPEC-source-boundaries.md).
Release gate served: R1 and the join work of V1-07.

## Objective

Find out, with evidence, whether the Diavgeia decision type that KIMDIS's `diavgeiaADA` points at is
Β.1.3 (commitment, "ανάληψη υποχρέωσης"), and if so collect a small, bounded set of Β.1.3 decisions through
the existing engine so that the KIMDIS citations can resolve. The first pilot found that nothing
resolves for award decisions (Δ.2.2): 0 of 4 cited ADAs, 0 of 11 related ADAs. This pilot tests the one
explanation we have, and it is only an inference from names until a real record confirms it.

Success looks like: a recorded answer to "what type are the cited ADAs", then (only if the answer is Β.1.3)
one bounded real run that reconstructs from its archive, with counts of how many citations resolve. It
creates no identity link, no join and no metric.

## What is known and not known

| Claim | Status |
|---|---|
| KIMDIS `diavgeiaADA` points at a commitment decision | **Unverified.** From earlier project work, not re-read in KIMDIS documentation ([dossier](../sources/diavgeia-acceptance.md)) |
| Δ.2.2 `textRelatedADA` points at the related *expenditure approval*, Δ.2.1 at the related *commitment* | Documented. So the 11 related ADAs on collected awards are probably approvals (Β.2.1), not commitments: unverified |
| Β.1.3 special fields | Documented list only (`financialYear`, `budgettype`, `partialead`, `kae`, `entryNumber`, `recalledExpenseDecision`, `amountWithVAT`, `amountWithKae`, `relatedPartialADA`). **No real Β.1.3 response has been seen.** The first Δ.2.2 run quarantined 10 of 262 on shapes the documentation did not show, so every shape below is provisional |
| 4 KIMDIS records cite an ADA, none shared | Measured 2026-11-20; sparse, so even a perfect resolution gives at most 4 links |

## Behaviour

### Step C0: look before collecting

Fetch only what is already cited: the 4 KIMDIS-cited ADAs and the 11 related ADAs, 15 decisions at most,
one request each, read only for the decision type and organisation. The result is a table of counts by
type, nothing else. This decides whether a Β.1.3 pilot is worth building: if the cited ADAs are not Β.1.3,
this spec stops here and records what they are.

How the lookup is made is an open question (decision C1): the engine pages a search, while a single
decision is a different request. The documentation read so far does not say whether the search can select
by ADA, and I will not guess.

### Step C1 to C3: collect Β.1.3 (only if C0 says yes)

Same shape as the first pilot: one organisation, one issue-date window of at most 30 days, `status=all`,
page size 100, type Β.1.3, archive before parsing, stop on any error, exact-byte ADA identity,
`source_id` `diavgeia:<ADA>`, statuses kept as observed, no Unicode folding, fixed error reasons.

### Normalised record (closed set, personal data excluded)

Everything the first pilot keeps (`ada`, `decision_type`, `organization_id`, `issue_timestamp_ms`,
`submission_timestamp_ms`, `version_id`, `status`, `corrected_version_id`, `private_data`), plus the
Β.1.3 fields below, every one optional because the documentation says none is guaranteed and absence is
data:

- `related_partial_ada`, a typed reference, never a merge.
- `financial_year`, `budget_type`, `entry_number`, `partial_ada` (as published, no coercion).
- `amount_with_vat` as exact decimal text. Unknown stays unknown, never zero.
- `kae_lines`: a list of `{kae, amount_with_vat}` for budget lines, exact decimals, never summed with
  the headline amount (a line total that differs from the headline is reported by the data, not repaired).
- **Suppliers (`sponsorAFMName`): a count only.** No tax number, no name (decision C3).

### Provenance and attribution

As the first pilot: endpoint, documentation URL, "CC BY 4.0 (Law 3448/2006)", and "Source: Diavgeia
(diavgeia.gov.gr), CC BY 4.0; data retrieved on `<date>`".

### Not collected

PDFs and attachments, version logs, other types, other organisations. Each keeps its trigger in the first
spec.

## Boundaries

**Always:** archive before parsing; one organisation and window per run; fixed error reasons; synthetic
fixtures only; stop on any non-success status; a count of decisions in a window never claims coverage.

**Ask first:** C0 requests (15 at most), the first Β.1.3 run (organisation, window, date), any second
organisation or type, any PDF fetch.

**Never:** a request before the matching code is merged and the request is approved; supplier tax numbers
or names in a normalised record; fuzzy ADA matching; treating a citation as an identity merge; counting a
commitment, an approval, an award and a payment as one economic event; real decisions in Git.

## Slices

| Slice | Content | Done when |
|---|---|---|
| C0 | Owner-approved lookup of the 15 already-cited ADAs; counts by type recorded in `docs/verification/` | Recorded; decides whether C1 to C3 happen |
| C1 | Synthetic samples and the Β.1.3 adapter with registry entry; **no network** | Shared parser and engine conformance pass; 100% line and branch; every rule break caught |
| C2 | `nima ingest` for the commitment type, then one owner-approved run with the archive preserved | Run reconstructs from the archive; counts recorded, no decision content |
| C3 | Overlap: how many of the 4 cited ADAs and 11 related ADAs resolve to a collected Β.1.3; umbrella check (one ADA cited by many) | Counts recorded; V1-07 join spec can use them |

Each slice is one review-ready PR with the repository gates. C0 and C2 contain the owner's live steps.

## Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| C1 | How C0 looks up 15 ADAs | Add a small single-decision request beside the search (its URL is the adapter's own declared endpoint, so the allowlist rule holds), written test-first like the rest. The alternative, collecting a whole window to find them, costs hundreds of requests for a yes/no answer |
| C2 | Organisation and window for the C2 run | Organisation `6` and the same window as the first pilot (2026-10-08 to 2026-11-06), so the 262 awards and the new commitments are comparable. A second body is a separate approval |
| C3 | Supplier fields | Count only, as in the first pilot. Supplier tax number is what a join would need, but the meaning of the `afmType` codes (`EL`, `EUP`) is still unverified, so a legal entity cannot be told from a person. Revisit after a written policy, not before |
| C4 | Adapter shape | A separate adapter (`diavgeia-commitment`) reusing the first adapter's helpers, so the Δ.2.2 connector and normaliser versions and its 96 tests stay untouched. A shared adapter with a type parameter would change a delivered contract |
| C5 | Stop rule | If C0 shows the cited ADAs are not Β.1.3, stop and record the types found; do not build C1 to C3 on a guess |

## Deferred, with triggers

| Item | Trigger |
|---|---|
| Expenditure approvals (Β.2.1) | C0 shows the related ADAs on awards are approvals and the owner wants the award-to-approval link |
| Payments (Β.2.2) | The owner wants the payment stage; KIMDIS `paymentRefNo` is a KIMDIS key, not Diavgeia |
| Supplier fields | A written policy for natural versus legal persons |
| Source-aware `nima archive replay` | Its own small design, recorded in the first run record |
