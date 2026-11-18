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
or SQL. URLs are never followed. This is not a universal ODCS execution engine.

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
```

These tests run in the existing `just check` gate. Historical PR-base comparison
is not wired into CI yet; passing policy tests is not proof that every future PR
was compared to a published contract. Contract-check history and scheduled
monitoring also remain later increments. The current 24-hour health threshold is
an operator setting, not a contract SLA or a government publication promise.

Source acceptance and normalized-dataset contracts follow this first output
boundary. No source request, source repair, schedule or private deployment follows
from adding this metadata.
