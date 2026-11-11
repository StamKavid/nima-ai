CREATE TABLE nima.workflow_requests (
    request_id uuid PRIMARY KEY,
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    parameters_sha256 text NOT NULL CHECK (parameters_sha256 ~ '^[0-9a-f]{64}$'),
    run_id uuid UNIQUE REFERENCES nima.ingest_runs,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','collected','projecting','complete','partial','failed','deferred')),
    failure text,
    executions integer NOT NULL DEFAULT 0 CHECK (executions BETWEEN 0 AND 4),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 300),
    projection_batches integer NOT NULL DEFAULT 0 CHECK (projection_batches BETWEEN 0 AND 100),
    source_owner uuid,
    started_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE nima.workflow_dispatches (
    dispatch_id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES nima.workflow_requests,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','unknown','accepted')),
    engine_run_id uuid,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    CHECK ((state = 'pending') = (finished_at IS NULL)),
    CHECK ((state = 'accepted') = (engine_run_id IS NOT NULL))
);
CREATE INDEX dispatches_by_request ON nima.workflow_dispatches (request_id, created_at);
CREATE FUNCTION nima.guard_workflow_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.request_id IS DISTINCT FROM NEW.request_id
        OR OLD.parameters IS DISTINCT FROM NEW.parameters
        OR OLD.parameters_sha256 IS DISTINCT FROM NEW.parameters_sha256
        OR OLD.created_at IS DISTINCT FROM NEW.created_at
        OR (OLD.run_id IS NOT NULL AND OLD.run_id IS DISTINCT FROM NEW.run_id)
        OR (OLD.started_at IS NOT NULL AND OLD.started_at IS DISTINCT FROM NEW.started_at)
        OR NEW.executions < OLD.executions OR NEW.attempts < OLD.attempts
        OR NEW.projection_batches < OLD.projection_batches
        OR (OLD.status = 'complete' AND NEW.status <> 'complete') THEN
        RAISE EXCEPTION 'Workflow identity or consumed budget cannot change' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER workflow_identity BEFORE UPDATE ON nima.workflow_requests
    FOR EACH ROW EXECUTE FUNCTION nima.guard_workflow_identity();
CREATE TRIGGER workflow_requests_no_delete BEFORE DELETE ON nima.workflow_requests
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER workflow_dispatches_no_delete BEFORE DELETE ON nima.workflow_dispatches
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE FUNCTION nima.guard_dispatch_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.dispatch_id IS DISTINCT FROM NEW.dispatch_id
        OR OLD.request_id IS DISTINCT FROM NEW.request_id
        OR OLD.created_at IS DISTINCT FROM NEW.created_at OR OLD.state <> 'pending' THEN
        RAISE EXCEPTION 'Dispatch history cannot be rewritten' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dispatch_identity BEFORE UPDATE ON nima.workflow_dispatches
    FOR EACH ROW EXECUTE FUNCTION nima.guard_dispatch_identity();
