-- =============================================================================
-- Intermediate: Medication Summary
-- Aggregate medication info per admission
-- =============================================================================

with prescriptions as (
    select * from {{ ref('stg_prescriptions') }}
),

med_summary as (
    select
        hadm_id,
        
        -- Total unique medications
        count(distinct drug) as unique_med_count,
        
        -- Total prescription records
        count(*) as total_prescription_count,
        
        -- High-risk medication flags
        max(is_anticoagulant) as on_anticoagulant,
        max(is_insulin) as on_insulin,
        max(is_antidiabetic) as on_antidiabetic,
        max(is_opioid) as on_opioid,
        max(is_diuretic) as on_diuretic,
        max(is_digoxin) as on_digoxin,
        
        -- Count of high-risk medications
        (
            max(is_anticoagulant) + 
            max(is_insulin) + 
            max(is_antidiabetic) + 
            max(is_opioid) + 
            max(is_diuretic) + 
            max(is_digoxin)
        ) as high_risk_med_count,
        
        -- Polypharmacy flag (>= 5 unique meds)
        case when count(distinct drug) >= 5 then 1 else 0 end as polypharmacy,
        
        -- Severe polypharmacy (>= 10 unique meds)
        case when count(distinct drug) >= 10 then 1 else 0 end as severe_polypharmacy,
        
        -- Route diversity
        count(distinct route) as unique_routes
        
    from prescriptions
    group by hadm_id
)

select * from med_summary
