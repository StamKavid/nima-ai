# Graph database candidate assessment

Reviewed 2026-11-15 against official project documentation and license files.
The owner approved the [graph contract](investigation-pilot.md) and requested this
comparison. #87 is merged at `eb3d2e0`; all three checks pass for its exact head.
This is documentation/licensing research, not an installation, runtime benchmark,
database adoption decision or change to the approved graph scope.

## Recommendation

Evaluate **Apache AGE first** and **Neo4j Community second** when a graph-store
adapter is separately scoped. AGE best matches the existing PostgreSQL stack and
the preference for permissive open-source licenses. Neo4j Community offers a
documented Cypher/browser/Python workflow and is a useful independent comparison.
These are architectural judgments from the sources below, not measured performance
or operational-reliability results. The current approved increment still builds
the portable private JSON graph without adding a database service or extension.

Memgraph was the initial candidate in the architecture and reference pipeline.
Its current Community license is BSL 1.1 with an Additional Use Grant. The license
itself says it is not an open-source license. Retain it as a source-available
alternative, outside a strict open-source shortlist. A reference implementation
using Memgraph does not override this project's licensing preference.

## Three products checked

| Candidate | License / project | Relevant fit | Trade-off for Nima | Assessment |
|---|---|---|---|---|
| Apache AGE | Apache 2.0; Apache Software Foundation top-level project | Graph functionality inside PostgreSQL, openCypher within SQL and transactional integration | Extension installation/version compatibility; agtype decoding and prepared-query behavior need verification; isolate derived graph writes from the evidence database | First open-source evaluation target |
| Neo4j Community | GPLv3 open-source core, vendor-led ecosystem | Native property graph, Cypher, Neo4j Browser and official Python driver | Separate server and projection lifecycle; Community is for single-instance use, while clustering, online backup and additional access controls are Enterprise features | Second open-source evaluation target |
| Memgraph Community | BSL 1.1 with restricted production grant; Enterprise code has separate terms | Cypher graph engine with transactional in-memory and on-disk modes | Source-available terms differ from Apache/GPL; use case and edition need their own review | Excluded from strict open-source shortlist |

License evidence: [AGE overview](https://age.apache.org/overview/),
[Neo4j licensing](https://neo4j.com/open-source-project/),
[Memgraph repository license](https://github.com/memgraph/memgraph/blob/master/LICENSE)
and [Community BSL terms](https://github.com/memgraph/memgraph/blob/master/licenses/BSL.txt).
GPLv3 is an open-source copyleft license; it is not the same licensing model as BSL's
production-use restrictions. Do not infer that using a separate Neo4j service
automatically changes Nima's license; distribution/embedding decisions need their
own concrete assessment.

## Apache AGE: fit and release discrepancy

AGE is a PostgreSQL extension implementing graph queries through SQL/openCypher;
the project documents PostgreSQL transaction/storage integration. That makes it a
plausible fit for a team already operating PostgreSQL. It still requires an explicit
projection/import: existing evidence tables do not automatically become the
approved graph. A derived graph database/schema needs its own limited write role,
rebuild policy and resource isolation; avoid installing into the authoritative
evidence database as an incidental change.

Official sources disagree on versions at the review date:

- The [download page](https://age.apache.org/download/) lists AGE 1.6.0 for PostgreSQL 17.
- The [PG17 release list](https://github.com/apache/age/releases/tag/PG17/v1.7.0-rc0)
  includes a later release named v1.7.0, published 2026-02-11. Its tag contains rc0
  even though the GitHub release metadata has prerelease=false.
- The older [setup manual](https://age.apache.org/age-manual/master/intro/setup.html)
  lists only PostgreSQL 11–15, while the current PG17 branch README identifies PG17
  support. Do not copy that older compatibility list as a present restriction.

No exact AGE build is selected here. Before any installation, reconcile the release
status and pin a PG17-specific source/image with verified upstream checksum/signature
and a passing compatibility test. Neither an unpinned master build nor a GitHub
prerelease flag alone is sufficient evidence of the intended supported release.

AGE returns a custom JSON-like agtype rather than ordinary driver-decoded JSON.
Its documented cypher(graph_name, query_string, parameters) interface permits
parameter maps through prepared statements. Verify actual psycopg binding and
typed decoding against the chosen release; never interpolate source labels or
IDs into query strings. See [query format](https://age.apache.org/age-manual/master/intro/cypher.html)
and [agtype/numeric types](https://age.apache.org/age-manual/master/intro/types.html).

## Neo4j Community: fit and edition boundaries

The [operations manual](https://neo4j.com/docs/operations-manual/current/introduction/)
describes a single-instance Community deployment with ACID transactions and Cypher.
Enterprise adds capabilities including clustering, online backup and additional
access controls. Community is a valid candidate for a private pilot; do not present
it as delivering the full later multi-user/availability requirements.

The [official Python driver](https://neo4j.com/docs/python-manual/current/) and
Neo4j Browser provide a documented exploration path. A separate server adds
deployment, credentials, resource management and projection-refresh work. Keep
PostgreSQL authoritative and import only a complete identified graph snapshot.
Native graph node IDs must not replace the contract's stable external node IDs.

Neo4j property values cannot directly store arbitrary nested maps/lists containing
null. Preserve canonical nested evidence as JSON text or an explicitly mapped
structure while promoting selected scalar fields for lookup. Keep decimal money
as exact text consistent with the approved contract, rather than coercing it into
FLOAT. See [property types](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/).
The data-science library is a separate product/plugin with Community and Enterprise
editions; database selection does not select every algorithm or paid feature.
See [GDS introduction](https://neo4j.com/docs/graph-data-science/current/introduction/).

## Memgraph: why the strict shortlist changes

The [BSL grant](https://github.com/memgraph/memgraph/blob/master/licenses/BSL.txt)
defines authorized production use around internal business purposes and restrictions
concerning third-party database access/distribution, database-as-a-service and
competing solutions. Do not assume that a future hosted investigator product is
covered solely because Community is free to download. Assess the exact edition,
release and distribution model before reconsidering it. The license includes a
later change-license mechanism; that does not make current code Apache-licensed.
No conclusion that Nima is prohibited from using Memgraph is made here.

The [storage documentation](https://memgraph.com/docs/fundamentals/storage-memory-usage)
describes transactional in-memory and on-disk modes, as well as analytical mode.
Do not reject it with a claim that it can only store the graph in RAM. Actual
resource use, durability and mode-specific behavior need workload measurements.
The present exclusion is the strict open-source criterion, not a performance result.

## Evaluation method before adopting an adapter

Compare AGE and Neo4j against the same approved canonical fixture and expected
external IDs. Cypher support does not guarantee identical syntax, property types,
parameter binding or plugin behavior; use explicit per-engine query adapters.

1. Import the same canonical snapshot and verify all expected nodes/edges,
   unresolved occurrences, duplicate selected handles, Greek strings, explicit
   unknowns, decimal money, source hashes/pointers and review-event references.
2. Execute party → reported contracts → selected buyers → evidence and the reverse
   buyer → contract → supplier-occurrence paths. Compare exact external-ID sets and
   the not-selected/no-active-link outcomes with the pure Python reference view.
3. Import a new snapshot after revocation, retaining the old snapshot unchanged.
   Use snapshot hash plus external node/edge ID as storage membership; a globally
   unique external node ID alone must not overwrite historical snapshot state.
   Show complete snapshots only; an interrupted import must not expose partial data.
4. Record pinned database/extension/driver versions, hardware/resource limits,
   dataset hashes, indexes, setup/rebuild time, warm/cold query distributions,
   memory/disk use and actual restart/rebuild behavior. Report correctness first.
5. Compare operational work and usable Community features. The current 600-node/
   500-edge ceiling is too small to establish future nationwide performance;
   larger performance experiments need separately declared inputs and scope.

No benchmark numbers, deployment, extension installation, model call or source
access occurred during this assessment. Database adaptation remains a separate
decision after the approved graph's implementation plan and measured technical
delivery. Preserve its public-source/identity/time/evidence boundaries in any store.
