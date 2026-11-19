# First ODCS output contract

Nima's first machine-readable contract describes the existing private
`nima-supplier-buyers-v1` readout. The contract is
[`supplier-buyers-v1.odcs.json`](../../src/nima/contracts/supplier-buyers-v1.odcs.json),
ODCS 3.2.0 / contract version 1.0.0, status **draft**. JSON is used directly to
avoid an additional YAML parsing boundary. Ownership is Nima's, not the Greek
government's. The metric remains a draft descriptive captured-record count.

The contract records output shape, grain, limits and references to the existing
SQL/pure-policy and original reconciliation checks. Its semantic-definition
snapshot must exactly match the authoritative provider, including the SQL hash.
It does not replace the calculation or introduce a second rule implementation.
Field schemas enforce declared types, presence/nullability, enums and logical
options. Opaque objects remain checked by the existing normalizer/reconciler;
this is not a complete field-level lineage contract.

The supported Nima profile includes string, integer, number, boolean, object and
array. Options are string min/max length and pattern; numeric min/max; object
min/max properties; array min/max items and whole-item uniqueness. Nested
properties/items and enums are supported. Other element constructs are refused,
not silently treated as enforced. Required properties must exist and be non-null;
optional properties may be absent/null, subject to any declared enum. Quality
implementation names document existing checks; no metadata is executed as Python
or SQL. Field-level quality declarations outside that profile are refused.
URLs are never followed. This is not a universal ODCS execution engine.

The actual readout reconciles originals first, then validates the generated output
before publication. The contract gate checks shape and provider binding, exact
typed metric-payload equality with the frozen calculation, evidence count and
observation uniqueness. Failure returns the fixed `analytics_contract` reason;
no new artifact is published and prior artifacts are preserved. Successful report
bytes remain unchanged, so historical report hashes can be reproduced. This is
not yet a persisted per-report contract-validation record.

The official schema is pinned and packaged with its
[provenance/license](../../src/nima/contracts/UPSTREAM.md). Runtime validation
is offline. `jsonschema==4.26.0` was already locked through Prefect and is now a
direct dependency; its typing stubs are development-only. No runtime package is
upgraded by that declaration.

## Evolution and verification

`nima.contracts.check_compatibility(previous, current)` validates both documents
and applies conservative SemVer rules. Changed content must have a newer version.
Optional additions require at least a minor bump. Existing field type, required,
enum or other shape changes, field removal, grain, quality, semantic-definition
or terms changes require a major. Name/support/field-description edits require
at least a patch. Conservative classification can require a major for a change
that a richer compatibility model might prove harmless. A major bump is only a
metadata decision: a new incompatible output also needs a separately versioned
consumer interface, migration and review before activation.

Run the current metadata/compatibility checks with:

```sh
uv run --frozen pytest tests/test_data_contracts.py
uv run --frozen pytest tests/test_data_contracts_publication.py
```

These tests run in the existing `just check` gate. The separate
[committed historical comparison](contract-evolution.md) now checks PR/push
catalogues in CI using immutable event baselines. Explicit post-publication
[validation history](../operations/validation-history.md) records the first
output boundary with a separate writer; other dataset boundaries and scheduled
monitoring remain later increments. The current 24-hour health threshold is
an operator setting, not a contract SLA or a government publication promise.

Source acceptance and normalized-dataset contracts follow this first output
boundary; the [KIMDIS extension](ingestion-contracts.md) defines their explicit
profile and failure semantics. No source request, source repair, schedule or
private deployment follows from adding this metadata.
