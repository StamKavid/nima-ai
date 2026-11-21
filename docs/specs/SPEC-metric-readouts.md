# Spec: readout commands for metrics U2, U3 and U4

Module ID: `metric-readouts`. Status: **draft for owner review; no code until approved.** Serves the
certification plan in [the metric catalogue](../semantics/metric-catalogue.md) (prerequisite 1) and
release gate R5 of the [v1.0 contract](SPEC-release-v1.0.md). It extends the delivered U1 readout
([SPEC-market-analytics](SPEC-market-analytics.md), `nima analytics supplier-buyers`) and the
[semantic model](SPEC-semantic-model.md). U1's command, request format, result format and the nine
characterisation pins in `tests/test_semantic_pins.py` stay unchanged.

## Objective

Let the owner compute U2, U3 and U4 over **stored runs**, and publish each result as a private,
verifiable, cited artifact, so that a real-data reconciliation (catalogue certification step 3) can
be performed. Today these metrics have pure providers and reference SQL but no way to read stored
data.

Success: for each of U2, U3, U4 one CLI command that (a) reads only stored data with SELECT,
(b) re-verifies every selected record against its **original archived bytes**, (c) evaluates the
metric with the pure provider, (d) checks the result equals the reference SQL result on the same
rows, and (e) publishes one content-addressed artifact naming the metric id, definition hash,
request hash, run IDs and cutoff. No network, no SQL writes, no repair of originals.

## Assumptions (correct me before I proceed)

1. One trusted local operator; the database is the pilot database; archives are local.
2. U1's evidence layer (`nima.analytics.snapshot`, `reconcile`, `result`) is supplier-specific
   (it selects by one tax id). It is reused by **generalising its selection**, not by copying it.
3. CPV is not in the normalized record. It is re-extracted from the original bytes with
   `nima.metadata.extract.kimdis_metadata`, which the reconciliation step already re-reads.
4. Counts only. No money, identity, market share or misconduct claim in any result.
5. Results stay private (outside Git), like U1's.

## Design

### Shared evidence layer (slice S8a)

A metric-agnostic **frozen cohort**: the selected runs' pages, record versions and observations
under one SELECT-only snapshot, each page's original bytes recovered and compared to the stored
hashes, the normalized form recomputed and compared, and the cohort digest recorded. The
supplier filter of U1 becomes one *view* over the cohort rather than part of the read. U1 keeps its
request format `nima-participation-request-v1` and must produce byte-identical output for the
existing fixtures (proved by the pins before and after).

### Per-metric requests

Each metric has its own versioned request format, strict like U1's (unknown or duplicate keys,
non-canonical UUIDs, relative paths, non-finite numbers all rejected with the single fixed reason
`analytics_input`):

| Metric | Request format | Parameters beyond `run_ids`, `observation_cutoff`, `archive_bindings` |
|---|---|---|
| U2 | `nima-cpv-period-request-v1` | optional `cpv_base_code`, optional `period_from`, `period_to` (reported months) |
| U3 | `nima-buyer-concentration-request-v1` | `buyer` (the buyer key) |
| U4 | `nima-observed-change-request-v1` | `earlier_run_ids`, `later_run_ids` (two captures), no cutoff |

The request hash covers the semantic payload only (never archive paths), as in U1.

### Evidence each metric needs

| Metric | From stored rows | From original bytes |
|---|---|---|
| U2 | observation id, source id, normalizer version, content hash, observed-at, cancelled flag, submitted-date text | CPV assertions per record (status and code) |
| U3 | same as U1 (buyer, suppliers, tax ids, classes) | none beyond U1's re-verification |
| U4 | per run: query, counters, completeness facts; per record version: source id, content hash | none beyond hash verification |

### U4 completeness

`observed_change` abstains unless both captures are complete. The readout decides each run's
`RunFacts` from the run's **stored counters** (pages, records, quarantined, terminal state), and
publishes the facts it used. A run is complete only if it ended successfully, nothing was
quarantined and the stored page and record counts agree with the totals the source reported.
The rule is spelled out in the U4 definition document, with a test per branch. This is the one
place where the readout adds a rule rather than only reading, so it is called out for review.

### Result and failure contract

One artifact per command, named by content hash: the metric payload, the metric's definition and
SQL hashes, the request hash, the cohort digest and the per-record citations (source id,
content hash, run, page, JSON pointer). Failures return one fixed reason from a closed set
(`analytics_input`, `analytics_limit`, `analytics_output`, `analytics_contract`, plus the
reconciliation reasons U1 already has); no value, path or SQL text is ever echoed.

## Commands

```
nima analytics cpv-period          --request <file> --output-dir <dir>
nima analytics buyer-concentration --request <file> --output-dir <dir>
nima analytics observed-change     --request <file> --output-dir <dir>
```

All read `NIMA_DATABASE_URL` and nothing else from the environment.

## Slices

| Slice | Content | Done when |
|---|---|---|
| S8a | Generalise the evidence layer into a frozen cohort; U1 rebuilt on it | U1 pins unchanged and green; U1 output byte-identical on the fixture; new cohort tests; mutation check |
| S8b | U2 readout | Request, command and artifact; pure vs SQL parity on stored rows; real-bytes CPV re-extraction tested |
| S8c | U3 readout | Same shape; parity on the spec example |
| S8d | U4 readout and completeness rule | Rule documented and tested per branch; abstention reasons surface in the artifact |
| S8e | Docs | Catalogue prerequisite 1 updated; runbook lines per command |

Each slice follows the handbook workflow: pins from unmodified main, tests first and seen to fail,
smallest change, mutation check of each new guard, 100% line and branch on new code, `just check`
and `just audit`, one draft PR to `main`. The owner merges.

## Boundaries

**Always:** read-only SQL; verify originals before publishing; fixed failure reasons; metric id and
definition hash on every artifact; unknown stays unknown.

**Ask first:** changing any metric definition (that needs a new metric version and a new catalogue
hash); any live request; promoting a status.

**Never:** write to the database; repair or rewrite originals; print source values, names or tax
numbers in errors; put a result artifact in Git; change U1's request or result format.

## Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| R1 | Generalise U1's evidence layer into a shared cohort (S8a) or duplicate it per metric | Generalise: one verifier means one place to get integrity wrong; the pins guard U1 |
| R2 | CPV from re-extracting original bytes, or from stored metadata snapshots | Re-extract: the bytes are the evidence, and U1's reconciliation already reads them |
| R3 | U4 completeness decided from stored counters inside the readout | Yes, as written above, with the rule recorded in the U4 definition document |
| R4 | Order of delivery | S8a, then U2, U3, U4 |

## Deferred, with triggers

| Item | Trigger |
|---|---|
| A single `nima analytics run` that takes the metric id | A fifth metric exists |
| Human-readable rendering of artifacts | The first analyst task (V1-12) |
| Reading archives from object storage | An off-host archive exists |
