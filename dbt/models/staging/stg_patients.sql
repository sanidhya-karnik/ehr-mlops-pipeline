-- =============================================================================
-- Staging: Patients
-- Clean patient demographics from MIMIC-IV
-- =============================================================================

with source as (
    select * from {{ source('mimic_hosp', 'patients') }}
    where subject_id is not null
      and subject_id::text != 'NaN'
),

cleaned as (
    select
        subject_id::integer as subject_id,
        gender,
        -- Calculate approximate age using anchor year
        anchor_age as age,
        anchor_year,
        anchor_year_group,
        dod  -- Date of death (if applicable)
    from source
    where anchor_age >= {{ var('min_age') }}
      and anchor_age <= {{ var('max_age') }}
)

select * from cleaned
