# Specifications

Specs live here, not at the repository root. Statuses are as recorded inside each spec
on 2026-11-20; the spec itself is authoritative when they differ.

| Spec | Scope | Status |
|---|---|---|
| [SPEC-release-v1.0](SPEC-release-v1.0.md) | v1.0 acceptance, R1-R10 and U1-U5 | Proposed release scope |
| [SPEC-source-ingestion](SPEC-source-ingestion.md) | KIMDIS contract ingestion | Current; full acceptance open |
| [SPEC-source-boundaries](SPEC-source-boundaries.md) | `SourceAdapter` protocol (V1-04) | Approved; S1-S4 delivered, S5 gated |
| [SPEC-entity-resolution](SPEC-entity-resolution.md) | Evidence-backed party identity | Approved |
| [SPEC-semantic-layer](SPEC-semantic-layer.md) | First shared metric definition | Provider implemented; metric draft |
| [SPEC-market-analytics](SPEC-market-analytics.md) | Cited supplier-buyer readout | CLI implemented; human validation open |
| [SPEC-source-neutral-collection](SPEC-source-neutral-collection.md) | Source-neutral request, provenance, run options | Approved; N1, N2 delivered |
| [SPEC-operating-controls](SPEC-operating-controls.md) | Diagnostics, health, roles, TRUNCATE guards (V1-03) | Mostly delivered |
| [SPEC-refresh-recovery](SPEC-refresh-recovery.md) | Bounded refresh recovery (V1-02) | Delivered (R1-R3) |
| [SPEC-validation-history](SPEC-validation-history.md) | Durable validation journal (V1-01) | Delivered |
| [SPEC-data-contracts](SPEC-data-contracts.md) | First machine-readable contracts and history check | Delivered (C8-C10) |

Delivered specs stay here because runbooks and ADRs cite their anchors. Delivered
history of work tracking lives under [../history/](../history/README.md).
