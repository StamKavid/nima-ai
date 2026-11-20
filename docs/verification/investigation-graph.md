# Investigation graph: operator workflow and measured delivery

The owner merged G1–G5 in #91–#95 through `4a33a3e`, 2026-11-15, following
approved scope #87 and plan #90. The local CLI connects selected reported parties,
exact contract versions, reviewed unclassified handles and source references in a
private reproducible artifact. This is a technical workflow; real-company identity
accuracy, source recovery and investigator usefulness still need evaluation.

## Prepare existing private evidence

Use Python 3.12/uv and an explicitly migrated PostgreSQL 17 database. Configure
`NIMA_DATABASE_URL` privately through environment settings. The graph command
applies no migrations/grants and makes no Greek-source or model-provider requests.
No GEMI key is required. Administrator setup, when needed, remains explicit:

```bash
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima graph snapshot --help
```

Start with an existing private comparison report from the
[comparison workflow](registry-comparison.md). It must select supported projected
KIMDIS observations and complete stored GEMI imports. Keep its owner-controlled
0700 directory and 0600 regular file outside Git. The existing strict reader rejects
symlink traversal, unsafe permissions, changed files and unsupported JSON/version
shapes. Manually saved Publicity PDFs/screenshots are opaque archive evidence and
cannot substitute for normalized SQL imports.

Use the [review workflow](reviewed-decisions.md) to record any intended
accept/reject/revoke decisions first. An unresolved comparison can also be graphed:
there is no automatic identity acceptance. Retain the original comparison file;
graph export revalidates its frozen selection against SQL rather than replacing it
with the current whole run or fetching more companies.

A responsible administrator provisions the login. A graph-only reader needs
schema usage and SELECT on the following existing relations, without review-write
privileges. If the approved role `nima_graph_reader` already exists, the grant set is:

```sql
GRANT USAGE ON SCHEMA nima TO nima_graph_reader;
GRANT SELECT ON
    nima.schema_migrations, nima.ingest_runs, nima.observations, nima.run_pages,
    nima.record_versions, nima.projection_contracts, nima.projection_mentions,
    nima.projection_receipts, nima.raw_objects, nima.gemi_imports,
    nima.gemi_responses, nima.gemi_profile_versions, nima.gemi_observations,
    nima.identity_entities, nima.identity_review_events, nima.identity_review_heads
TO nima_graph_reader;
```

This role can read private source/review material. Credentials and artifacts stay
with trusted local operators. Graph reads use repeatable-read, read-only UTC
transactions even when the supplied login has broader privileges. Attribution of
stored decisions remains `database_principal_only`; this is not human authentication
or a public/multi-user service. Trusted SQL owners can rewrite stored evidence;
consistency checks do not establish publisher truth or issuer authority.

## Export and inspect

Replace `REPORT_SHA256` with the existing comparison artifact's hash. For a focused
view, replace `ENTITY_UUID` with an actual handle from its selected review history.
These are placeholders, not sample identity assertions.

```bash
uv run --frozen python -m nima graph snapshot \
  --report-file data/registry-review/REPORT_SHA256.json \
  --output-dir data/investigation-graph

uv run --frozen python -m nima graph snapshot \
  --report-file data/registry-review/REPORT_SHA256.json \
  --entity-id ENTITY_UUID --max-events 10000 \
  --output-dir data/investigation-graph
```

One SQL snapshot revalidates selected occurrences, the full declared registry
catalog, current selected review heads/history/anchors and exact contract facts.
The existing codec re-derives every full contract projection; its digest and stored
columns must agree. Full additional normalized/projection payload bytes reserve
space in the same 8 MiB SQL preflight before private labels or notes are transferred.
SQL closes before graph construction, final encoding and publication. No source,
projection, outbox, workflow, migration or review rows are written.

Success is `status=complete`, including empty/unresolved selections. Stdout contains
`graph_sha256`, `comparison_report_sha256`, `reviewed_resolution_sha256`, the run
and optional focus UUID, numeric counts and zero automatic links. It omits source
labels, AFMs, notes, paths and driver details. The artifact is
`<output-dir>/<graph_sha256>.json`: an owner-only 0700 directory, 0600 file and local
Git exclusion. No symlink traversal or clobbering is allowed. Byte-identical reuse
retains the existing file and modification time; conflicting contents fail.

The artifact contains private notes and the **complete selected graph and embedded
comparison/resolution**, including other selected parties and the registry catalog.
Focus adds a view inside this selection. Review the entire private artifact before
sharing any case material. Hashes identify bytes; they neither anonymize data nor
authenticate a publisher. A graph read retains `archive_integrity=not_checked`;
physical recovery of supporting archived bytes is a separate verification step.

## Interpret graph and focus

`graph_format=nima-investigation-graph-v1` and
`graph_policy_version=investigation-graph-v1` bind the representation. The complete
canonical `reviewed_resolution` has its own SHA256; the whole artifact hash also
binds focus. There is no generated wall clock, local path or process identity in
the graph. Same selected facts/revisions/focus reproduce bytes; a later decision
creates a new artifact without changing earlier files.

| Node kind | Meaning |
|---|---|
| `contract_version` | Complete projection/source/normalizer/content key; exact nullable contract facts |
| `party_occurrence` | Full run/observation/version/role/ordinal subject; retains original reported labels and record locator |
| `entity_handle` | Existing UUID with `entity_kind=unclassified`, including selected historical handles |
| `registry_observation` | Exact anchor import UUID/registry number, observed fields and field-level JSON pointers |
| `evidence_object` | Original raw SHA256 reference; archived bytes are not fetched or authenticated here |

`reported_buyer_in`/`reported_supplier_in` connect occurrences to their contract
version. `supported_by` connects occurrences/registry observations to raw evidence.
Only an active accepted pair creates `reviewed_as`, with its exact acceptance event,
candidate and current subject revision. Later review of a different pair does not
change which acceptance event supports that edge. `anchored_to` retains a handle's
exact registry anchor/creating-event reference, including outside-report anchors.

IDs use `nima:graph:v1`, kind and complete canonical keys; UUID/hash identities are
direct. Nodes/edges sort by ID. Shared evidence/version/anchor nodes are reused;
collisions, duplicate assertions and dangling references fail. Duplicate selected
handles for one registry number stay separate, with the embedded resolution's
`selected_history_handles` ambiguity scope. Names, AFMs and neighbors never merge
nodes or propagate review decisions.

Procurement attribution stays record-level (`/content/INDEX`); registry support
uses the JSON root while original fields retain their specific pointers. Source
submission/update strings, observation timestamps and review-recording time remain
distinct. `legal_valid_from`/`legal_valid_to` stay unknown; there is no global as-of
query, inferred supersedes link, current-ownership assertion or legal classification.

Money stays exact decimal text on contracts, with nullable net/gross amount and
currency. Unknown is not zero. `supplier_count` is source-reported;
`selected_supplier_occurrence_count` counts only selected supplier occurrences.
Joint awards have one contract version, no amount allocation to participation
edges and no spending total or risk score. Source counts can exceed selected counts.

| `focus.state` | Interpretation |
|---|---|
| `omitted` | No entity UUID requested |
| `active_links` | Selected actively accepted occurrences, distinct contract references/facts and selected buyer references |
| `no_active_links` | Handle appears in selected history but has no currently accepted selected occurrences |
| `not_in_selected_history` | UUID is absent from this selection's history, regardless of other database contents |

Focused contracts label absent buyers `buyer_selection=not_selected`; no public
body is inferred or fetched. An empty focus says nothing about contracts elsewhere.
All unresolved/rejected/revoked selected members and historical handles remain in
the complete artifact. Rejection does not prove that parties are unrelated.
`automatic_identity_links=0` remains separate from `reviewed_accepted_links`.

## Bounds and recovery

| Bound | Enforcement |
|---|---|
| Private comparison input / canonical graph output | Exactly 32 MiB maximum each |
| Selected procurement occurrences / contract versions | At most 100 each; version payload read once when shared |
| Registry context | Full catalog plus distinct needed anchor observations, combined at most 100 |
| Selected review history | Requested 1–10,000 events; default 10,000 |
| SQL input | Combined 8 MiB, including additional full normalized/projection and review provenance |
| Graph | At most 600 nodes and 500 edges, without history events becoming nodes |
| SQL execution | Existing 5 s connection/lock and 30 s statement bounds |

Limits fail without truncation, hidden pagination or omitted conflicts. The source
snapshot is bounded to the supplied report; these ceilings are not production
capacity or Greek-company coverage measurements.

| Exit | Fixed failure | Operator action |
|---|---|---|
| 0 | Complete graph, including empty/unknown focus | Inspect private source and review context |
| 2 | `graph_configuration`, `graph_input` | Correct environment, options or private report format |
| 1 | `graph_input_io` | Restore safe private-file ownership/permissions and input access |
| 1 | `graph_evidence`, `graph_state` | Investigate missing/mismatched source or review state; preserve originals |
| 1 | `graph_limit` | Choose a legitimate smaller selection; do not discard conflicts silently |
| 1 | `graph_schema`, `graph_permission`, `graph_database` | Have the responsible administrator inspect explicit setup privately |
| 1 | `graph_output` | Inspect permissions/conflicting bytes without replacing evidence to force success |
| 130 | `graph_interrupted` | Retry and inspect the returned hash/current selected revisions |

Unknown/misplaced graph options, invalid values and unsupported option abbreviations
produce fixed JSON without echoing arguments. Ctrl+C during handled work returns
130. SIGKILL cannot print graceful JSON. A completed artifact or private `.tmp-*`
files may remain after interruption; temporary files are not accepted artifacts.
Retry the normal command rather than renaming temporary files into place. Retain
conflicting evidence for inspection. Later review changes can produce a new hash
on retry; identical selected state reuses the original complete file.

## Measured implementation delivery

| Slice | Final candidate | Owner merge | Hosted run | Quality | Full worker suite |
|---|---|---|---|---|---|
| G1 [#91](https://github.com/StamKavid/nima-ai/pull/91) | [964c33a](https://github.com/StamKavid/nima-ai/commit/964c33a9ae02ab34f1f25e608821458ce5914c1f) | `0f623a1` | [43728911740](https://github.com/StamKavid/nima-ai/actions/runs/43728911740) | 1,390 / 92.12% | 12 / 648.97 s |
| G2 [#92](https://github.com/StamKavid/nima-ai/pull/92) | [7e7660b](https://github.com/StamKavid/nima-ai/commit/7e7660b3838cfe35239ba3dfbd530437bb542fe5) | `7de0b9c` | [43731028497](https://github.com/StamKavid/nima-ai/actions/runs/43731028497) | 1,431 / 92.25% | 12 / 824.38 s |
| G3 [#93](https://github.com/StamKavid/nima-ai/pull/93) | [1f39df4](https://github.com/StamKavid/nima-ai/commit/1f39df48f1a1eb75703e75033d0a2d9d60ad3b4e) | `652e609` | [43734319903](https://github.com/StamKavid/nima-ai/actions/runs/43734319903) | 1,451 / 92.23% | 12 / 647.94 s |
| G4 [#94](https://github.com/StamKavid/nima-ai/pull/94) | [8518a7f](https://github.com/StamKavid/nima-ai/commit/8518a7f729a841c0a251acf0546e659aae0dcd0c) | `eb5d9dd` | [43735285943](https://github.com/StamKavid/nima-ai/actions/runs/43735285943) | 1,462 / 92.31% | 12 / 830.39 s |
| G5 [#95](https://github.com/StamKavid/nima-ai/pull/95) | [e406c02](https://github.com/StamKavid/nima-ai/commit/e406c027c601ec36f36c40e1e4c9973c67b9e80a) | `4a33a3e` | [43739790204](https://github.com/StamKavid/nima-ai/actions/runs/43739790204) | 1,508 / 92.37% | 12 / 833.86 s |

All three hosted jobs pass for each exact candidate: PostgreSQL quality/build/
security/audit, Compose and the complete controlled-worker check. Each worker run
validates one fresh full 28-case fixture receipt. Its Internet-egress,
investigator-IP-protection and production-ready flags remain false. Documentation
candidates have their own PR checks; those add no runtime capability.

G1 preserves caller-owned transaction lifetime and canonical resolution behavior.
G2 verifies corruption/count/byte guards before private payloads, historical
selection and an independent committed revoke inside a pinned read. G3 independently
checks expected graph sets, exact keys/values/locators, focus states, duplicate
handles, outside anchors and review reversals. G4 verifies deterministic private
publication, exact output bounds, all 26 unchanged authoritative relations and
two revoke interleavings: during the pinned read and after SQL closes.

G5 passes 91 focused CLI/crash/legacy checks. Four real child-process cases interrupt
before/after the final `os.link`: two SIGKILL and two SIGINT. Independent
`pg_stat_activity` observation proves SQL connections are already closed before
interruption. Normal uninstrumented CLI retry produces one canonical complete
artifact with the predicted hash; an already-published file retains bytes/mtime,
and all 23 source/workflow plus three review relations remain unchanged. These are
process-failure tests, not server/power-loss/storage-device recovery guarantees.

Mutation regressions detect unsafe read context (G1: one failure), digest-only
stored-fact checking (G2: seven), inverted active acceptance (G3: three; G5 real
CLI: two) and a broken focus-configuration boundary (G4: three). Every experiment
restored exact original bytes before normal gates; no mutant or pause hook was
committed. The shared builder SHA256 remains
`bdcba43f5f5f5747639ac057ec432ab853eee4fa7acc79b7939d156e500eb48c`.

Local SQL verification now uses disposable loopback PostgreSQL 17.11, extracted
outside Git from signature/hash-verified official Debian packages without changing
system packages. G5's complete local gate passes 1,508 tests/92.32%, build/security
and audit. The executor's Docker capacity remains unsupported; full worker evidence
comes from hosted Docker, with no new skip, suppression, dependency or weakened gate.
Earlier runbooks retain their historical local-prerequisite limitations.

An additional local documentation smoke run on main `4a33a3e` uses a disposable
login with exactly the 16-table SELECT grant set above. Three normal CLI calls
produce the same hash/bytes across retry and a different output directory; reuse
preserves mtime, UPDATE is denied and all 26 relations remain unchanged. The stored
synthetic fixture yields seven nodes/seven edges and one reviewed link. Roles,
database and fixture files are removed afterward. This is not a real-company pilot.

## Next product gate

Select a separately authorized private real-company cohort and recover every
displayed active link's original evidence/locations. Record selection, coverage,
contradictions, unresolved cases and numerator/denominator of checked links. Any
critical identity, provenance, date or amount error blocks describing that cohort
as a verified demonstration. No population matching precision follows from a small
example. Live GEMI compatibility remains a separate source gate.

Then observe an investigator trace participation, recover a citation and explain
a changed/revoked link against the manual workflow. Record task completion, critical
errors, time, familiarity and failures. A thin dossier/explorer is a candidate for
a separate product scope. No observed task-time improvement is claimed here.

The [database assessment](../history/graph/database-candidates.md) compares Memgraph/FalkorDB
as prototype candidates, Neo4j as a tooling baseline and AGE/HydraDB alternatives.
No adapter, store or benchmark has been adopted. Broader temporal relationships,
sector eligibility, graph analytics/ML, cited AI, public authentication, browser
workspace and production operations still need their own implementation/evaluation.
