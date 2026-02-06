-- =============================================================================
-- Intermediate: Comorbidities
-- Calculate comorbidity flags using ICD codes
-- =============================================================================

with diagnoses as (
    select * from {{ ref('stg_diagnoses') }}
),

comorbidities as (
    select
        subject_id,
        hadm_id,
        
        -- Congestive Heart Failure (CHF)
        max(case 
            when icd_code like 'I50%' 
              or icd_code in ('4280', '4281', '42820', '42821', '42822', '42823', '42830', '42831', '42832', '42833', '42840', '42841', '42842', '42843', '4289')
            then 1 else 0 
        end) as has_chf,
        
        -- Diabetes
        max(case 
            when icd_code like 'E10%' or icd_code like 'E11%' or icd_code like 'E13%'
              or icd_code like '250%'
            then 1 else 0 
        end) as has_diabetes,
        
        -- Chronic Kidney Disease (CKD)
        max(case 
            when icd_code like 'N18%' or icd_code like 'N19%'
              or icd_code like '585%' or icd_code like '586%'
            then 1 else 0 
        end) as has_ckd,
        
        -- COPD
        max(case 
            when icd_code like 'J44%' or icd_code like 'J43%'
              or icd_code like '491%' or icd_code like '492%' or icd_code like '496%'
            then 1 else 0 
        end) as has_copd,
        
        -- Hypertension
        max(case 
            when icd_code like 'I10%' or icd_code like 'I11%' or icd_code like 'I12%' or icd_code like 'I13%'
              or icd_code like '401%' or icd_code like '402%' or icd_code like '403%' or icd_code like '404%'
            then 1 else 0 
        end) as has_hypertension,
        
        -- Cancer (malignant neoplasms)
        max(case 
            when icd_code like 'C%' and icd_code not like 'C44%'  -- Exclude non-melanoma skin cancer
              or (icd_code >= '140' and icd_code < '210')
            then 1 else 0 
        end) as has_cancer,
        
        -- Count total diagnoses
        count(distinct icd_code) as diagnosis_count,
        
        -- Simplified Charlson Comorbidity Index (subset)
        (
            max(case when icd_code like 'I50%' or icd_code like '428%' then 1 else 0 end) +  -- CHF
            max(case when icd_code like 'E10%' or icd_code like 'E11%' or icd_code like '250%' then 1 else 0 end) +  -- Diabetes
            max(case when icd_code like 'N18%' or icd_code like '585%' then 2 else 0 end) +  -- CKD (weight 2)
            max(case when icd_code like 'J44%' or icd_code like '496%' then 1 else 0 end) +  -- COPD
            max(case when icd_code like 'C%' then 2 else 0 end)  -- Cancer (weight 2)
        ) as charlson_index
        
    from diagnoses
    group by subject_id, hadm_id
)

select * from comorbidities
