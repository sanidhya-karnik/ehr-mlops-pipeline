-- =============================================================================
-- Marts: Readmission Prediction Features (v2)
-- Complete feature table for ML model with labs and medications
-- =============================================================================

with admissions as (
    select * from {{ ref('stg_admissions') }}
),

patients as (
    select * from {{ ref('stg_patients') }}
),

prior_admits as (
    select * from {{ ref('int_prior_admissions') }}
),

comorbidities as (
    select * from {{ ref('int_comorbidities') }}
),

lab_summary as (
    select * from {{ ref('int_lab_summary') }}
),

med_summary as (
    select * from {{ ref('int_med_summary') }}
),

-- Calculate readmission flag
readmission_calc as (
    select
        a.subject_id,
        a.hadm_id,
        a.dischtime,
        lead(a.admittime) over (
            partition by a.subject_id 
            order by a.admittime
        ) as next_admittime,
        case 
            when lead(a.admittime) over (
                partition by a.subject_id 
                order by a.admittime
            ) - a.dischtime <= interval '{{ var("readmission_window", 30) }} days'
            then 1
            else 0
        end as readmitted_30d
    from admissions a
),

final as (
    select
        -- Identifiers
        a.subject_id,
        a.hadm_id,
        
        -- Demographics
        p.age,
        p.gender,
        
        -- Admission details
        a.admission_type,
        a.insurance,
        a.marital_status,
        a.race,
        a.ed_admission,
        a.los_days,
        
        -- Discharge info
        a.discharge_location,
        extract(dow from a.dischtime)::integer as discharge_dow,
        extract(hour from a.dischtime)::integer as discharge_hour,
        
        -- Prior utilization
        coalesce(pa.prior_admits_6mo, 0) as prior_admits_6mo,
        coalesce(pa.prior_admits_12mo, 0) as prior_admits_12mo,
        coalesce(pa.prior_ed_visits_6mo, 0) as prior_ed_visits_6mo,
        coalesce(pa.avg_prior_los, 0) as avg_prior_los,
        
        -- Comorbidities
        coalesce(c.diagnosis_count, 0) as diagnosis_count,
        coalesce(c.charlson_index, 0) as charlson_index,
        coalesce(c.has_chf, 0) as has_chf,
        coalesce(c.has_diabetes, 0) as has_diabetes,
        coalesce(c.has_ckd, 0) as has_ckd,
        coalesce(c.has_copd, 0) as has_copd,
        coalesce(c.has_hypertension, 0) as has_hypertension,
        coalesce(c.has_cancer, 0) as has_cancer,
        
        -- Lab values
        coalesce(l.creatinine_max, 0) as creatinine_max,
        coalesce(l.creatinine_avg, 0) as creatinine_avg,
        coalesce(l.glucose_max, 0) as glucose_max,
        coalesce(l.glucose_avg, 0) as glucose_avg,
        coalesce(l.hemoglobin_min, 0) as hemoglobin_min,
        coalesce(l.hemoglobin_avg, 0) as hemoglobin_avg,
        coalesce(l.wbc_max, 0) as wbc_max,
        coalesce(l.wbc_avg, 0) as wbc_avg,
        coalesce(l.sodium_min, 0) as sodium_min,
        coalesce(l.sodium_max, 0) as sodium_max,
        coalesce(l.potassium_min, 0) as potassium_min,
        coalesce(l.potassium_max, 0) as potassium_max,
        coalesce(l.bun_max, 0) as bun_max,
        coalesce(l.platelet_min, 0) as platelet_min,
        coalesce(l.abnormal_lab_count, 0) as abnormal_lab_count,
        coalesce(l.abnormal_lab_ratio, 0) as abnormal_lab_ratio,
        
        -- Medication features
        coalesce(m.unique_med_count, 0) as unique_med_count,
        coalesce(m.on_anticoagulant, 0) as on_anticoagulant,
        coalesce(m.on_insulin, 0) as on_insulin,
        coalesce(m.on_antidiabetic, 0) as on_antidiabetic,
        coalesce(m.on_opioid, 0) as on_opioid,
        coalesce(m.on_diuretic, 0) as on_diuretic,
        coalesce(m.on_digoxin, 0) as on_digoxin,
        coalesce(m.high_risk_med_count, 0) as high_risk_med_count,
        coalesce(m.polypharmacy, 0) as polypharmacy,
        coalesce(m.severe_polypharmacy, 0) as severe_polypharmacy,
        
        -- Target variable
        r.readmitted_30d,
        
        -- Metadata
        current_timestamp as feature_created_at
        
    from admissions a
    inner join patients p on a.subject_id = p.subject_id
    inner join readmission_calc r on a.hadm_id = r.hadm_id
    left join prior_admits pa on a.hadm_id = pa.hadm_id
    left join comorbidities c on a.hadm_id = c.hadm_id
    left join lab_summary l on a.hadm_id = l.hadm_id
    left join med_summary m on a.hadm_id = m.hadm_id
    
    where 
        -- Filter criteria
        a.los_days >= 1
        and a.hospital_expire_flag = 0
        and p.age >= {{ var("min_age", 18) }}
        and p.age <= {{ var("max_age", 120) }}
)

select * from final
