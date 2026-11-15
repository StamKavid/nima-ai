# Reviewed decisions: operator workflow and measured delivery

The owner merged the write library through #82 (`b37ec70`) and the private
snapshot/operator workflow through #84 (`50b43be`), 2026-11-15. These commands
record an investigator's decision about one occurrence/candidate pair. Acceptance
does not certify legal identity, issuer authority, ownership or wrongdoing.

## Prepare the operator environment

Use the tested Python 3.12/uv environment and PostgreSQL 17. Configure
`NIMA_DATABASE_URL` privately through environment settings. Keep credentials,
source records, rationales and private artifacts outside Git and terminal logs.
No GEMI key or HTTP client is needed for these offline commands.

Database setup remains explicit:

```bash
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima identities review --help
uv run --frozen python -m nima identities resolution --help
```

Migration 0007 adds immutable entity anchors/events and mutable revision heads;
0001–0006 retain their checksums. Review/export never applies migrations or changes
source, projection, outbox or workflow state. No PUBLIC/worker grants are added.

A database administrator owns authentication and grants. A dedicated operator
needs schema usage and SELECT on the stored evidence, migration history and review
relations; writes additionally need INSERT on the three review tables and UPDATE
of `identity_review_heads.revision/latest_event_id`. The disposable-role tests
exercise that limited grant set. Read-only principals cannot perform new writes.
No command provisions roles, grants permissions or exposes a network service.

Attribution is the server's `session_user`, recorded as
`database_principal_only`. A shared or trust-authenticated login does not identify
a human. Database owners/superusers and holders of direct SQL privileges remain
trusted; this is not tamper-proof evidence or a multi-user authorization system.

Prepare an existing private comparison report using the
[comparison runbook](registry-comparison.md). It must refer to supported, projected
KIMDIS occurrences and completed stored GEMI imports. Manually saved Publicity
files remain opaque evidence and cannot substitute for normalized SQL imports.
The original comparison remains immutable and contains no accepted identity links.

## Create a private request

Choose a request UUID once per intended operation; retain it for lost-acknowledgment
recovery. Copy the complete subject and candidate references from the comparison.
Array positions, names and AFMs alone are not subjects. Each observation, role,
ordinal and projection version is separate and inherits no decision automatically.

Create an owner-controlled 0700 directory and 0600 request file with a private
editor, outside Git. The following is a synthetic shape example, not a working
identity assertion: replace every evidence reference and hash with actual report
values. SQL revalidation rejects fabricated or missing references.

```json
{
  "request_format": "nima-identity-review-request-v1",
  "operation": "accept",
  "subject": {
    "run_id": "00000000-0000-0000-0000-000000000001",
    "observation_id": 1,
    "projection_version": "kimdis-participation-v1",
    "source_id": "kimdis:EXAMPLE",
    "normalizer_version": "kimdis-normalized-v1",
    "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "role": "supplier",
    "ordinal": 0
  },
  "candidate": {
    "import_id": "00000000-0000-0000-0000-000000000002",
    "registry_number": "1"
  },
  "expected_revision": 0,
  "report_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "entity_id": "00000000-0000-0000-0000-000000000003",
  "rationale": "Έλεγχος συμφωνίας αναγνωριστικών",
  "acknowledged_issues": []
}
```

The request UUID is a CLI argument, not a JSON field. `expected_revision=0` means
no history for this subject. After review, obtain the current revision from a new
resolution export. Rationales retain original Unicode and whitespace; blank notes
are rejected. Duplicate/unknown JSON fields, wrong types and unsupported versions
fail before SQL. Private reads reject symlinks, unsafe permissions and changed files.

For acceptance, select an entity UUID explicitly. Its first accepted link creates
an `unclassified` handle anchored to that exact found GEMI observation. The same
anchor cannot initialize another handle. Existing handles require the same GEMI
number and their own revalidated anchor; different observations of one number may
still anchor different handles. Consolidation/reanchoring is outside this release.

Acknowledgment must exactly cover the recomputed conflict codes, including
`multiple_registry_numbers_for_reported_afm` and
`reported_afm_changed_for_registry_number`. An outside-report existing anchor
participates in that recomputation. Consent records a decision, not resolution
of the underlying contradiction. A 404, missing candidate or unassessed identifier
cannot become a reviewed match through an override.

For `reject`, omit `entity_id`; conflict acknowledgment is omitted or `[]`.
Keep the report hash and candidate: rejection is a decision about that eligible
pair and creates no entity. It does not declare a company unrelated or a source
false. A later explicit acceptance/rejection can supersede a rejection.

For `revoke`, keep subject/candidate, current expected revision and rationale;
include `reverses_event_id` naming that pair's current acceptance/rejection.
Omit report hash, entity UUID and acknowledgments. It works without the original
report or current eligibility, including historical policy issue labels.

## Record, retry and revoke

Replace UUID/path placeholders with your own private references:

```bash
uv run --frozen python -m nima identities review REQUEST_UUID \
  --request-file data/private-review/accept.json \
  --report-file data/registry-review/REPORT_SHA256.json

uv run --frozen python -m nima identities review REVOKE_REQUEST_UUID \
  --request-file data/private-review/revoke.json

# Recover a committed receipt using its original UUID and exact request payload.
uv run --frozen python -m nima identities review REQUEST_UUID \
  --request-file data/private-review/accept.json
```

A new accept/reject needs its comparison file; omission fails with
`review_evidence` unless an exact committed receipt can be replayed. Revoke never
opens a report, even if a path is supplied. A supplied accept/reject report is
privately decoded and checked against the expected byte hash.

One read-committed transaction locks the exact subject, validates sources/anchors,
reconciles its history/head and atomically commits entity/event/revision. At most
one candidate is accepted for a subject. Direct replacement or rejection of an
active acceptance fails: revoke explicitly, then accept the replacement. An
interruption between those operations leaves the subject unresolved.

Success is printed after COMMIT. Request UUID replay binds exact normalized
payload and database principal, before and again after the head lock. An identical
retry returns the original receipt/revision with `replayed=true`, even after
later decisions; it does not reactivate that old acceptance or describe current
state. Changed payload or another principal cannot reuse a committed UUID. Failed,
rolled-back work reserves no UUID. Paths/server recording time are not identity.

Stdout contains only IDs, revision, fixed operation/status, replay flag and
attribution assurance. Notes, source labels, AFMs, paths and driver details remain
private. Do not infer current state from an old receipt: export a new snapshot.

## Export and interpret current selected state

```bash
uv run --frozen python -m nima identities resolution \
  --report-file data/registry-review/REPORT_SHA256.json \
  --output-dir data/reviewed-resolution --max-events 10000
```

One repeatable-read, read-only transaction validates all selected occurrences,
the full declared registry catalog, selected review history and needed entity
anchors. It uses the report's selected occurrences even after later collection;
report coverage remains `unverified_report_context`, not historical completeness
certification. SQL closes before publication.

The file is `<output-dir>/<report_sha256>.json`, using the existing canonical,
private 0700/0600 no-clobber/hash publisher. The summary contains IDs, counts,
statuses and hashes. Exact reuse preserves an existing artifact; conflicting bytes
are rejected. Hashes identify bytes and do not authenticate or anonymize contents.

`report_format=nima-reviewed-resolution-v1` binds the original comparison hash,
current selected revisions/events and review policy. `comparison_report` preserves
source claims and unchecked authority/issuer fields. `occurrences` retains every
member, with pair states/history IDs; no active acceptance means `unresolved`.
`events` retains original requests, issues, policy, principal, recording time and
terminal candidate provenance, including historical candidates outside the current
comparison catalog. Original notes/events are never rewritten by a revocation.

`entities` retains selected history handles and exact anchor evidence.
`selected_handle_ambiguities` lists multiple selected handles for one registry
number; its scope is `selected_history_handles`, with each handle's active selected
occurrence count. It does not choose a winner or claim global deduplication.
`reviewed_accepted_links` counts accepted selected occurrences separately from
`automatic_identity_links=0`. Accepted review remains separate from source authority.

Stored recording time is not source validity time or global commit order. There
is no generated wall clock, sequence-based global ordering or temporal ownership
assertion. Same selected inputs/heads reproduce bytes; later decisions create a
different artifact. Old exports preserve their original revisions and decisions.

| Bound | Enforcement |
|---|---|
| Request/rationale | 16 KiB request; 4 KiB UTF-8 nonblank rationale |
| Comparison/output | Exact 32 MiB canonical ceiling |
| Occurrences/history | Up to 10,000 report members; requested 1–10,000 selected events |
| Registry context | Complete catalog plus distinct needed anchors, combined at most 100 |
| SQL context | Combined 8 MiB before source labels/notes; extra exported provenance reserves space too |
| SQL execution | Existing 5 s connection/lock and 30 s statement bounds |

Bounds fail without truncation, hidden pagination or omitted conflicting evidence.

## Failures and physical recovery

| Exit | Fixed outcome | Recovery |
|---|---|---|
| 0 | `committed` / replayed receipt; `complete` export, including unresolved state | Inspect the private snapshot and evidence |
| 2 | `configuration`, `review_input` | Correct options/environment or request/report format privately |
| 1 | `review_input_io`, `review_evidence` | Restore private inputs or investigate mismatched/missing source facts |
| 1 | `review_conflict`, `review_state` | Inspect current revision/history; do not overwrite rows or silently reassign |
| 1 | `review_limit` | Choose a legitimate smaller scope; no automatic omission |
| 1 | `review_permission`, `review_schema`, `review_database` | Ask the responsible administrator to inspect the private environment; setup is explicit |
| 1 | `review_output` | Inspect permissions/bytes and retain conflicting artifacts |
| 130 | `interrupted` | Retry the same intended request or export and verify its result |

SIGKILL cannot print graceful JSON. For a lost write acknowledgment, retain the
same UUID and normalized payload and retry; export afterward to see current state.
For interrupted publication, retry normally. A complete reusable artifact or
private `.tmp-*` files may remain; temporary files are not accepted reports. Do
not rename them into place or delete conflicting evidence to force success.

## Measured delivery

| Slice | Final candidate / run | Quality | Full worker suite |
|---|---|---|---|
| RI1 #76 | `90f1138` / [43688164556](https://github.com/StamKavid/nima-ai/actions/runs/43688164556) | 1,188 tests / 92.28% | 12 tests / 718.08 s |
| RI2 #77 | `e4f3b5f` / [43691051026](https://github.com/StamKavid/nima-ai/actions/runs/43691051026) | 1,219 / 92.40% | 12 / 661.92 s |
| RI3 #78 | `1a05fde` / [43692701325](https://github.com/StamKavid/nima-ai/actions/runs/43692701325) | 1,250 / 92.47% | 12 / 713.84 s |
| RI4 #79 | `3225edb` / [43693728353](https://github.com/StamKavid/nima-ai/actions/runs/43693728353) | 1,272 / 92.43% | 12 / 655.10 s |
| RI5 #80 | `884b085` / [43701029607](https://github.com/StamKavid/nima-ai/actions/runs/43701029607) | 1,291 / 92.19% | 12 / 848.00 s |
| RI6 #81 | `cf8dbe9` / [43702642809](https://github.com/StamKavid/nima-ai/actions/runs/43702642809) | 1,303 / 92.26% | 12 / 755.43 s |
| RI7 #82 | `cff6aec` / [43703286067](https://github.com/StamKavid/nima-ai/actions/runs/43703286067) | 1,316 / 92.22% | 12 / 749.21 s |
| RI8 #83 | `04e8789` / [43706527461](https://github.com/StamKavid/nima-ai/actions/runs/43706527461) | 1,336 / 92.08% | 12 / 652.66 s |
| RI9 #84 | `fdf8289` / [43707453503](https://github.com/StamKavid/nima-ai/actions/runs/43707453503) | 1,375 / 92.13% | 12 / 855.34 s |

All three hosted jobs pass for these candidates: quality/build/security/audit,
Compose and the real Docker suite. Each worker verifier accepts one full 28-case
controlled-fixture receipt; internet-egress, investigator-IP-protection and
production-ready flags stay false. Documentation candidates have their own checks.

Independent SQL connections prove exact concurrent replay after a waiting head
lock, competing accepts, cross-subject UUID collisions, entity/anchor creation
conflicts and clean rollback/recovery. Disposable limited logins prove server
principal attribution and denied read-only writes/other-principal UUID reuse;
their grants/roles are removed afterward, only on local `nima_test_*` databases.

Six actual child SIGKILL cases cover accept/reject/revoke before and after real
COMMIT while acknowledgment is unsent. Independent connections observe INTRANS
versus IDLE and committed row visibility before normal-library retry. Two further
cases interrupt real publication before/after its atomic final link, verify SQL
is closed, then retry the normal CLI. All 23 pre-existing source/projection/outbox/
workflow/migration relations retain their complete JSON rows. These are process
failure tests, not server/power-loss/storage-device recovery or deployed operations.

Mutation experiments detected bypasses of request-envelope equality (one failure),
history limits (four), private parser errors (seven) and exact reversal event ID
(one). Every file was restored before normal gates; no mutant or product pause hook
was committed. Final CLI SHA256 is
`b49cc3bd8b5b42a226cbbcc5328116b57ab6144c12f84848bf8454ab95237c28`;
snapshot `c6e8ec3a7ffb8afd5b193c1b6558521ec99f8088f1cde0daa6df3c4df9ba7350`;
shared state `1961d7f4bd7be57534f142a0369299ee85292cbc4b5ff49a77c7cffa63925bed`.
The built wheel matches these restored bytes.

The executor lacks a configured local PostgreSQL server and supported Docker
capacity. Its local first-party checks pass, with SQL fixture setup errors reported
honestly; supported hosted PostgreSQL/Docker provide the physical evidence above.
No new skip, suppression, dependency or weakened gate was introduced.

Live GEMI profile compatibility, empirical matching/false-merge quality, entity
consolidation, production authentication/operations and investigator usefulness
remain separate gates. The next product target is a reproducible company →
procurement → buyer investigation with source evidence; graph, evaluated signals,
cited AI and a browser workspace still require implementation and evaluation.
