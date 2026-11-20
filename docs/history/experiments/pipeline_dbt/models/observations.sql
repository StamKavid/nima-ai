-- Synthetic sealed input only; byte verification remains the application boundary.
with members as (
    select observation_id, count(*) as member_count,
        jsonb_agg(jsonb_build_object(
            'ordinal', ordinal, 'tax_id', tax_id, 'country_code', country_code
        ) order by ordinal) as suppliers,
        min(ordinal) = 0 and max(ordinal) = count(*) - 1
            and count(distinct ordinal) = count(*) as ordinals_valid
    from {{ ref('input_mentions') }} group by observation_id
), assembled as (
    select o.observation_id, o.source_id collate "C" as source_id,
        o.normalizer_version, o.content_sha256, o.observed_at::timestamptz as observed_at,
        o.observed_at as captured_at_text,
        o.buyer_key collate "C" as buyer_key, o.cancelled, o.supplier_state,
        o.run_id, o.page_number, o.record_index, o.raw_sha256, o.json_pointer,
        o.projection_version, o.projection_sha256,
        case o.supplier_state
            when 'unknown' then null::jsonb
            when 'empty' then '[]'::jsonb
            else m.suppliers
        end as suppliers,
        coalesce(m.ordinals_valid, true)
            and case o.supplier_state
                when 'known' then coalesce(m.member_count, 0) > 0
                when 'unknown' then coalesce(m.member_count, 0) = 0
                when 'empty' then coalesce(m.member_count, 0) = 0
                else false
            end as members_valid
    from {{ ref('input_observations') }} o left join members m using (observation_id)
), versions as (
    select source_id, normalizer_version, content_sha256,
        count(distinct jsonb_build_object(
            'buyer_key', buyer_key, 'cancelled', cancelled, 'suppliers', suppliers
        )) = 1 as facts_consistent
    from assembled group by source_id, normalizer_version, content_sha256
)
select a.*,
    members_valid and v.facts_consistent
        and count(*) over (partition by observation_id) = 1
        and observation_id > 0 and source_id like 'kimdis:_%'
        and normalizer_version = 'kimdis-normalized-v1'
        and projection_version = 'kimdis-participation-v1'
        and content_sha256 ~ '^[0-9a-f]{64}$'
        and raw_sha256 ~ '^[0-9a-f]{64}$'
        and projection_sha256 ~ '^[0-9a-f]{64}$'
        and page_number >= 0 and record_index >= 0
        and json_pointer = '/content/' || record_index::text as quality_ok
from assembled a join versions v using (source_id, normalizer_version, content_sha256)
