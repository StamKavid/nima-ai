# Offline GEMI evidence persistence

Status: **approved**, 2026-11-10, by explicit user approval before implementation.
Implemented on the delivery branch; personal-key/live profile acceptance is pending.
Provider: `source-ingestion` in CAPABILITIES.md. Supplements the approved
[GEMI profile contract](gemi.md) and SPEC-source-ingestion.md; no new module.

## Objective and assumptions

Make collected registry snapshots durably queryable before company matching or
graph work. An investigator must be able to distinguish what GEMI returned,
when it was observed, and which archived bytes support each assertion.

Build and verify this boundary without a GEMI key, using synthetic archives
produced through the existing collector and mocked HTTP transport. The importer
itself makes no HTTP requests, reads no API key and performs no discovery.
Real-profile compatibility remains a separate personal-key pilot. The earlier
public-test-key request returned HTTP 401; it supplied no accepted profile.

First release imports **one completed, non-quarantined collector run** containing
1–10 selected registry numbers. Each number must have an accounted-for accepted
200 or 404 response. Failed, running, interrupted, quarantined and unknown-format
runs are rejected before any evidence rows are committed. Their files remain
available for investigation; this restriction is not permission to discard them.

The deliverable is registry evidence storage, not company resolution. Matching,
review decisions, graph projection, sector analytics and live-collection changes
remain separate increments. It does not require a generic connector framework.

## Command and structure

Implemented offline interface:

```bash
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima gemi import RUN_ID --archive-dir data/gemi
```

`RUN_ID` identifies an existing collector run under `runs/`. NIMA_DATABASE_URL
remains environment-only. No key, URL override, network fallback, implicit
migration or automatic import of every archive is supported.

Keep Python 3.12, PostgreSQL 17 and locked Psycopg 3.3.8; add no dependency or CI
service. Files: `src/nima/storage/gemi.py`, read-only `gemi_archive.py`, migration `0004.sql`,
CLI routing in `src/nima/__main__.py`, focused `tests/test_gemi_import*.py`, and
`docs/verification/gemi-persistence.md`. Update the existing migration loader
without changing the bytes or checksums of migrations 0001–0003.

Use immutable typed values, explicit unknowns, parameterized SQL, Ruff and strict
mypy. Style excerpt; the implemented summary also includes hash/version metadata:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportSummary:
    run_id: str
    profiles: int
    not_found: int
    reused: bool
```

## Verify the archive before writing

Read an existing recognized archive without creating directories, changing
permissions, repairing files or rewriting manifests. Validate the run identifier
before constructing paths. Reject symlinks, nonregular files, missing objects,
unsafe paths, duplicate JSON keys and malformed or unsupported metadata.
The archive is a private, single-owner local store; this does not establish
protection against an administrator changing it concurrently.

Require supported manifest, connector and normalizer versions; the fixed GEMI
profile endpoint; a matching run identity; canonical, unique selected IDs; aware
timestamps; and reconciled attempts, outcomes and counters. Reconcile supplied
input strings with the canonical ID list without inventing registry-number zeros.
Save an exact manifest-byte snapshot and its SHA-256 in the database.

Bounds: 1 MiB manifest, at most 10 selected IDs, at most 3 attempts per ID,
8 MiB per complete body, 240 MiB aggregate body reads and 16 MiB aggregate
serialized normalized profiles. Reject excess before publication; do not truncate.
Read bodies sequentially rather than retaining the aggregate in memory.

For every complete response referenced by the attempts, verify its archived
SHA-256 and byte length, including retry/error bodies. Transport attempts with
no completed body remain explicitly bodyless. Finished 200/404 outcomes require
the final applicable completed response; an earlier retry must not become the
selected observation. Inconsistent attempt order, terminal status or observation
time fails validation. A pending attempt is incompatible with this release.

Re-run the existing strict GEMI normalizer on every accepted 200 body with its
requested ID. Ignore `normalized.jsonl` as an authority: SQL assertions must come
from verified original bytes. A normalization failure stops the whole import
with a redacted field/reason; it does not silently change the collector outcome.
Existing manifests do not record response Content-Type: preserve that limitation
instead of claiming the importer independently revalidated the original header.

Preserve unknown versus empty values, leading-zero AFM, Greek text, field pointers,
partial-registration flags, KAD code/version and source dates exactly. No numeric
capital value is converted into a financial projection. Retain per-source license
and publisher attribution from the approved contract.

## Additive database boundary

Use a small GEMI-specific aggregate because existing KIMDIS pages/checkpoints and
participation events describe contracts. Do not pretend a company profile is a
procurement page or send it to the KIMDIS projector.

Implemented immutable evidence relations:

| Relation | Identity and purpose |
|---|---|
| `gemi_imports` | Collector run UUID; exact manifest bytes/hash, archive locator, versions, source attribution, reported collection coverage and import time |
| `gemi_responses` | Run UUID, registry number and attempt ordinal; original attempt times/status/failure and optional complete-body reference |
| `gemi_profile_versions` | Namespaced `gemi:<number>`, normalizer version and response-body SHA-256; strict normalized assertions and pointers |
| `gemi_observations` | Run UUID and selected registry number; terminal response reference, original observation time, found/404 outcome and optional profile-version reference |

Reuse `raw_objects` for verified body hash/length metadata; keep bodies in the
archive. A found observation must reference a matching profile version and 200
response. A 404 references its response but creates no profile, deletion or
nonexistence claim. Every selected ID has exactly one observation.

Version identity deliberately uses **response bytes**, including unprojected
fields. Formatting-only changes can create another version; this is not proof of
a business event. Identical bytes under the same extraction version reuse a
profile version. New collector runs always retain new observations, even when
the body is unchanged. A→B→A therefore retains three observations and two versions.
Do not replace source dates with retrieval/import time or synthesize a general
company `lastUpdated` value.

Commit the entire bounded run in one PostgreSQL transaction after validation.
Serialize imports of the same run; identical concurrent/repeated imports must
converge on one verified result. On replay, verify source bytes again and compare
the manifest, selected evidence and stored normalized assertions. Conflicting
run evidence, locator or version contents fails visibly; no silent overwrite.
Reject evidence-row updates/deletes using the existing immutability convention.

An import is complete only when all selected outcomes and their evidence commit
together. A killed worker before commit leaves no partial import; after commit,
replay verifies and reuses it. Import time describes local persistence, not a new
source observation. Filesystem evidence and PostgreSQL are not one transaction;
later archive loss remains possible and must be detectable on verification.

No GEMI events enter the existing procurement outbox in this increment. Preserve
KIMDIS collection, resume, projection and identity-report behavior after explicit
schema upgrade. Source-aware downstream dispatch requires its own later contract.

## Output, testing and acceptance

Stdout exposes only run ID, fixed status/reason, import-format version, manifest
hash and counts/reuse state. Never print company/person names, AFM, raw bodies,
connection strings, keys or driver messages. Exit 0 means a complete verified
import or verified reuse; configuration errors exit 2; validation, archive,
schema, conflict, budget and database failures exit 1; interruption exits 130.
An all-404 import can succeed without demonstrating profile compatibility.

Write failing behavioral tests before implementation. Use existing pytest and
disposable real PostgreSQL fixtures; maintain the 90% combined coverage floor.
Synthetic source fixtures must be labeled and kept distinct from live evidence.

Acceptance requires:

- Successful mixed 200/404 import, exact identifiers, nullable assertions, KAD
  versions, byte hashes, original dates and every selected outcome reconciled.
- Retry/error-body evidence retained; rejected incomplete/quarantined/foreign
  runs, tampering, unsafe paths, unsupported versions, bad counts and all budgets.
- Re-derived assertions despite altered derived JSONL; immutable A→B→A history;
  identical replay/concurrency without duplicates; conflicting replay rejected.
- Atomic rollback and actual child-process SIGKILL before/after commit, verified
  through a new connection. Mutation of a meaningful integrity guard must fail
  the relevant regression test, followed by restoration.
- No network request, API-key dependency or archive modification during import;
  populated v3 schema upgrade and existing KIMDIS workflows still verified.
- Five-axis review, `just check`, `just audit`, and private main-targeted PR with
  hosted CI and StamKavid attribution. No automatic merge or deployment.

## Search runs (slice L5a, migration 0014)

A verified AFM search run ([search by AFM](gemi.md), [SPEC-gemi-afm-import](../specs/SPEC-gemi-afm-import.md))
is imported with `nima gemi import-afm RUN_ID --archive-dir DIR`, which needs `NIMA_DATABASE_URL` and no key.
It re-verifies the archive on every call, writes in one transaction under an advisory lock, and on a repeat
checks that the stored rows are identical and changes nothing.

Four immutable tables, with no grant and a TRUNCATE guard each, leave the profile tables untouched:

| Table | One row per |
|---|---|
| `gemi_search_imports` | imported run: manifest bytes and hash, versions, license, counts |
| `gemi_search_requests` | HTTP attempt, keyed by AFM (nine digits, leading zero kept) |
| `gemi_search_outcomes` | searched AFM: the fixed outcome and the final request it rests on |
| `gemi_search_hits` | returned company, with `afm_matches` and the profile version it points at |

Each hit's normalized payload is also a `gemi_profile_versions` row whose raw hash is the search response's,
so the evidence pointer stays `/searchResults/<i>/...`. Quarantined answers are outcomes without hits; an
unconfirmed quarantine (media type not archived) is flagged. The comparison does not read these tables yet
(slice L5b), and a hit cannot yet be reviewed as an identity (decision L5-2).

## Review and later work

Always preserve assertions, original evidence, observation times and unknowns.
Never infer identity, legal form, ownership, collusion or tax evasion from an
import. Do not add dependencies, alter CI/security constraints, expose a write
API, publish source data or broaden collection as part of this increment.

The additive schema and offline policy were explicitly approved before planning.
Delivery is split into two reviewable PRs: archive verification, then storage/CLI.
The first targets main; the dependent PR targets its branch until the predecessor
is merged, then is retargeted to main. No automatic merge or deployment.
No external-access question blocks this scope. Registry/procurement comparison
can consume these observations
under a separate identity policy; reviewed links precede a resolved temporal graph.
