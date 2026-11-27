# Citation acceptance history: software verification

G1–G3, including schema/implementation, were approved on 2026-11-26
(Europe/Athens). Work resumed after #234 reached main at `62d03e1`, with identical
reviewed `3bd1cca` tree. This candidate adds only the first citation record/inspect
slice; the existing policy, five acceptance consumers and legacy journal remain
unchanged. No dependency, CI, source acquisition or deployment change.

## Focused proof

Missing identity, journal, recorder and CLI APIs failed before implementation.
The focused/compatibility run passed **272 cases**, with **100% line and branch
coverage** across the four new modules (345 statements, 100 branches). Native
PostgreSQL 17 cases use owned disposable databases and synthetic archived source
bytes, with HTTP forbidden. They establish software behavior, not market coverage.

- Canonical immutable request/parent/policy identities exclude execution metadata;
  malformed envelopes, bindings, counts, checks and sidecar bytes are refused.
- Native ready/limited decisions preserve exact sidecar bytes; controlled producer
  frames exercise the actual policy's blocked/not_assessed decisions. Refusal is
  distinct and stores no fitness/body. Unknown failures leave pending work.
- A valid intent is visible from another connection before preparation. Cached
  completion preserves result/times, consults neither current policy nor source,
  and remains historical after originals disappear. New IDs reverify and refuse.
- Real locks reject concurrency; actual SIGKILL and SIGINT stop before and after
  terminal commit. Retries recover pending work or reuse the complete result.
  Original report bytes/mtime, archives and source tables stay unchanged.
- Dedicated roles suffice; missing grants and excess source/legacy/column/PUBLIC/
  inherited/owner/sequence/elevated rights fail closed. RLS cannot hide an attempt.
- Migration 0015 adds two immutable evidence tables. Real SQL checks enforce
  composite FKs, DB-stamped times/principals, bytea bounds/hashes without pgcrypto,
  UPDATE/DELETE/TRUNCATE refusal and contradictory-state rejection. Populated
  migration-0014 legacy records survive upgrade unchanged; old checksums stay intact.
- Native command recording/inspection uses separate connections, limited private-safe
  output and honest exit codes. Inspector success is distinct from data fitness.

All **26 behavior mutations were rejected**, covering identity/profile survival,
refusal honesty, byte/canonical limits, parent/request/cohort/check/count bindings,
recorded-body equivalence, locks/conflicts, source privilege ceilings, RLS,
cached scope, unsupported pending work, prepared-assessment integrity, inspection
exit codes, stdout bounds and SQL stamp/body hash/size guards. Source was restored
byte-for-byte and SHA-256 checked. A mutation initially stopped test collection;
the fixture was made lazy and the mutation then failed behavioral assertions.
No pin-only failure is counted as behavioral proof.

## Delivery gates and limits

Before review readiness require restored behavior mutations, full `just check`
and `just audit`, isolated final-wheel migration/native-command proof, unchanged
earlier migration/semantic/policy pins, and every exact-head hosted job. Keep
source stable during those gates; final results are recorded on the delivery PR.
Private evidence: `/workspace/work/nima-acceptance-history-proof`.

This checkpoint ends at a verified citation record/inspect slice. Revisit actual
cohort proof before extending history to other consumers. V1-08, actual data
acceptance, metric certification and release acceptance remain open.
[Operator runbook](../runbooks/acceptance-history.md).
