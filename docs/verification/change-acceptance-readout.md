# U4 acceptance consumer: software verification

The owner approved F1–F3 including implementation on 2026-11-26 (Europe/Athens).
The candidate extends #233 against main after #232. It adds one frozen preparation
result, a bounded acceptance adapter and the existing DataOps CLI route. No
policy, metric/SQL, source/parser, run-facts query, schema/grant, dependency or CI
change is included. Durable history and actual cohort proof remain separate.

## Focused proof

The missing preparation API failed first, then 29 preparation/existing-readout
cases passed on native PostgreSQL 17 with owned synthetic originals. Old tuples
and report bytes match on both comparable and incomparable paths, using the same
two sequential read-only connections. Missing consumer/CLI and mismatched typed
witness tests also failed before their implementation or guard was added.

Final focused run: **228 passed / 100% line and branch coverage** for the adapter
(236 statements/102 branches), producer (106/8) and shared CLI (45/2). Covers:

- Native seven-observation/two-page comparison: five distinct category-union
  records, zero ambiguity/quarantine. Every retry uses two closed connections;
  inputs and SQL remain unchanged. Source HTTP is forbidden.
- Controlled hand answers for one-/both-side ambiguity, repeated observations,
  A→B→A, all-ambiguous and empty captures. Counts are distinct across captures;
  a source ambiguous on both sides contributes one ambiguity, not two. Controlled
  frames exercise mapping; they do not establish original or SQL verification.
- Native complete-empty comparison requires two valid original empty pages.
  Every abstention reason and their combination publish `blocked` with unavailable
  proof explicit, even after originals are removed. Only SQL quarantine is counted;
  no zero coverage or current run profiles are invented.
- Actual raw/missing/normalized/page/membership/projection/principal failures,
  publication/retry/relocation and removal of originals after prior success.
  Malformed envelopes, typed witnesses, category accounting, policy/check drift,
  private paths, request/report/cohort/sidecar bounds and closed errors are tested.
- Four actual SIGKILL/SIGINT cases stop before/after final linking; SQL sessions
  are closed at that boundary. Retry publishes identical bytes without changing
  originals, SQL or an existing final artifact's mtime.

All **25 behavior mutations were rejected**: six counter scopes, capture-end
binding, single preparation, byte equality, subject/sidecar bounds, publication/
error handling, assessment/cohort/run-facts/witness/summary/category binding,
invented version profiles, unverified pass checks, fabricated zero observations,
source-detail leakage, incomparable evidence scope and JSON-pointer binding.
Source was restored byte-for-byte and SHA-256 checked. These do not rely on
changing a semantic-definition pin to make the test fail.

The adapter calls the existing public selector once per nonempty comparable
capture to validate typed summaries/witnesses. It does not recalculate U4, add a
selection algorithm, reread the source cohort or touch archives on abstention.
Policy/model hashes, draft status, earlier/later role identity, page-observation
clock and native category meanings stay unchanged.

## Delivery gates and limits

Before review readiness require full `just check`/`just audit`, isolated final
built-wheel/native CLI on both paths, independent baseline tuple/report-byte
comparison, unchanged policy/semantic/SQL/ODCS pins and all exact-head hosted jobs.
Keep source stable during gates; record late results on #233 without repeating
an unchanged full suite solely for documentation status. Private proof remains
at `/workspace/work/nima-change-acceptance-proof`.

Synthetic software proof does not close actual market-data reconciliation,
investigator task proof, metric review/certification, durable acceptance history
or release acceptance. No new acquisition, activation, deployment or agent merge.
[Operator command](../runbooks/change-acceptance.md).
