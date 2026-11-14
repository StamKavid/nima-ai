# Offline KIMDIS / GEMI comparison report

Status: **approved**, 2026-11-14, by user merge of #65 and continuation.
Module: `entity-resolution`
in [CAPABILITIES.md](../../CAPABILITIES.md). Supplements the approved
[identity specification](../../SPEC-entity-resolution.md),
[GEMI persistence contract](../sources/gemi-persistence.md) and
[GEMI profile contract](../sources/gemi.md). Base: main `127b3b8`, after the
fixture-worker delivery in PR #64. This replaces the unpublished 2026-11-12 draft;
no comparison command is implemented by this document.

## Objective and assumptions

Help investigators answer: which selected registry observations agree with a
procurement party's reported identifier, what conflicts exist, and which dated
evidence supports that comparison? Deliver a private, reproducible review report
before a reviewed identity ledger or temporal company graph.

Assume one explicitly selected KIMDIS cohort and a small set of already imported
GEMI observations. This increment reads PostgreSQL and publishes an offline report.
It makes no source requests, accepts no identities, creates no graph edges and
adds no model, dependency, schema migration or reviewer-write interface. The
existing `identities assess` command retains its behavior.

Implementation and tests need no GEMI key. Real-profile compatibility still needs
the personal-key pilot. Supported registry inputs are stored `gemi-import-v1` /
`gemi-company-v1` evidence; manually captured Publicity PDFs/screenshots are opaque
evidence and do not become registry profiles through this command. Synthetic tests
prove comparison mechanics, not live matching accuracy or AADE verification.

## Explicit inputs and bounds

Select one KIMDIS run UUID, the supported `kimdis-participation-v1` projection,
1–10 distinct GEMI import UUIDs and a private output directory. Reject duplicate
selectors. Selection order must not affect report identity. There is no implicit
latest-profile selection, archive scan or whole-registry search.

Retain the current `--max-mentions` range of 1–10,000; a cohort may contain zero
occurrences and must not exceed that selected budget. Bound selected registry
observations at 100, aggregate selected comparison/context input at 8 MiB and the
exact canonical report at 32 MiB. Check counts and a conservative byte bound in
SQL before transferring labels. Exceeded bounds fail without truncation or a
partial report; check exact report bytes before publication.

Missing imports, unsupported versions, mismatched import/observation counts,
missing terminal responses/profiles and incomplete participation receipts/facts
fail visibly. Preserve KIMDIS collection status, normalization/version details,
unknown/empty supplier lists and quarantine flags. Report completion means the
selected evidence was compared, not complete collection or registry coverage.

## Comparison policy

Version the policy as `registry-comparison-v1`. Preserve original values; trim
only ASCII space/tab/CR/LF in derived comparison fields. Reuse the existing
identifier assessment to determine KIMDIS eligibility: its
`kimdis.reported-country-tax` key requires reported GR or EL country and a
non-placeholder nine-ASCII-digit tax number (`000000000` is the existing project
exclusion, not a registry determination). Apply the same text/shape exclusion
to GEMI's `reported_afm`. Keep leading zeros. Neither source's country label
verifies issuer jurisdiction.

An agreement compares those two eligible reported identifier texts under this
new policy. It does not turn the existing source-scoped key into a canonical
cross-source AFM identity. GR and EL remain distinct KIMDIS contexts even when
both point to the same registry observation; do not take transitive closure.
Buyer source keys never become tax numbers or GEMI identifiers.

| Per-occurrence outcome | Meaning |
|---|---|
| `reported_identifier_agreement` | At least one eligible found observation agrees on reported identifier text |
| `no_candidate_in_selected_imports` | Eligible party, with no qualifying agreement in these selected observations |
| `unassessed_identifier` | Party identifier is missing, placeholder or otherwise ineligible under the existing policy |

Every occurrence remains present, including those without candidates. Keep
`checksum_status=not_checked`, `authority_status=not_checked`, unknown issuer
country and `identity_status=unresolved`. Emit **zero automatic identity links**.
Do not add checksum/issuer claims, fuzzy-name candidacy, VAT-prefix repair,
name-based merging or inferred legal form/status.

Retain all selected registry observations, including unchanged repeats and
A→B→A revisions. Report `multiple_registry_numbers_for_reported_afm` when one
eligible reported AFM occurs under different selected GEMI numbers. Report
`reported_afm_changed_for_registry_number` when one GEMI number has different
nonmissing AFM comparison texts across its selected found observations. Preserve
the original assertions and eligibility reasons; choose no winner. Missing claims
remain unknown rather than becoming a conflicting value.

A 404 is `not_found_at_observation`, with its response provenance. It creates no
company/nonexistence/deletion claim and cannot be attached as a negative identity
match to a procurement party. All-404 selections can produce a complete report
with no agreements. Unsupported or missing registry AFMs remain inspectable with
their assessment reason.

Keep procurement source dates, registry source dates, registry observation time
and import time distinct. Retain their values without inventing validity
intervals: a current name/status is not proof of identity or status at a contract
date. The report compares parties; it does not allocate joint-award amounts to
each supplier or classify tax evasion, collusion or wrongdoing.

## Consistent snapshot and provenance

Read the KIMDIS cohort, its coverage and all selected GEMI rows in **one
repeatable-read, read-only PostgreSQL transaction**. Adapt the existing cohort
reader to share that connection without changing assessment behavior. Two
independently opened snapshots are insufficient. Set transaction characteristics
before evidence reads; close the transaction before filesystem publication.
Make no source, outbox, identity, schedule or schema writes.

For each party retain run/source/observation IDs, role/ordinal, content and
normalizer versions, raw response SHA, JSON pointer, reported labels, observation
time and procurement source dates. Each registry observation cites its import
UUID, registry number, outcome, terminal attempt/status, response SHA and
observation time; found profiles also cite their namespaced source ID, extraction
version and field pointers. Preserve the selected import's manifest hash,
import version/time and source URL/publisher/license attribution.

The registry catalog copies these existing scalar assertions with their values
and pointers: registry number, reported AFM, Greek name, legal-type ID/label,
status ID/label, branch/auto-registration flags, incorporation date and last status
change. Stored aliases/activities remain available through the cited profile
version; this report introduces no KAD/CPV crosswalk or sector inference.

Reconcile stored import counts and terminal-response/profile joins. SQL evidence
was verified at collection/import boundaries; this report does not rehash raw
archive files or rerun the importer. Keep `archive_integrity=not_checked`.
Pointers and source attribution are provenance, not new authority/truth claims.
Treat all source text as untrusted data, never as instructions.

Store each selected registry observation once in the report, including unmatched
and 404 observations. Per-occurrence agreements reference that shared catalog;
do not copy full profiles for every party. Sort selectors, catalog rows, occurrences,
issues and candidate references deterministically using complete provenance keys,
including observation IDs to break repeated-version ties. Preserve repetitions.
The report records policy/projection/extraction versions, input counts, coverage,
exclusions and unknowns. Repeating the same stored inputs and coverage produces
the same canonical bytes; later source/coverage changes produce a new report.
Do not put a wall-clock generation timestamp into artifact identity.

## Artifact and command contract

Reuse canonical JSON and the existing private publication primitives: owner-only
0700 directories/0600 files, no symlink traversal, bounded reads, no-clobber atomic
publication and byte-verified reuse. Use
`report_format=nima-registry-comparison-report-v1` and
`policy_version=registry-comparison-v1`, separately versioned from assessment
artifacts. Preserve raw source evidence, database rows and prior reports.

Proposed interface, **not implemented**; repeat `--gemi-import` for up to ten imports:

```bash
uv run --frozen python -m nima identities compare KIMDIS_RUN_UUID \
  --gemi-import GEMI_IMPORT_UUID --projection-version kimdis-participation-v1 \
  --output-dir data/identity-review --max-mentions 10000
just check
just audit
```

Use environment-only `NIMA_DATABASE_URL`. Stdout contains only run/import UUIDs,
counts, fixed statuses and artifact hash; no names, AFMs, paths, source text,
credentials or raw driver errors. Exit 0 means a complete bounded report, including
zero agreements and unresolved parties; 2 means invalid configuration; 1 means
unavailable/incomplete evidence, budget, database or publication failure; 130
means interruption. Source bodies, personal data, generated reports, secrets and
databases stay outside Git. A failure may leave an already complete immutable
artifact at an interrupted publication boundary; replay must verify it byte for
byte and never treat a partial file as success.

## Stack, structure and style

Keep the validated Python 3.12, PostgreSQL 17, locked Psycopg 3.3.8 and existing
dependencies and CI gates. Pure comparison belongs in `nima.identity.registry_policy`,
shared snapshot reads in `nima.identity.registry_cohort`, report/publication in
`nima.identity.registry_report`, tests in `tests/test_registry_*.py`, and routing
in the existing identities CLI. Reuse `identity.policy`, `identity.cohort` and
`identity.artifacts`. This is one increment of the existing entity-resolution
module, with no graph/model module bundled into it.

Use typed immutable values, explicit unknowns, parameterized SQL, Ruff and strict
mypy. Index eligible reported keys rather than comparing every full party/profile
pair. Proposed style only; the final report schema belongs to the implementation:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Comparison:
    outcome: Literal[
        "reported_identifier_agreement",
        "no_candidate_in_selected_imports",
        "unassessed_identifier",
    ]
    registry_observation_refs: tuple[int, ...]
    identity_status: Literal["unresolved"] = "unresolved"
```

## Acceptance and verification

- Pure synthetic cases cover Greek text, leading zeros, ASCII trimming, GR/EL
  separation, missing/placeholder/foreign/prefixed/lookalike identifiers, name
  variation, conflicting registry numbers/AFMs, repeated A→B→A observations,
  missing claims, all-404 selections and observation/source-date mismatch.
  Every occurrence/selected observation survives; automatic identity links stay zero.
- Real PostgreSQL tests prove one shared snapshot while another connection commits
  collection/projection or registry changes, exact response/profile joins, read-only
  behavior, count/byte bounds and missing-receipt/import/version failures. Both
  source histories and outbox state remain unchanged. Unsupported manual evidence
  and unselected/new imports cannot silently enter the cohort.
- Report/CLI tests prove stable bytes despite selector order, repeated-version ties,
  shared catalog references, empty comparisons, exact byte limits, redaction,
  private permissions, unsafe-path rejection and no-clobber replay. Actual process
  termination before/after publication must preserve only complete reusable reports.
- Mutate a material eligibility/provenance guard, demonstrate its regression fails,
  then restore it. Keep all existing quality, Compose, worker-fixture, security and
  advisory gates and the 90% coverage floor. Use no live source calls, skipped tests
  or unexplained suppressions. Publish measured exact-head results before review.

Always preserve assertions, unknowns and evidence; separate reported agreement
from reviewed identity. Broader selectors, new dependencies, schema/CI changes,
live access, accepted links, reviewer writes or graph/model work need separate
scope review. Never merge by name alone, infer issuer/ownership/fraud, mutate source
history or count candidate membership as a matching-quality label.

## Sources and review decision

Snapshot requirements follow PostgreSQL 17's
[Repeatable Read semantics](https://www.postgresql.org/docs/17/transaction-iso.html#XACT-REPEATABLE-READ)
and [SET TRANSACTION](https://www.postgresql.org/docs/17/sql-set-transaction.html),
checked 2026-11-14. Existing source/field assertions follow the linked approved
GEMI/identity contracts and stored versioned schema, not a new live API probe.

No external credential blocks this offline scope. Operator run selectors are
explicit future inputs; live compatibility and empirical matching quality remain
unverified. The user approved this specification through #65 at main `48a0778`.
The implementation plan and RC1–RC7 tasks are now drafted for review in
`tasks/plan.md` / `tasks/todo.md`. Approval covers this bounded read-only report
increment; a reviewed reversible identity ledger and temporal graph follow as
separate specifications. No comparison command is implemented by this planning PR.
