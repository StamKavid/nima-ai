# Reported participation verification

Date: 2026-11-10. Base: merged PR #13 (`14063bf`). Scope: additive migration 0003
and a bounded local projection consumer under SPEC-source-ingestion.md. No new
dependencies, CI controls, quality-floor changes or production deployment.

Local `make check` passes: 222 tests and 97.04% combined Python line/branch
coverage. The new mapper and worker each have 100% line/branch coverage. Formatting,
lint, strict types, package build, skill integrity, Bandit and Gitleaks pass.
The hash-locked dependency audit reports no known vulnerabilities.

## Evidence and review

- Mapping/worker tests initially failed because the projection package did not
  exist. Pure tests cover exact money, original Greek/identifiers, explicit nulls,
  source-local occurrence order and the 1,000-supplier boundary.
- Real PostgreSQL 17 tests cover joint awards without duplicated monetary facts,
  A→B→A and unchanged observations, evidence pointers, empty/unknown suppliers,
  supported migrations, bounded batches and versioned replay of acknowledged events.
- Concurrent consumers, skipped locked events and fresh receipt checks under the
  event lock prevent duplicate work. No persistent high watermark can strand an
  older skipped event. A fresh invocation starts its search from the beginning.
- A malformed/unsupported version stays pending; a poison event stops the batch
  while earlier event commits survive. A forced SQL exception proves rollback
  and CLI driver-message redaction. Hash conflicts fail without a receipt or ack.
- Real child workers receive SIGKILL before acknowledgement (after projection
  writes) and after commit. New connections observe complete rollback or the
  durable projection respectively; replay creates one receipt per observation.
- Mutation experiment: removing the projection-hash mismatch guard made its
  regression test fail (DID NOT RAISE). Original bytes were restored; the mutation
  used an isolated Python bytecode cache.
- Offline cached 2026-11-06 evidence produced 1,118 contract facts, 1,118 buyers,
  1,157 supplier occurrences, 1,118 receipts/acknowledgements and 1,157 edges.
  There were 21 joint contracts, zero unknown/empty supplier lists in this sample.
  Batches processed 1,000 then 118 events; replay processed zero. This reused cached
  bodies, not live source requests. Every original archive file hash stayed equal;
  the disposable replay database/archive were removed.

Review covers correctness (atomicity/replay and exact values), readability
(pure mapping separated from SQL orchestration), architecture (rebuildable
assertions before identity resolution), security (parameterized bounded inputs,
count-only summaries, no added dependencies) and performance (one bulk mention
insert per event, indexed receipts and invocation-local ordered cursor). Remaining
work counting scans the event set; production scale/latency is not benchmarked.
PostgreSQL locking/JSON conversion and Psycopg transaction documentation were
consulted; links appear in implementation modules.

## Boundaries

Mentions are assertions, not resolved companies. Matching identifiers are retained
without merging or ownership/fraud inference. Contract values are stored once per
version; repeated observations/versions must not be summed as new spending.
Reported edges exclude values. Choose a run and projection version and inspect
coverage/unknowns before analysis. Event completion is local only; external
consumers need separate receipts. A connection loss at commit can leave the client
uncertain; retry consults committed receipts. Worker termination tests do not prove
database/storage crash recovery. A bad event requires review; no automatic skip,
dead-letter queue, graph store, models or scheduler is included.

Final local and hosted results are recorded with the delivery PR.
