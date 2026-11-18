WITH pages AS (
    SELECT count(*)::bigint AS page_count,
           coalesce(sum(record_count), 0)::bigint AS record_count,
           coalesce(sum(quarantined_count), 0)::bigint AS quarantined_count,
           min(observed_at) AS oldest_observed_at,
           max(observed_at) AS newest_observed_at
    FROM nima.run_pages WHERE run_id = %(run_id)s
), facts AS (
    SELECT count(*)::bigint AS observation_count,
           count(*) FILTER (WHERE NOT EXISTS (
               SELECT 1 FROM nima.projection_receipts p
               WHERE p.observation_id = o.observation_id
                 AND p.projection_version = %(projection_version)s
           ))::bigint AS pending_projection_count
    FROM nima.observations o WHERE o.run_id = %(run_id)s
)
SELECT r.run_id, transaction_timestamp() AS sampled_at, r.status,
       r.query->>'dateFrom' AS query_from, r.query->>'dateTo' AS query_to,
       pages.*, facts.*, %(projection_version)s::text AS projection_version,
       w.request_id AS workflow_id, w.status AS workflow_status,
       w.updated_at AS workflow_updated_at
FROM nima.ingest_runs r CROSS JOIN pages CROSS JOIN facts
LEFT JOIN nima.workflow_requests w ON w.run_id = r.run_id
WHERE r.run_id = %(run_id)s
