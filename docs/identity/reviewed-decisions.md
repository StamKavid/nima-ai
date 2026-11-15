# Reviewed, reversible identity decisions

Status: **scope approved** by owner merge #74 at `2428b9d`, 2026-11-15.
No interface or migration below is implemented. Module: `entity-resolution` in [CAPABILITIES.md](../../CAPABILITIES.md).
Supplements the [approved identity specification](../../SPEC-entity-resolution.md)
and [implemented comparison contract](registry-comparison.md). Base: main
`d6c1552`, after human merge of #73. This proposal earns no completion credit.

## Objective and assumptions

Let a local investigator accept or reject a specific reported-identifier candidate,
explain the decision and revoke it later without changing any source observation.
The result is a bounded, reproducible reviewed-resolution snapshot that a later
graph projection can consume. Human acceptance records an investigator's decision;
it does not verify issuer, legal form, ownership, authority or wrongdoing.

Assume a trusted local operator CLI backed by PostgreSQL, existing stored KIMDIS /
GEMI evidence and an existing private comparison report. No public write API,
browser UI, shared-reviewer service or external identity provider is included.
Reviewer attribution is the database session principal, not a verified human name.
No live source call, GEMI key, hosted model or empirical accuracy claim is needed.

The proposed new scope includes append-only identity tables, an explicit migration,
a local decision-write command and a read-only private snapshot command. Scope
approval must cover those changes; this specification does not execute them.
The implementation plan/tasks are now proposed for their own review in
[tasks/plan.md](../../tasks/plan.md) and [tasks/todo.md](../../tasks/todo.md).

## Review unit and stable identifiers

A subject is one exact projected procurement occurrence: run UUID, observation ID,
projection version, source ID, normalizer/content hashes, role and ordinal. Resolve
that tuple against existing SQL facts; an artifact array index alone is not a
subject identifier. New observations, revised records and other roles are distinct
subjects and inherit no decision automatically.

A candidate is an exact GEMI observation `(import UUID, registry number)`, with its
terminal response SHA, observed time and extraction version. Repeated imports,
unchanged bodies and A→B→A observations remain separately inspectable. A registry
number alone is not a dated observation or proof of historical continuity.

A stable internal `entity_id` is an operator-selected UUID, independent of AFM,
company names or graph IDs. It is created atomically on the first accepted link,
anchored to that found registry observation. It represents a reviewed party handle;
its kind remains `unclassified`. Rejection creates no entity.

For this first release, another accepted observation attached to that handle must
report the same GEMI number as its anchor and still pass explicit review. Different
registry numbers cannot share a handle. The same exact anchor cannot initialize
two handles. Different observations of one registry number can anchor distinct
handles: expose ambiguity among selected handles in snapshots, without
deduplicating, choosing a winner or asserting global uniqueness. This favors
explicit unresolved duplication over a false entity merge.
Entity merging, splitting, reanchoring and canonical-name editing are later scope.

When selecting an existing handle, also revalidate its exact anchor against SQL
and include that anchor in the reviewed evidence context. Recompute conflicts
over the selected catalog plus this anchor, deduplicating only identical observation
keys for policy input. A changed nonmissing AFM for the same GEMI number requires
`reported_afm_changed_for_registry_number` acknowledgment even if the anchor was
outside the supplied report's selected imports. Same registry number is a
compatibility guard, not sufficient evidence by itself. This bounded anchor check
does not claim to inspect all past profiles or all reviews of the handle.

## Report and evidence boundary

Accept/reject requests cite a private `nima-registry-comparison-report-v1` artifact
and its SHA256. Enforce the current comparison/procurement/projection versions,
strict shape, unique full-provenance occurrence/catalog keys and bounded input.
Hash agreement verifies selected bytes, not authorship or authenticity.

Before deciding, resolve all evidence used by the decision against immutable SQL
rows in the same transaction: selected run/occurrence and its original labels,
body hash/pointer, candidate import/terminal response/profile, scalar assertions
and source/observation/import dates. Recompute the existing pure eligibility and
agreement policy; do not trust a copied outcome, reference index or issue list.
Reconcile the entire registry catalog against all declared selected imports,
including unmatched/404 rows and counts; an omitted conflicting observation must
not disappear from the recomputed policy. Reject missing, unsupported, mismatched
or malformed evidence with a fixed reason. Do not rehash raw archive bodies or
silently import missing evidence.

A report can predate later collection coverage. Do not invalidate its immutable
occurrence merely because more observations arrived, and do not certify historical
coverage from an unsigned file. Retain the supplied report coverage as report
context only; it cannot authorize a decision, prove completeness or hide missing
references. Snapshot selection means the subjects present in that report, not all
records that now exist in its run. Every selected subject must still be represented.

Only an existing `reported_identifier_agreement` under the unchanged policy is
reviewable in this release. `unassessed_identifier`, no-candidate and 404 rows remain
inspectable but cannot be converted into accepted identities or negative matches.
No name matching, prefix repair, checksum/issuer inference or manual unsupported
match override is introduced. Broader evidence/manual adjudication needs its own
source-validation policy.

## Actions, state and reversal

A review pair is `(subject, candidate observation)`. Each pair has a derived current
state: `unreviewed`, `accepted` or `rejected`. Decisions are immutable events.

| Operation | Preconditions and effect |
|---|---|
| `accept` | Revalidated eligible agreement; target entity UUID; required rationale; exact acknowledgment of all current pair conflict codes. Creates or explicitly selects a compatible handle and records one accepted pair |
| `reject` | Revalidated eligible candidate; required rationale; no entity UUID. Records rejection of this pair only, without declaring the company unrelated or the source false |
| `revoke` | Names the current accept/reject event of that exact pair, with rationale. Appends a revocation and returns that pair to `unreviewed`; it never revives an earlier event |

A new accept/reject cannot supersede an active acceptance, even for the same
pair/entity; only an identical request replay can reuse it. Revoke it explicitly
first. A current rejection may be superseded by a new accept/reject with history.
At most one pair may be actively accepted for a subject, even if another pair
would target the same handle. Rejecting a different pair does not erase an active
acceptance. Reassignment requires revoking the active acceptance, then explicitly
accepting the replacement; interruption between them leaves the subject unresolved.
There is no cascade to other occurrences, registry observations or handles.

Accept acknowledgment must exactly cover the recomputed pair/anchor conflict codes,
including `multiple_registry_numbers_for_reported_afm` and
`reported_afm_changed_for_registry_number` when present. Store the codes and
rationale together; acknowledgment is not evidence that a conflict is resolved.
Rejection and revocation retain the original issues and require no fabricated
supporting evidence. No active decision means unresolved, not rejected.

Revocation depends on the stored event and current subject revision. It must
remain possible without reopening the original report or archive, and must not
require the candidate to remain eligible under a later policy. Preserve the
original decision's references and policy; revocation does not rewrite them.

Recording time is a server-generated UTC timestamp. It is not source validity
time or a finding that the company had a role on a contract date. This release
assigns no legal-validity intervals and offers no timestamp-based global “as of”
query. Human-reviewed state and unchanged unchecked authority fields stay separate.

## Atomicity, concurrency and authorization

Each request supplies a unique UUID and expected subject revision (`0` for no
history). A successful request appends exactly one event and advances that subject
revision once. Validate the complete request/evidence before committing any entity,
event or head update. Conflicting writes cannot create two accepted pairs.

Serialize modifications for the subject and compare the expected revision in the
same transaction as the append and head update. Stale revisions, competing accepts,
altered payload reuse and incompatible handles fail without partial changes.
A new reject/accept can supersede a pair's current rejection explicitly in history;
it cannot replace an active acceptance or silently replace another pair.

Idempotency binds request UUID to the exact normalized operation payload and
recorded database principal. An identical replay by that principal returns the
original committed event even if later decisions advanced the subject revision.
Check that identity before applying the stale-revision test. Changed content or
another principal reusing a UUID fails; never overwrite or disclose prior private
payloads. Paths and server recording time are not operation identity. Lost
acknowledgment after commit is recovered by retrying the same request UUID/payload.

Events and entity anchors are append-only. A mutable per-subject head is concurrency
state and must reconcile with the event fold; it is not independent evidence.
Preserve migrations 0001–0006 and all existing source/projection/outbox/workflow
relations, immutable triggers, delivery state and report behavior. Add no ingestion
event, scheduling action or implicit migration from a review command.

Use only environment-supplied `NIMA_DATABASE_URL`. PostgreSQL's configured login
and grants define this local trust boundary. Record `session_user` from the server;
request files cannot choose or spoof it. Expose attribution assurance as
`database_principal_only`; a shared/trust-authenticated database account does not
prove which human acted. Existing read-only principals must be unable to write.

The explicit migration must not grant PUBLIC or ingestion workers new review
privileges. Operator-specific grants are deliberate administrator setup, not
performed implicitly by the command. No service is exposed on a network. Database
owners/superusers are trusted administrators who can bypass ordinary constraints;
this ledger is not tamper-proof evidence against them. Multi-user attribution,
permissions and deployment require a separate authentication/authorization design.

## Proposed private CLI and artifacts

These commands are proposed and must not appear as implemented help routes yet:

```bash
uv run --frozen python -m nima identities review REQUEST_UUID \
  --request-file data/private-review/request.json \
  --report-file data/registry-review/REPORT_SHA256.json

# A revoke request names its prior event; it needs no report file.
uv run --frozen python -m nima identities review REQUEST_UUID \
  --request-file data/private-review/revoke.json

uv run --frozen python -m nima identities resolution \
  --report-file data/registry-review/REPORT_SHA256.json \
  --output-dir data/reviewed-resolution --max-events 10000
```

Accept/reject request format `nima-identity-review-request-v1` includes operation,
expected report SHA256, full subject key, candidate import/number, expected subject
revision, rationale and conflict acknowledgments; `accept` additionally includes
entity UUID. Revoke includes the exact subject, candidate, event-to-revoke,
expected revision and rationale, without a report requirement. Reject unknown or
duplicate JSON keys, non-finite numbers, wrong types, blank rationales and unsupported
versions; never echo a bad value. Preserve original Unicode and rationale text.

Read only owner-controlled regular private files without symlink traversal. Bound
requests at 16 KiB and rationales at 4 KiB UTF-8; comparison files at the existing
32 MiB ceiling. Keep credentials, source labels and free text out of arguments,
stdout, logs and Git. Request UUIDs and expected revisions are explicit operator
inputs, not generated anew on retry.

Resolution export uses one repeatable-read, read-only snapshot and revalidates the
selected report references. Retain all selected occurrences, including unreviewed,
rejected and revoked cases; include current pair states, selected event history,
entity anchors and their additional evidence context, observed subject revisions,
original report hash and source refs.
Mark report-supplied coverage as context, keep `automatic_identity_links=0`, and
count reviewed accepted links separately. Do not mutate old comparison reports.

Use `report_format=nima-reviewed-resolution-v1` and
`review_policy_version=reviewed-identity-v1`. Bind artifact identity to the exact
selected heads/event IDs, report hash and policy, with deterministic full-provenance
ordering and no wall-clock generation field. PostgreSQL sequence allocation or
recorded timestamps must not be presented as global commit order. Same inputs and
heads reproduce bytes; later decisions produce a different snapshot. Previously
published snapshots remain immutable; their contained event IDs/revisions record
what was reviewed then. They do not silently adopt later reversals.

Retain the report's 10,000-occurrence limit. Count its complete registry catalog
and any additional distinct entity-anchor observations against one combined
100-registry-observation budget, on writes and exports; overlapping observation
keys count once. Fail rather than omit catalog/anchor evidence. Bound selected
review history at the requested 1–10,000 events, combined selected SQL source/ledger context transfer at 8 MiB
before materializing private text, and exact canonical output at 32 MiB. Fail without
truncation or hidden pagination. Reuse the current private 0700/0600 no-clobber/hash
publisher; close SQL before publication. An interrupted export may leave a complete
reusable artifact or private temporary files, never an accepted partial report.

Write summaries contain only request/event/entity UUIDs, revision, fixed operation/
status and replay flag. Snapshot summaries contain only IDs/counts/statuses/hash.
All commands use exits 0 (complete/replayed, including unresolved subjects),
2 (invalid configuration), 1 (evidence, permission, conflict, database, budget or
publication failure) and 130 (graceful interruption), with fixed value-free reason
codes. Rejection is a successful recorded review, not a command failure. SIGKILL
cannot report graceful JSON; retry must distinguish committed from uncommitted work.
No batch acceptance, bulk import, public read endpoint or free-text search is included.

## Stack, structure and style

Retain Python 3.12, PostgreSQL 17, locked Psycopg and current dependencies/CI.
Implementation will stay within `src/nima/identity/`, an explicit additive storage
migration, existing CLI routing, `tests/test_identity_review_*.py` and verification
docs. Exact table/module decomposition belongs to the later implementation plan.
Separate pure event folding, SQL transactions and private artifact publication.
Use immutable typed values, explicit unknowns, parameterized SQL, Ruff and strict
mypy. Illustrative style only, not a committed implementation:

```python
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class ReviewState:
    subject_revision: int
    state: Literal["unreviewed", "accepted", "rejected"]
    event_id: UUID | None
    entity_id: UUID | None
```

Existing validation commands remain:

```bash
just check
just audit
just source-worker-check
```

The implementation plan must supply focused executable test commands once files
are defined. No skipped tests, scanner exclusion, coverage reduction or installed
skill modification is authorized by this proposal.

## Acceptance and evaluation gates

- Pure state tests cover accept/reject/revoke, supersession, no resurrection,
  multiple rejected candidates, refusal of direct replacement/rejection of an active
  acceptance, one accepted pair, entity compatibility, explicit
  conflict acknowledgments (including an existing anchor outside the report) and
  no propagation across observations or revisions.
- Real PostgreSQL tests prove append-only events/anchors, exact evidence joins,
  atomic entity/event/head writes, rollback, identical replay after later decisions,
  conflicting UUID payloads/principals, missing privileges and unchanged source,
  outbox/projection/workflow state. Independent connections race on one subject;
  at most one conflicting acceptance commits and the loser gets a fixed failure.
- Mutated/forged report references/outcomes/issue lists must not authorize a write.
  Historical report coverage does not override SQL evidence or become a completeness
  claim. 404/ineligible/no-candidate rows cannot be accepted or negatively matched.
- Actual child-process SIGKILL before/after SQL commit proves retry creates at most
  one committed event/entity and no partial source state. Revoke works without a
  report file. Test graceful interruption and lost acknowledgment separately.
- Read-only exports reconcile every selected subject/event/head, retain ambiguity,
  reproduce canonical bytes and preserve old snapshots after reversal. Test concurrent
  later decisions, exact input/output budgets, permissions, symlinks, collisions,
  and actual export publication termination/replay using child-only interception.
- CLI tests verify private request validation, all exits, database-principal
  attribution, no API-key/HTTP use and redaction of source text, notes, paths,
  credentials and raw driver errors. Mutate a material concurrency/reversal guard,
  show a relevant regression fail, restore exact bytes and rerun normal gates.
- Keep at least 90% combined coverage and all three exact-head hosted checks.
  Synthetic mechanics do not establish matching accuracy: accepted/rejected reviews
  are selected investigator judgments, not verified ground truth or fraud labels.

## Boundaries and review decision

Always preserve evidence, uncertainty, original decisions and revisions. Require
explicit review for each accepted occurrence and retain unresolved selection members.
Never merge by name/AFM shape, mutate source history, create automatic links,
infer legal form/ownership/collusion, or silently rewrite a published snapshot.

Scope approval through #74 covers the local database-principal trust model, bounded
eligible-candidate review, stable unclassified handles, explicit additive ledger
migration/writes and private snapshot export. Changes to dependencies, CI, source
access, public services, multi-user authentication, manual unmatched adjudication,
entity merge/split/reanchoring, graph projection or models need separate review.

No external credential blocks this proposed offline scope. There are no additional
required operator preferences before scope review; the stated assumptions can be
changed by explicit scope review. The proposed implementation plan/tasks remain
unapproved; do not implement them or apply database/admin changes before that
review. This planning PR contains no application code, DDL or role/grant action.
