WITH runs AS (
    SELECT x.capture, x.run_id COLLATE "C" AS run_id, x.query_sha256, x.collection_complete,
        x.normalization_complete, x.quarantined, x.observed_from, x.observed_to
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        capture text, run_id text, query_sha256 text, collection_complete boolean,
        normalization_complete boolean, quarantined integer,
        observed_from timestamptz, observed_to timestamptz
    )
), vers AS (
    SELECT x.capture, x.observation_id, x.source_id COLLATE "C" AS source_id,
        x.content_sha256, x.observed_at
    FROM jsonb_to_recordset(%s::jsonb) AS x(
        capture text, observation_id bigint, source_id text,
        content_sha256 text, observed_at timestamptz
    )
), latest AS (
    SELECT vers.*, max(observed_at) OVER (PARTITION BY capture, source_id) AS latest FROM vers
), current_rows AS (
    SELECT * FROM latest WHERE observed_at = latest
), per_source AS (
    SELECT capture, source_id,
        jsonb_agg(observation_id ORDER BY observation_id) AS observation_ids,
        count(DISTINCT content_sha256) AS version_count,
        min(content_sha256) AS version
    FROM current_rows GROUP BY capture, source_id
), e AS (
    SELECT * FROM per_source WHERE capture = 'earlier'
), l AS (
    SELECT * FROM per_source WHERE capture = 'later'
), excluded AS (
    -- A record ambiguous in either capture is excluded from every category below.
    SELECT DISTINCT source_id FROM per_source WHERE version_count > 1
), pairs AS (
    SELECT coalesce(e.source_id, l.source_id) AS source_id,
        e.version AS earlier_version, l.version AS later_version,
        e.observation_ids AS earlier_ids, l.observation_ids AS later_ids,
        CASE WHEN e.source_id IS NULL THEN 'added'
            WHEN l.source_id IS NULL THEN 'missing_from_later_capture'
            WHEN e.version <> l.version THEN 'changed'
            ELSE 'unchanged' END AS category
    FROM e FULL JOIN l ON e.source_id = l.source_id
    WHERE coalesce(e.source_id, l.source_id) NOT IN (SELECT source_id FROM excluded)
), reasons AS (
    SELECT r.reason FROM (VALUES
        ('no_runs', NOT EXISTS (SELECT 1 FROM runs WHERE capture = 'earlier')
            OR NOT EXISTS (SELECT 1 FROM runs WHERE capture = 'later')),
        ('not_later', EXISTS (SELECT 1 FROM runs WHERE capture = 'earlier')
            AND EXISTS (SELECT 1 FROM runs WHERE capture = 'later')
            AND (SELECT max(observed_to) FROM runs WHERE capture = 'earlier')
                >= (SELECT min(observed_from) FROM runs WHERE capture = 'later')),
        ('quarantined_records', EXISTS (SELECT 1 FROM runs WHERE quarantined > 0)),
        ('query_mismatch', (SELECT count(DISTINCT query_sha256) FROM runs) > 1),
        ('run_incomplete', EXISTS (SELECT 1 FROM runs
            WHERE NOT (collection_complete AND normalization_complete)))
    ) AS r(reason, hit) WHERE r.hit
), comparable AS (
    SELECT NOT EXISTS (SELECT 1 FROM reasons) AS ok
)
SELECT jsonb_build_object(
    'status', CASE
        WHEN EXISTS (SELECT 1 FROM reasons) THEN 'incomparable'
        WHEN EXISTS (SELECT 1 FROM pairs WHERE category <> 'unchanged') THEN 'observed_changes'
        ELSE 'no_observed_change' END,
    'reasons', coalesce((SELECT jsonb_agg(reason ORDER BY reason COLLATE "C") FROM reasons), '[]'),
    'earlier', jsonb_build_object(
        'run_ids', coalesce((SELECT jsonb_agg(run_id ORDER BY run_id COLLATE "C")
            FROM runs WHERE capture = 'earlier'), '[]'),
        'query_hashes', coalesce((SELECT jsonb_agg(q ORDER BY q COLLATE "C") FROM (
            SELECT DISTINCT query_sha256 AS q FROM runs WHERE capture = 'earlier') d), '[]'),
        'records', (SELECT count(*) FROM per_source
            WHERE capture = 'earlier' AND version_count = 1),
        'ambiguous_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
            FROM per_source WHERE capture = 'earlier' AND version_count > 1), '[]')),
    'later', jsonb_build_object(
        'run_ids', coalesce((SELECT jsonb_agg(run_id ORDER BY run_id COLLATE "C")
            FROM runs WHERE capture = 'later'), '[]'),
        'query_hashes', coalesce((SELECT jsonb_agg(q ORDER BY q COLLATE "C") FROM (
            SELECT DISTINCT query_sha256 AS q FROM runs WHERE capture = 'later') d), '[]'),
        'records', (SELECT count(*) FROM per_source
            WHERE capture = 'later' AND version_count = 1),
        'ambiguous_source_ids', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
            FROM per_source WHERE capture = 'later' AND version_count > 1), '[]')),
    'counts', jsonb_build_object(
        'added', (SELECT count(*) FROM pairs
            WHERE category = 'added' AND (SELECT ok FROM comparable)),
        'changed', (SELECT count(*) FROM pairs
            WHERE category = 'changed' AND (SELECT ok FROM comparable)),
        'missing_from_later_capture', (SELECT count(*) FROM pairs
            WHERE category = 'missing_from_later_capture' AND (SELECT ok FROM comparable)),
        'unchanged', (SELECT count(*) FROM pairs
            WHERE category = 'unchanged' AND (SELECT ok FROM comparable))),
    'added', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', source_id,
        'later_version', later_version,
        'later_observation_ids', later_ids) ORDER BY source_id COLLATE "C")
        FROM pairs WHERE category = 'added' AND (SELECT ok FROM comparable)), '[]'),
    'changed', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', source_id,
        'earlier_version', earlier_version,
        'later_version', later_version,
        'earlier_observation_ids', earlier_ids,
        'later_observation_ids', later_ids) ORDER BY source_id COLLATE "C")
        FROM pairs WHERE category = 'changed' AND (SELECT ok FROM comparable)), '[]'),
    'missing_from_later_capture', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'source_id', source_id,
        'earlier_version', earlier_version,
        'earlier_observation_ids', earlier_ids) ORDER BY source_id COLLATE "C")
        FROM pairs WHERE category = 'missing_from_later_capture'
            AND (SELECT ok FROM comparable)), '[]'),
    'unchanged', coalesce((SELECT jsonb_agg(source_id ORDER BY source_id COLLATE "C")
        FROM pairs WHERE category = 'unchanged' AND (SELECT ok FROM comparable)), '[]')
)
