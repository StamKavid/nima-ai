WITH input AS (
    SELECT x.*, x.source_id COLLATE "C" AS sid,
        x.observed_at::timestamptz AS observation_time
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        observation_id bigint, source_id text, normalizer_version text,
        content_sha256 text, observed_at text, "references" jsonb,
        cancelled boolean, ada text, decision_type text, decision_status text
    )
), eligible AS (
    SELECT input.*, max(observation_time) OVER (PARTITION BY sid) AS latest
    FROM input WHERE observation_time <= %s::timestamptz
), versions AS (
    SELECT DISTINCT ON (sid, content_sha256) * FROM eligible
    WHERE observation_time = latest
    ORDER BY sid, content_sha256, observation_id
), lineage AS (
    SELECT sid, content_sha256,
        jsonb_agg(jsonb_build_array(observation_id, observed_at) ORDER BY observation_id) AS observations
    FROM eligible GROUP BY sid, content_sha256
), version_values AS (
    SELECT v.*, jsonb_build_object(
        'content_sha256', v.content_sha256,
        'normalizer_version', v.normalizer_version,
        'observations', l.observations,
        'decision_type', v.decision_type,
        'decision_status', v.decision_status,
        'cancelled', v.cancelled
    ) AS value FROM versions v JOIN lineage l USING (sid, content_sha256)
), selections AS (
    SELECT sid, count(*) AS version_count,
        jsonb_agg(value ORDER BY content_sha256) AS versions,
        jsonb_agg("references" ORDER BY content_sha256)->0 AS refs
    FROM version_values GROUP BY sid
), sources AS (
    SELECT * FROM selections WHERE starts_with(sid, 'kimdis:')
), citations AS (
    SELECT DISTINCT s.sid, r.value->>'target_id' COLLATE "C" AS target_id
    FROM sources s CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN s.version_count = 1 AND jsonb_typeof(s.refs) = 'array'
        THEN s.refs ELSE '[]'::jsonb END
    ) r(value) WHERE r.value->>'relation' = 'commitment_decision'
), edges AS (
    SELECT c.sid, c.target_id, CASE
        WHEN t.sid IS NULL THEN 'unresolved'
        WHEN t.version_count > 1 THEN 'target_ambiguous'
        WHEN t.versions->0->>'decision_type' IS NULL THEN 'target_type_unknown'
        WHEN t.versions->0->>'decision_type' = 'Β.1.3' THEN 'resolved'
        ELSE 'target_type_mismatch' END AS outcome,
        s.versions->0 AS source_version, coalesce(t.versions, '[]'::jsonb) AS target_versions
    FROM citations c JOIN sources s USING (sid)
    LEFT JOIN selections t ON t.sid = c.target_id
), shared AS (
    SELECT target_id, count(*) AS citing_records,
        jsonb_agg(sid ORDER BY sid) AS source_ids
    FROM edges GROUP BY target_id HAVING count(*) > 1
), outcomes(name) AS (
    VALUES ('resolved'), ('unresolved'), ('target_ambiguous'),
        ('target_type_unknown'), ('target_type_mismatch')
)
SELECT jsonb_build_object(
    'status', CASE
        WHEN NOT EXISTS (SELECT 1 FROM input WHERE starts_with(sid, 'kimdis:')) THEN 'empty_capture'
        WHEN NOT EXISTS (SELECT 1 FROM sources) THEN 'no_observations_before_cutoff'
        WHEN EXISTS (SELECT 1 FROM edges) THEN 'observed_citations'
        ELSE 'no_observed_citations' END,
    'records', (SELECT count(*) FROM sources),
    'source_ambiguous_ids', coalesce((SELECT jsonb_agg(sid ORDER BY sid)
        FROM sources WHERE version_count > 1), '[]'::jsonb),
    'unknown_reference_ids', coalesce((SELECT jsonb_agg(sid ORDER BY sid)
        FROM sources WHERE version_count = 1 AND refs = 'null'::jsonb), '[]'::jsonb),
    'no_citation_ids', coalesce((SELECT jsonb_agg(s.sid ORDER BY s.sid)
        FROM sources s WHERE s.version_count = 1 AND s.refs <> 'null'::jsonb
        AND NOT EXISTS (SELECT 1 FROM citations c WHERE c.sid = s.sid)), '[]'::jsonb),
    'sources', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', sid, 'versions', versions) ORDER BY sid) FROM sources), '[]'::jsonb),
    'edges', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', sid, 'target_id', target_id, 'outcome', outcome,
        'source_version', source_version, 'target_versions', target_versions,
        'relation', 'cites_decision', 'source_field', 'diavgeiaADA',
        'reported_relation', 'commitment_decision', 'expected_target_type', 'Β.1.3'
    ) ORDER BY sid, target_id) FROM edges), '[]'::jsonb),
    'distinct_targets', (SELECT count(DISTINCT target_id) FROM edges),
    'outcome_counts', (SELECT jsonb_object_agg(name,
        (SELECT count(*) FROM edges WHERE outcome = name)) FROM outcomes),
    'shared_targets', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'target_id', target_id, 'citing_records', citing_records, 'source_ids', source_ids
    ) ORDER BY target_id) FROM shared), '[]'::jsonb)
)
