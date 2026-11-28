# Readout certification runbook (U1 to U4)

How to produce the evidence that moves a metric from `reviewed` to `certified` in the
[metric catalogue](../semantics/metric-catalogue.md). The owner runs the live capture and the hand
reconciliation; nothing here is run by an agent against a live source. Keep requests, originals and
result files outside Git (`data/` is ignored).

**Current U3 starting point, 2026-11-28:** the
[private owner review packet](u3-owner-review-packet.md) is prepared from retained
originals: a complete primary cohort, eligibility examples and repeated-capture
selection. Start with that packet; no fresh capture is needed for this scoped
review. Human calculations/sign-off and compatible definition/policy admission
remain open. The older four-record rehearsal below is historical evidence.

## What was already checked offline

On 2026-11-21 all four commands ran against the only local capture whose original archive survives
(4 records, one complete run) on a local pilot database, with a read-only role and private 0700/0600
copies. Counts only: U1 matched 1 record for one reported supplier; U2 placed 4 records in 4
CPV-and-month cells; U3 found 4 records and 3 distinct suppliers for one buyer; U4 abstained
(`incomparable`) against a second run that has no archive. That shows the commands work on real
archived bytes. It is not a reconciliation: four records are too few and nobody checked them by hand.
Running it also projected the pending outbox events of the five local runs.

## Steps

1. **Capture with the archive preserved** (live request: owner only). Mount a folder for the archive and
   copy it out of the container, because the archives of earlier containers were lost. Use one bounded
   query, for example one buyer for one day:

   ```sh
   uv run --frozen python -m nima ingest kimdis --database \
     --from-date 2026-11-06 --to-date 2026-11-06 --buyer-id 6 --archive-dir /out/raw
   ```

   For U4 take the **same query a second time, later**, after the first run has finished.
2. **Project** until nothing remains: `uv run --frozen python -m nima outbox project --max-events 500`.
3. **Read role**: create the read-only role from the setup block in
   [the supplier-buyer runbook](../analytics/supplier-buyers.md#read-role-setup) and set
   `NIMA_DATABASE_URL` to it in your private environment.
4. **Requests**: one file per command, in a 0700 directory with 0600 files. Replace the placeholders.

   | Command | Request `version` | Fields besides `source`, `archive_bindings` |
   |---|---|---|
   | `supplier-buyers` | `nima-participation-request-v1` | `run_ids`, `observation_cutoff`, `supplier_country` (`GR`), `supplier_tax_id` |
   | `cpv-period` | `nima-cpv-period-request-v1` | `run_ids`, `observation_cutoff`, `cpv_base_code`, `period_from`, `period_to` (each may be `null`) |
   | `buyer-concentration` | `nima-buyer-concentration-request-v1` | `run_ids`, `observation_cutoff`, `buyer` (the reported organization key) |
   | `observed-change` | `nima-observed-change-request-v1` | `earlier_run_ids`, `later_run_ids` (disjoint) |

   `source` is always `kimdis.contract`; `archive_bindings` is one `{"run_id", "root"}` per run, with
   absolute paths. Record each request file's run IDs, cutoff and the metric's definition hash.
5. **Run** `nima analytics <command> --request <file> --output-dir <dir>` for each. The result is
   `<sha256>.json` in the output folder; keep it private.
6. **Reproduce by hand** from the original source records, without the tool: choose a stratified sample
   that includes a joint record (several suppliers), a record with no CPV code, a record with an
   unknown or unparseable date, and a revised record. Work out each metric's cell for those records.
7. **Reconcile exactly.** Every hand result must equal the tool's. Any difference blocks certification
   until explained; a rule change needs a new metric version.
8. **Record it** in `docs/verification/reconciliation-<metric id>.md`: the request (run IDs, cutoff),
   definition and SQL hashes, the sample (source IDs only), hand results, the outcome and your
   sign-off, with no names or tax numbers. Change the status in its own pull request afterwards.

U4 also needs the second capture to be complete; if the runs disagree on completeness, query or order,
the result is `incomparable` with the reason named, which is itself a correct outcome to record.
