# Reported market metadata v1

This is an evidence-linked, read-only query over explicitly selected captured
occurrences. It is not a company-sector dimension or a certified business metric.
Structured source fields precede model suggestions; no model is used here.

| Dimension | Subject | Reported field / taxonomy | Version |
|---|---|---|---|
| `buyer_function` | Contract's buyer | KIMDIS `contractingAuthorityActivity` | Not supplied |
| `buyer_legal_class` | Contract's buyer | KIMDIS `classificationOfPublicLawOrganization` | Not supplied |
| `buyer_type` | Contract's buyer | KIMDIS `typeOfContractingAuthority` | Not supplied |
| `procurement_cpv` | Purchased object position | KIMDIS `objectDetailsList[].cpvs[]` | Not supplied |
| `supplier_kad` | GEMI registry profile's reported activity | `activities[].activity` | Reported `kadVersion`, possibly unknown |

The extraction/artifact contract is `market-metadata-v1`. Buyer codes are positive
ASCII integer strings; CPV codes receive an ASCII `########-#` syntax check only.
Neither check certifies official taxonomy membership or a check digit. KAD codes
remain reported text with their supplied taxonomy version. No crosswalk between
these taxonomies is assumed. A defence buyer can purchase food or software; this
does not classify the supplier as a defence-industry company.

Rows distinguish `reported`, `missing`, `null`, `empty` and `invalid` source values.
`reported` means structurally usable, with `taxonomy_validation: not_checked`.
Usable codes/versions (up to 512 characters) and labels (up to 4,096 characters)
retain original text and whitespace; unusable shapes remain
located in original evidence. Field pointers distinguish absent and present null
fields. KAD type and validity dates retain their own pointers; an expired or
unknown interval is not automatically interpreted as current activity.

Each record carries original observation time, raw response SHA-256, parent JSON
pointer, source/run and record status; KIMDIS also carries the source-content hash
and page/index. Assertions carry actual/expected locations and field pointers.
An expected pointer can describe an absent field and must not be treated as a
resolvable evidence location. A GEMI 404 remains `not_found_at_observation`, without
an activity assertion. It does not establish that a company does not exist.

## Query and reproducibility

```sh
uv run python -m nima metadata kimdis --run-id "$RUN_UUID" \
  --archive-dir "$ARCHIVE_DIR" --output-dir "$OUTPUT_DIR" \
  --dimension procurement_cpv --code 33141120-7

uv run python -m nima metadata gemi --run-id "$GEMI_RUN_UUID" \
  --archive-dir "$GEMI_ARCHIVE_DIR" --output-dir "$OUTPUT_DIR"
```

KIMDIS needs `NIMA_DATABASE_URL` with SELECT on `schema_migrations`, `ingest_runs`,
`run_pages`, `raw_objects`. SQL is REPEATABLE READ/READ ONLY and closes before
archive recovery. GEMI verifies a completed collector archive without SQL or an
API key. This does not create a GEMI archive or make unavailable profiles appear.

Omit filters to inspect all metadata. Dimension-only queries include unknown and
invalid states. Code filters match exact structurally reported strings and retain
full-scope quality counts. Code requires a dimension; an unsupported source/dimension
combination fails before I/O. No match means no matching eligible assertion in this
capture, not real-market absence. A reported optional field may belong to a
quarantined contract; its parent `record_status` remains visible.

The grain is an assertion occurrence at a source record/position. Repeated capture
observations and repeated CPV positions are retained. Counts are diagnostics, not
unique-company, procurement-value or current-state metrics. Full original capture
status and quality counts remain in filtered output. No amount is allocated.

Publication uses the existing canonical private no-clobber writer. Repeated and
relocated reads produce identical bytes and hashes; paths and execution time are
not identity. Terminal JSON contains fixed status and counts, never source values,
selection IDs, paths or result hashes. Full private artifacts are not safe to publish.

The existing replay bounds apply: 32 pages, 5,000 committed KIMDIS records and
64 MiB distinct bodies; GEMI retains its ten-profile completed-archive limits.
Output is capped at 10,000 assertions and the existing 32 MiB report ceiling.
No truncated success, archive repair, SQL promotion, source request or implicit
activation is performed. SQL metadata projections/indexes, taxonomy dictionaries,
reviewed crosswalks and Greek-model evaluation are later reviewed work.

Source contracts: https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help and
https://opendata-api.businessportal.gr/api-docs (retained schemas; no fresh request).
