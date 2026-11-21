WITH input AS (
    SELECT x.observation_id, x.source_id COLLATE "C" AS source_id, x.content_sha256,
        x.observed_at, x.buyer_key COLLATE "C" AS buyer_key, x.cancelled, x.suppliers
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        observation_id bigint, source_id text, content_sha256 text,
        observed_at timestamptz, buyer_key text, cancelled boolean, suppliers jsonb
    )
), selection AS (
    SELECT %s::timestamptz AS cutoff, %s::text AS buyer
), eligible AS (
    SELECT input.*, max(observed_at) OVER (PARTITION BY source_id) AS latest
    FROM input, selection WHERE observed_at <= cutoff
), current_rows AS (
    SELECT * FROM eligible WHERE observed_at = latest
), versions AS (
    SELECT DISTINCT ON (source_id, content_sha256) *
    FROM current_rows ORDER BY source_id, content_sha256, observation_id
), per_source AS (
    SELECT source_id,
        jsonb_agg(observation_id ORDER BY observation_id) AS observation_ids,
        jsonb_agg(DISTINCT content_sha256 ORDER BY content_sha256) AS version_hashes,
        count(DISTINCT content_sha256) AS version_count
    FROM current_rows GROUP BY source_id
), elements AS (
    SELECT v.source_id, v.cancelled,
        nullif(btrim(v.buyer_key, E' \t\r\n\f\013'), '') AS buyer_trimmed,
        (v.suppliers IS NULL OR v.suppliers = 'null'::jsonb) AS unknown_suppliers,
        coalesce(v.suppliers = '[]'::jsonb, false) AS empty_suppliers,
        s.value AS supplier, t.tax, t.country
    FROM versions v
    JOIN per_source p ON p.source_id = v.source_id AND p.version_count = 1
    LEFT JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(v.suppliers) = 'array' THEN v.suppliers ELSE '[]' END
    ) s(value) ON true
    CROSS JOIN LATERAL (SELECT
        btrim(coalesce(s.value->>'tax_id', ''), E' \t\r\n\f\013') AS tax,
        btrim(coalesce(s.value->>'country_code', ''), E' \t\r\n\f\013') AS country
    ) t
), keyed AS (
    SELECT e.*, CASE WHEN e.supplier IS NOT NULL AND e.tax ~ '^[0-9]{9}$'
        AND e.tax <> '000000000' AND e.country IN ('GR', 'EL')
        THEN ('GR:' || e.tax) COLLATE "C" END AS supplier_key
    FROM elements e
), buyer_records AS (
    SELECT p.source_id, p.version_hashes, p.observation_ids,
        bool_or(k.unknown_suppliers) AS unknown_suppliers,
        bool_or(k.empty_suppliers) AS empty_suppliers,
        coalesce(jsonb_agg(DISTINCT k.supplier_key ORDER BY k.supplier_key)
            FILTER (WHERE k.supplier_key IS NOT NULL), '[]'::jsonb) AS supplier_keys,
        count(*) FILTER (WHERE k.supplier IS NOT NULL AND k.supplier_key IS NULL) AS ineligible,
        bool_or(k.cancelled) AS cancelled
    FROM keyed k
    JOIN per_source p ON p.source_id = k.source_id
    CROSS JOIN selection s
    WHERE k.buyer_trimmed = s.buyer COLLATE "C"
    GROUP BY p.source_id, p.version_hashes, p.observation_ids
), decisions AS (
    SELECT b.*, CASE
        WHEN b.unknown_suppliers THEN 'unknown_suppliers'
        WHEN b.empty_suppliers THEN 'empty_suppliers'
        WHEN jsonb_array_length(b.supplier_keys) = 0 THEN 'no_eligible_supplier'
        ELSE 'resolved' END AS resolution
    FROM buyer_records b
), resolved AS (
    SELECT * FROM decisions WHERE resolution = 'resolved'
), supplier_counts AS (
    SELECT sk.key AS supplier_key, count(*) AS record_count,
        jsonb_agg(r.source_id ORDER BY r.source_id COLLATE "C") AS source_ids,
        count(*) FILTER (WHERE r.cancelled IS TRUE) AS cancelled_count,
        count(*) FILTER (WHERE r.cancelled IS NULL) AS unknown_count
    FROM resolved r CROSS JOIN LATERAL jsonb_array_elements_text(r.supplier_keys) sk(key)
    GROUP BY sk.key
), top AS (
    SELECT max(record_count) AS top_count FROM supplier_counts
)
SELECT jsonb_build_object(
    'status', CASE
        WHEN NOT EXISTS (SELECT 1 FROM input) THEN 'empty_capture'
        WHEN NOT EXISTS (SELECT 1 FROM per_source) THEN 'no_observations_before_cutoff'
        WHEN EXISTS (SELECT 1 FROM resolved) THEN 'observed_concentration'
        WHEN EXISTS (SELECT 1 FROM decisions) THEN 'buyer_records_unresolved'
        WHEN EXISTS (SELECT 1 FROM per_source WHERE version_count > 1) THEN 'selection_unresolved'
        ELSE 'no_observed_buyer_records' END,
    'buyer_key', 'kimdis.buyer-key:' || (SELECT buyer FROM selection),
    'buyer_records', (SELECT count(*) FROM decisions),
    'resolved_records', (SELECT count(*) FROM resolved),
    'unresolved_records', (SELECT count(*) FROM decisions WHERE resolution <> 'resolved'),
    'unresolved_share', CASE WHEN EXISTS (SELECT 1 FROM decisions) THEN jsonb_build_object(
        'numerator', (SELECT count(*) FROM decisions WHERE resolution <> 'resolved'),
        'denominator', (SELECT count(*) FROM decisions)) ELSE 'null'::jsonb END,
    'top_supplier_keys', coalesce((SELECT jsonb_agg(supplier_key ORDER BY supplier_key COLLATE "C")
        FROM supplier_counts WHERE record_count = (SELECT top_count FROM top)), '[]'),
    'top_record_count', (SELECT top_count FROM top),
    'top_share', CASE WHEN (SELECT top_count FROM top) IS NOT NULL THEN jsonb_build_object(
        'numerator', (SELECT top_count FROM top),
        'denominator', (SELECT count(*) FROM resolved)) ELSE 'null'::jsonb END,
    'distinct_suppliers', (SELECT count(*) FROM supplier_counts),
    'participation_total', coalesce((SELECT sum(record_count) FROM supplier_counts), 0),
    'joint_records', (SELECT count(*) FROM resolved WHERE jsonb_array_length(supplier_keys) >= 2),
    'partial_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM resolved WHERE ineligible > 0), '[]'),
    'suppliers', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'supplier_key', supplier_key,
        'record_count', record_count,
        'source_ids', source_ids,
        'cancelled_count', cancelled_count,
        'unknown_cancellation_count', unknown_count)
        ORDER BY record_count DESC, supplier_key COLLATE "C") FROM supplier_counts), '[]'),
    'ambiguous_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM per_source WHERE version_count > 1), '[]'),
    'records', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', source_id,
        'version_hashes', version_hashes,
        'observation_ids', observation_ids,
        'resolution', resolution,
        'supplier_keys', supplier_keys,
        'ineligible_occurrences', ineligible,
        'cancelled', cancelled) ORDER BY source_id COLLATE "C") FROM decisions), '[]')
)
