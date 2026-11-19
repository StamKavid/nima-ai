# Recovering a refresh child

Use this local operator control for an interrupted or incomplete child whose
original budgets still have headroom. Inspect the policy and selected request
first, using the existing private environment configuration:

```sh
uv run --frozen python -m nima refresh show POLICY_UUID
uv run --frozen python -m nima workflows show REQUEST_UUID
uv run --frozen python -m nima refresh recover POLICY_UUID --request-id REQUEST_UUID
```

Replace both UUIDs with the recorded identities. Recovery authorizes a local
Prefect dispatch; its worker may contact the configured source. This code PR
does not itself run recovery, enable a policy or activate collection. Use the
existing protected worker/egress procedure for an approved live operation.

The policy must be enabled and compatible. The request must be an unreconciled
child in its open cycle, with a sending/accepted window. `allocated` work belongs
to the existing tick path. Recovery holds the policy and global source locks
through the send; busy policy/collector returns `policy_busy`/`source_busy`.
This serializes controls and collection, without establishing worker liveness.
Accepted/queued engine jobs may already exist, so duplicate delivery remains
possible and workers continue to use the same SQL identity/leases/checkpoints.

Recovery requires all original headroom: elapsed time at most 30 minutes from
the original start (if started), fewer than four collection executions, 300 HTTP
attempt reservations and 100 projection batches. Future start clocks are refused.
There must also be fewer than four saved dispatches for this request, including
the original and pending/unknown/manual sends. A recovery reservation adds one
dispatch. These are independent budgets; a dispatch does not reset or consume a
collection execution/HTTP reservation before the worker starts.

Exhaustion returns existing fixed budget codes, or `recovery_dispatch_limit`.
Invalid child selection returns `recovery_child`; a complete request returns
`recovery_complete`. Version incompatibility retains its original fixed code.
Expired/exhausted work stays blocked. Audited policy supersession/terminal
resolution remains later work; changing IDs or deadlines would bypass history.
The general manual `workflows dispatch` command retains its separate semantics;
the new cap is enforced on recovery reservations, not all independent controls.

A successful response acknowledges dispatch only. It retains the request/run,
saved intent, counters and clock; a sending window may become accepted. The next
tick uses existing evidence reconciliation before advancing completed coverage.
An unavailable/lost engine acknowledgement leaves an unknown dispatch; a process
death can leave a pending intent. Both count against headroom. Retry the same
request only after inspecting it. Never infer non-delivery from a lost response.

Exit codes retain refresh semantics: 0 acknowledgement, 1 operational/eligibility
refusal, 2 configuration, 130 interruption. Error output contains fixed reasons,
without DSNs, archive paths or arbitrary engine exception text. No SQL/engine
atomic commit or automatic retry is claimed. See the [R1 contract](../../SPEC-refresh-recovery.md)
for synthetic process/SQL/control verification and the remaining V1-02 scope.
