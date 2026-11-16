WITH input AS (
    SELECT x.observation_id, x.source_id COLLATE "C" AS source_id, x.content_sha256,
        x.observed_at, x.buyer_key COLLATE "C" AS buyer_key, x.cancelled, x.suppliers
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        observation_id bigint, source_id text, content_sha256 text,
        observed_at timestamptz, buyer_key text, cancelled boolean, suppliers jsonb
    )
), selection AS (
    SELECT %s::timestamptz AS cutoff, %s::text AS tax_id
), eligible AS (
    SELECT input.*, max(observed_at) OVER (PARTITION BY source_id) AS latest
    FROM input, selection WHERE observed_at <= cutoff
), current_rows AS (
    SELECT * FROM eligible WHERE observed_at = latest
), versions AS (
    SELECT DISTINCT ON (source_id, content_sha256) *
    FROM current_rows ORDER BY source_id, content_sha256, observation_id
), details AS (
    SELECT v.source_id, v.content_sha256,
        nullif(btrim(v.buyer_key, E' \t\r\n\f\013'), '') AS buyer_key,
        v.cancelled,
        coalesce(jsonb_agg((s.value->>'ordinal')::int ORDER BY (s.value->>'ordinal')::int)
            FILTER (WHERE t.tax = p.tax_id AND t.country IN ('GR', 'EL')), '[]') AS matching,
        coalesce(bool_or(t.tax = p.tax_id AND t.country NOT IN ('GR', 'EL')), false) AS unassessed,
        coalesce(bool_or(t.tax = p.tax_id), false) AS candidate,
        v.suppliers IS NULL OR v.suppliers = 'null'::jsonb AS unknown_suppliers,
        coalesce(v.suppliers = '[]'::jsonb, false) AS empty_suppliers,
        count(*) FILTER (WHERE s.value IS NOT NULL
            AND (t.tax COLLATE "C" !~ '^[0-9]{9}$' OR t.tax = '000000000')) AS invalid_count
    FROM versions v CROSS JOIN selection p
    LEFT JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(v.suppliers) = 'array' THEN v.suppliers ELSE '[]' END
    ) s(value) ON true
    CROSS JOIN LATERAL (SELECT
        btrim(coalesce(s.value->>'tax_id', ''), E' \t\r\n\f\013') AS tax,
        btrim(coalesce(s.value->>'country_code', ''), E' \t\r\n\f\013') AS country
    ) t
    GROUP BY v.source_id, v.content_sha256, v.buyer_key, v.cancelled, v.suppliers
), observation_ids AS (
    SELECT source_id, jsonb_agg(observation_id ORDER BY observation_id) AS ids
    FROM current_rows GROUP BY source_id
), decisions AS (
    SELECT d.source_id, jsonb_build_object(
        'source_id', d.source_id,
        'version_hashes', jsonb_agg(d.content_sha256 ORDER BY d.content_sha256),
        'observation_ids', o.ids,
        'buyer_key', CASE WHEN count(*) = 1 THEN 'kimdis.buyer-key:' || max(d.buyer_key) END,
        'cancelled', CASE WHEN count(*) = 1 THEN bool_or(d.cancelled) END,
        'matching_ordinals', CASE WHEN count(*) = 1
            THEN jsonb_agg(d.matching ORDER BY d.content_sha256)->0 ELSE '[]'::jsonb END,
        'unassessed', bool_or(d.unassessed),
        'unknown_suppliers', bool_or(d.unknown_suppliers),
        'empty_suppliers', bool_or(d.empty_suppliers),
        'ambiguous', count(*) > 1,
        'ambiguous_candidate', count(*) > 1 AND bool_or(d.candidate),
        'invalid_supplier_count', sum(d.invalid_count)
    ) AS value
    FROM details d JOIN observation_ids o USING (source_id)
    GROUP BY d.source_id, o.ids
), matched AS (
    SELECT * FROM decisions WHERE jsonb_array_length(value->'matching_ordinals') > 0
), buyers AS (
    SELECT value->>'buyer_key' AS buyer_key, jsonb_build_object(
        'buyer_key', value->>'buyer_key',
        'source_ids', jsonb_agg(source_id ORDER BY source_id),
        'record_count', count(*),
        'cancelled_count', count(*) FILTER (WHERE value->'cancelled' = 'true'::jsonb),
        'unknown_cancellation_count', count(*) FILTER (WHERE value->'cancelled' = 'null'::jsonb)
    ) AS value
    FROM matched WHERE value->>'buyer_key' IS NOT NULL GROUP BY value->>'buyer_key'
)
SELECT jsonb_build_object(
    'status', CASE
        WHEN NOT EXISTS (SELECT 1 FROM input) THEN 'empty_capture'
        WHEN NOT EXISTS (SELECT 1 FROM decisions) THEN 'no_observations_before_cutoff'
        WHEN EXISTS (SELECT 1 FROM matched) THEN 'observed_participation'
        WHEN EXISTS (SELECT 1 FROM decisions WHERE (value->>'unassessed')::boolean
            OR (value->>'ambiguous_candidate')::boolean OR (value->>'unknown_suppliers')::boolean)
            THEN 'selection_unresolved' ELSE 'no_observed_participation' END,
    'total', (SELECT count(*) FROM matched),
    'cancelled_count', (SELECT count(*) FROM matched WHERE value->'cancelled' = 'true'::jsonb),
    'unknown_cancellation_count', (SELECT count(*) FROM matched WHERE value->'cancelled' = 'null'::jsonb),
    'not_cancelled_count', (SELECT count(*) FROM matched WHERE value->'cancelled' = 'false'::jsonb),
    'buyers', coalesce((SELECT jsonb_agg(value ORDER BY buyer_key COLLATE "C") FROM buyers), '[]'),
    'unassigned_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM matched WHERE value->>'buyer_key' IS NULL), '[]'),
    'unassessed_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM decisions WHERE (value->>'unassessed')::boolean), '[]'),
    'ambiguous_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM decisions WHERE (value->>'ambiguous')::boolean), '[]'),
    'unknown_supplier_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM decisions WHERE (value->>'unknown_suppliers')::boolean), '[]'),
    'empty_supplier_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM decisions WHERE (value->>'empty_suppliers')::boolean), '[]'),
    'invalid_supplier_count', coalesce((SELECT sum((value->>'invalid_supplier_count')::int) FROM decisions), 0),
    'records', coalesce((SELECT jsonb_agg(value ORDER BY source_id COLLATE "C") FROM decisions), '[]')
)
