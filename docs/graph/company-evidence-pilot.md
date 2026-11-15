# Specification: one-company evidence-recovery pilot

Status: **owner-approved and merged in #98**, 2026-11-15, main `aef9f53`. This follows graph
scope #87, plan #90 and completed checkpoint D (#97, main `686875d`). It specifies
one evaluation capability: determine whether a bounded real-company graph can be
traced to its original records. The owner approved the scope in a later turn.
The proposed [delivery plan](../../tasks/plan.md) needs separate review before code.

## Objective and assumptions

For journalists, independent investigators and researchers, verify a private case
connecting one exact company identity, selected procurement occurrences, contract
versions and buyers to recoverable official evidence. This tests the reliability
of the implemented workflow before expanding the graph, models or interface.

METLEN is the preferred candidate from the owner's earlier request. The brand does
not identify one legal entity or its subsidiaries. Confirm one exact registry
entity and original GEMI/AFM text from official evidence before selecting records;
preserve leading zeros and Greek text. Name similarity cannot establish identity.
No exact identifier or usable real-company archive is confirmed in this proposal.

Assume existing, legitimately obtained KIMDIS and GEMI archives can be made
available privately. The checked project data directories contain no such source
archives. A pending GEMI key is not evidence of access or a completed import.
If archives are unavailable, record the input block; do not replace them with
fixtures, opaque Publicity captures or an invented company profile.

## Cohort and input gate

Freeze a selection manifest before auditing: exact target identity and basis,
one supported comparison report/run, selection rule, publication window, included
contract-version keys, selected occurrences/buyers, omissions and known conflicts.
Choose 1–10 contract versions within existing limits. This is a deliberately small
case, not a representative sample, group consolidation or all-company search.

Required inputs are original archived KIMDIS responses with matching stored
observations/projections; complete supported GEMI profile archives/imports; a valid
private comparison report; and source-supported review decisions for the target.
The existing comparison/import requirements remain unchanged. A GEMI-free graph
extension would need a different scope. Use the existing review workflow only for
explicit human decisions; conflicts require acknowledgment, and no decision
propagates to other occurrences.

At least one target occurrence must have an active reviewed link, with a selected
buyer and recoverable contract/registry citations. Otherwise the demonstration is
`blocked_inputs` or `insufficient_evidence`, with specific reasons. These are pilot
assessment outcomes, not new CLI status values. A successful empty graph is not a
successful real-company demonstration.

## Evidence checks and private outputs

Audit every active `reviewed_as` edge in the complete selected artifact, including
edges outside its optional focus. Freeze and hash the comparison, reviewed
resolution and graph artifacts; preserve source observation times and current
review revisions. Audit each edge against that pinned snapshot, not a changing
live review head. Later review changes produce a separate artifact and assessment.

For every audited link:

1. Recover its original procurement and registry bytes; verify SHA256 against the
   referenced raw objects and identify the exact version/observation keys.
2. Resolve procurement record and registry field pointers in those bytes. Check
   the subject, source identifiers, original labels, role, buyer context and
   registry anchor against the report, stored projection and graph. Reuse existing
   normalizer/codec semantics; retain contrary evidence and missing fields.
3. Check contract net/gross values as exact decimal text, currency and unknowns.
   Keep contract versions and procurement stages distinct; no joint-supplier
   allocation or spending sum. Check source dates separately from observation and
   review times; do not invent validity intervals.
4. Check the exact accepted candidate/event/revision and anchor. Record the human
   identity rationale and unresolved conflicts. SQL consistency and matching hashes
   do not authenticate a publisher or prove that a reported assertion is true.

Store an owner-only 0700 case directory with 0600 files outside Git: the selection
manifest, input/artifact hashes, archive mapping, audit matrix and findings/unknowns.
For each required check, the matrix records the full evidence key and locator,
expected/observed value, reviewer, result and reason. Results distinguish recovered,
missing, mismatch, unknown and not applicable. Required identity/provenance checks
cannot become optional by labeling them unknown. Source-consistent unknown amounts
or dates remain unknown and are not themselves discrepancies.

Report the count of selected contracts/occurrences/active links and checked-link
numerator/denominator, with all exceptions. One accountable human reviewer is
required; disclose self-review and any independent second review. Review notes and
company evidence remain private. Only a separately owner-reviewed redacted method
summary may be published; hashes are not anonymization.

An assessment may conclude `verified_selected_cohort` only with a nonzero active-link
denominator, every required check completed and no unresolved critical identity,
source-hash/pointer, edge, date or amount error. Missing evidence yields
`insufficient_evidence`; a critical discrepancy yields `failed_audit`. Neither is
reported as a verified demonstration. This assessment never changes the graph's
`archive_integrity=not_checked`, `coverage_assurance=unverified_report_context` or
`attribution_assurance=database_principal_only`; it is a separate pinned audit.

## Existing stack, structure and commands

Python 3.12, uv/just, PostgreSQL 17 and locked psycopg/standard-library utilities
remain the stack. `src/nima/graph/` owns graph reads/build/export/CLI;
`src/nima/identity/` owns comparison/review and private publication. Existing graph
and registry tests live in `tests/`; this proposal lives in `docs/graph/`.
No new framework, store, model, schema or normalizer is selected.

After inputs are available, use the existing
[comparison](../verification/registry-comparison.md),
[review](../verification/reviewed-decisions.md) and
[graph](../verification/investigation-graph.md) runbooks. These executable commands
inspect the real interface; they do not request official source data:

```bash
uv run --frozen python -m nima graph snapshot --help
uv run --frozen python -m nima graph snapshot \
  --report-file /PRIVATE_CASE/comparison/REPORT_SHA256.json \
  --entity-id ENTITY_UUID --max-events 10000 \
  --output-dir /PRIVATE_CASE/graph
just check
just audit
```

Replace the private path/hash/UUID placeholders with actual case inputs.
Configure database access privately through `NIMA_DATABASE_URL`, never arguments
or committed files. Focus retains the full selected artifact and registry catalog.
The export command revalidates SQL but does not recover original archive bytes;
the audit above is a separate evaluation, not a claim about existing CLI features.

Follow existing typed Python and fixed-error conventions if an approved later
plan needs small evaluation tooling. For example, the current export boundary is:

```python
snapshot = read_snapshot(dsn, report, max_events=max_events)
try:
    graph = build_graph(snapshot, entity_id=entity_id)
    body = encode(graph)
except AssessmentError:
    raise GraphError("graph_limit") from None
```

This excerpt is from `src/nima/graph/export.py`; SQL closes inside the reader.
Reuse canonical helpers, exact money and bounded inputs; source-bearing values
must not escape through error messages. The snippet proposes no code change.

## Verification and boundaries

Documentation gets link/prose review. Any later tooling must have meaningful
pytest cases for missing/tampered bytes, invalid pointers, incorrect identity,
amount/date discrepancies and non-vacuous denominators. Synthetic regression
fixtures must be labeled and separate from the real-company assessment.
Existing combined coverage stays at least 90%; `just check`, `just audit` and all
three exact-head hosted jobs remain required before merge. No new tests merely
mirror a documentation edit. Existing 100-occurrence/100-registry-anchor,
10,000-event, 8 MiB SQL, 32 MiB private input/output and 600-node/500-edge limits
are unchanged. Later planning must specify any evaluation-specific resource bounds.

- **Always:** preserve original evidence/Greek text/unknowns, document selection and
  contradictions, use private files and explicit human review, report blocked work.
- **Ask first:** source acquisition or changes to access/egress, schema/dependencies,
  CI/limits, public evidence publication, broader cohorts or a new evaluator API.
- **Never:** commit evidence/credentials, infer ownership or wrongdoing from a graph,
  automatically merge identities, bypass source access controls, or call a fixture
  a real-company result. No live collection or IP-protection claim is authorized
  by this offline scope; deployment and public access remain separate work.

Formal investigator timing/usefulness studies, a browser dossier, graph-database
adapters, statistical/ML signals and cited AI are follow-on scopes. Evidence
recovery establishes a prerequisite for those evaluations, not product usefulness,
national coverage, matching accuracy or conclusions about the chosen company.

## Success criteria and open questions

Success requires a frozen, nonempty real cohort with the full audit matrix,
recoverable supporting/contradicting evidence, no unresolved critical discrepancy
and a reproducible private assessment tied to exact input/artifact hashes. A
blocked or failed audit is an honest deliverable but does not satisfy that success
criterion. Proposal/documentation work adds no capability-progress credit.

Before executing the pilot, confirm the exact METLEN legal entity and identifiers,
private archive/database/report locations, the selection window and accountable
reviewer. These are currently unresolved. Approval of this scope permits subsequent
planning; it does not supply missing records or approve live acquisition. After
source correctness is demonstrated, separately specify observed investigator tasks
and a manual-workflow comparison before claiming time saved or differentiated value.
