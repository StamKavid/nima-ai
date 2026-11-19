-- Explicit post-publication validation; no source or processing rows are changed.
CREATE SCHEMA nima_validation;
REVOKE ALL ON SCHEMA nima_validation FROM PUBLIC;
CREATE TABLE nima_validation.attempts (
    attempt_id uuid PRIMARY KEY,
    intent_sha256 text NOT NULL CHECK (intent_sha256 ~ '^[0-9a-f]{64}$'),
    document jsonb NOT NULL CHECK (jsonb_typeof(document)='object' AND octet_length(document::text)<=4096),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    UNIQUE (attempt_id,intent_sha256),
    CHECK (coalesce(document->>'version'='nima-validation-intent-v1',false)),
    CHECK (coalesce(document->>'contract_id'='nima.supplier-buyers-readout',false)),
    CHECK (coalesce(document->>'validator_version'='nima-readout-verification-v1',false)),
    CHECK (coalesce(document->>'artifact_sha256' ~ '^[0-9a-f]{64}$',false)),
    CHECK (coalesce(document->>'request_sha256' ~ '^[0-9a-f]{64}$',false)),
    CHECK (coalesce(document->>'contract_sha256' ~ '^[0-9a-f]{64}$',false))
);
CREATE TABLE nima_validation.outcomes (
    attempt_id uuid PRIMARY KEY,
    intent_sha256 text NOT NULL,
    outcome_sha256 text NOT NULL CHECK (outcome_sha256 ~ '^[0-9a-f]{64}$'),
    document jsonb NOT NULL CHECK (jsonb_typeof(document)='object' AND octet_length(document::text)<=4096),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    database_principal name NOT NULL DEFAULT current_user,
    FOREIGN KEY (attempt_id,intent_sha256) REFERENCES nima_validation.attempts(attempt_id,intent_sha256),
    CHECK ((document->>'intent_sha256') IS NOT DISTINCT FROM intent_sha256),
    CHECK (coalesce(document->>'version'='nima-validation-outcome-v1',false)),
    CHECK (coalesce((document->>'status',document->>'check',document->>'reason') IN (
        ('blocked','artifact_integrity','artifact_unavailable'),
        ('failed','artifact_integrity','artifact_digest'),
        ('blocked','reconstruction','inputs_unavailable'),
        ('failed','output_contract','contract_rejected'),
        ('failed','byte_equivalence','bytes_differ'),
        ('passed','byte_equivalence','ok')),false))
);
CREATE FUNCTION nima_validation.stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.database_principal := current_user;
    IF TG_TABLE_NAME='attempts' THEN NEW.started_at := clock_timestamp();
    ELSE NEW.recorded_at := clock_timestamp(); END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validation_attempt_stamp BEFORE INSERT ON nima_validation.attempts
    FOR EACH ROW EXECUTE FUNCTION nima_validation.stamp();
CREATE TRIGGER validation_outcome_stamp BEFORE INSERT ON nima_validation.outcomes
    FOR EACH ROW EXECUTE FUNCTION nima_validation.stamp();
CREATE TRIGGER validation_attempts_immutable BEFORE UPDATE OR DELETE ON nima_validation.attempts
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER validation_outcomes_immutable BEFORE UPDATE OR DELETE ON nima_validation.outcomes
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER validation_attempts_no_truncate BEFORE TRUNCATE ON nima_validation.attempts
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER validation_outcomes_no_truncate BEFORE TRUNCATE ON nima_validation.outcomes
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
REVOKE ALL ON ALL TABLES IN SCHEMA nima_validation FROM PUBLIC;
