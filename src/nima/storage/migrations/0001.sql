CREATE TABLE nima.raw_objects (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_length bigint NOT NULL CHECK (byte_length >= 0)
);
CREATE TABLE nima.ingest_runs (
    run_id uuid PRIMARY KEY,
    query jsonb NOT NULL CHECK (jsonb_typeof(query) = 'object'),
    connector_version text NOT NULL,
    normalizer_version text NOT NULL,
    archive_root text NOT NULL,
    next_page integer NOT NULL DEFAULT 0 CHECK (next_page >= 0),
    total_records bigint,
    total_pages integer,
    page_size integer,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((total_records IS NULL AND total_pages IS NULL AND page_size IS NULL)
        OR (total_records >= 0 AND total_pages >= 0 AND page_size > 0
            AND total_records IS NOT NULL AND total_pages IS NOT NULL AND page_size IS NOT NULL))
);
CREATE TABLE nima.run_pages (
    run_id uuid REFERENCES nima.ingest_runs,
    page_number integer CHECK (page_number >= 0),
    raw_sha256 text NOT NULL REFERENCES nima.raw_objects,
    observed_at timestamptz NOT NULL,
    record_count integer NOT NULL CHECK (record_count >= 0),
    quarantined_count integer NOT NULL CHECK (quarantined_count BETWEEN 0 AND record_count),
    PRIMARY KEY (run_id, page_number)
);
CREATE TABLE nima.source_records (source_id text PRIMARY KEY);
CREATE TABLE nima.record_versions (
    source_id text REFERENCES nima.source_records,
    normalizer_version text,
    content_sha256 text CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    normalized jsonb NOT NULL CHECK (jsonb_typeof(normalized) = 'object'),
    PRIMARY KEY (source_id, normalizer_version, content_sha256)
);
CREATE TABLE nima.observations (
    observation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL,
    page_number integer NOT NULL,
    record_index integer NOT NULL CHECK (record_index >= 0),
    source_id text NOT NULL,
    normalizer_version text NOT NULL,
    content_sha256 text NOT NULL,
    UNIQUE (run_id, page_number, record_index),
    UNIQUE (run_id, source_id),
    FOREIGN KEY (run_id, page_number) REFERENCES nima.run_pages,
    FOREIGN KEY (source_id, normalizer_version, content_sha256)
        REFERENCES nima.record_versions
);
CREATE TABLE nima.quarantine (
    run_id uuid,
    page_number integer,
    record_index integer CHECK (record_index >= 0),
    reason text NOT NULL,
    PRIMARY KEY (run_id, page_number, record_index),
    FOREIGN KEY (run_id, page_number) REFERENCES nima.run_pages
);
CREATE TABLE nima.outbox (
    observation_id bigint PRIMARY KEY REFERENCES nima.observations,
    event_type text NOT NULL DEFAULT 'record.observed' CHECK (event_type = 'record.observed'),
    delivered_at timestamptz
);
CREATE INDEX outbox_pending ON nima.outbox (observation_id) WHERE delivered_at IS NULL;
CREATE FUNCTION nima.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Evidence rows are immutable' USING ERRCODE = '55000';
END;
$$;
CREATE TRIGGER versions_immutable BEFORE UPDATE OR DELETE ON nima.record_versions
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER observations_immutable BEFORE UPDATE OR DELETE ON nima.observations
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER pages_immutable BEFORE UPDATE OR DELETE ON nima.run_pages
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER quarantine_immutable BEFORE UPDATE OR DELETE ON nima.quarantine
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER raw_objects_immutable BEFORE UPDATE OR DELETE ON nima.raw_objects
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
