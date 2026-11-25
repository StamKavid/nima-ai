# V1-07: pure citation model and reference SQL

Date: 2026-11-25. Contract: [SPEC-cross-source-citations](../specs/SPEC-cross-source-citations.md),
owner approved J1–J4. Baseline main `eb0c903`. This is the first model/SQL
checkpoint, not the verified two-source readout or completed V1-07 acceptance.

## Scope and checks

`explicit_procurement_citations.v1` is a draft, deterministic model over typed
observations. It selects latest observed content before classifying exact ADA
references, keeps source/target conflicts visible and preserves observations of
selected content at or before the cutoff. Re-observation and A→B→A do not multiply
edges. It imports only pure semantic siblings and the standard library.

The first three tests failed at collection while the provider was absent, then
passed after the smallest provider implementation. Expanded synthetic checks:

| Check | Observed result |
|---|---|
| Citation tests, including reference-SQL parity on native PostgreSQL 17.11 | 61 passed |
| Provider line and branch coverage | 100%; no missing lines or partial branches |
| Existing lifecycle, U1 characterization pins and documentation link tests | 60 passed unchanged |
| Strict mypy and Ruff on new Python; Bandit on the provider | Pass |
| Representative deliberate Python rule breaks | All 13 rejected |
| Deliberate reference-SQL rule breaks | All 8 rejected |
| Locked dependency advisory audit | No known vulnerabilities found |
| SQL ownership guard | Explicit citation-model owner/hash checked; an unregistered SQL file is rejected |

Python mutations: cutoff, source conflict, target conflict, exact identifier,
type, same-version facts, duplicate IDs, normalizer, observation bound, edge
bound, output bound, shared-target count and supported-relation membership. SQL mutations: cutoff, latest
selection, target conflict, type, source conflict, sharing, full selected-content
lineage and lineage order. Each produced a failing test; originals were restored.
The private harness/logs remain outside Git. This is targeted mutation evidence,
not an exhaustive mutation score.

The existing SQL-inventory test assumed every semantic SQL file was a metric.
It now names the citation model explicitly, verifies its SQL hash and still
rejects every undeclared file. The four metric entries, statuses and published
hashes are unchanged; citations are not inserted as a fifth metric.

Parity executes the packaged SQL with bound JSON/cutoff parameters inside a
read-only transaction on a disposable local database. SQL creates no views,
tables or migrations. Scenarios include unknown/mismatched types, all supported
decision statuses, cancellation, missing targets, tied revisions, shared and
duplicate references, Unicode lookalikes, cutoff boundaries and microsecond lineage.

Full `just check`, built-wheel inspection and hosted exact-head results are
tracked in the delivery PR. The focused checks above do not substitute for them;
neither an open PR nor this report establishes a main merge.

## Limits and next boundary

No CLI, source request, application-database change, new dependency or metric
promotion. This model does not recover original bytes or establish publisher
authenticity. The later readout must verify SQL, both archives and normalizer
parity before publishing any evidence artifact, and disclose partial captures.

Real positive reconciliation remains pending: the earlier four-citation/32-target
pilot needs its actual private KIMDIS and Diavgeia originals plus the selected SQL
snapshot. Published counts and synthetic parity are not substitutes. Human metric
reconciliation/certification in V1-05 and V1-08 acceptance remain open.
