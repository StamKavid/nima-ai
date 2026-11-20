# SQL/dbt experiment — 2026-11-17

**Recommendation: retain packaged SQL and Prefect for this readout.** dbt passed
the bounded experiment and provides useful model/test artifacts. One metric does
not yet justify a second production model system, SQL definition and publication
protocol. No application dependency, runtime requirement, CI job, source schedule,
migration or authoritative serving path changed. The owner merged #119/#120 into
main at `3cd4f77` and requested continuation on 2026-11-17, completing V-D review.
Retain SQL/Prefect and the isolated experiment; the
[real-data pilot](../../verification/market-readout.md) remains a separate input/task gate.

Tested: Core **1.11.17**, Postgres adapter **1.11.0**, Python **3.12.14**,
PostgreSQL **17.11**, Linux x86-64. This implements PV8–PV9 of the approved
[plan](../../../tasks/plan.md), after owner-merged #117/#118 completed V-C.

## Inputs and prerequisites

The baseline is an actual managed **synthetic** capture: eight source IDs, eleven
observations, ten versions and thirteen supplier mentions. The application
projected it, read it through a SELECT-only role and reconciled every original
page before export. Sealed CSVs retain facts and original-record citations; full
normalized/text evidence stays in the private application report.

The hand-labelled answer is total five: B1=A/C/H, B2=D, unassigned=E.
Cancellation counts are false=3, true=1, unknown=1; F is unassessed, G has tied
conflicting versions, and the latest B removes the supplier.

A separate non-superuser builder owns the experiment schema in a separately
named disposable database and cannot read application evidence. All 26 reference
tables are unchanged. Model execution disabled usage reporting and refused Python
HTTP, nonlocal DNS and nonlocal socket calls; no refused runtime call occurred.
The native Postgres driver used configured loopback. This is not a deployed
network-isolation attestation. Package/advisory/document downloads were setup;
no source acquisition occurred during this experiment. The later separately
authorized real pilot is recorded in [market-readout.md](../../verification/market-readout.md).

The [isolated lock](pipeline_dbt/uv.lock) resolves 55 external
distributions, 54 applicable on tested Linux. All 55 compatible wheels were
hash-checked; license metadata and packaged texts were reviewed. The applicable
54-package Python advisory audit reports zero known vulnerabilities. Bundled
native-library CVEs and redistribution/legal approval were not assessed.

Core and its adapter/common/protos/semantic-interface packages use Apache-2.0.
Other licenses include MIT, BSD, MPL-2.0 and PSF-2.0. `psycopg2-binary` 2.9.13 is
LGPL-3.0-or-later with its stated OpenSSL linking exception. `text-unidecode` 1.3
offers Artistic or GPL terms; this self-hosted experiment uses the Artistic option.
The dependency graph is not uniformly Apache-2.0.

Isolated install, CLI import/help and the actual Postgres-driver connection pass.
The pinned source confirms `DBT_SEND_ANONYMOUS_USAGE_STATS=false`; optional
`dbt --version` performs a separate PyPI lookup. Versions were read locally with
`importlib.metadata` instead.

## Correctness and failure results

The manifest has **two seeds, three models and 28 data tests**. Explicit text
types preserve leading-zero identifiers. Tests check observation/ordinal
uniqueness, required fields, relationships, supplier states, version-fact
consistency, supported transformations, citations and count reconciliation.
Repeated source IDs remain valid observation history.

Fifteen successful runs compare **complete metric payloads, revision decisions
and observation/citation sets** against both the pure provider and packaged SQL:
baseline, unchanged repeat, earlier cutoff, before-capture cutoff, unmatched key,
fractional timestamp, re-observed version, A→B→A, unknown list, empty list,
unassessed country, empty capture, ASCII whitespace/EL alias, non-ASCII identifier
space and Greek buyer key. All five consumer outcomes are exercised. A→B→A
returns six; the earlier cutoff returns two; the ordinary baseline returns five.

Only baseline is an original-byte-verified capture. Edge cases are derived
synthetic semantic inputs, not newly observed publications. Restoring baseline
after defects/mutations reproduces its metric and evidence hashes.

| Injected defect | Actual failing test | Result view after failure |
|---|---|---|
| Duplicate observation ID | Observation uniqueness | Readable; domain flag false |
| Orphan supplier mention | Relationship | Readable; domain flag true |
| Duplicate supplier ordinal | Composite-key uniqueness | Readable; domain flag false |
| Conflicting facts under one version | Domain check | Absent |
| Unsupported normalizer | Domain check | Absent |

All five return exit 1 with failing data tests. In-place `dbt build` is not an
atomic release of the whole graph. View existence or `quality_ok=true` is
insufficient publication evidence. Future integration needs sealed inputs,
separate generations and publication gated on every required run/test result.
The application readout remains the private publication boundary.

Independent checks caught two defects outside generic tests. An initial citation
formatter truncated fractional seconds; retaining original capture text fixed the
evidence mismatch. Deliberately filtering suppliers before selecting revisions
produces **7 instead of 5**, while all **28 generic tests pass**; the independent
semantic oracle rejects that mutation. Restored SQL returns five.

The dbt DAG supplements record-to-original attribution; dbt does not perform the
application's original-byte verification. The experimental SQL port records the
authoritative SQL and definition hashes, without becoming a certified production
definition. Production adoption would need one authoritative definition.

## Measured effort and cost

| Operation over successful scenarios | Median | Range |
|---|---:|---:|
| dbt build, CLI startup and 28 tests | 3.93 s | 3.58–4.28 s |
| Packaged reference SQL query | 4.01 ms | 3.56–6.92 ms |
| dbt view query | 9.64 ms | 7.54–43.40 ms |

The view returns evidence/quality with the metric; reference SQL returns the
metric. These are diagnostic timings on 0–12 observations, not equivalent-payload
throughput benchmarks or production latency claims. No volume, concurrency or
memory benchmark was performed.

Initial lock resolution took 1.59 s according to uv; initial seeding took 3.63 s.
Setup also required a separate profile/role/database, typed seeds, license and
advisory review, a runtime guard and independent semantic/evidence oracles.
The core project/models/tests add 282 lines plus isolated prerequisites.
Revisit adoption when several cross-source curated models make DAGs/tests/docs
reduce measured maintenance effort. Keep Prefect for coordination and Python for
acquisition. Adoption needs a separate dependency, release and operating review.

## Reproduction and retained proof

Use a new disposable PostgreSQL 17 database named `nima_dbt_test_*`. Pre-create
`nima_dbt_experiment` under a dedicated builder without application access. Copy
`profiles.example.yml` to a 0700 private directory as `profiles.yml` (0600).
Privately set `NIMA_DBT_PORT`, `NIMA_DBT_USER`, `NIMA_DBT_DATABASE` and optional
password; the profile fixes loopback. Verify those disposable identities first.
Set a private umask and absolute paths outside Git for `DBT_PROFILES_DIR`,
`DBT_LOG_PATH` and `DBT_TARGET_PATH`; preserve configured CA/proxy controls.
Measured runs additionally used a Python HTTP/socket guard.

```sh
uv sync --frozen --no-build --project experiments/pipeline_dbt
DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1 OTEL_SDK_DISABLED=true \
  DBT_PARTIAL_PARSE=false experiments/pipeline_dbt/.venv/bin/dbt \
  --no-send-anonymous-usage-stats seed --project-dir experiments/pipeline_dbt
DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1 OTEL_SDK_DISABLED=true \
  DBT_PARTIAL_PARSE=false experiments/pipeline_dbt/.venv/bin/dbt \
  --no-send-anonymous-usage-stats build --project-dir experiments/pipeline_dbt
```

Use `build`, including tests. Pass cutoff/key cases through JSON `--vars`; change
only private seed/project copies for defects. Provider APIs `Observation`,
`Supplier`, `evaluate`, `sql_rows` and `reference_sql` supply independent pure and
bound-SQL comparisons. Compare entire payloads and citations. Public CSV replay
does not repeat byte verification; that requires the private originals.

Exact commands/vars, inventories, compiled SQL, manifests, run results, comparisons
and synthetic originals remain private outside Git. The immutable reviewed result
hashes 153 target artifacts. SHA-256 identities:

| Item | SHA-256 |
|---|---|
| Candidate lock | `63550b67b8ffed9e9376da5c24f08980837c6e79ad9e2e9eeb74d1164d25df2a` |
| Observation CSV | `fdf714e62cd16294d1584a8c68cd1bf7de301dd29f900b54f3d8745c35da0d9f` |
| Mention CSV | `87aac6e9f7b21ecaa56c0212f1f86c2caa0138aed9b25744d71ef85580e81121` |
| Reference SQL | `85134c5d800350adfedf7dce6d995a36c48b194d919912695992f83369e11d5f` |
| Verified application report | `417a569a449fb90274773233a3fa03a7f389788fa6634c994940615edbb23a68` |
| Private experiment report | `8192684fddbf57416f0c97ea9758c9e9cbe71120b87cb27bc1d6b9757704edd9` |

The application gate passes 1,941 tests/92.97% and clean lint/types/build/security/
secret/skill checks and advisory audit. Existing hosted jobs check the application;
they do not install/rerun this isolated experiment. Per-head status is in PRs.
At experiment completion no protected real-company task had run: project
`data`/`work` locations contained no managed raw-body cohort for the pilot and no
analyst task was observed. The later owner-requested setup/capture and automated
real-data checks are recorded in [market-readout.md](../../verification/market-readout.md); they do
not turn this synthetic dbt comparison into a real-data experiment. PV10 remains
open for human review/task observation; no further source activation or external
contact is implied.

## Official references

- [Seed types](https://docs.getdbt.com/reference/resource-configs/column_types)
- [Project configuration](https://docs.getdbt.com/reference/dbt_project.yml)
- [Postgres setup](https://docs.getdbt.com/docs/local/connect-data-platform/postgres-setup)
- [Data tests](https://docs.getdbt.com/docs/build/data-tests)
- [Usage statistics](https://docs.getdbt.com/reference/global-configs/usage-stats)
- [Core metadata](https://pypi.org/pypi/dbt-core/1.11.17/json)
- [Adapter metadata](https://pypi.org/pypi/dbt-postgres/1.11.0/json)

Version-specific CLI/tracking behavior and license texts were also inspected in
the hash-verified pinned wheels, rather than inferred from current documentation.
