WITH input AS (
    SELECT x.observation_id, x.source_id COLLATE "C" AS source_id, x.content_sha256,
        x.observed_at, x.cancelled, x.period COLLATE "C" AS period, x.date_outcome, x.cpv
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        observation_id bigint, source_id text, content_sha256 text, observed_at timestamptz,
        cancelled boolean, period text, date_outcome text, cpv jsonb
    )
), selection AS (
    SELECT %s::timestamptz AS cutoff, %s::text AS cpv_filter,
        %s::text AS period_from, %s::text AS period_to
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
), base_codes AS (
    SELECT DISTINCT v.source_id, left(a.value->>'code', 8) COLLATE "C" AS base
    FROM versions v
    JOIN per_source p ON p.source_id = v.source_id AND p.version_count = 1
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(v.cpv) = 'array' THEN v.cpv ELSE '[]' END
    ) a(value)
    WHERE a.value->>'status' = 'reported' AND a.value->>'code' ~ '^[0-9]{8}-[0-9]$'
), bases AS (
    SELECT source_id, jsonb_agg(base ORDER BY base) AS codes FROM base_codes GROUP BY source_id
), decisions AS (
    SELECT p.source_id, p.version_hashes, p.observation_ids, p.version_count > 1 AS ambiguous,
        CASE WHEN p.version_count = 1 THEN v.period END AS period,
        CASE WHEN p.version_count = 1 THEN v.date_outcome END AS date_outcome,
        CASE WHEN p.version_count = 1 THEN coalesce(b.codes, '[]'::jsonb)
            ELSE '[]'::jsonb END AS bases,
        CASE WHEN p.version_count > 1 THEN NULL
            WHEN v.cpv IS NULL OR v.cpv = 'null'::jsonb THEN 'unclassified_metadata_unavailable'
            WHEN b.codes IS NULL THEN 'unclassified_no_reported_code'
            ELSE 'classified' END AS classification,
        CASE WHEN p.version_count = 1 THEN v.cancelled END AS cancelled
    FROM per_source p
    LEFT JOIN versions v ON v.source_id = p.source_id AND p.version_count = 1
    LEFT JOIN bases b ON b.source_id = p.source_id
), placements AS (
    -- An ambiguous record has no classification, so neither branch ever places it.
    SELECT d.source_id, b.base COLLATE "C" AS cpv, d.period, d.cancelled
    FROM decisions d CROSS JOIN LATERAL jsonb_array_elements_text(d.bases) b(base)
    WHERE d.classification = 'classified'
    UNION ALL
    SELECT d.source_id, NULL::text COLLATE "C", d.period, d.cancelled
    FROM decisions d WHERE d.classification <> 'classified'
), placed AS (
    SELECT pl.* FROM placements pl CROSS JOIN selection s
    WHERE (s.cpv_filter IS NULL OR pl.cpv = s.cpv_filter COLLATE "C")
        AND ((s.period_from IS NULL AND s.period_to IS NULL)
            -- A comparison with an unknown period is never true, so unknown periods drop out.
            OR ((s.period_from IS NULL OR pl.period >= s.period_from COLLATE "C")
                AND (s.period_to IS NULL OR pl.period <= s.period_to COLLATE "C")))
), cells AS (
    SELECT cpv, period, jsonb_build_object(
        'cpv_base_code', cpv,
        'period', period,
        'record_count', count(*),
        'source_ids', jsonb_agg(source_id ORDER BY source_id COLLATE "C"),
        'cancelled_count', count(*) FILTER (WHERE cancelled IS TRUE),
        'unknown_cancellation_count', count(*) FILTER (WHERE cancelled IS NULL)
    ) AS value
    FROM placed GROUP BY cpv, period
), totals AS (
    SELECT period, jsonb_build_object(
        'period', period, 'record_count', count(DISTINCT source_id)
    ) AS value
    FROM placed GROUP BY period
), coverage AS (
    SELECT count(*) AS selected,
        count(*) FILTER (WHERE classification = 'classified') AS classified,
        count(*) FILTER (WHERE classification = 'unclassified_no_reported_code') AS no_code,
        count(*) FILTER (WHERE classification = 'unclassified_metadata_unavailable') AS no_metadata,
        count(*) FILTER (WHERE date_outcome = 'parsed') AS parsed,
        count(*) FILTER (WHERE date_outcome = 'absent') AS absent,
        count(*) FILTER (WHERE date_outcome = 'unparseable') AS unparseable
    FROM decisions WHERE NOT ambiguous
)
SELECT jsonb_build_object(
    'status', CASE
        WHEN NOT EXISTS (SELECT 1 FROM input) THEN 'empty_capture'
        WHEN NOT EXISTS (SELECT 1 FROM decisions) THEN 'no_observations_before_cutoff'
        WHEN EXISTS (SELECT 1 FROM cells) THEN 'observed_activity'
        WHEN EXISTS (SELECT 1 FROM decisions WHERE ambiguous)
            OR ((SELECT cpv_filter IS NOT NULL FROM selection)
                AND (SELECT no_code + no_metadata > 0 FROM coverage))
            OR ((SELECT period_from IS NOT NULL OR period_to IS NOT NULL FROM selection)
                AND (SELECT absent + unparseable > 0 FROM coverage))
            THEN 'selection_unresolved'
        ELSE 'no_observed_activity' END,
    'cells', coalesce((SELECT jsonb_agg(value ORDER BY cpv COLLATE "C" NULLS LAST,
        period COLLATE "C" NULLS LAST) FROM cells), '[]'),
    'period_totals', coalesce((SELECT jsonb_agg(value ORDER BY period COLLATE "C" NULLS LAST)
        FROM totals), '[]'),
    'coverage', (SELECT jsonb_build_object(
        'selected_records', selected,
        'classified', classified,
        'unclassified_no_reported_code', no_code,
        'unclassified_metadata_unavailable', no_metadata,
        'period_parsed', parsed,
        'period_absent', absent,
        'period_unparseable', unparseable) FROM coverage),
    'ambiguous_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM decisions WHERE ambiguous), '[]'),
    'records', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', source_id,
        'version_hashes', version_hashes,
        'observation_ids', observation_ids,
        'ambiguous', ambiguous,
        'period', period,
        'date_outcome', date_outcome,
        'cpv_base_codes', bases,
        'classification', classification,
        'cancelled', cancelled) ORDER BY source_id COLLATE "C") FROM decisions), '[]')
)
