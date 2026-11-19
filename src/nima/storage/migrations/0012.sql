CREATE TABLE nima.refresh_successions (
    predecessor_id uuid PRIMARY KEY REFERENCES nima.refresh_retirements(policy_id),
    successor_id uuid NOT NULL UNIQUE REFERENCES nima.refresh_policies(policy_id),
    new_budgets_authorized boolean NOT NULL CHECK (new_budgets_authorized IS TRUE),
    budget_profile text NOT NULL CHECK (budget_profile='nima-refresh-budgets-v1'),
    successor_configuration_sha256 text NOT NULL
        CHECK (successor_configuration_sha256 ~ '^[0-9a-f]{64}$'),
    authorized_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    CHECK (predecessor_id<>successor_id)
);
REVOKE ALL ON nima.refresh_successions FROM PUBLIC;

CREATE FUNCTION nima.stamp_refresh_succession() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    candidate nima.refresh_policies%ROWTYPE;
    previous_configuration jsonb;
BEGIN
    SELECT * INTO candidate FROM nima.refresh_policies
        WHERE policy_id=NEW.successor_id FOR UPDATE;
    SELECT configuration INTO previous_configuration FROM nima.refresh_policies
        WHERE policy_id=NEW.predecessor_id;
    IF candidate.policy_id IS NULL OR candidate.state<>'paused'
        OR candidate.last_tick_at IS NOT NULL
        OR EXISTS (SELECT 1 FROM nima.refresh_retirements WHERE policy_id=NEW.successor_id)
        OR EXISTS (SELECT 1 FROM nima.refresh_cycles WHERE policy_id=NEW.successor_id)
        OR EXISTS (SELECT 1 FROM nima.refresh_events WHERE policy_id=NEW.successor_id AND state<>'paused')
        OR (candidate.configuration - ARRAY['connector_version','normalizer_version'])
            IS DISTINCT FROM (previous_configuration - ARRAY['connector_version','normalizer_version'])
    THEN
        RAISE EXCEPTION 'Successor must be fresh, paused and in the same scope' USING
            ERRCODE='55000', CONSTRAINT='refresh_succession_valid';
    END IF;
    NEW.successor_configuration_sha256 := candidate.configuration_sha256;
    NEW.authorized_at := clock_timestamp();
    NEW.database_principal := current_user;
    RETURN NEW;
END;
$$;
CREATE TRIGGER refresh_succession_stamp BEFORE INSERT ON nima.refresh_successions
    FOR EACH ROW EXECUTE FUNCTION nima.stamp_refresh_succession();
CREATE TRIGGER refresh_succession_immutable BEFORE UPDATE OR DELETE ON nima.refresh_successions
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER refresh_succession_no_truncate BEFORE TRUNCATE ON nima.refresh_successions
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
