-- =============================================================================
-- Staging: Admissions
-- Clean hospital admission records
-- =============================================================================

with source as (
    select * from {{ source('mimic_hosp', 'admissions') }}
    where subject_id is not null
      and subject_id::text != 'NaN'
      and hadm_id is not null
      and hadm_id::text != 'NaN'
),

cleaned as (
    select
        subject_id::integer as subject_id,
        hadm_id::integer as hadm_id,
        admittime,
        dischtime,
        deathtime,
        admission_type,
        admit_provider_id,
        admission_location,
        discharge_location,
        insurance,
        language,
        marital_status,
        race,
        edregtime,
        edouttime,
        hospital_expire_flag,
        
        -- Derived fields
        extract(epoch from (dischtime - admittime)) / 86400.0 as los_days,
        case when edregtime is not null then 1 else 0 end as ed_admission,
        case when deathtime is not null then 1 else 0 end as died_in_hospital
        
    from source
    where dischtime is not null
      and dischtime > admittime
)

select * from cleaned
