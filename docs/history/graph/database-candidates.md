# Graph database assessment: technical fit and operating evidence

Revised 2026-11-15 for the owner's personal project and possible additional users.
The [graph contract](investigation-pilot.md) is approved in #87. Licensing remains
important alongside query latency, correctness, durability, resource use, community
support, tooling and operating cost. This review includes Memgraph, FalkorDB,
Neo4j Community, Apache AGE and HydraDB. No engine is installed or benchmarked here.

## Recommendation and decision method

Start a separately scoped prototype comparison with **Memgraph and FalkorDB**;
use **Neo4j Community** as the exploration/tooling baseline if the evaluation budget
allows three engines. Memgraph's graph/analytics workflow fits the reference
architecture; FalkorDB offers a different matrix-based execution approach. This is
an evaluation order inferred from documented capabilities, not a speed ranking.

Retain **Apache AGE** as the PostgreSQL-integrated alternative, especially when a
single database technology and Apache 2.0 licensing outweigh another server's
exploration tooling. **HydraDB** is an exploratory candidate if object-store-backed
storage and independent compute become useful. Its local mode permits a small test;
a distributed deployment is not required just to evaluate it.

Use the same reference answers and resource budget for every engine. A candidate
must preserve the graph contract and have terms appropriate for the actual planned
use. Then compare latency/concurrency, recovery, memory/operating cost, query and
driver compatibility, exploration ergonomics and support evidence. There are no
weighted numerical scores or declared winners without measurements. Strict OSI
open-source classification alone does not disqualify a usable prototype candidate.

The approved increment remains a private portable JSON graph rebuilt from
PostgreSQL. It supplies the reference corpus/view before any store adapter is
adopted; no paid feature or model is required for this increment.

## Technical comparison

The latency expectations below are architectural hypotheses. They do not predict
Nima p95/p99 or establish that any engine outperforms another.

| Engine | Execution and potential latency factors | Memory, durability and operations | Query/tooling questions for Nima |
|---|---|---|---|
| Memgraph | Native in-memory transactional graph execution can avoid disk reads for resident data; fan-out, indexes, temporary state and concurrent refresh still affect latency | Transactional modes use WAL/snapshots; on-disk transactional mode also exists. Analytical mode has different guarantees and must not stand in for the transactional comparison. Measure RSS and import/recovery peaks | Cypher/Bolt ecosystem, Lab and MAGE are relevant to exploration. Check actual dialect, algorithm/edition availability and external-user licensing |
| FalkorDB | Sparse adjacency matrices and linear-algebra execution offer a different traversal engine; test selective starts, high-degree buyers, result sizes and concurrent read/write behavior | Redis-module deployment with configured persistence and mounted storage. Declare AOF/fsync, snapshot, memory and eviction settings; measure peak memory and recovery, not just steady-state queries | GRAPH.* protocol, Python SDK, Browser and PROFILE are available. Version 6 is a Rust rewrite; version 4 and 6 evidence is not interchangeable |
| Neo4j Community | Native graph traversal backed by storage and page cache; indexes, query plans, heap/GC, cache residency and result materialization can influence tails | JVM heap, native memory and page cache all matter. Separate server/refresh operations; Community is single-instance and does not include every Enterprise availability/security feature | Documented Browser, Cypher, official Python driver and query profiling make it a useful baseline. Verify per-edition procedures and constraints |
| Apache AGE | openCypher inside SQL/PostgreSQL; inspect join/traversal plans, indexes, selectivity and agtype decoding instead of assuming relational reuse gives low latency | PostgreSQL transaction/storage operations are familiar, but extension compatibility and graph-schema/write isolation add work; keep evidence tables authoritative | Hybrid SQL/Cypher can suit exact evidence joins. Verify prepared parameter handling, projected-property indexes, driver decoding and the exact PG17 release |
| HydraDB | Rust/SlateDB graph on object storage with graph indexes, cache/WAL overlay and snapshot-consistent queries; cache misses, locality and object-store RTT can influence tails | Compute/cache can be rebuilt from durable storage. Include cache/index warm-up, index lag, writer handoff, restart and object-store cost in an evaluation; local mode differs from remote S3 | OpenCypher subset, Bolt and HTTP are documented. Check unsupported query shapes, consistency/atomicity settings and stable external-ID mapping against a pinned release |

Primary technical sources:
[Memgraph storage](https://memgraph.com/docs/fundamentals/storage-memory-usage),
[durability](https://memgraph.com/docs/fundamentals/data-durability),
[Cypher differences](https://memgraph.com/docs/querying/differences-in-cypher-implementations);
[FalkorDB deployment](https://docs.falkordb.com/operations/docker),
[PROFILE](https://docs.falkordb.com/commands/graph.profile),
[6.0 engine changes](https://github.com/FalkorDB/FalkorDB/releases/tag/v6.0.0);
[Neo4j memory](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/),
[edition boundaries](https://neo4j.com/docs/operations-manual/current/introduction/),
[Python driver](https://neo4j.com/docs/python-manual/current/);
[AGE architecture](https://age.apache.org/overview/),
[query format](https://age.apache.org/age-manual/master/intro/cypher.html),
[agtype](https://age.apache.org/age-manual/master/intro/types.html);
[HydraDB architecture](https://github.com/hydra-db/hydradb/blob/main/architecture.md)
and [runtime/query contract](https://github.com/hydra-db/hydradb/blob/main/README.md).

PROFILE may execute writes: use read-only queries on disposable fixtures. Do not
copy example latest tags, credentials, persistence or eviction defaults into Nima.
A successful write acknowledgment is not by itself a measured crash/power-loss
recovery guarantee. Keep explicit nulls/nested evidence in a lossless mapping and
money as exact decimal text; native IDs never replace our external graph IDs.

## Community, maintenance and support evidence

| Project | Evidence checked on 2026-11-15 | What remains unmeasured |
|---|---|---|
| Memgraph | Published releases v3.14.0 (Oct 21), v3.13.2 (Oct 9), v3.13.1 (Sep 14); repository links documentation, Discord, MAGE and contribution channels | Maintainer response times, support for our pinned version and free/paid feature boundaries; recent releases alone do not prove response quality |
| FalkorDB | Published v4.22.4 (Nov 12), v6.0.4 (Nov 5), v4.22.3 (Oct 28); official SDKs, Browser, docs, Discussions and Discord | Choose an engine line. 6.0 replaces the C engine with Rust and changes replication format; the release notes prohibit mixing 4.x/6.x replicas. Test migration and regressions rather than extrapolating old benchmarks |
| Neo4j | Extensive official operations/Cypher/Python manuals, Browser and public community/training resources provide a documented developer path | No measured support response, comparative community-size claim or Community SLA; verify current version/edition support and upgrade policy |
| Apache AGE | Apache Foundation top-level governance and official manuals/source/release artifacts | PG17 release documentation is inconsistent; maintainer response and extension/driver compatibility need verification |
| HydraDB | Published v0.4.0 (Nov 14), v0.3.0 (Oct 25), v0.2.0 (Sep 30); source, Discord, deployment docs and a public benchmark harness | The checked 0.x series needs a pinned upgrade/query contract and operational testing; release activity is not proof of production reliability or support turnaround |

Release evidence: [Memgraph](https://github.com/memgraph/memgraph/releases),
[FalkorDB](https://github.com/FalkorDB/FalkorDB/releases),
[HydraDB](https://github.com/hydra-db/hydradb/releases).
The [FalkorDB 6.0 release notes](https://github.com/FalkorDB/FalkorDB/releases/tag/v6.0.0)
explain its engine/replication change. Do not pick a release by date alone when
multiple major lines are published; pin the tested version and image digest.

For a later support assessment, sample comparable recent issues and record first
maintainer response, resolution/reproduction quality, distinct active maintainers,
security policy, upgrade notes and available commercial support. Stars, forks and
raw issue counts are not support-quality scores. No such response-time study has
been run here.

## Licensing and release eligibility

| Engine | Current core terms checked | Consequence for this project |
|---|---|---|
| Memgraph Community | BSL 1.1 plus Additional Use Grant | Development/evaluation is permitted and specified internal production use has a grant. External users/distribution depend on the actual model; examine the OEM/SaaS terms. Source-available classification is not a finding that Nima cannot use it |
| FalkorDB | SSPLv1 | Internal/evaluation use and service-source obligations differ; assess whether planned functionality is offered as a service, rather than assume any application or any user count decides it |
| Neo4j Community | GPLv3 | Open-source copyleft core; evaluate concrete distribution/embedding and Community feature needs separately from performance |
| Apache AGE | Apache 2.0 | Permissive core terms; extension/platform compatibility still needs validation |
| HydraDB | Current main LICENSE/README: Elastic License 2.0 | Older indexed AGPL descriptions are stale for the checked source. Hosted-service restrictions concern substantial database functionality; verify the intended model/version |

License sources: [Memgraph BSL](https://github.com/memgraph/memgraph/blob/master/licenses/BSL.txt),
[OEM/SaaS](https://memgraph.com/pricing),
[FalkorDB FAQ](https://docs.falkordb.com/references/license),
[Neo4j licensing](https://neo4j.com/open-source-project/),
[AGE license/governance](https://age.apache.org/overview/),
[HydraDB LICENSE](https://github.com/hydra-db/hydradb/blob/main/LICENSE).
Review the full deployment bundle, including server/extension/SDK/UI components,
and the actual intended use; this assessment does not grant rights or authorize
purchases, contact with vendors or a deployment.

AGE version caveat: the [download page](https://age.apache.org/download/) lists 1.6.0
for PG17, while [GitHub lists a later PG17 1.7.0 release](https://github.com/apache/age/releases/tag/PG17/v1.7.0-rc0)
whose tag includes rc0 but has prerelease=false. The older setup manual also lists
fewer PostgreSQL versions. Reconcile and verify the exact signed PG17 artifact
before installing; no build is selected from those conflicting signals.

## Benchmark evidence and proposed Nima protocol

Published benchmarks supply reproducible hypotheses, not Nima measurements.
[Memgraph's harness](https://github.com/memgraph/memgraph/blob/master/tests/mgbench/how_to_use_benchgraph.md)
allows custom workloads. [HydraDB's methodology](https://github.com/hydra-db/benchmark/blob/main/METHODOLOGY.md)
explicitly measures an in-process harness with same-host MinIO, excluding network,
authentication and server runtime. Those results cannot be compared directly with
client-to-server latency or remote-S3 cold reads. Vendor speed claims, different
query outputs and different durability settings are not a common leaderboard.

A separately scoped adapter evaluation should record:

1. **Correctness first:** identical canonical fixture/hash and expected external
   node/edge sets. Preserve unresolved/ambiguous parties, joint suppliers, repeated
   observations, contract versions, Greek labels, nulls, exact money, citations and
   review histories. A faster incomplete answer does not pass.
2. **Nima queries:** Q1 handle → active reviewed occurrences → contract versions →
   selected buyers; Q2 buyer occurrence → contract → supplier occurrences; Q3 each
   result → source locator and exact review event. Q4 rebuild after revocation:
   new active links change while the old snapshot remains unchanged. No automatic
   buyer consolidation or unsupported relationship inference.
3. **Comparable setup:** pin engine/image/driver versions, chosen major line,
   indexes, parameter bindings, hardware, CPU/RAM limits, storage mode, persistence,
   dataset size/degree distribution, result size and network/object-store locality.
   Use lossless per-engine property mappings and explicit dialect adapters.
4. **Client-observed latency:** include serialization, authenticated transport,
   server queue/execution and full result decoding. Report connection/setup and
   engine profiling separately. Measure p50/p95/p99, successful throughput,
   timeouts/errors and offered rate at 1, 5 and 10 concurrent clients; retain slow
   samples and queue time. Label closed-loop and offered-rate experiments.
5. **Cache and repeatability:** distinguish process-cold, actual data-cache-cold and
   warmed/compiled queries; a restart does not necessarily clear OS caches. Record
   preparation, randomized seed order, repeated runs, sample counts and variability.
   Do not publish a confident p99 from a tiny sample or remove pauses as outliers.
6. **Resources and recovery:** idle/steady/peak total memory including native/cache
   and child processes, CPU, disk/object requests, load/rebuild time and restart
   recovery. Interrupt imports to verify complete-snapshot publication. Report the
   configured acknowledgment/durability loss window instead of equating all modes.
7. **Operating/support cost:** installation/upgrade effort, diagnostics, browser/SDK
   usability, permission/backup controls available in the chosen edition, measured
   issue-response evidence and infrastructure/license costs for the intended use.

Start inside the approved 600-node/500-edge graph bound. This is useful for query
compatibility and investigator ergonomics; it cannot establish nationwide scale.
Larger/skewed stress corpora need their own declared scope and may not silently
raise this contract's limits. Observed investigator verification time remains a
separate product metric. No numbers, database adapter, installation or executed
benchmark are delivered by this document. The next step is the approved graph
implementation plan and reference graph delivery; store adoption follows evidence.
