CREATE TABLE nima.refresh_retirements (
    policy_id uuid PRIMARY KEY REFERENCES nima.refresh_policies,
    reason text NOT NULL CHECK (reason IN
        ('budget_exhausted','processing_incompatible','operator_stop')),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user
);
REVOKE ALL ON nima.refresh_retirements FROM PUBLIC;

CREATE FUNCTION nima.stamp_refresh_retirement() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE next_state text;
BEGIN
    SELECT CASE WHEN state='paused' THEN 'paused' ELSE 'pending' END INTO next_state
        FROM nima.refresh_policies WHERE policy_id=NEW.policy_id FOR UPDATE;
    NEW.recorded_at := clock_timestamp();
    NEW.database_principal := current_user;
    IF EXISTS (SELECT 1 FROM nima.refresh_retirements WHERE policy_id=NEW.policy_id) THEN
        RETURN NEW;
    END IF;
    UPDATE nima.refresh_policies SET state=next_state WHERE policy_id=NEW.policy_id;
    INSERT INTO nima.refresh_events(policy_id,state) VALUES (NEW.policy_id,next_state);
    RETURN NEW;
END;
$$;
CREATE TRIGGER refresh_retirement_stamp BEFORE INSERT ON nima.refresh_retirements
    FOR EACH ROW EXECUTE FUNCTION nima.stamp_refresh_retirement();
CREATE TRIGGER refresh_retirement_immutable BEFORE UPDATE OR DELETE ON nima.refresh_retirements
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER refresh_retirement_no_truncate BEFORE TRUNCATE ON nima.refresh_retirements
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();

CREATE FUNCTION nima.assert_refresh_live(target uuid) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    -- A row lock, rather than the application's session lock, also covers manual
    -- dispatch on another connection. Check retirement after acquiring the lock.
    PERFORM 1 FROM nima.refresh_policies WHERE policy_id=target FOR UPDATE;
    IF EXISTS (SELECT 1 FROM nima.refresh_retirements WHERE policy_id=target) THEN
        RAISE EXCEPTION 'Refresh policy is retired' USING
            ERRCODE='55000', CONSTRAINT='refresh_policy_live';
    END IF;
END;
$$;
CREATE FUNCTION nima.guard_refresh_live() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid;
BEGIN
    IF TG_TABLE_NAME='workflow_dispatches' THEN
        SELECT policy_id INTO target FROM nima.refresh_windows WHERE request_id=NEW.request_id;
    ELSE
        target := NEW.policy_id;
    END IF;
    IF target IS NOT NULL THEN
        PERFORM nima.assert_refresh_live(target);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER refresh_live_cycle BEFORE INSERT ON nima.refresh_cycles
    FOR EACH ROW EXECUTE FUNCTION nima.guard_refresh_live();
CREATE TRIGGER refresh_live_window BEFORE INSERT ON nima.refresh_windows
    FOR EACH ROW EXECUTE FUNCTION nima.guard_refresh_live();
CREATE TRIGGER refresh_live_dispatch BEFORE INSERT ON nima.workflow_dispatches
    FOR EACH ROW EXECUTE FUNCTION nima.guard_refresh_live();
CREATE TRIGGER refresh_live_enable BEFORE UPDATE ON nima.refresh_policies
    FOR EACH ROW WHEN (NEW.state='enabled') EXECUTE FUNCTION nima.guard_refresh_live();
