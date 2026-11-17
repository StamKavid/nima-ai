-- Experimental port; authoritative reference SQL SHA256: 85134c5d800350adfedf7dce6d995a36c48b194d919912695992f83369e11d5f
with input as (select * from {{ ref('observations') }}), selection as (
    select '{{ var('observation_cutoff') | replace("'", "''") }}'::timestamptz as cutoff,
        '{{ var('supplier_tax_id') | replace("'", "''") }}'::text as tax_id
), decisions as (select * from {{ ref('selected_revisions') }}), matched AS (
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
), computed as (
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
) as result
)
select 'captured_contract_record_count.v1'::text as metric_id, result,
    '7d8b5f8ecf6ae366482f4b06cd245f16d23408b489ad9bcb44af493282ac043f'::text as definition_sha256,
    (select coalesce(jsonb_agg(jsonb_build_object(
        'observation_id', observation_id, 'source_id', source_id,
        'normalizer_version', normalizer_version, 'content_sha256', content_sha256,
        'observed_at', captured_at_text, 'run_id', run_id, 'page_number', page_number,
        'record_index', record_index, 'raw_sha256', raw_sha256, 'json_pointer', json_pointer,
        'projection_version', projection_version, 'projection_sha256', projection_sha256
    ) order by observation_id), '[]'::jsonb) from input) as evidence,
    (select coalesce(bool_and(quality_ok), true) from input)
        and (result->>'total')::int = coalesce((select sum((b->>'record_count')::int)
            from jsonb_array_elements(result->'buyers') b), 0)
            + jsonb_array_length(result->'unassigned_source_ids')
        and (result->>'total')::int = (result->>'cancelled_count')::int
            + (result->>'unknown_cancellation_count')::int
            + (result->>'not_cancelled_count')::int as quality_ok
from computed
