# Runtime-role and evidence-protection audit

[O3](../../SPEC-operating-controls.md#o3-runtime-role-and-evidence-protection-audit)
adds two commands driven by one packaged access contract (`access-contract-v1`):

- `dataops access-audit` reads PostgreSQL catalogue facts for one named role and
  reports whether it holds more than its profile allows and whether evidence
  protections are intact. It is read-only and changes nothing.
- `dataops access-grants` only **prints** the reviewed `GRANT` statements for a
  profile and role name. It never reads configuration, connects or runs SQL. You
  review the output and run it yourself as an authorised database administrator.

Neither command creates roles, passwords, schemas or migrations. A passing audit
means the selected recorded checks passed. It is not proof of a secure deployment:
it does not cover passwords, `pg_hba.conf`, network exposure, a compromised
superuser, row-level-security policies, rules, or what a trigger function does.

## Profiles

Each profile is a privilege **ceiling** taken from the operator runbooks. Holding
less is fine; holding more is attention.

| Profile | Tables (schema `nima` unless noted) | Writes |
|---|---|---|
| `analytics-reader` | schema_migrations, ingest_runs, run_pages, raw_objects, observations, record_versions, quarantine, projection_contracts/mentions/receipts | none |
| `run-health-reader` | schema_migrations, ingest_runs, run_pages, observations, projection_receipts, workflow_requests | none |
| `refresh-health-reader` | schema_migrations, refresh_policies/cycles/windows/retirements, workflow_requests/dispatches | none |
| `projector` | schema_migrations, outbox, observations, record_versions, projection_receipts, projection_contracts (read); projection_contracts, projection_mentions, projection_receipts (insert) | INSERT projection tables; UPDATE(delivered_at) on outbox only; no sequence |
| `validation-reader` | schema_migrations; `nima_validation` attempts, outcomes | none |
| `validation-writer` | as the reader | INSERT on `nima_validation` attempts, outcomes |
| `retirement-operator` | schema_migrations, refresh_policies, refresh_retirements | INSERT retirements and events; UPDATE(state) on policies; sequence `refresh_events_event_id_seq` |
| `successor-operator` | the above plus refresh_successions, refresh_events, refresh_cycles | INSERT policies, events, successions; UPDATE(state) on policies; same sequence |

Database `CONNECT` is granted separately and is not part of the contract.
The `projector` ceiling is not copied from a document: it is the smallest set under
which the real projector (`drain`) completes with source evidence unchanged, and
removing any one privilege makes it fail (see `tests/test_access_projector.py`).
`collector` and the other pipeline duties get their profiles the same way, one
reviewed increment at a time; none is guessed.

## Provision a role

An administrator creates the login role with a credential kept outside Git, then:

```sh
uv run --frozen python -m nima dataops access-grants \
  --profile analytics-reader --role nima_analytics_reader > grants.sql
# review grants.sql, then run it as an authorised administrator
```

Role names must be lowercase `[a-z_][a-z0-9_]*` up to 63 characters, not `public`
and not starting with `pg_`; anything else is refused with exit 2 and no SQL.

## Audit a role

Use the protected `NIMA_DATABASE_URL` of a connection that can read the catalogue
(catalogue reads need no special privilege):

```sh
uv run --frozen python -m nima dataops access-audit \
  --role nima_analytics_reader --profile analytics-reader \
  --output-dir /absolute/private/access-audit
```

The canonical report (`access-audit-v1`, at most 32 KiB, 0600 in a 0700 directory,
content-named, no overwrite) holds the contract version, role, profile, UTC
observation time, fixed reason codes with object names, and fixed limitations. It
carries no credentials, connection strings, server error text or row data. stdout
prints only status and attention count; fixed started/completed/failed events go to
stderr. Keep reports and event streams outside Git.

Exit codes: 0 passed, 3 attention, 2 invalid configuration, 1 operational,
integrity or output failure, 130 interruption. A missing role, unmigrated
database or oversized catalogue (more than 128 tables or 64 sequences) is a
failure, never an empty pass.

## What is checked

- Role: not superuser; no CREATEROLE, CREATEDB, REPLICATION or BYPASSRLS; owns no
  Nima object; not a member of the schema or table owner; no CREATE on the
  database or a Nima schema; USAGE only on its profile's schemas.
- Tables: all 33 are classified (22 evidence, 11 control). A table present in the
  database but not in the contract (`table_unclassified`) or the reverse
  (`table_missing`) fails closed, so new migrations must be classified.
- Privileges: effective direct, inherited, column-level and PUBLIC grants beyond
  the ceiling (`privilege_excess`). UPDATE, DELETE, TRUNCATE, TRIGGER or
  REFERENCES on an evidence table is the distinct `evidence_rewrite_privilege`.
- Evidence protection: an enabled BEFORE trigger covers UPDATE and DELETE
  (`evidence_trigger_missing` / `evidence_trigger_disabled`); the seven newer
  evidence tables also need an enabled TRUNCATE trigger (`truncate_trigger_missing`).
- Sequences: privileges beyond the profile (`sequence_privilege_excess`).

## Known limitations (reported on every audit)

- Fifteen older evidence tables have no TRUNCATE trigger, so TRUNCATE there is
  protected only by withholding the privilege, which this audit checks. The table
  owner is not blocked. Each is listed as `truncate_not_trigger_guarded:<table>`.
  A trigger would need a reviewed migration and is not part of this change.
- The audit is point-in-time, not an atomic snapshot. PostgreSQL privilege
  functions return the newest committed grants, so a grant made during the audit
  is reported rather than hidden.
- A present, enabled trigger is checked for existence and firing mode, not for
  what its function does.
