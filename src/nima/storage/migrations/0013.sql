-- Fifteen older evidence tables block UPDATE and DELETE with row triggers, but row
-- triggers never fire on TRUNCATE. Add the same statement-level guard the newer
-- evidence tables already carry. Additive: no data, table, column or function change.
CREATE TRIGGER raw_objects_no_truncate BEFORE TRUNCATE ON nima.raw_objects
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER run_pages_no_truncate BEFORE TRUNCATE ON nima.run_pages
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER record_versions_no_truncate BEFORE TRUNCATE ON nima.record_versions
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER observations_no_truncate BEFORE TRUNCATE ON nima.observations
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER quarantine_no_truncate BEFORE TRUNCATE ON nima.quarantine
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER projection_contracts_no_truncate BEFORE TRUNCATE ON nima.projection_contracts
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER projection_mentions_no_truncate BEFORE TRUNCATE ON nima.projection_mentions
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER projection_receipts_no_truncate BEFORE TRUNCATE ON nima.projection_receipts
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_imports_no_truncate BEFORE TRUNCATE ON nima.gemi_imports
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_responses_no_truncate BEFORE TRUNCATE ON nima.gemi_responses
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_profile_versions_no_truncate BEFORE TRUNCATE ON nima.gemi_profile_versions
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER gemi_observations_no_truncate BEFORE TRUNCATE ON nima.gemi_observations
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER refresh_events_no_truncate BEFORE TRUNCATE ON nima.refresh_events
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER identity_entities_no_truncate BEFORE TRUNCATE ON nima.identity_entities
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER identity_review_events_no_truncate BEFORE TRUNCATE ON nima.identity_review_events
    FOR EACH STATEMENT EXECUTE FUNCTION nima.reject_mutation();
