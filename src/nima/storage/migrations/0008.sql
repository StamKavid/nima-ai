-- Reprocessing is derived state; it never advances source observation time.
CREATE SCHEMA nima_processing;
REVOKE ALL ON SCHEMA nima_processing FROM PUBLIC;
CREATE TABLE nima_processing.replay_batches (
    replay_sha256 text PRIMARY KEY CHECK (replay_sha256 ~ '^[0-9a-f]{64}$'),
    source_run_id uuid NOT NULL REFERENCES nima.ingest_runs,
    normalizer_version text NOT NULL CHECK (length(normalizer_version)>0),
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest)='object'),
    page_count integer NOT NULL CHECK (page_count BETWEEN 1 AND 32),
    normalized_count integer NOT NULL CHECK (normalized_count>=0),
    quarantined_count integer NOT NULL CHECK (quarantined_count>=0),
    processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    UNIQUE (replay_sha256,source_run_id),
    CHECK (normalized_count+quarantined_count<=5000)
);
CREATE TABLE nima_processing.replay_results (
    replay_sha256 text NOT NULL,
    source_run_id uuid NOT NULL,
    page_number integer NOT NULL CHECK (page_number BETWEEN 0 AND 31),
    record_index integer NOT NULL CHECK (record_index BETWEEN 0 AND 4999),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('normalized','quarantined')),
    source_id text,
    normalized jsonb,
    quarantine_reason text,
    PRIMARY KEY (replay_sha256,page_number,record_index),
    FOREIGN KEY (replay_sha256,source_run_id)
        REFERENCES nima_processing.replay_batches(replay_sha256,source_run_id),
    FOREIGN KEY (source_run_id,page_number) REFERENCES nima.run_pages(run_id,page_number),
    CHECK ((status='normalized' AND source_id IS NOT NULL AND length(source_id)>0
            AND normalized IS NOT NULL AND jsonb_typeof(normalized)='object'
            AND (normalized->>'source_id') IS NOT DISTINCT FROM source_id
            AND quarantine_reason IS NULL)
        OR (status='quarantined' AND source_id IS NULL AND normalized IS NULL
            AND quarantine_reason IS NOT NULL AND length(quarantine_reason)>0))
);
CREATE FUNCTION nima_processing.guard_replay_location() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM nima.run_pages p
        JOIN nima_processing.replay_batches b ON b.replay_sha256=NEW.replay_sha256
        WHERE p.run_id=NEW.source_run_id AND p.page_number=NEW.page_number
        AND NEW.record_index<p.record_count AND NEW.page_number<b.page_count) THEN
        RAISE EXCEPTION 'Replay location outside selected capture' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER replay_location BEFORE INSERT ON nima_processing.replay_results
    FOR EACH ROW EXECUTE FUNCTION nima_processing.guard_replay_location();
CREATE TRIGGER replay_batches_immutable BEFORE UPDATE OR DELETE ON nima_processing.replay_batches
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER replay_results_immutable BEFORE UPDATE OR DELETE ON nima_processing.replay_results
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER replay_batches_no_truncate BEFORE TRUNCATE ON nima_processing.replay_batches
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER replay_results_no_truncate BEFORE TRUNCATE ON nima_processing.replay_results
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE VIEW nima_processing.replayed_contracts AS
SELECT b.replay_sha256,b.source_run_id AS run_id,b.normalizer_version,
    b.manifest->'source_run'->>'status' AS capture_status,
    b.processed_at,b.database_principal,p.observed_at,p.raw_sha256,
    r.page_number,r.record_index,'/content/'||r.record_index AS json_pointer,
    r.content_sha256,r.source_id,r.normalized
FROM nima_processing.replay_batches b
JOIN nima_processing.replay_results r USING(replay_sha256,source_run_id)
JOIN nima.run_pages p ON p.run_id=r.source_run_id AND p.page_number=r.page_number
WHERE r.status='normalized';
