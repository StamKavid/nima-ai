-- Derived metadata snapshots never advance source observation time.
CREATE TABLE nima_processing.metadata_snapshots (
    snapshot_sha256 text PRIMARY KEY CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    source text NOT NULL CHECK (source IN ('kimdis','gemi')),
    kimdis_run_id uuid REFERENCES nima.ingest_runs(run_id),
    gemi_run_id uuid REFERENCES nima.gemi_imports(run_id),
    document jsonb NOT NULL CHECK (jsonb_typeof(document)='object'),
    extraction_version text GENERATED ALWAYS AS (document->>'artifact_version') STORED NOT NULL,
    record_count integer GENERATED ALWAYS AS (jsonb_array_length(document->'records')) STORED NOT NULL,
    assertion_count integer GENERATED ALWAYS AS (jsonb_array_length(jsonb_path_query_array(document,'strict $.records[*].assertions[*]'))) STORED NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    CHECK ((source='kimdis' AND kimdis_run_id IS NOT NULL AND gemi_run_id IS NULL)
        OR (source='gemi' AND gemi_run_id IS NOT NULL AND kimdis_run_id IS NULL)),
    CHECK ((document->>'source') IS NOT DISTINCT FROM source),
    CHECK ((document#>>'{capture,run_id}') IS NOT DISTINCT FROM coalesce(kimdis_run_id,gemi_run_id)::text),
    CHECK ((document->'query') IS NOT DISTINCT FROM '{"dimension":null,"code":null}'::jsonb),
    CHECK (coalesce(document#>>'{capture,status}' IN ('complete','quarantined'),false)),
    CHECK (jsonb_typeof(document->'records') IS NOT DISTINCT FROM 'array'),
    CHECK (record_count BETWEEN 0 AND 5000 AND record_count=jsonb_array_length(document->'records')),
    CHECK ((document#>>'{coverage,record_count}') IS NOT DISTINCT FROM record_count::text),
    CHECK ((document#>>'{coverage,assertion_count}') IS NOT DISTINCT FROM assertion_count::text),
    CHECK (source<>'gemi' OR record_count<=10),
    CHECK (assertion_count BETWEEN 0 AND 10000),
    CHECK (octet_length(document::text)<=67108864)
);
CREATE TRIGGER metadata_snapshots_immutable BEFORE UPDATE OR DELETE ON nima_processing.metadata_snapshots
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER metadata_snapshots_no_truncate BEFORE TRUNCATE ON nima_processing.metadata_snapshots
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
REVOKE ALL ON nima_processing.metadata_snapshots FROM PUBLIC;

-- PostgreSQL 17 JSON processing: https://www.postgresql.org/docs/17/functions-json.html
CREATE VIEW nima_processing.reported_market_metadata AS
SELECT s.snapshot_sha256,s.source,coalesce(s.kimdis_run_id,s.gemi_run_id) AS source_run_id,
    s.extraction_version,s.processed_at,s.database_principal,
    s.document#>>'{capture,status}' AS capture_status,
    r.ordinality-1 AS record_ordinal,a.ordinality-1 AS assertion_ordinal,
    r.value->>'source_id' AS source_id,r.value->>'record_status' AS record_status,
    (r.value->>'observed_at')::timestamptz AS observed_at,
    r.value->>'raw_sha256' AS raw_sha256,r.value->>'content_sha256' AS content_sha256,
    r.value->>'record_pointer' AS record_pointer,
    a.value->>'dimension' AS dimension,a.value->>'code' AS code,a.value->>'label' AS label,
    a.value->>'status' AS status,a.value->>'taxonomy_version' AS taxonomy_version,
    a.value->>'taxonomy_validation' AS taxonomy_validation,
    a.value->>'json_pointer' AS json_pointer,a.value->>'expected_pointer' AS expected_pointer,
    a.value->'field_pointers' AS field_pointers,a.value->'details' AS details,a.value AS assertion
FROM nima_processing.metadata_snapshots s
CROSS JOIN LATERAL jsonb_array_elements(s.document->'records') WITH ORDINALITY r
CROSS JOIN LATERAL jsonb_array_elements(r.value->'assertions') WITH ORDINALITY a;
REVOKE ALL ON nima_processing.reported_market_metadata FROM PUBLIC;
