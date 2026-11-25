# Inspect explicit KIMDIS–Diavgeia citations offline

Contract: [V1-07 source citations](../specs/SPEC-cross-source-citations.md).
Model `explicit_procurement_citations.v1` remains draft. This readout checks stored
observations and their originals; it never contacts either government source.

## Required inputs

Use the existing SELECT-only analytics reader through `NIMA_DATABASE_URL`.
Database owners, superusers and principals with effective write privileges are
refused. Current migrations must already be applied; the command never migrates.
The same reader grants used by the existing analytics commands are sufficient.

Choose explicit KIMDIS and Diavgeia ingest-run IDs and the private archive root
for each. Only KIMDIS contracts, Diavgeia awards and Diavgeia commitments with the
supported v1 processing identities are admitted. A GEMI run, a single-decision
lookup receipt or a replay artifact is not a replacement for an ingest run.

Create a private request file (0600, in a 0700 directory) with this structure.
The IDs and paths below are placeholders, not existing captures:

```json
{
  "version": "nima-source-citations-request-v1",
  "kimdis_run_ids": ["00000000-0000-0000-0000-000000000001"],
  "diavgeia_run_ids": ["00000000-0000-0000-0000-000000000002"],
  "observation_cutoff": "2026-11-25T00:00:00Z",
  "archive_bindings": [
    {
      "source": "kimdis",
      "run_id": "00000000-0000-0000-0000-000000000001",
      "root": "/srv/nima-private/archives/contracts"
    },
    {
      "source": "diavgeia",
      "run_id": "00000000-0000-0000-0000-000000000002",
      "root": "/srv/nima-private/archives/decisions"
    }
  ]
}
```

Each group must be nonempty; every run appears once, in one group, with one matching
binding. Use canonical UUIDs, absolute paths and an explicit UTC cutoff. Unknown
fields, duplicate keys/bindings, symlinked or multiply linked request files and
oversized selections are refused. Keep credentials in protected environment/service
configuration, never in the request or Git.

```text
uv run --frozen python -m nima analytics source-citations --request /srv/nima-private/citations.json --output-dir /srv/nima-private/results
```

## Read the result

Stdout contains the artifact hash and fixed outcome/counts/coverage. The private
output directory is 0700; its immutable, content-addressed JSON files are 0600.
Retrying an unchanged request reproduces its bytes and verifies an existing file;
it never overwrites a conflicting result. Keep results and originals outside Git.

The result includes the draft model definition/hash, reference-SQL hash, semantic
request hash, verified cohort hash, capture facts, verified pages and per-observation
evidence. Record and field locations lead to response hashes and JSON pointers.
`value_status` distinguishes reported fields from unknown or unreported values;
in the latter cases the field path is an expected location, not proof that a field exists.
Source names, subjects, supplier details and amounts are not exported.

References are exact, directional citations. Missing targets are `unresolved`
within this selected cohort; tied latest revisions are `target_ambiguous`;
missing or other decision types remain `target_type_unknown` or
`target_type_mismatch`. A revoked target or cancelled contract retains its citation
and status. No identity merge, economic-event collapse, value allocation or
misconduct inference follows.

`selected_complete_captures` describes only the selected captures. `partial_capture`
discloses interruption, missing pages, quarantine or other incomplete accounting;
it never establishes absence, market coverage or a complete match rate. An empty
completed capture still requires its archived empty page. A run without committed
pages carries no observation span; when neither source has pages the result says
`no_admitted_pages`. Metric eligibility is explicitly unassessed pending V1-08.

## Limits and failures

One SELECT-only repeatable-read session covers both source groups and SQL parity.
Preflights cap 10 runs, 5,000 normalized observations, 5,000 quarantines, 500 page
references, 8 MiB frozen input, 32 distinct physical objects, 8 MiB per object,
64 MiB total original bytes and 8 MiB canonical result. Requests are at most 16 KiB.
Excessive counts fail before normalized-payload serialization/fetch. There is no
truncation, source fetch, SQL write, original repair or promotion fallback.

Failures use `citation_input`, `citation_limit`, `citation_contract`,
`citation_evidence`, `citation_database` or `citation_output`, without source values,
private paths or driver details. Invalid input exits 2, other failures 1, operator
interruption 130. No success result is printed after a failed publication.

All admitted originals are checked even when no reference resolves or every record
is after the cutoff. A historical normalization that disagrees with the installed
adapter fails closed, including changed quarantine outcomes. An existing replay
does not silently replace its stored facts; review that mismatch separately.

Moving archives changes only request binding roots; hashes exclude their physical
locations. Preserve run IDs, original bytes and observation times when restoring SQL.
The earlier four-positive real pilot remains pending its actual private originals
and SQL snapshot; synthetic tests do not certify those joins or the metrics.
