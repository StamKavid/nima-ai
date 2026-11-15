-- Review state is separate from immutable source/projection and delivery state.
CREATE TABLE nima.identity_review_heads (
    observation_id bigint NOT NULL,
    projection_version text NOT NULL,
    role text NOT NULL CHECK (role IN ('buyer','supplier')),
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 999),
    run_id uuid NOT NULL REFERENCES nima.ingest_runs,
    source_id text NOT NULL,
    normalizer_version text NOT NULL,
    content_sha256 text NOT NULL,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    latest_event_id uuid,
    PRIMARY KEY (observation_id,projection_version,role,ordinal),
    FOREIGN KEY (projection_version,observation_id) REFERENCES nima.projection_receipts,
    FOREIGN KEY (projection_version,source_id,normalizer_version,content_sha256,role,ordinal)
        REFERENCES nima.projection_mentions,
    CHECK ((revision = 0) = (latest_event_id IS NULL))
);

CREATE FUNCTION nima.guard_review_subject() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NOT EXISTS (SELECT 1 FROM nima.observations o
            WHERE o.observation_id=NEW.observation_id AND o.run_id=NEW.run_id
            AND o.source_id=NEW.source_id AND o.normalizer_version=NEW.normalizer_version
            AND o.content_sha256=NEW.content_sha256) THEN
            RAISE EXCEPTION 'Review subject differs from source observation' USING ERRCODE='23514';
        END IF;
        IF NEW.revision <> 0 THEN
            RAISE EXCEPTION 'New review head must start at zero' USING ERRCODE='23514';
        END IF;
    ELSIF (to_jsonb(OLD)-'revision'-'latest_event_id') IS DISTINCT FROM
          (to_jsonb(NEW)-'revision'-'latest_event_id') OR NEW.revision <> OLD.revision+1 THEN
        RAISE EXCEPTION 'Review head identity or revision differs' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER review_subject_identity BEFORE INSERT OR UPDATE ON nima.identity_review_heads
    FOR EACH ROW EXECUTE FUNCTION nima.guard_review_subject();
CREATE TRIGGER review_heads_no_delete BEFORE DELETE ON nima.identity_review_heads
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();

CREATE TABLE nima.identity_entities (
    entity_id uuid PRIMARY KEY,
    kind text NOT NULL DEFAULT 'unclassified' CHECK (kind='unclassified'),
    anchor_import_id uuid NOT NULL,
    registry_number text NOT NULL,
    creating_event_id uuid NOT NULL UNIQUE,
    creating_operation text NOT NULL DEFAULT 'accept' CHECK (creating_operation='accept'),
    UNIQUE (anchor_import_id,registry_number),
    UNIQUE (entity_id,registry_number),
    FOREIGN KEY (anchor_import_id,registry_number) REFERENCES nima.gemi_observations
);

CREATE TABLE nima.identity_review_events (
    event_id uuid PRIMARY KEY,
    observation_id bigint NOT NULL,
    projection_version text NOT NULL,
    role text NOT NULL,
    ordinal integer NOT NULL,
    subject_revision bigint NOT NULL CHECK (subject_revision > 0),
    candidate_import_id uuid NOT NULL,
    registry_number text NOT NULL,
    operation text NOT NULL CHECK (operation IN ('accept','reject','revoke')),
    entity_id uuid,
    reverses_event_id uuid,
    reversed_operation text CHECK (reversed_operation IN ('accept','reject')),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    request_payload jsonb NOT NULL CHECK (jsonb_typeof(request_payload)='object'),
    report_sha256 text CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    rationale text NOT NULL CHECK (octet_length(rationale) BETWEEN 1 AND 4096
        AND length(btrim(rationale,E' \t\r\n')) > 0),
    issues text[] NOT NULL CHECK (array_position(issues,NULL) IS NULL),
    policy_version text NOT NULL CHECK (length(policy_version) > 0),
    database_principal name NOT NULL DEFAULT session_user,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (observation_id,projection_version,role,ordinal,subject_revision),
    UNIQUE (event_id,observation_id,projection_version,role,ordinal,subject_revision),
    UNIQUE (event_id,entity_id,candidate_import_id,registry_number,operation),
    UNIQUE (event_id,operation,observation_id,projection_version,role,ordinal,
            candidate_import_id,registry_number),
    FOREIGN KEY (observation_id,projection_version,role,ordinal)
        REFERENCES nima.identity_review_heads,
    FOREIGN KEY (candidate_import_id,registry_number) REFERENCES nima.gemi_observations,
    FOREIGN KEY (entity_id,registry_number) REFERENCES nima.identity_entities(entity_id,registry_number)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (reverses_event_id,reversed_operation,observation_id,projection_version,role,ordinal,
                 candidate_import_id,registry_number)
        REFERENCES nima.identity_review_events
            (event_id,operation,observation_id,projection_version,role,ordinal,
             candidate_import_id,registry_number),
    CHECK ((operation='accept' AND entity_id IS NOT NULL AND report_sha256 IS NOT NULL
                AND reverses_event_id IS NULL AND reversed_operation IS NULL)
        OR (operation='reject' AND entity_id IS NULL AND report_sha256 IS NOT NULL
                AND reverses_event_id IS NULL AND reversed_operation IS NULL)
        OR (operation='revoke' AND entity_id IS NULL AND report_sha256 IS NULL
                AND reverses_event_id IS NOT NULL AND reversed_operation IS NOT NULL)),
    CHECK (event_id IS DISTINCT FROM reverses_event_id)
);

ALTER TABLE nima.identity_review_heads ADD FOREIGN KEY
    (latest_event_id,observation_id,projection_version,role,ordinal,revision)
    REFERENCES nima.identity_review_events
        (event_id,observation_id,projection_version,role,ordinal,subject_revision)
    DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE nima.identity_entities ADD FOREIGN KEY
    (creating_event_id,entity_id,anchor_import_id,registry_number,creating_operation)
    REFERENCES nima.identity_review_events
        (event_id,entity_id,candidate_import_id,registry_number,operation)
    DEFERRABLE INITIALLY DEFERRED;

-- A dated 404 may remain evidence but cannot anchor an entity or a review pair.
CREATE FUNCTION nima.guard_review_registry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    selected_import uuid;
BEGIN
    IF TG_TABLE_NAME='identity_entities' THEN
        selected_import := NEW.anchor_import_id;
    ELSE
        selected_import := NEW.candidate_import_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM nima.gemi_observations o
        WHERE o.run_id=selected_import AND o.registry_number=NEW.registry_number
            AND o.outcome='found' AND o.status=200) THEN
        RAISE EXCEPTION 'Review requires a found registry observation' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER review_entity_anchor BEFORE INSERT ON nima.identity_entities
    FOR EACH ROW EXECUTE FUNCTION nima.guard_review_registry();
CREATE TRIGGER review_event_candidate BEFORE INSERT ON nima.identity_review_events
    FOR EACH ROW EXECUTE FUNCTION nima.guard_review_registry();
CREATE TRIGGER identity_entities_immutable BEFORE UPDATE OR DELETE ON nima.identity_entities
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER identity_review_events_immutable BEFORE UPDATE OR DELETE ON nima.identity_review_events
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();

-- No grants: a database administrator chooses any dedicated operator privileges.
