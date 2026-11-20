# Spec: semantic model, party tier and metric catalogue (V1-05)

Module ID: `semantic-model`. Status: **approved by the owner on 2026-11-20, with decisions D1-D5 recorded as recommended
("do recommended for 1-5"). S2 is next; its plan is in [tasks/plan.md](../../tasks/plan.md).** Backlog card: [V1-05](../roadmap/agent-backlog.md). Release gates served:
R5 (shared semantics, at least four internally certified metrics) and the acceptance
scenarios U1-U4 of the [v1.0 release contract](SPEC-release-v1.0.md). It extends, and does
not replace, the [first shared definition](SPEC-semantic-layer.md) (`semantic-layer`),
the [identity policy](SPEC-entity-resolution.md) and the existing
[participation semantics](../semantics/participation.md).

## Objective

One person asking a company/market question must get the same number whether it comes from
the CLI, a later API or a later view: the same record selection, the same time basis, the
same party keys and the same counting rule, each named, versioned and traceable to original
bytes. Today only one metric exists (`captured_contract_record_count.v1`, U1, status
`draft`). V1-05 defines the shared model and three more metric families (U2-U4), so that R5
can be met, and it does so without a new warehouse, ontology or service.

Success looks like: four reviewed metric definitions in one catalogue; every metric
reproducible by a pure Python provider and a reference SQL query that agree on a
hand-calculated fixture; unknowns reported as unknowns; no number that silently depends on a
default.

## Assumptions (correct me before I proceed)

1. One trusted local operator; selected explicit run cohorts; KIMDIS is the only live source.
   Diavgeia (V1-06) and GEMI enrichment are consumers of this model later, not part of it.
2. The normalized KIMDIS record carries only two dates, `source_submitted_at` and
   `source_updated_at`, both as source text. No contract-signing, start/end or payment date is
   available, so no metric may claim an effective-date basis.
3. The format of those date strings has not been measured on real data. The time slice (S2)
   measures it first and specifies the parser from the result, not from a guess.
4. CPV reaches the model through the existing market-metadata extraction (reported code,
   `taxonomy_validation: not_checked`) and the explicitly selected CPV 2008 reference
   (OP-TED SDK 1.15.1). It is not a field of the normalized record.
5. Counting is **count-based**. No monetary aggregation, no allocation of a contract value to
   suppliers, in any metric here.
6. Reported-identifier grouping stays distinct from reviewed identity. No automatic identity
   link is created. Reviewed decisions are consumed only through an explicit snapshot.
7. No schema migration is needed for the first three slices; derived definitions run over the
   existing record, observation and reference tables. A migration is an "ask first" item.

## Model

### M1. Record selection ("current as observed")

The existing rule generalizes, unchanged in meaning: for an explicit run cohort and an inclusive
UTC cutoff, select the **latest observed version per source ID** before any filter is applied;
identical versions collapse; tied different versions mark the source ID
`ambiguous_revision` and exclude it from counts while keeping the evidence. "Latest" never
means source-current or legally effective. This becomes one named selection function that
every metric calls, instead of each metric restating it.

### M2. Time model

| Concept | Rule |
|---|---|
| Observed time | Recorded UTC capture time of a page; the only ordering key |
| Reported submission date | `source_submitted_at` parsed to a calendar date; the text is always retained |
| Reported update date | `source_updated_at`, same treatment; never used as an ordering key |
| Parse outcome | `parsed`, `absent`, `unparseable` (fixed reasons); the last two are the **unknown period** |
| Period | Calendar month of the reported submission date, in Europe/Athens civil time (decision D2) |
| Not provided | Effective, signing, award or payment dates: unsupported, stay unknown, never inferred |

A record whose date does not parse is counted in an explicit "unknown period" bucket, never
dropped and never assigned to the observation time.

### M3. Party tier

Three tiers, each rebuildable from the one below and never merged silently:

1. **Party occurrence**: version, role (buyer or supplier) and ordinal, as stored today.
2. **Reported party key**: `(country, tax_id)` for suppliers and the existing
   `kimdis.buyer-key` namespace for buyers. Eligible when the rules of
   [participation semantics](../semantics/participation.md) hold (GR/EL country, nine ASCII
   digits, not all zero). Names and addresses are labels, never keys. The key is a grouping
   key, not a legal entity.
3. **Reviewed entity**: only through accepted decisions of the existing review store, supplied
   as an explicit snapshot with its own hash. Default basis is `reported_identifier`.

Conflict and placeholder rules (new, all disclosed, none hidden):

- Same tax text with different countries stays two keys; same key with different names is not a
  conflict.
- Placeholder or repeated-digit tax IDs beyond the existing all-zero rule are **disclosed
  counts**, not silently excluded (decision D4).
- A key that appears as both buyer and supplier stays two roles; no cross-role merge.
- Reviewed `reject` and `revoke` decisions can only remove a link from a reviewed-basis result;
  they never edit a reported-identifier group.

### M4. Contract lifecycle references

Only explicit source references form edges: `award` (`auctionRefNo`), `previous_record`
(`prevReferenceNo`), `payment_order` (`paymentRefNo`) and, after V1-06, `commitment_decision`
(`diavgeiaADA`). Rules:

- An edge is *resolved* only if its target source ID is observed in the cohort; otherwise it is
  `reference_unresolved`, kept and counted, not guessed.
- A reference records that a record **cites** another; it does not say the cited record is
  superseded. Counts stay publication counts; an amendment with a new ID remains a separate
  publication (decision D5: no second basis now).
- A reference shared by many records (an umbrella) is flagged, never turned into a chain
  (threshold measured first, decision D5).
- Stages stay distinct: commitment, award, contract and payment are never summed.

## Metric catalogue

Every definition has an ID, a version, a grain, an inputs list, eligibility and exclusion
rules, a denominator where one exists, disclosed unknown buckets, an evidence mapping, a
status (`draft`, `reviewed`, `certified`) and a canonical definition hash (as for `.v1` today).
Behaviour changes need a new version. Status meanings follow the
[existing contract](SPEC-semantic-layer.md): `certified` needs a recorded real-data
reconciliation and sign-off and is **not** granted by this spec.

| Scenario | Metric ID | Grain and rule |
|---|---|---|
| U1 | `captured_contract_record_count.v1` (exists) | Distinct selected records per (supplier key, buyer key); unchanged, moved into the catalogue |
| U2 | `captured_record_count_by_cpv_period.v1` | Distinct selected records per (CPV main base code, month of reported submission date); a record with several CPVs appears under each, with the overlap disclosed; records without a CPV go to `unclassified`; unparseable dates to `unknown_period`; CPV release and language are explicit inputs |
| U3 | `buyer_supplier_record_concentration.v1` | For one buyer: records with at least one eligible supplier (denominator), per-supplier record counts, top-supplier share, **unresolved share** (records with unknown or ineligible suppliers over all the buyer's selected records) |
| U4 | `observed_change_between_captures.v1` | Two captures, each a complete run set of the same declared query: `added`, `changed` (same source ID, different version), `missing_from_later_capture`, `unchanged`; abstains with `incomparable` unless both are complete and the query payloads are equal |

U3 uses **record-participation counts**: a record with two eligible suppliers counts once for
each, so supplier counts overlap and must not be summed to the denominator; the output states
this. It is not market share, not a monetary share and not a concentration index of spend.
`missing_from_later_capture` is never deletion, withdrawal or a legal event.

## Hand-calculated examples (synthetic)

**U2.** R1: CPV A, submitted 2026-03-10. R2: CPVs A and B, 2026-03-20. R3: no CPV, 2026-03-25.
R4: CPV B, date text unparseable. Expected: March: A=2, B=1, unclassified=1, distinct records=3
(the CPV rows overlap because R2 is under A and B); unknown period: B=1.

**U3.** One buyer, five selected records. R1: S1. R2: S1 and S2. R3: S2. R4: supplier list
unknown. R5: suppliers present, none eligible. Expected: denominator 3 (R1-R3); S1=2, S2=2
(they overlap through R2 and sum to 4); top-supplier share 2/3 of the denominator; unresolved
share 2/5 of all selected records.

**U4.** Capture A: X v1, Y v1, Z v1. Capture B (same query, both complete): X v1, Y v2, W v1.
Expected: unchanged 1 (X), changed 1 (Y), added 1 (W), missing_from_later_capture 1 (Z).
With capture B incomplete: result `incomparable`, no category counts.

Each is extended with revision (A-B-A), tie, cutoff and duplicate-ordinal cases in the tests.

## Commands

Local Windows machines cannot run the archive code; use the Linux container for the full suite.

```sh
just check            # lint, strict mypy, tests with coverage, build, security
just audit            # dependency audit
uv run --frozen pytest tests/test_semantics.py tests/test_semantic_model.py
```

## Project structure

```
src/nima/semantics/selection.py   M1 shared selection, pure
src/nima/semantics/timemodel.py   M2 typed dates and periods, pure
src/nima/semantics/parties.py     M3 party keys, conflicts, basis, pure
src/nima/semantics/lifecycle.py   M4 reference edges, pure
src/nima/semantics/catalogue.py   metric definitions, IDs, hashes, status
src/nima/semantics/*.sql          one packaged reference query per metric
docs/semantics/metric-catalogue.md  glossary and per-metric definition
tests/test_semantic_model.py      hand-calculated and property tests
```

The provider must not import consumers, Prefect, graph, storage adapters or network clients
(as for `semantic-layer`).

## Code style

Frozen typed values, explicit unknowns, fixed domain error reasons; Ruff format and strict
mypy as locked. Example of the intended shape:

```python
@dataclass(frozen=True)
class CpvPeriodCount:
    cpv_main_code: str | None  # None means the unclassified bucket
    period: str | None  # "2026-03"; None means unknown_period
    record_count: int  # distinct selected records
```

## Testing strategy

- Hand-calculated fixtures above, asserted on exact contributing source IDs, not only totals.
- Pure provider and reference SQL must return identical complete results (parity test on real
  PostgreSQL 17 in CI), as for `participation`.
- Invariants as properties: permuting inputs changes nothing; counts reconcile to their
  stated denominators; overlap disclosures present when overlap exists.
- Mutation check each new rule (break it, see a test fail, restore).
- Coverage 100% line and branch for new code; the combined floor stays as in `CONSTRAINTS.md`.
- Synthetic success establishes definitions, not real-data accuracy; certification waits for
  S7.

## Boundaries

- Always: keep source text next to parsed values; disclose unknown buckets; one definition per
  concept; version every behaviour change; run `just check` and `just audit`.
- Ask first: any schema migration, new dependency, a changed metric meaning, enabling the
  reviewed-entity basis, promoting any metric past `draft`.
- Never: infer legal identity, allocate contract value to suppliers, treat observation time as
  an effective date, drop unparseable records, create a single trust score, certify from
  synthetic data alone.

## Slices (one PR each, in order; each stops for review)

| Slice | Content | Exit |
|---|---|---|
| S1 | This spec | Owner approves or edits; decisions D1-D5 recorded |
| S2 | M2 time model: measure date formats on a real private cohort, then parser and period rules | Measured format table; tests for every observed shape and for unparseable text |
| S3 | M1 shared selection and M3 party tier, `participation` rewired onto them | `captured_contract_record_count.v1` results byte-identical before and after |
| S4 | U2 metric and SQL reference | Parity and hand-calculated tests pass |
| S5 | U3 metric and SQL reference | Same |
| S6 | M4 lifecycle plus U4 metric | Same; `incomparable` abstention proven |
| S7 | Catalogue page, definition hashes, promotion of U1-U4 to `reviewed`; real-data reconciliation plan for `certified` | Owner review; certification needs the owner's real-data check |

## Success criteria

Four catalogue metrics `reviewed`, each with parity-tested pure and SQL implementations, a
published definition hash and hand-calculated acceptance; every metric output names its
cohort, cutoff, definition version, time basis and unknown buckets; U1 unchanged byte for
byte; no migration unless separately approved; `just check` and `just audit` pass on hosted CI.
This satisfies the *definition* part of R5. `certified` status, and therefore the full gate,
still needs the owner's real-data reconciliation.

## Decisions (recorded 2026-11-20)

The owner answered "do recommended for 1-5". Recorded as follows.

- **D1 Metric set:** U1 unchanged plus U2 (CPV by period), U3 (buyer record concentration) and
  U4 (change between captures).
- **D2 Period basis:** calendar month of the reported submission date in Europe/Athens civil time.
- **D3 Concentration measure:** record-participation counts with an explicit unresolved share; no
  fractional allocation of joint records.
- **D4 Placeholder tax IDs:** only the existing all-zero rule excludes a key now; other
  suspicious patterns are disclosed as counts. Slice S2 reports real-data frequencies and
  proposes any further rule for a later decision.
- **D5 Lifecycle:** amendments stay separate publications. The umbrella-reference threshold is
  measured on real data before it is set (Diavgis's 25 is a reference point, not adopted). No
  chain-collapsed second basis in V1-05; revisit when V1-07 cross-source joins are specified.
