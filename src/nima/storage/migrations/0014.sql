-- GEMI AFM search runs (SPEC-gemi-afm-import, slice L5a). Evidence only, additive, immutable.
-- A search is requested by AFM, one answer holds several companies, and the profile tables key
-- their responses by registry number, so a search run gets its own four tables. Each hit's
-- normalized payload is stored as a gemi_profile_versions row whose raw hash is the search
-- response's, so the evidence location (/searchResults/<i>/...) stays exact. No existing table,
-- column or constraint changes, and no privilege is granted.
CREATE TABLE nima.gemi_search_imports (
    run_id uuid PRIMARY KEY,
    import_version text NOT NULL CHECK (import_version = 'gemi-search-import-v1'),
    archive_root text NOT NULL,
    manifest bytea NOT NULL CHECK (octet_length(manifest) BETWEEN 1 AND 1048576),
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    connector_version text NOT NULL CHECK (connector_version = 'gemi-afm-search-v1'),
    normalizer_version text NOT NULL,
    source_url text NOT NULL,
    license text NOT NULL,
    publisher text NOT NULL,
    afm_count integer NOT NULL CHECK (afm_count BETWEEN 1 AND 25),
    request_count integer NOT NULL CHECK (request_count BETWEEN 1 AND 75),
    hit_count integer NOT NULL CHECK (hit_count BETWEEN 0 AND 500),
    unconfirmed_quarantine_count integer NOT NULL CHECK (unconfirmed_quarantine_count BETWEEN 0 AND 25),
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (request_count >= afm_count),
    CHECK (unconfirmed_quarantine_count <= afm_count)
);

-- One row per HTTP attempt. The AFM keeps its leading zero, so it is text of nine digits.
CREATE TABLE nima.gemi_search_requests (
    run_id uuid REFERENCES nima.gemi_search_imports,
    afm text CHECK (afm ~ '^[0-9]{9}$' AND afm <> '000000000'),
    attempt integer CHECK (attempt BETWEEN 1 AND 3),
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL CHECK (finished_at >= started_at),
    status integer CHECK (status BETWEEN 100 AND 599),
    failure text CHECK (failure = 'transport'),
    raw_sha256 text REFERENCES nima.raw_objects,
    byte_length bigint CHECK (byte_length BETWEEN 0 AND 8388608),
    observed_at timestamptz,
    PRIMARY KEY (run_id, afm, attempt),
    UNIQUE (run_id, afm, attempt, status, raw_sha256, observed_at),
    CHECK ((raw_sha256 IS NULL) = (byte_length IS NULL)),
    CHECK ((raw_sha256 IS NULL) = (observed_at IS NULL)),
    CHECK ((raw_sha256 IS NULL) = (failure IS NOT NULL)),
    CHECK (raw_sha256 IS NULL OR status IS NOT NULL),
    CHECK (observed_at IS NULL OR observed_at BETWEEN started_at AND finished_at)
);

-- One row per searched AFM: the fixed outcome and the final request it rests on. A 404 says
-- nothing about whether a company exists; an unconfirmed quarantine rests on a response media
-- type that is not archived.
CREATE TABLE nima.gemi_search_outcomes (
    run_id uuid,
    afm text,
    attempt integer NOT NULL,
    outcome text NOT NULL CHECK (outcome IN
        ('hit_single', 'hit_multiple', 'truncated', 'afm_mismatch',
         'not_found_at_observation', 'quarantined')),
    status integer NOT NULL CHECK (status IN (200, 404)),
    raw_sha256 text NOT NULL,
    observed_at timestamptz NOT NULL,
    truncated boolean NOT NULL,
    unconfirmed_quarantine boolean NOT NULL DEFAULT false,
    hit_count integer NOT NULL CHECK (hit_count BETWEEN 0 AND 20),
    PRIMARY KEY (run_id, afm),
    UNIQUE (run_id, afm, raw_sha256),
    FOREIGN KEY (run_id, afm, attempt, status, raw_sha256, observed_at)
        REFERENCES nima.gemi_search_requests (run_id, afm, attempt, status, raw_sha256, observed_at),
    CHECK ((outcome = 'not_found_at_observation' AND status = 404
                AND hit_count = 0 AND NOT truncated AND NOT unconfirmed_quarantine)
        OR (outcome = 'quarantined' AND status = 200 AND hit_count = 0 AND NOT truncated)
        OR (outcome = 'hit_single' AND status = 200 AND hit_count = 1
                AND NOT truncated AND NOT unconfirmed_quarantine)
        OR (outcome = 'hit_multiple' AND status = 200 AND hit_count >= 2
                AND NOT truncated AND NOT unconfirmed_quarantine)
        OR (outcome = 'truncated' AND status = 200 AND hit_count >= 1 AND truncated
                AND NOT unconfirmed_quarantine)
        OR (outcome = 'afm_mismatch' AND status = 200 AND hit_count >= 1
                AND NOT unconfirmed_quarantine))
);

-- One row per returned company. Every hit is kept; none is chosen. afm_matches says whether the
-- company reports the queried AFM; a branch repeats its head office's AFM.
CREATE TABLE nima.gemi_search_hits (
    run_id uuid,
    afm text,
    hit_index integer CHECK (hit_index BETWEEN 0 AND 19),
    registry_number text NOT NULL CHECK (registry_number ~ '^[1-9][0-9]{0,63}$'),
    afm_matches boolean NOT NULL,
    raw_sha256 text NOT NULL,
    source_id text NOT NULL,
    normalizer_version text NOT NULL,
    PRIMARY KEY (run_id, afm, hit_index),
    UNIQUE (run_id, afm, registry_number),
    FOREIGN KEY (run_id, afm, raw_sha256)
        REFERENCES nima.gemi_search_outcomes (run_id, afm, raw_sha256),
    FOREIGN KEY (source_id, normalizer_version, raw_sha256)
        REFERENCES nima.gemi_profile_versions,
    CHECK (source_id = 'gemi:' || registry_number)
);

CREATE TRIGGER gemi_search_imports_immutable BEFORE UPDATE OR DELETE ON nima.gemi_search_imports
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_requests_immutable BEFORE UPDATE OR DELETE ON nima.gemi_search_requests
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_outcomes_immutable BEFORE UPDATE OR DELETE ON nima.gemi_search_outcomes
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_hits_immutable BEFORE UPDATE OR DELETE ON nima.gemi_search_hits
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_imports_no_truncate BEFORE TRUNCATE ON nima.gemi_search_imports
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_requests_no_truncate BEFORE TRUNCATE ON nima.gemi_search_requests
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_outcomes_no_truncate BEFORE TRUNCATE ON nima.gemi_search_outcomes
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_search_hits_no_truncate BEFORE TRUNCATE ON nima.gemi_search_hits
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
