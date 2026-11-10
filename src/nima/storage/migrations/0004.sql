-- Registry evidence has no procurement page/checkpoint or participation event.
CREATE TABLE nima.gemi_imports (
    run_id uuid PRIMARY KEY,
    import_version text NOT NULL CHECK (import_version = 'gemi-import-v1'),
    archive_root text NOT NULL,
    manifest bytea NOT NULL CHECK (octet_length(manifest) BETWEEN 1 AND 1048576),
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    normalizer_version text NOT NULL,
    source_url text NOT NULL,
    license text NOT NULL,
    publisher text NOT NULL,
    profile_count integer NOT NULL CHECK (profile_count BETWEEN 0 AND 10),
    not_found_count integer NOT NULL CHECK (not_found_count BETWEEN 0 AND 10),
    response_count integer NOT NULL CHECK (response_count BETWEEN 1 AND 30),
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (profile_count + not_found_count BETWEEN 1 AND 10),
    CHECK (response_count >= profile_count + not_found_count)
);
CREATE TABLE nima.gemi_responses (
    run_id uuid REFERENCES nima.gemi_imports,
    registry_number text CHECK (registry_number ~ '^[1-9][0-9]{0,63}$'),
    attempt integer CHECK (attempt BETWEEN 1 AND 3),
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL CHECK (finished_at >= started_at),
    status integer CHECK (status BETWEEN 100 AND 599),
    failure text CHECK (failure = 'transport'),
    raw_sha256 text REFERENCES nima.raw_objects,
    byte_length bigint CHECK (byte_length BETWEEN 0 AND 8388608),
    observed_at timestamptz,
    PRIMARY KEY (run_id, registry_number, attempt),
    UNIQUE (run_id, registry_number, attempt, status, raw_sha256, observed_at),
    CHECK ((raw_sha256 IS NULL) = (byte_length IS NULL)),
    CHECK ((raw_sha256 IS NULL) = (observed_at IS NULL)),
    CHECK ((raw_sha256 IS NULL) = (failure IS NOT NULL)),
    CHECK (raw_sha256 IS NULL OR status IS NOT NULL),
    CHECK (observed_at IS NULL OR observed_at BETWEEN started_at AND finished_at)
);
CREATE TABLE nima.gemi_profile_versions (
    source_id text CHECK (source_id ~ '^gemi:[1-9][0-9]{0,63}$'),
    normalizer_version text,
    raw_sha256 text REFERENCES nima.raw_objects,
    normalized jsonb NOT NULL CHECK (jsonb_typeof(normalized) = 'object'),
    PRIMARY KEY (source_id, normalizer_version, raw_sha256),
    CHECK ((normalized->>'source_id') IS NOT DISTINCT FROM source_id),
    CHECK ((normalized->>'normalizer_version') IS NOT DISTINCT FROM normalizer_version),
    CHECK ((normalized->>'response_sha256') IS NOT DISTINCT FROM raw_sha256)
);
CREATE TABLE nima.gemi_observations (
    run_id uuid,
    registry_number text,
    attempt integer NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('found', 'not_found_at_observation')),
    status integer NOT NULL CHECK (status IN (200, 404)),
    raw_sha256 text NOT NULL,
    observed_at timestamptz NOT NULL,
    source_id text,
    normalizer_version text,
    PRIMARY KEY (run_id, registry_number),
    FOREIGN KEY (run_id, registry_number, attempt, status, raw_sha256, observed_at)
        REFERENCES nima.gemi_responses
            (run_id, registry_number, attempt, status, raw_sha256, observed_at),
    FOREIGN KEY (source_id, normalizer_version, raw_sha256)
        REFERENCES nima.gemi_profile_versions,
    CHECK ((outcome = 'found' AND status = 200
                AND source_id IS NOT NULL AND source_id = 'gemi:' || registry_number
                AND normalizer_version IS NOT NULL)
        OR (outcome = 'not_found_at_observation' AND status = 404
                AND source_id IS NULL AND normalizer_version IS NULL))
);
CREATE TRIGGER gemi_imports_immutable BEFORE UPDATE OR DELETE ON nima.gemi_imports
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_responses_immutable BEFORE UPDATE OR DELETE ON nima.gemi_responses
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_versions_immutable BEFORE UPDATE OR DELETE ON nima.gemi_profile_versions
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_observations_immutable BEFORE UPDATE OR DELETE ON nima.gemi_observations
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
