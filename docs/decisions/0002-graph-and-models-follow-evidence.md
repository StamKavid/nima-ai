# ADR-0002: Evaluate graph and model capabilities against an evidence baseline

## Status

Accepted staged direction; individual model choices remain proposed experiments.

## Date

2026-11-08

## Context

The user reaffirmed the initial company/public-spending investigation project and
asked to strengthen it with graph networks, AI, ML, and insights. A model can
rank unreliable identities or incomplete bidder data convincingly without
improving the investigation. The reference architecture already separates durable
ingestion, temporal evidence, graph projection, and citation-aware retrieval.

## Decision

Keep an evidence-first collection and identity layer. Build a rebuildable temporal
graph, transparent rules and peer comparisons, then evaluate ML and AI on defined
research tasks. Model outputs remain derived assertions with method versions and
review status. Preserve the user's private-hosting requirement for `nima-ai`.

## Alternatives

Starting with a graph neural network would require a reliable graph, labels, and
leakage controls that do not yet exist. Extracting all records through an LLM
would add cost and uncertainty to already structured fields. A search-only
aggregator would leave relationship verification and investigative workflow
requirements unresolved.

## Consequences

The first implemented source slice is typed contract normalization, covered by
behavioral tests. Durable collection remains the next milestone. Models need
baselines and evaluation evidence before adoption; there is no claim that a
model currently detects tax evasion or cartels. The phased graph/model plan is
documented in `docs/architecture.md`.
