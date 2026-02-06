-- =============================================================================
-- Staging: Diagnoses
-- ICD diagnosis codes per admission
-- =============================================================================

with source as (
    select * from {{ source('mimic_hosp', 'diagnoses_icd') }}
    where subject_id is not null
      and subject_id::text != 'NaN'
      and hadm_id is not null
      and hadm_id::text != 'NaN'
),

cleaned as (
    select
        subject_id::integer as subject_id,
        hadm_id::integer as hadm_id,
        seq_num,
        icd_code,
        icd_version
    from source
)

select * from cleaned
