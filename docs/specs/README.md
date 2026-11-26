# Specifications

Specs live here, not at the repository root. Statuses are as recorded inside each spec
on 2026-11-20; the spec itself is authoritative when they differ.

| Spec | Scope | Status |
|---|---|---|
| [SPEC-release-v1.0](SPEC-release-v1.0.md) | v1.0 acceptance, R1-R10 and U1-U5 | Proposed release scope |
| [SPEC-source-ingestion](SPEC-source-ingestion.md) | KIMDIS contract ingestion | Current; full acceptance open |
| [SPEC-source-boundaries](SPEC-source-boundaries.md) | `SourceAdapter` protocol (V1-04) | Approved; S1-S4 delivered, S5 gated |
| [SPEC-entity-resolution](SPEC-entity-resolution.md) | Evidence-backed party identity | Approved |
| [SPEC-semantic-model](SPEC-semantic-model.md) | Shared selection, time, party tier and metrics U1-U4 (V1-05) | Draft for owner review |
| [SPEC-gemi-afm-lookup](SPEC-gemi-afm-lookup.md) | GEMI search by reported tax number | Draft for owner review |
| [SPEC-gemi-afm-import](SPEC-gemi-afm-import.md) | Importing GEMI AFM search runs into SQL (slice L5) | Approved (L5-1 to L5-5 as recommended); L5a to L5c delivered, L5c-1 decided and delivered |
| [SPEC-diavgeia-pilot](SPEC-diavgeia-pilot.md) | Diavgeia second-source pilot, Δ.2.2 by organisation and window (V1-06) | Decided except P2 (organisation, window); D2, D3 command and first real run delivered |
| [SPEC-diavgeia-commitments](SPEC-diavgeia-commitments.md) | Second Diavgeia pilot: do KIMDIS citations point at Β.1.3 commitments (V1-06) | Decided (C1 to C5 as recommended); C0 to C3 not started |
| [SPEC-archive-replay-sources](SPEC-archive-replay-sources.md) | Source-aware `archive replay` and `promote` for the Diavgeia pilots | Delivered (R1, R2); promotion awaits an owner-selected digest |
| [SPEC-cross-source-citations](SPEC-cross-source-citations.md) | Exact KIMDIS–Diavgeia citations with two-sided evidence (V1-07) | Model/SQL #221 and verified readout #222 delivered; real reconciliation open |
| [SPEC-dataset-acceptance](SPEC-dataset-acceptance.md) | Per-use data fitness and check policy (first V1-08 slice) | Pure policy #223 and citation consumer #225 delivered; U1 contract drafted; history/real acceptance open |
| [SPEC-citation-acceptance-readout](SPEC-citation-acceptance-readout.md) | Verified citation-report acceptance sidecar (V1-08 first consumer) | Delivered #225; B1–B3 approved 2026-11-26 |
| [SPEC-participation-acceptance-readout](SPEC-participation-acceptance-readout.md) | Supplier–buyer (U1) data-fitness sidecar | C1–C3 approved 2026-11-26; implementation active |
| [SPEC-metric-readouts](SPEC-metric-readouts.md) | Readout commands for U2-U4 over stored runs | Approved; S8a next |
| [SPEC-semantic-layer](SPEC-semantic-layer.md) | First shared metric definition | Provider implemented; metric draft |
| [SPEC-market-analytics](SPEC-market-analytics.md) | Cited supplier-buyer readout | CLI implemented; human validation open |
| [SPEC-source-neutral-collection](SPEC-source-neutral-collection.md) | Source-neutral request, provenance, run options | Approved; N1, N2 delivered |
| [SPEC-operating-controls](SPEC-operating-controls.md) | Diagnostics, health, roles, TRUNCATE guards (V1-03) | Mostly delivered |
| [SPEC-refresh-recovery](SPEC-refresh-recovery.md) | Bounded refresh recovery (V1-02) | Delivered (R1-R3) |
| [SPEC-validation-history](SPEC-validation-history.md) | Durable validation journal (V1-01) | Delivered |
| [SPEC-data-contracts](SPEC-data-contracts.md) | First machine-readable contracts and history check | Delivered (C8-C10) |

Delivered specs stay here because runbooks and ADRs cite their anchors. Delivered
history of work tracking lives under [../history/](../history/README.md).
