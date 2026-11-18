# Selected-run DataOps health

This offline operational command reads one explicitly selected KIMDIS run. It
never collects data, repairs an archive, clears a failed request, changes grants
or enables a schedule. There is no new dependency or migration.

Load a private NIMA_DATABASE_URL for a scoped SELECT-only principal, then run:

```sh
python -m nima dataops health --run-id SELECTED_RUN_UUID \
  --capacity-dir /private/archive \
  --max-capture-age-hours 24 --min-free-bytes 1073741824 \
  --output-dir /private/health-reports
```

The numbers above are example operator thresholds, not publisher SLAs. Both are
required. Capacity directory must already exist, be owner-only (0700) and have no
symlinked path components. Output must be outside it. Canonical reports are 0600
in a 0700 directory and include private IDs/paths; do not publish them.

Minimum SQL scope: schema `nima` USAGE and SELECT on `schema_migrations`,
`ingest_runs`, `run_pages`, `observations`, `projection_receipts` and
`workflow_requests`. Set up grants separately with an authorized owner; the command
never grants itself access. Reads use repeatable-read READ ONLY and five-second
per-statement timeouts. Only selected-run aggregates are returned.

The report flags recorded run states, stale/missing/future page observations,
quarantine, cardinality mismatch, missing current-version projection receipts,
a linked non-complete workflow, low available bytes and exhausted finite inodes.
Freshness uses the oldest committed page; a new last page cannot hide old pages.
Available space excludes reserved blocks. SQL and filesystem sample times are
separate; the capacity target is operator-selected, not a verified archive binding.

Exit 0: limited checks pass. Exit 3: attention report published. Exit 2: invalid
configuration. Exit 1: unavailable database/schema/capacity/output. Exit 130:
interruption. Stdout contains fixed status/counts; stderr contains fixed structured
start/completed/failed events, without source values or driver errors.

This does not verify archived bytes, field-level correctness, source-currentness,
worker/scheduler liveness, execution compatibility or broader coverage. Use archive
verification/readout reconciliation separately. An empty captured page is not
proof of company absence. Full refresh-policy/child diagnostics, pipeline-wide
logging, alerts and pre-collection capacity enforcement remain later work.
