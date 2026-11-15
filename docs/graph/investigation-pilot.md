# Specification: bounded investigation graph

Status: **contract approved by the owner**, 2026-11-15, following merged scope #87
at `eb3d2e0`. The owner also requested the [database candidate assessment](database-candidates.md).
This approved contract follows reviewed-identity release #85/#86; no graph code,
implementation plan, new dependency, service or deployment is included here.

## Objective and product boundary

Help a trusted local investigator follow a selected reviewed party through
reported contracts and buyers to inspectable source references. Deliver one
bounded, reproducible graph snapshot with an optional party-focused JSON view.
Its consumer is the local CLI; a browser dossier, graph-store adapter, monitoring,
detectors and AI research are later capabilities requiring their own scope.

This is a technical precursor to a real-company investigation pilot. Fixture
correctness does not prove company identity accuracy or investigator usefulness.
The [architecture](../architecture.md) retains the wider product/model roadmap;
the [reviewed-decision contract](../identity/reviewed-decisions.md) remains authoritative
for accept/reject/revoke and unclassified handles. No inference or source coverage
is added merely by displaying stored data as a graph.

Approved scope assumptions: offline stored evidence, one frozen comparison
selection, trusted local PostgreSQL credentials and private filesystem output.
No GEMI key, live collection, model/provider call or public service is needed.

## User outcome and command

Proposed commands, **not implemented commands**:

~~~bash
uv run --frozen python -m nima graph snapshot \
  --report-file data/registry-review/REPORT_SHA256.json \
  --output-dir data/investigation-graph

uv run --frozen python -m nima graph snapshot \
  --report-file data/registry-review/REPORT_SHA256.json \
  --entity-id ENTITY_UUID --max-events 10000 \
  --output-dir data/investigation-graph
~~~

Read only NIMA_DATABASE_URL for database access; no automatic migrations or grants.
Use the existing private comparison-report reader and its version/hash validation.
The optional entity UUID selects a view within the same bounded selection; it
does not search the database for other occurrences or expand the collection.
Malformed configuration fails before SQL; source-bearing values stay off stdout.

A focused view identifies actively reviewed occurrences, their distinct contract
versions, selected buyer occurrences and supporting record locators. It also
provides per-occurrence review revision/event references and the handle's anchor.
Return explicit focus states: omitted, active_links, no_active_links for a selected
historical handle, or not_in_selected_history. Empty results are successful bounded
results, not claims that the company has no contracts elsewhere. A missing selected
buyer is reported as not_selected; do not fill it with an inferred public body.

## Input, consistency and validation

The comparison report supplies immutable selected subjects and registry context;
its coverage remains unverified_report_context. It is not a credential or a
historical-completeness certificate. Revalidate every selected subject/catalog
against SQL using the existing review-evidence boundary. Read current selected
heads/history/anchors and exact contract facts in **one repeatable-read, read-only,
UTC transaction**. Reusing two independently timed exports is insufficient.

Validate every contract version against its stored normalized record with the
existing contract projection codec and digest. Compare the complete projected
payload, including title, amounts, currency, supplier count, cancellation and source
dates; a matching stored digest alone must not hide altered stored attributes.
Never mutate, repair or reproject source data while building this graph.

Preserve all selected subjects, including unresolved or rejected pairs, and every
selected history handle. Rejection does not assert that parties are unrelated.
Revocation removes the active reviewed link in a new snapshot without deleting
the historical event or changing earlier files. Existing CLI/report bytes and
review semantics must retain their current behavior.

## Graph contract

The canonical artifact has graph_format=nima-investigation-graph-v1 and a versioned
graph_policy_version=investigation-graph-v1. It includes the original comparison hash, projection version, the
complete canonical reviewed-resolution object, nodes, edges and the focus view.
Embedded resolution retains selected review events/rationales, exact registry
anchors, ambiguity and source context; it is private investigative material.
Compute its canonical hash as reviewed_resolution_sha256. Whole-artifact SHA256
identifies the exact published graph, including the optional focus selection.

| Node kind | Stable identity and meaning |
|---|---|
| contract_version | Projection version + namespaced source ID + normalizer version + content SHA256; one node per exact stored contract version |
| party_occurrence | Complete ReviewSubject tuple, including run/observation, projection/source/content, role and ordinal; no merging by label or identifier |
| entity_handle | Existing entity UUID; kind remains unclassified, including handles with only historical selected links |
| registry_observation | Exact anchor import UUID + registry number; retains original observed fields and their JSON pointers, not an inferred current profile |
| evidence_object | Original raw-object SHA256; a reference to archived bytes, not a certificate of issuer authority |

Node IDs use the namespace nima:graph:v1 and the kind. For composite keys, append
SHA256 of canonical JSON encoding of the complete named key fields; entity and
evidence identities use their canonical UUID/hash directly. Canonical JSON uses
UTF-8, sorted object keys, compact separators and no non-finite numbers. Retain
complete original key fields on nodes; hash identity must not erase provenance.

| Edge kind | Direction and required context |
|---|---|
| reported_buyer_in / reported_supplier_in | Occurrence → contract version; source observation and record locator, with original role/ordinal |
| supported_by | Occurrence or registry observation → raw evidence object; record/field location context and original observation time |
| reviewed_as | Occurrence → active accepted handle only; exact candidate, current subject revision and acceptance event reference |
| anchored_to | Handle → its exact registry observation; creating-event reference, without certifying legal identity |

Edge IDs hash canonical kind, endpoints and its exact assertion key: full subject
for occurrence edges; import/registry key for registry support; subject revision,
event and candidate for reviewed_as; entity/creating event for anchored_to. Sort
nodes and edges by ID. Reject collisions, duplicate IDs or dangling endpoints;
identical evidence bytes may support multiple distinct observations.

Each occurrence retains its record-level raw SHA256 and /content/INDEX pointer,
plus observed_at. Registry nodes preserve field-specific source JSON pointers;
their response-level evidence locator uses the empty pointer for the JSON root.
Do not label record-level procurement attribution as verified field-level spans.
Review edges refer to embedded ledger events and their supporting occurrence/
anchor paths; review decisions are investigator assertions, not publisher claims.

Do not automatically group buyers by source key, classify a buyer as a legal public
body or rename a handle Company. Preserve duplicate selected handles for one GEMI
number and the existing selected-history ambiguity scope. No name, AFM, address,
registry-number or shared-neighbor rule may merge nodes or propagate acceptance.

## Dates, money and selected views

Store source_submitted_at and source_updated_at as original nullable source text;
keep observation timestamps and database review-recording times separately.
Legal relationship-validity start/end remain unknown. No global timestamp-based
as-of view, review timestamp ordering across subjects, inferred revision chronology
or claim that a formerly observed relationship is current is included.

Contract nodes retain exact nullable Decimal money as decimal text, net/gross
basis and currency, plus title, bidder count, cancellation and supplier count.
Never distribute contract totals to party edges, sum contract versions into spend,
replace unknown money with zero or infer payments from contracts. Repeated
observations refer to one version node; different versions remain distinct without
invented supersedes edges. The focused view returns version references and source
facts, with no supplier-spend total, market denominator or risk score.

Only buyer/supplier occurrences selected by the comparison are graph members.
Source-reported supplier count may differ from selected supplier occurrences;
retain both with their different meanings. No claim covers every version, buyer,
supplier, contract or company outside the bounded selection. CPV/KAD cohorts,
identified losing bidders and linked procurement lifecycle stages are not available
merely because this graph exists; sector, co-bidding and amendment analytics remain
outside this feature.

## Resource, trust and publication boundary

Keep the existing 32 MiB private comparison-input bound, combined 100 selected
procurement occurrences and 100 registry-observation/anchor budget, and configurable
1–10,000 selected review events (default 10,000). Apply the same **8 MiB combined SQL
input preflight**, reserving all additional contract/normalized-record payload and
graph source context before transferring labels or review notes. Count repeated
version payload once when read once; do not exclude extra data from the reservation.

Graph ceilings are 600 nodes and 500 edges: at most 100 contract versions,
100 occurrences, 100 selected-history handles, 100 exact anchors and 200 distinct
raw objects; at most 100 each of occurrence→contract, occurrence→evidence,
occurrence→handle, handle→registry and registry→evidence edges. Historical review events remain in the embedded ledger,
not new graph nodes. Fail closed on any budget excess; never silently truncate.
The final canonical artifact, including focus and embedded resolution, is bounded
at exactly 32 MiB. Bounds are not production capacity or performance measurements.

Close SQL before encoding/publication. Reuse the existing private no-clobber
publisher: owner-controlled 0700 directory, 0600 SHA256-named artifact, no symlink
traversal, verified byte-identical reuse and fixed errors on conflicting contents.
Old artifacts remain immutable after new collection or review. Same SQL facts,
selected revisions, report and focus produce identical bytes; do not add a fresh
generation timestamp, machine path or process ID to the artifact.

Retain archive_integrity=not_checked, attribution_assurance=database_principal_only,
automatic_identity_links=0 and the separate reviewed accepted occurrence count.
Existing archive verification is a separate explicit action; building the graph
does not fetch raw files or verify the issuer. Trusted SQL owners, shared credentials
and authorized local readers remain inside the current trust boundary.

Success stdout contains only status, artifact/comparison/resolution hashes, safe
run/focus IDs and numeric counts. Fixed failures use the graph_ prefix with
configuration, input, input_io, evidence, state, limit, schema, permission, database,
output or interrupted as the suffix,
with no paths, labels, notes, SQL/driver exception text or source values. Exit 0
for complete output; 2 for configuration/input shape, 1 for evidence/state/storage/
budget failures and 130 for handled interruption. Preserve unrelated CLI behavior.

## Stack, structure and code style

Use the locked Python 3.12, PostgreSQL 17, psycopg, pytest, Ruff and strict mypy
environment. The graph builder/traversal needs only existing dependencies and the
standard library. PostgreSQL stays authoritative; the JSON graph is rebuildable.
Memgraph remains a candidate for a later adapter: no graph-store or model license,
hosting choice or running service is selected by this specification.

Proposed ownership: src/nima/graph/ for typed snapshot inputs, pure graph/focus
construction and graph-specific command handling; existing identity/storage modules
own evidence and review validation. The implementation plan determines exact files
and any small connection-owned read extraction needed for one snapshot. Avoid
duplicating ledger validation or embedding graph policy in shared identity code.

Keep immutable typed inputs, explicit unknowns, parameterized SQL and a pure
builder separate from database/file ownership. This example follows existing style:

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractKey:
    projection_version: str
    source_id: str
    normalizer_version: str
    content_sha256: str
~~~

## Verification and acceptance

Use pytest cases under tests/test_graph_*.py; focused commands will be selected in
the reviewed implementation plan. Existing executable gates remain unchanged:

~~~bash
just check
just audit
just source-worker-check
~~~

Hosted quality/PostgreSQL, Compose and full controlled-worker checks remain
required for each delivery candidate, with ≥90% combined line/branch coverage.
Missing local PostgreSQL/Docker prerequisites must be reported, not skipped or
described as passing. This documentation adds no tests or runtime behavior.

Acceptance requires all of the following, measured against the actual implementation:

1. One read-only SQL snapshot supplies validated contract facts and selected review
   state. Independent concurrent-revocation tests see a complete before or after
   state, never mixed facts/heads/history. All pre-existing source, projection,
   workflow, migration and review relations remain byte-equivalent as JSON rows.
2. Exact fixture node/edge sets have no inferred links, duplicate version nodes,
   dangling references, lost unresolved members or joint-supplier value allocation.
   Include repeated observations, multiple versions, nullable/invalid dates, absent
   selected buyers, unknown suppliers, outside-report anchors, duplicate selected
   handles and reject/revoke/reassignment histories.
3. Same facts/selection/revisions/focus produce the same artifact hash; a new
   decision changes its dependent graph while prior bytes stay intact. Validate
   source/anchor locators and every active review edge's exact ledger reference.
4. Tampered reports, contract payload/hash mismatches, missing evidence, unsupported
   versions and bound overflows fail before publication. Prove count/byte preflight,
   fixed redacted parser/driver failures, private permissions and verified reuse.
5. Actual child termination before/after publication followed by normal CLI retry
   yields one canonical complete artifact, closed SQL and unchanged authoritative
   data. A material review-link or deduplication mutation must fail a regression;
   restore exact original bytes before normal gates. No production pause hooks.
6. The measured runbook records commands, exact candidates/results, limits and
   remaining empirical gates. Documentation alone earns no roadmap credit.

## Empirical pilot and remaining product gates

After technical delivery, select an authorized private real-company cohort and
record its selection, available sources and missing coverage. METLEN may be a
candidate from earlier investigation requests; no new retrieval or verification is
asserted here. Manually review all displayed active links in this small cohort and
recover the supporting archived records/locations; report numerator/denominator,
contradictions, unresolved cases and errors. Any critical identity, provenance,
date or amount error blocks describing that cohort as a verified demonstration.
This checks the selected example, not population-wide matching precision.

Then observe an investigator locate participation, recover a source citation and
explain a changed/revoked link. Record task completion, critical errors and time
against the manual record workflow, including user familiarity and failures.
No real-user result, representative benchmark, time saving or product-value claim
is made until observed. A browser dossier and wider product validation remain
separately specified follow-ons; this CLI feature does not complete the workspace.

## Boundaries and approval

- Always preserve source Greek text, identifiers, unknowns, evidence locations,
  review/history semantics, private outputs and existing quality/security gates.
- Seek separate scope approval for migrations, new dependencies/services, graph-store
  deployment, live source access, broader source selection, UI, authentication,
  model/provider use or changes to this graph/identity contract.
- Never infer wrongdoing, ownership, legal entity class or relationship-validity
  intervals; commit evidence/credentials; silently consolidate entities; change
  source/review rows; weaken gates or auto-merge/deploy.

No blocking external-access question prevents specifying this offline increment.
The owner approved the CLI-first scope and graph contract on 2026-11-15.
Real-cohort availability and observed investigator testing remain explicit later
gates. Contract approval permits the next implementation-plan phase; it does not
itself approve code, dependencies, database adoption, source requests or deployment.
