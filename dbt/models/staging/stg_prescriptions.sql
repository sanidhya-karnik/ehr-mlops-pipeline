-- =============================================================================
-- Staging: Prescriptions
-- Medication orders
-- =============================================================================

with source as (
    select 
        -- Convert NaN to NULL using text comparison before casting
        case when subject_id::text = 'NaN' then null else subject_id end as subject_id,
        case when hadm_id::text = 'NaN' then null else hadm_id end as hadm_id,
        case when pharmacy_id::text = 'NaN' then null else pharmacy_id end as pharmacy_id,
        starttime,
        stoptime,
        drug_type,
        drug,
        gsn,
        ndc,
        prod_strength,
        dose_val_rx,
        dose_unit_rx,
        route
    from {{ source('mimic_hosp', 'prescriptions') }}
    where hadm_id is not null
      and hadm_id::text != 'NaN'
      and subject_id is not null
      and subject_id::text != 'NaN'
),

cleaned as (
    select
        subject_id::integer as subject_id,
        hadm_id::integer as hadm_id,
        pharmacy_id,
        starttime,
        stoptime,
        drug_type,
        drug,
        gsn,
        ndc,
        prod_strength,
        dose_val_rx,
        dose_unit_rx,
        route,
        
        -- High-risk medication flags
        case 
            when lower(drug) like '%warfarin%' then 1
            when lower(drug) like '%heparin%' then 1
            when lower(drug) like '%enoxaparin%' then 1
            when lower(drug) like '%rivaroxaban%' then 1
            when lower(drug) like '%apixaban%' then 1
            else 0
        end as is_anticoagulant,
        
        case 
            when lower(drug) like '%insulin%' then 1
            else 0
        end as is_insulin,
        
        case 
            when lower(drug) like '%metformin%' then 1
            when lower(drug) like '%glipizide%' then 1
            when lower(drug) like '%glyburide%' then 1
            else 0
        end as is_antidiabetic,
        
        case 
            when lower(drug) like '%oxycodone%' then 1
            when lower(drug) like '%hydrocodone%' then 1
            when lower(drug) like '%morphine%' then 1
            when lower(drug) like '%fentanyl%' then 1
            when lower(drug) like '%tramadol%' then 1
            else 0
        end as is_opioid,
        
        case 
            when lower(drug) like '%furosemide%' then 1
            when lower(drug) like '%lasix%' then 1
            when lower(drug) like '%bumetanide%' then 1
            else 0
        end as is_diuretic,
        
        case
            when lower(drug) like '%digoxin%' then 1
            else 0
        end as is_digoxin
        
    from source
)

select * from cleaned
