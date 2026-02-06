-- =============================================================================
-- Intermediate: Prior Admissions
-- Calculate prior admission counts for each admission
-- =============================================================================

with admissions as (
    select * from {{ ref('stg_admissions') }}
),

prior_admits as (
    select
        a.subject_id,
        a.hadm_id,
        a.admittime,
        
        -- Count admissions in prior 6 months
        count(case 
            when p.dischtime < a.admittime 
             and p.dischtime >= a.admittime - interval '180 days'
            then 1 
        end) as prior_admits_6mo,
        
        -- Count admissions in prior 12 months
        count(case 
            when p.dischtime < a.admittime 
             and p.dischtime >= a.admittime - interval '365 days'
            then 1 
        end) as prior_admits_12mo,
        
        -- Count ED visits in prior 6 months
        count(case 
            when p.dischtime < a.admittime 
             and p.dischtime >= a.admittime - interval '180 days'
             and p.ed_admission = 1
            then 1 
        end) as prior_ed_visits_6mo,
        
        -- Average LOS of prior admissions
        avg(case 
            when p.dischtime < a.admittime 
             and p.dischtime >= a.admittime - interval '365 days'
            then p.los_days 
        end) as avg_prior_los
        
    from admissions a
    left join admissions p 
        on a.subject_id = p.subject_id 
        and a.hadm_id != p.hadm_id
    group by a.subject_id, a.hadm_id, a.admittime
)

select * from prior_admits
