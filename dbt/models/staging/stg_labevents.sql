-- =============================================================================
-- Staging: Lab Events
-- Key laboratory measurements
-- =============================================================================

with source as (
    select 
        labevent_id,
        -- Convert NaN to NULL using text comparison before casting
        case when subject_id::text = 'NaN' then null else subject_id end as subject_id,
        case when hadm_id::text = 'NaN' then null else hadm_id end as hadm_id,
        case when itemid::text = 'NaN' then null else itemid end as itemid,
        charttime,
        case when valuenum::text = 'NaN' then null else valuenum end as valuenum,
        valueuom,
        case when ref_range_lower::text = 'NaN' then null else ref_range_lower end as ref_range_lower,
        case when ref_range_upper::text = 'NaN' then null else ref_range_upper end as ref_range_upper,
        flag
    from {{ source('mimic_hosp', 'labevents') }}
    where hadm_id is not null
      and hadm_id::text != 'NaN'
      and valuenum is not null
      and valuenum::text != 'NaN'
      and subject_id is not null
      and subject_id::text != 'NaN'
      and itemid is not null
      and itemid::text != 'NaN'
),

cleaned as (
    select
        labevent_id,
        subject_id::integer as subject_id,
        hadm_id::integer as hadm_id,
        itemid::integer as itemid,
        charttime,
        valuenum::float as valuenum,
        valueuom,
        ref_range_lower::float as ref_range_lower,
        ref_range_upper::float as ref_range_upper,
        flag,
        
        -- Lab test names based on itemid
        case itemid::integer
            when 50912 then 'creatinine'
            when 50931 then 'glucose'
            when 51222 then 'hemoglobin'
            when 51301 then 'wbc'
            when 50971 then 'potassium'
            when 50983 then 'sodium'
            when 51006 then 'bun'
            when 50882 then 'bicarbonate'
            when 51265 then 'platelet'
            when 50893 then 'calcium'
            else 'other'
        end as lab_name,
        
        -- Flag if abnormal
        case 
            when flag in ('abnormal', 'delta') then 1
            when ref_range_lower is not null and valuenum::float < ref_range_lower::float then 1
            when ref_range_upper is not null and valuenum::float > ref_range_upper::float then 1
            else 0
        end as is_abnormal
        
    from source
)

select * from cleaned
