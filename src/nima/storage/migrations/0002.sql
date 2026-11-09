ALTER TABLE nima.ingest_runs
    ADD COLUMN owner uuid,
    ADD COLUMN settings jsonb,
    ADD COLUMN status text NOT NULL DEFAULT 'unmanaged'
        CHECK (status IN ('unmanaged', 'running', 'failed', 'interrupted', 'complete', 'quarantined')),
    ADD COLUMN failure text,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT clock_timestamp();
-- Historical v1 rows keep unknown IDs; only new managed runs are inspectable.
ALTER TABLE nima.run_pages ADD COLUMN source_ids text[];
CREATE TABLE nima.http_attempts (
    attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES nima.ingest_runs,
    owner uuid NOT NULL,
    page_number integer NOT NULL CHECK (page_number >= 0),
    retry_number integer NOT NULL CHECK (retry_number > 0),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    state text NOT NULL DEFAULT 'started' CHECK (state IN ('started', 'finished')),
    raw_sha256 text REFERENCES nima.raw_objects,
    receipt jsonb NOT NULL CHECK (jsonb_typeof(receipt) = 'object'),
    CHECK ((state = 'started' AND finished_at IS NULL) OR
           (state = 'finished' AND finished_at IS NOT NULL))
);
CREATE INDEX attempts_by_run ON nima.http_attempts (run_id, attempt_id);
