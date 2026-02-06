-- =============================================================================
-- Intermediate: Lab Summary
-- Aggregate lab values per admission
-- =============================================================================

with labs as (
    select * from {{ ref('stg_labevents') }}
    -- Extra NaN safety filter
    where valuenum = valuenum
),

lab_summary as (
    select
        hadm_id,
        
        -- Creatinine (kidney function)
        max(case when lab_name = 'creatinine' then valuenum end) as creatinine_max,
        min(case when lab_name = 'creatinine' then valuenum end) as creatinine_min,
        avg(case when lab_name = 'creatinine' then valuenum end) as creatinine_avg,
        
        -- Glucose (diabetes)
        max(case when lab_name = 'glucose' then valuenum end) as glucose_max,
        min(case when lab_name = 'glucose' then valuenum end) as glucose_min,
        avg(case when lab_name = 'glucose' then valuenum end) as glucose_avg,
        
        -- Hemoglobin (anemia)
        max(case when lab_name = 'hemoglobin' then valuenum end) as hemoglobin_max,
        min(case when lab_name = 'hemoglobin' then valuenum end) as hemoglobin_min,
        avg(case when lab_name = 'hemoglobin' then valuenum end) as hemoglobin_avg,
        
        -- WBC (infection/inflammation)
        max(case when lab_name = 'wbc' then valuenum end) as wbc_max,
        min(case when lab_name = 'wbc' then valuenum end) as wbc_min,
        avg(case when lab_name = 'wbc' then valuenum end) as wbc_avg,
        
        -- Sodium
        max(case when lab_name = 'sodium' then valuenum end) as sodium_max,
        min(case when lab_name = 'sodium' then valuenum end) as sodium_min,
        
        -- Potassium
        max(case when lab_name = 'potassium' then valuenum end) as potassium_max,
        min(case when lab_name = 'potassium' then valuenum end) as potassium_min,
        
        -- BUN (kidney)
        max(case when lab_name = 'bun' then valuenum end) as bun_max,
        avg(case when lab_name = 'bun' then valuenum end) as bun_avg,
        
        -- Platelet count
        min(case when lab_name = 'platelet' then valuenum end) as platelet_min,
        
        -- Abnormal lab counts (coalesce to handle any remaining edge cases)
        coalesce(sum(case when is_abnormal = 1 then 1 else 0 end), 0) as abnormal_lab_count,
        count(*) as total_lab_count,
        
        -- Ratio of abnormal labs
        round(
            coalesce(sum(case when is_abnormal = 1 then 1 else 0 end), 0)::numeric 
            / nullif(count(*), 0), 
            3
        ) as abnormal_lab_ratio
        
    from labs
    group by hadm_id
)

select * from lab_summary
