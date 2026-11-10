CREATE TABLE nima.projection_contracts (
    projection_version text,
    source_id text,
    normalizer_version text,
    content_sha256 text,
    projection_sha256 text NOT NULL CHECK (projection_sha256 ~ '^[0-9a-f]{64}$'),
    title text NOT NULL,
    net_amount numeric,
    gross_amount numeric,
    currency text,
    bidder_count bigint CHECK (bidder_count >= 0),
    cancelled boolean,
    source_submitted_at text,
    source_updated_at text,
    supplier_count integer CHECK (supplier_count BETWEEN 0 AND 1000),
    PRIMARY KEY (projection_version, source_id, normalizer_version, content_sha256),
    FOREIGN KEY (source_id, normalizer_version, content_sha256) REFERENCES nima.record_versions
);
CREATE TABLE nima.projection_mentions (
    projection_version text,
    source_id text,
    normalizer_version text,
    content_sha256 text,
    role text CHECK (role IN ('buyer', 'supplier')),
    ordinal integer CHECK (ordinal BETWEEN 0 AND 999),
    name text,
    tax_id text,
    source_key text,
    country_code text,
    PRIMARY KEY (projection_version, source_id, normalizer_version, content_sha256, role, ordinal),
    FOREIGN KEY (projection_version, source_id, normalizer_version, content_sha256)
        REFERENCES nima.projection_contracts,
    CHECK (role <> 'buyer' OR ordinal = 0)
);
CREATE TABLE nima.projection_receipts (
    projection_version text,
    observation_id bigint REFERENCES nima.observations,
    processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (projection_version, observation_id)
);
CREATE TRIGGER projection_contracts_immutable BEFORE UPDATE OR DELETE ON nima.projection_contracts
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER projection_mentions_immutable BEFORE UPDATE OR DELETE ON nima.projection_mentions
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();
CREATE TRIGGER projection_receipts_immutable BEFORE UPDATE OR DELETE ON nima.projection_receipts
    FOR EACH ROW EXECUTE FUNCTION nima.reject_mutation();

CREATE VIEW nima.reported_procurement_edges AS
SELECT r.projection_version, o.observation_id, o.run_id, run.status AS run_status,
    o.source_id, o.normalizer_version, o.content_sha256,
    p.observed_at, p.raw_sha256, '/content/' || o.record_index AS json_pointer,
    b.name AS buyer_name, b.tax_id AS buyer_tax_id, b.source_key AS buyer_source_key,
    b.country_code AS buyer_country_code, s.ordinal AS supplier_ordinal,
    s.name AS supplier_name, s.tax_id AS supplier_tax_id,
    s.source_key AS supplier_source_key, s.country_code AS supplier_country_code
FROM nima.projection_receipts r
JOIN nima.observations o USING (observation_id)
JOIN nima.run_pages p USING (run_id, page_number)
JOIN nima.ingest_runs run USING (run_id)
JOIN nima.projection_mentions b ON b.projection_version = r.projection_version
    AND b.source_id = o.source_id AND b.normalizer_version = o.normalizer_version
    AND b.content_sha256 = o.content_sha256 AND b.role = 'buyer'
JOIN nima.projection_mentions s ON s.projection_version = b.projection_version
    AND s.source_id = b.source_id AND s.normalizer_version = b.normalizer_version
    AND s.content_sha256 = b.content_sha256 AND s.role = 'supplier';
