-- Exact source assertion policy over one explicitly selected immutable snapshot.
WITH parameters AS (SELECT %s::text AS dimension,%s::text AS code),
records AS (
    SELECT r.value,r.ordinality-1 AS ordinal
    FROM nima_processing.metadata_snapshots s,
        LATERAL jsonb_array_elements(s.document->'records') WITH ORDINALITY r
    WHERE s.snapshot_sha256=%s
), matches AS (
    SELECT m.record_ordinal,
        jsonb_agg(m.assertion ORDER BY m.assertion_ordinal) AS assertions
    FROM nima_processing.reported_market_metadata m CROSS JOIN parameters p
    WHERE m.snapshot_sha256=%s
        AND (p.dimension IS NULL OR m.dimension COLLATE "C"=p.dimension COLLATE "C")
        AND (p.code IS NULL OR (m.status='reported' AND m.code COLLATE "C"=p.code COLLATE "C"))
    GROUP BY m.record_ordinal
)
SELECT coalesce(jsonb_agg(r.value || jsonb_build_object('assertions',coalesce(m.assertions,'[]'))
    ORDER BY r.ordinal) FILTER (WHERE m.record_ordinal IS NOT NULL
        OR (p.dimension IS NULL AND p.code IS NULL)), '[]'),
    coalesce((SELECT sum(jsonb_array_length(assertions)) FROM matches),0)::bigint
FROM records r LEFT JOIN matches m ON m.record_ordinal=r.ordinal CROSS JOIN parameters p;
