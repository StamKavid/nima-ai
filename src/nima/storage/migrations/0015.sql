-- Additive citation-acceptance attestation history. Legacy 0010 objects stay intact.
CREATE TABLE nima_validation.acceptance_attempts (
    attempt_id uuid PRIMARY KEY,
    intent_sha256 text NOT NULL CHECK (intent_sha256 ~ '^[0-9a-f]{64}$'),
    document jsonb NOT NULL CHECK (jsonb_typeof(document)='object' AND octet_length(document::text)<=4096),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    UNIQUE (attempt_id,intent_sha256),
    CHECK (document ?& ARRAY['version','use','subject_format','policy_id','request_sha256',
        'subject_sha256','policy_sha256','policy_version','recorder_version']),
    CHECK (document - ARRAY['version','use','subject_format','policy_id','request_sha256',
        'subject_sha256','policy_sha256','policy_version','recorder_version'] = '{}'::jsonb),
    CHECK (document @> '{"version":"nima-acceptance-intent-v1","use":"citations",
        "subject_format":"nima-source-citations-v1","policy_id":"nima.dataset-acceptance"}'::jsonb),
    CHECK (coalesce(jsonb_typeof(document->'request_sha256')='string'
        AND document->>'request_sha256' ~ '^[0-9a-f]{64}$',false)),
    CHECK (coalesce(jsonb_typeof(document->'subject_sha256')='string'
        AND document->>'subject_sha256' ~ '^[0-9a-f]{64}$',false)),
    CHECK (coalesce(jsonb_typeof(document->'policy_sha256')='string'
        AND document->>'policy_sha256' ~ '^[0-9a-f]{64}$',false)),
    CHECK (coalesce(jsonb_typeof(document->'policy_version')='string'
        AND length(document->>'policy_version')<=64
        AND document->>'policy_version' ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$',false)),
    CHECK (coalesce(jsonb_typeof(document->'recorder_version')='string'
        AND document->>'recorder_version' ~ '^[A-Za-z][A-Za-z0-9_.-]{0,95}$',false))
);
CREATE TABLE nima_validation.acceptance_outcomes (
    attempt_id uuid PRIMARY KEY,
    intent_sha256 text NOT NULL,
    outcome_sha256 text NOT NULL CHECK (outcome_sha256 ~ '^[0-9a-f]{64}$'),
    document jsonb NOT NULL CHECK (jsonb_typeof(document)='object' AND octet_length(document::text)<=4096),
    acceptance_body bytea CHECK (octet_length(acceptance_body) BETWEEN 1 AND 65536),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    FOREIGN KEY (attempt_id,intent_sha256)
        REFERENCES nima_validation.acceptance_attempts(attempt_id,intent_sha256),
    CHECK ((document->>'intent_sha256') IS NOT DISTINCT FROM intent_sha256),
    CHECK (document ?& ARRAY['version','intent_sha256','execution_state','data_fitness','acceptance_sha256','refusal_code']),
    CHECK (document - ARRAY['version','intent_sha256','execution_state','data_fitness','acceptance_sha256','refusal_code'] = '{}'::jsonb),
    CHECK (document @> '{"version":"nima-acceptance-outcome-v1"}'::jsonb),
    CHECK (coalesce(
        (document->>'execution_state'='assessed'
            AND document->>'data_fitness' IN ('ready','limited','blocked','not_assessed')
            AND document->'refusal_code'='null'::jsonb
            AND acceptance_body IS NOT NULL
            AND jsonb_typeof(document->'acceptance_sha256')='string'
            AND document->>'acceptance_sha256'=pg_catalog.encode(pg_catalog.sha256(acceptance_body),'hex'))
        OR (document->>'execution_state'='refused'
            AND document->'data_fitness'='null'::jsonb
            AND document->'acceptance_sha256'='null'::jsonb
            AND acceptance_body IS NULL
            AND document->>'refusal_code' IN ('acceptance_input','acceptance_limit',
                'acceptance_evidence','acceptance_database','acceptance_contract','acceptance_output')),
        false))
);
CREATE FUNCTION nima_validation.stamp_acceptance() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.database_principal := current_user;
    IF TG_TABLE_NAME='acceptance_attempts' THEN NEW.started_at := clock_timestamp();
    ELSE NEW.recorded_at := clock_timestamp(); END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER acceptance_attempt_stamp BEFORE INSERT ON nima_validation.acceptance_attempts
    FOR EACH ROW EXECUTE FUNCTION nima_validation.stamp_acceptance();
CREATE TRIGGER acceptance_outcome_stamp BEFORE INSERT ON nima_validation.acceptance_outcomes
    FOR EACH ROW EXECUTE FUNCTION nima_validation.stamp_acceptance();
CREATE TRIGGER acceptance_attempts_immutable BEFORE UPDATE OR DELETE ON nima_validation.acceptance_attempts
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER acceptance_outcomes_immutable BEFORE UPDATE OR DELETE ON nima_validation.acceptance_outcomes
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER acceptance_attempts_no_truncate BEFORE TRUNCATE ON nima_validation.acceptance_attempts
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER acceptance_outcomes_no_truncate BEFORE TRUNCATE ON nima_validation.acceptance_outcomes
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
REVOKE ALL ON nima_validation.acceptance_attempts,nima_validation.acceptance_outcomes FROM PUBLIC;
