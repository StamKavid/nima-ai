# Delivery plan

## Current increment: Nima investigation foundation

The user reaffirmed the company/public-spending investigation concept, supplied
the original architecture as the project brief, and created `StamKavid/nima-ai`.
Keep the ingestion-first sequence while making graph, ML, AI, and investigative
insights explicit downstream capabilities. The election concept is a separate
idea and has no implementation tasks here.

GitHub authentication works, but the repository was initially public and the
integration cannot change visibility (403). Do not push before independently
confirming private visibility. Earlier private-hosting authorization remains in
effect. Keep local changes on `feature/nima-investigation-foundation`.

## Ordered increments

1. Install the complete skill snapshot and record provenance.
2. Establish locked Python tooling and behavioral tests for snapshot integrity.
3. Add CI, security checks, review conventions, and architectural context.
4. Rename first-party package metadata to `nima-ai` and import namespace to `nima`.
5. Implement one contract-normalization slice with exact money, unknown-value
   preservation, source references, and evidence pointers. Use standard-library
   JSON/Decimal; introduce no model dependency into the collection path.
6. Document graph ontology, model candidates, detector coverage prerequisites,
   and the investigation workflow, with acceptance gates for each stage.
7. Verify private GitHub visibility, connect the remote, push the existing
   bootstrap main and the feature branch, then open a draft PR. Run hosted CI
   and verify available branch controls. Never merge the PR without authorization.

The task state is in `tasks/todo.md`. Remote controls and hosted CI cannot be
marked complete from local evidence alone.

## Risks

| Risk | Handling |
|---|---|
| GitHub credential fails | Continue local work; use the authorized GitHub integration once connected |
| A skill update changes operating rules | Pin the source revision, preserve full references, and review updates separately |
| Bootstrap checks look like product validation | State exactly which behavior is tested; ingestion has its own acceptance criteria |
| Private repository plan lacks branch rules | Verify support and report limitations; never claim protection from configuration alone |

## Source-normalization acceptance

- Decode source decimals without a binary-float intermediate; reject duplicate
  keys, non-finite amounts, malformed shapes, and out-of-range record indexes.
- Preserve missing bidders/suppliers, leading-zero identifiers, multiple supplier
  participation, cancellation state, and raw source timestamps.
- Attach the original response hash and record JSON pointer. Preserve the meaning
  of source reference fields; do not infer ownership, transfers, or bid collusion.

Verify with focused behavioral tests followed by `make check` and `make audit`.
The raw collector, archive, database, checkpointing, and crash-recovery guarantees
remain open work; this increment does not satisfy the full ingestion spec.

## Next slices

KIMDIS HTTP collection and bounded pagination → raw archive → PostgreSQL
observations/versions/outbox → restart/reconciliation tests → document evidence →
Diavgeia linking → GEMI enrichment. See `docs/architecture.md` for the later graph,
model, and insights roadmap. Stage completion requires its acceptance tests.
