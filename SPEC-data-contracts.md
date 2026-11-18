# Spec: first machine-readable analytics contract

## Objective and authorization

The owner requested continued implementation after the data-contract proposal on
2026-11-18. Extend the existing semantic-layer/market-analytics boundary with one
offline ODCS contract. This is a thin extension of the approved capability map,
not a new orchestration platform. Preserve all pending pipeline and human tasks.

The first output is the existing `nima-supplier-buyers-v1` private artifact. Nima
owns its guarantees; it cannot promise government-source accuracy, availability
or national coverage. The metric remains draft. Source-acceptance and normalized
dataset contracts follow after this output boundary is proved.

## Contract and implementation

- Pin official ODCS 3.2.0 JSON Schema, upstream commit and SHA-256, with its
  Apache-2.0 license. Package it locally; validation never retrieves references.
- Package a reviewable JSON contract (JSON is also valid YAML). Record Nima
  ownership, use/coverage limits, output fields, quality-check references and
  the existing semantic definition. The latter is a reviewed snapshot compared
  with `nima.semantics.participation.definition()`, not a second calculation.
- Declare the supported Nima profile: string/integer/number/boolean/object/array,
  required/nullability, enum, nested properties/items, and the explicit supported
  logical options. Fail unsupported constructs instead of silently ignoring them.
- Validate the actual output against that shape after original reconciliation
  and before private publication. Refuse metadata/semantic/shape mismatches with
  `analytics_contract`; preserve previous artifacts, source rows and originals.
- Keep every existing successful report byte unchanged. Contract validation does
  not make a draft metric certified, nor add a release/validation-result registry.
- Provide conservative compatibility comparison: removals, existing field shape,
  grain/semantic/quality/terms changes require a major version; optional added
  fields require a minor; descriptive-only edits require a patch. Changed content
  cannot reuse a version and versions cannot go backwards. A major bump still
  needs a separately versioned consumer interface and review before activation.

## Structure and commands

`src/nima/contracts/`: contract, local schema/license, loader/profile validation
and compatibility policy. `tests/test_data_contracts*.py`: metadata, compatibility
and real publication tests. `docs/semantics/data-contracts.md`: operational scope,
upstream provenance and reproduction. No new service, migration or source request.

```sh
uv run --frozen pytest tests/test_data_contracts.py
uv run --frozen pytest tests/test_data_contracts_publication.py
just check
just audit
```

Use the existing Python 3.12, immutable values, fixed failures and strict mypy
conventions. Declare jsonschema 4.26.0 directly (already in the locked runtime
through Prefect); add its typing stubs to development dependencies. Review the
lock/export changes; do not upgrade unrelated packages or change CI policy.

## Acceptance and boundaries

1. Official-schema validation and installed-wheel resource loading work offline.
2. Current metric/SQL definition matches the reviewed contract; changing its
   revision rule or SQL hash fails without intentional contract evolution.
3. Real readout passes; removed required field/wrong type/negative count fail;
   existing duplicate-grain, missing-evidence and bad-projection guards still
   prevent publication. Existing report bytes and private data remain unchanged.
4. Compatibility tests cover same-version edits, backwards versions, optional
   additions, field removal/type/nullability changes and semantic changes.
5. A meaningful disabled-guard mutation fails its regression; complete local
   gates/audit and actual final-head hosted results precede handoff.

Always preserve original evidence and consumer semantics. Never execute code,
SQL or links from contract metadata. No scheduled monitoring, alerts, automatic
certification, universal ODCS execution, source refresh or live pilot deployment.
Historical PR-baseline automation and durable contract-check history are later
increments; passing policy tests alone is not that automation.
