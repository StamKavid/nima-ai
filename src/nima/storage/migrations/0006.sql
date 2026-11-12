CREATE TABLE nima.refresh_policies (
    policy_id uuid PRIMARY KEY,
    configuration jsonb NOT NULL,
    configuration_sha256 text NOT NULL CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
    start_date date NOT NULL,
    state text NOT NULL DEFAULT 'paused' CHECK (state IN ('paused','pending','enabled')),
    last_tick_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (configuration->>'start_date' = start_date::text)
);
CREATE TABLE nima.refresh_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_id uuid NOT NULL REFERENCES nima.refresh_policies,
    state text NOT NULL CHECK (state IN ('paused','pending','enabled')),
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE nima.refresh_cycles (
    cycle_id uuid PRIMARY KEY,
    policy_id uuid NOT NULL REFERENCES nima.refresh_policies,
    business_date date NOT NULL,
    query_dates date[] NOT NULL CHECK (cardinality(query_dates) BETWEEN 1 AND 14),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    UNIQUE (policy_id,business_date),
    UNIQUE (cycle_id,policy_id)
);
CREATE UNIQUE INDEX one_open_refresh_cycle ON nima.refresh_cycles(policy_id)
    WHERE completed_at IS NULL;
CREATE TABLE nima.refresh_windows (
    cycle_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    query_date date NOT NULL,
    request_id uuid NOT NULL UNIQUE REFERENCES nima.workflow_requests,
    dispatch_state text NOT NULL DEFAULT 'allocated'
        CHECK (dispatch_state IN ('allocated','sending','accepted')),
    completed_at timestamptz,
    source_observed_at timestamptz,
    CHECK ((completed_at IS NULL) = (source_observed_at IS NULL)),
    PRIMARY KEY (cycle_id,query_date),
    FOREIGN KEY (cycle_id,policy_id) REFERENCES nima.refresh_cycles(cycle_id,policy_id)
);
CREATE INDEX completed_refresh_dates ON nima.refresh_windows(policy_id,query_date)
    WHERE completed_at IS NOT NULL;
CREATE FUNCTION nima.guard_refresh_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'refresh_policies' THEN
        IF (to_jsonb(OLD)-'state'-'last_tick_at') IS DISTINCT FROM
           (to_jsonb(NEW)-'state'-'last_tick_at') THEN
            RAISE EXCEPTION 'Refresh policy is immutable' USING ERRCODE = '55000';
        END IF;
    ELSIF TG_TABLE_NAME = 'refresh_cycles' THEN
        IF (to_jsonb(OLD)-'completed_at') IS DISTINCT FROM (to_jsonb(NEW)-'completed_at')
            OR (OLD.completed_at IS NOT NULL AND OLD.completed_at IS DISTINCT FROM NEW.completed_at) THEN
            RAISE EXCEPTION 'Refresh cycle is immutable' USING ERRCODE = '55000';
        END IF;
    ELSE
        IF (to_jsonb(OLD)-'dispatch_state'-'completed_at'-'source_observed_at') IS DISTINCT FROM
           (to_jsonb(NEW)-'dispatch_state'-'completed_at'-'source_observed_at')
            OR (OLD.completed_at IS NOT NULL AND OLD.completed_at IS DISTINCT FROM NEW.completed_at)
            OR (OLD.source_observed_at IS NOT NULL AND OLD.source_observed_at IS DISTINCT FROM NEW.source_observed_at)
            OR (OLD.dispatch_state <> 'allocated' AND NEW.dispatch_state = 'allocated')
            OR (OLD.dispatch_state = 'accepted' AND NEW.dispatch_state <> 'accepted') THEN
            RAISE EXCEPTION 'Refresh child identity cannot regress' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER refresh_policy_identity BEFORE UPDATE ON nima.refresh_policies
    FOR EACH ROW EXECUTE FUNCTION nima.guard_refresh_identity();
CREATE TRIGGER refresh_cycle_identity BEFORE UPDATE ON nima.refresh_cycles
    FOR EACH ROW EXECUTE FUNCTION nima.guard_refresh_identity();
CREATE TRIGGER refresh_window_identity BEFORE UPDATE ON nima.refresh_windows
    FOR EACH ROW EXECUTE FUNCTION nima.guard_refresh_identity();
CREATE TRIGGER refresh_policies_no_delete BEFORE DELETE ON nima.refresh_policies
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER refresh_cycles_no_delete BEFORE DELETE ON nima.refresh_cycles
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER refresh_windows_no_delete BEFORE DELETE ON nima.refresh_windows
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER refresh_events_immutable BEFORE UPDATE OR DELETE ON nima.refresh_events
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
