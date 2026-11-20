# ADR-0005: Build a shared market-intelligence foundation before persona workflows

## Status

Product direction accepted on 2026-11-16 through the owner's instruction to follow
the product-first audit response and clarification: “Company and market
intelligence: sectors, competitors, public procurement and corporate changes”.
The revised [capability map](../../CAPABILITIES.md) was owner-approved through
merged [#108](https://github.com/StamKavid/nima-ai/pull/108) and the subsequent
instruction to continue on 2026-11-16. Individual module scopes/plans and
implementation are not approved by that map review alone. The first
[semantic provider](../specs/SPEC-semantic-layer.md) and
[analytics consumer](../specs/SPEC-market-analytics.md) scopes have advanced into
planning after the owner's subsequent conceptual quality/pipeline review and
instruction to continue. See the current [plan](../../tasks/plan.md) and
[validation contract](../pipeline-quality-validation.md); implementation is pending.

## Date

2026-11-16

## Context

The project has substantial provenance and failure-path engineering, but no
implemented serving/metric surface or measured investigator/analyst usefulness.
The owner wants trusted data, a semantic layer and analytics before choosing
persona workflows and activating AI. This broadens the original investigation
positioning without granting access to unavailable private business information.

A read-only audit response at main `538de66` reproduced six diagnostics on
PostgreSQL 17: request normalizer/default-limit coupling, policy-version coupling,
expired-child recovery blockage, owner TRUNCATE exposure and path-bound archive
identity. Two mutual package dependency pairs and 25 cross-module private imports
were also observed. The companion diagnostic artifact is retained outside Git;
these reproduced gaps are not implemented fixes. All three #107 hosted jobs passed.

## Decision

Position Nima as Greece-focused company and market intelligence supported by
traceable public records. Preserve the evidence/version/review core, PostgreSQL,
private original archives and the accepted HTTPX/Playwright/Prefect direction.
Journalists remain a supported future persona alongside sector/company researchers,
procurement analysts and business-development users.

Build a small shared semantic layer: precise terms, record grains and keys,
procurement stages, observed versus effective time, CPV versus KAD, currency/value
basis, coverage/eligibility rules and versioned metric definitions with lineage.
Unknowns and reported-identifier groupings remain separate from reviewed facts.
Metrics are computed deterministically; source text cannot become tool instructions.

Deliver one thin data-to-metric-to-evidence readout before generalizing the platform.
The first proposed metric counts captured contract-publication records by reported
supplier and buyer. Its serving contract must select revisions before supplier
filtering, deduplicate repeated observations and expose evidence/coverage limits.
It does not infer payments, legal identities, complete market share or wrongdoing.

Pause new RP3–RP9 egress feature work at the delivered RP1–RP2 checkpoint. Keep
its implementation, tests, pins and required checks. Resume only for a concrete
approved live-capture need with the necessary host/control inputs. The user's IP
requirement still applies; development uses synthetic or authorized protected
archives rather than a direct request from the investigator's connection.

Keep refresh recovery/version evolution, private backup/restore and restricted
application roles as explicit reliability work before live/shared operation.
Effective main/dev protection still needs repository-admin action. These concerns
have separate review scopes; do not silently change migrations, credentials or CI.
They do not require completing a generic ingestion-engine rewrite before the
first read-only query can be developed and tested.

AI later consumes tested metrics and cited records for explanations/briefings.
Deterministic alerts and exports do not need a model. Broader retrieval requires
a document corpus and evaluation; graph/ML adoption requires demonstrated value.
No new datastore, framework, ontology package, persona UI or notification service
is adopted by this direction.

## Alternatives

Continuing the full remote worker before every product experiment would leave
usefulness untested despite the available archive/projection interfaces. Replacing
it immediately with a broad kernel/connector/package rewrite repeats that delay.

Building separate journalist and commercial data pipelines would duplicate identity,
time and metric policies and make results diverge. A shared foundation lets later
views differ in workflow while retaining the same evidence and definitions.

Starting with a generic semantic platform across every source would postpone a
measurable result. One reviewed metric and a cited readout test the foundation
while leaving source expansion and persona selection reversible.

## Consequences

The old capability percentages describe the original scope; do not recompute them
for this broader direction without a separately stated rubric. No new capability
is counted as delivered by these documents. Existing incomplete PE and egress work
is retained, with the latter paused rather than deleted or relabelled complete.

A future market view must distinguish captured records from the actual market and
reported ties from established corporate relationships. A real-data pilot and one
observed analyst task remain necessary. If protected input archives/reviewer context
are unavailable, record the blocked outcome instead of substituting a fixture.

## Sources

- [Shared capability map and first proof](../../CAPABILITIES.md)
- [Existing architecture and evidence principles](../architecture.md)
- [Accepted acquisition direction](0004-bounded-http-and-browser-acquisition.md)
- [Existing bounded recovery contract](../graph/company-evidence-pilot.md)
- [Normal refresh limitations](../sources/kimdis-refresh.md)
