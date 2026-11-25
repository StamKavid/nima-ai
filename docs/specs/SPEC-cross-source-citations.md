# Spec: evidence-backed KIMDIS–Diavgeia citations

Module ID: `cross-source-citations` (V1-07). Status: **owner approved J1–J4 as
recommended on 2026-11-25. Model/SQL implementation first; no source acquisition.**
Baseline: main `eb0c903` (#220). Extends the [lifecycle model](../semantics/lifecycle-references.md)
and [source acceptance](../sources/diavgeia-acceptance.md); serves R2/R3/R5 of the
[release contract](SPEC-release-v1.0.md). V1-05 metric review/certification stays open.

## Objective and assumptions

An operator can inspect which captured KIMDIS contracts explicitly cite which
captured Diavgeia commitments, with the supporting originals on both sides and
an explanation for every unresolved or conflicting reference. This is a
reported citation, not a legal identity, verified procurement chain or spending metric.

Assumptions for review: one trusted local operator; PostgreSQL 17 and local private
archives; explicitly selected stored runs; no network; existing source normalizers.
The first supported relation is KIMDIS `diavgeiaADA` to Diavgeia `ada`, not every
lifecycle reference. No schema, dependency, scheduler or infrastructure change is proposed.

## Measured starting point

These are recorded prior observations, not checks re-executed in this spec increment:

- The [lifecycle census](../semantics/lifecycle-references.md#measured-on-real-records-2026-11-21-1317-records)
  found four citing KIMDIS records in 1,317 records. The field is sparse in that sample.
- The [first award pilot](../verification/diavgeia-pilot-run.md) found no resolution
  among 262 award decisions. The [targeted lookup](../verification/diavgeia-c0-lookup.md)
  identified all four cited decisions as commitments (Β.1.3), under different
  organisations from the award pilot. Matching organisation IDs is not a join rule.
- The [commitment pilot](../verification/diavgeia-c2-commitments.md) collected
  32 distinct decisions and found all four cited ADAs. Its
  [SQL/replay follow-up](../verification/diavgeia-r2-replay.md) reproduced all 32.
  Those owner-machine originals are not available in this workspace.
- The separate preserved 77-record cohort used for the private metric evidence
  pack is not the four-citation cohort. It cannot substantiate positive join checks.

Today `lifecycle.evaluate` labels all Diavgeia targets `external` because its
selection is KIMDIS-only. The analytics cohort/reconciler is also KIMDIS-specific;
`ArchiveBinding` and `RawReference` currently admit only KIMDIS and GEMI.
Ingestion/replay support for Diavgeia does not mean downstream verification exists.

## Join and selection contract

New model `explicit_procurement_citations.v1`, initially `draft`; keep
`lifecycle_references.v1` and all U1–U4 definitions, hashes and result bytes unchanged.
It consumes validated observations, not a database connection or filesystem path.

1. Use `selection.select_latest` independently on each source's declared cohort,
   at one inclusive UTC observation cutoff, before filtering references, type or
   status. Never order by issue date, version-ID text or SQL row order.
2. Match the exact stored string `diavgeia:<diavgeiaADA>` to the target source ID
   and normalized `ada`. Preserve the source field and original value. No trimming,
   case folding, Unicode normalization, Greek/Latin substitution or fuzzy matching.
3. Equal content observed repeatedly is one selected version with its observation
   lineage retained. Different content hashes tied at the latest observation time
   are ambiguous. Never choose a winner by hash, normalizer or decision status.
4. A selected source with ambiguous latest content contributes no asserted outgoing
   citation. List it as source-ambiguous; never fall back to an older citation.
   Unknown reference lists and known lists without a Diavgeia citation have separate
   record counts and IDs. Duplicate identical citations in a record form one edge.
5. Validate identity/normalizer agreement and consistent normalized facts for every
   `(source_id, content_sha256)` before selection. Unsupported versions, a normalized
   `ada` disagreeing with its source ID, duplicate observation IDs, or inconsistent
   facts under one version fail with a fixed contract reason. Do not silently drop them.
   Validate both cohorts even if no citation resolves.

Each edge has direction KIMDIS → Diavgeia, relation `cites_decision`, source field
`diavgeiaADA`, and the existing reported relation `commitment_decision` retained
as source semantics. It includes expected target type Β.1.3 and independently
observed target type/status; the field name cannot establish the target's type.

| Edge outcome | Meaning |
|---|---|
| `resolved` | Exact target, one selected version, observed type Β.1.3 |
| `unresolved` | No target selected at the cutoff; means absent from this cohort, not nonexistent |
| `target_ambiguous` | Exact target's latest content conflicts; show candidate version/evidence references |
| `target_type_unknown` | Exact unambiguous target has no observed decision type |
| `target_type_mismatch` | Exact unambiguous target has another observed decision type; retain it without calling it a commitment |

REVOKED and PENDING_REVOCATION targets remain citations, with their observed
status disclosed. Cancellation of a KIMDIS record also does not erase its citation.
Neither condition establishes legal validity, supersession or payment. Sharing a
target yields distinct citing-record counts and IDs; adopt no umbrella threshold.
Do not infer edges through `textRelatedADA`, `relatedPartialADA` or correction IDs.

## Evidence and readout boundary

Proposed command (not yet implemented):

```text
uv run --frozen python -m nima analytics source-citations --request <private-file> --output-dir <private-dir>
```

Request format `nima-source-citations-request-v1`: explicit nonempty
`kimdis_run_ids` and `diavgeia_run_ids`, `observation_cutoff`, and an archive binding
`{source, run_id, root}` for every run exactly once. At most 10 runs combined;
canonical unique UUIDs; only the two declared namespaces; absolute roots; no
unknown/duplicate JSON keys, duplicate runs across groups or implicit database discovery.
Wrong-source bindings fail. The semantic request hash excludes physical archive paths.

Take one bounded SELECT-only repeatable-read snapshot for both groups. Reuse the
existing session/schema/role checks, safe blob recovery and private artifact publisher;
extend their source handling narrowly, with KIMDIS/GEMI regression checks. Do not
turn the KIMDIS projection into a Diavgeia projection or build a parallel archive.
The reference join SQL uses the same frozen, verified input, with no persistent view.

Before publication, recover every admitted page and recompute its response hash,
record identity/hash, normalized facts and pointer using its explicitly supported
adapter. Check against frozen SQL. Archive validity without SQL/normalizer parity
is insufficient. A missing, unreadable, replaced or corrupt original fails closed;
there is no fetch, write, migration, replay-promotion or repair fallback.

Reuse existing ceilings: 5,000 observations combined, 8 MiB frozen SQL input,
32 raw objects, 8 MiB/object and 64 MiB total recovered bytes. Add at most
5,000 citation edges and an 8 MiB canonical output bound. Check limits before
allocation/publication; exceeding one yields a fixed limit failure, never truncation.

The private canonical result carries the model definition/hash, reference-SQL hash,
semantic request hash, input/cohort hashes, selected runs and cutoff. Each source,
target and ambiguous candidate retains source ID, content hash, normalizer,
observation IDs/times, run, page, response hash and JSON pointer. Field locations
identify KIMDIS `diavgeiaADA` and target `ada`/`decisionTypeId` in the original records.
Physical paths are recovery configuration, not artifact identity.

Publish separate counters for selected KIMDIS records, source ambiguity, unknown
reference lists, known records without this citation, distinct citation edges,
distinct target IDs and each edge outcome. Record collection completeness,
quarantine and observation span per run. Incomplete or quarantined captures may
yield inspected citations from verified records, explicitly marked
`partial_capture`; no completeness, match-rate or market-coverage claim follows.
An empty edge set in partial data does not establish an absence of citations.
V1-08 decides metric acceptance separately.

Errors use closed reasons (`citation_input`, `citation_limit`, `citation_contract`,
`citation_evidence`, `citation_database`, `citation_output`), without driver text,
paths or source values. Stdout contains only artifact hash and fixed outcome/counts;
identifiers/citations stay in the private artifact. Export no subjects, persons,
supplier details or amounts from Diavgeia. Preserve source attribution/retrieval dates.

## Structure, style and verification

Use frozen typed dataclasses, deterministic ordering and fixed error enums/reasons,
following `semantics/lifecycle.py`. A planned provider call looks like:

```python
result = evaluate(kimdis_observations, diavgeia_observations, cutoff=cutoff)
```

Likely implementation: `semantics/citations.py` and reference SQL; narrowly scoped
`analytics/` request/snapshot/reconciliation/readout modules; existing command
registration. Tests belong in `tests/test_source_citations*.py`. These are boundaries,
not a demand to create every module. No generic relationship framework or graph DB.

After approval, use pytest with synthetic public fixtures only. Hand-calculate
positive, unmatched, wrong-type, unknown-type and conflict results; compare Python
with independent reference SQL on PostgreSQL 17. Include equal bytes re-observed,
A→B→A, source/target latest-time conflicts, inclusive cutoff, later unsupported or
revoked target, unknown versus empty references, repeated/shared references,
Unicode lookalikes and different-organisation targets. Verify no filtered older
version replaces the latest. These tests are not independent real-data reconciliation.

Integration checks: mixed sources in one database, restricted reader, all source
groups verified even with zero edges, query/row/output bounds, bad archive bindings,
corrupt bytes/pointers/normalized rows, private no-clobber publication, deterministic
retry and relocated archives. Assert zero HTTP and zero database/source-file writes.
Mutation-check selection, equality, evidence and bound guards. Existing U1 pins and
U1–U4 readout regressions must stay unchanged; new code needs 100% line/branch
coverage and the unchanged repository-wide floor. Before a merge proposal:

```text
uv run --frozen pytest tests/test_source_citations.py tests/test_semantic_pins.py
just check
just audit
```

The proposed test file does not exist yet. This documentation increment checks
links, whitespace and public-diff secret hygiene; it does not claim those feature
tests or full quality gates passed. Hosted exact-head checks remain distinct.

## Acceptance and review decisions

Acceptance requires: independently known synthetic/SQL answers; a reproducible
read-only two-source artifact with both originals verified; unchanged U1–U4;
then offline reconciliation against the prior four-positive/32-target pilot using
its actual originals and selected SQL snapshot. If those inputs cannot be supplied,
record that final evidence as pending. Do not recreate it from published counts,
claim a negative cohort proves positive joins, or acquire replacement data implicitly.

| Decision | Recommended default |
|---|---|
| J1 — first relation | Only explicit KIMDIS `diavgeiaADA` → Diavgeia `ada`; expose actual type/status and conflicts |
| J2 — partial input | Permit clearly marked citation inspection; no match-rate/completeness claim or metric eligibility |
| J3 — compatibility | Add a separately versioned model/readout; preserve lifecycle and U1–U4 contracts |
| J4 — delivery boundary | Pure model/SQL first, then verified readout; real-input reconciliation after both, with no fresh source requests |

**Always:** preserve originals, exact IDs, unknowns, typed stages and provenance;
keep metrics draft until their separate review/certification requirements pass.
**Ask first:** source acquisition, schema/dependency/CI changes, widened bounds,
additional relation types, or promotion to a reviewed identity/fact/metric.
**Never:** infer company ownership, join by names/amounts/organisation coincidence,
sum stages, collapse an economic event, publish source records, or bypass egress controls.

Deferred: V1-08 acceptance journal integration after this result contract stabilizes;
decision-to-decision citations after a concrete analyst question and source semantics
are reviewed; storage/index materialization after a measured query needs it;
graph/AI consumers after the roadmap's analytics and product evidence gates.
