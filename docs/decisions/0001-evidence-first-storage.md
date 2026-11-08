# ADR-0001: Preserve evidence before derived analysis

## Status

Accepted research direction; implementation details remain subject to the
source-ingestion spec review.

## Date

2026-11-08

## Context

Journalists need to verify claims and reconstruct what the platform knew at a
particular time. Public records can be corrected, cancelled, or published late.
Graph projections and model outputs cannot replace the original evidence.

## Decision

Preserve source responses and documents in object storage and use PostgreSQL
for normalized records, observations, versions, and transactional job handoff.
Introduce a rebuildable graph after the source and identity contracts are tested.
LLMs and embeddings are optional downstream enrichment steps.

## Alternatives

A graph-only store would make collection bookkeeping and audit requirements
harder to implement. Keeping extracted text without original files would lose
layout and revision evidence. Starting with LLM extraction would introduce
unnecessary cost and uncertainty for structured API fields.

## Consequences

Original archives need retention and access policies. Derived projections must
retain evidence references and processing versions. Data recovery and replay
become explicit acceptance criteria.
