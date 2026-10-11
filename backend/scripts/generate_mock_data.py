"""Generate all mock CSV files with guaranteed column alignment.

Run this once from the backend/ folder:

    python scripts/generate_mock_data.py

It will overwrite mock/business/*.csv with correctly formatted content.
"""

import json
import sys
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------
# Locate repo root and mock folder
# ----------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
MOCK_BUSINESS = REPO_ROOT / "mock" / "business"
MOCK_BUSINESS.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------
# assets.csv
# ----------------------------------------------------------------
assets = pd.DataFrame([
    {
        "asset_id": "B-03",
        "asset_type": "commercial",
        "parcel_id": "P-B03",
        "building_id": "BLD-B03",
        "asset_name": "Commercial Lot B-03",
        "land_use": "commercial",
        "development_phase": 2,
        "status": "existing",
        "completion_year": 2024,
        "target_demographic": "mixed",
        "floor_area_m2": 6800,
        "lettable_area_m2": 5200,
        "land_area_m2": 2400,
        "capex_initial_rm": 45_000_000,
        "opex_annual_rm": 820_000,
        "maintenance_annual_rm": 180_000,
        "capacity": 80,
        "data_completeness": 0.78,
        "data_sources": "property_records;osm;mock_business",
    },
    {
        "asset_id": "F-02",
        "asset_type": "community_facility",
        "parcel_id": "P-F02",
        "building_id": "BLD-F02",
        "asset_name": "Community Facility F-02",
        "land_use": "community_facility",
        "development_phase": 2,
        "status": "existing",
        "completion_year": 2024,
        "target_demographic": "families",
        "floor_area_m2": 1200,
        "lettable_area_m2": 1200,
        "land_area_m2": 1800,
        "capex_initial_rm": 6_000_000,
        "opex_annual_rm": 280_000,
        "maintenance_annual_rm": 90_000,
        "capacity": 200,
        "data_completeness": 0.82,
        "data_sources": "property_records;osm;mock_facility",
    },
    {
        "asset_id": "P-05",
        "asset_type": "undeveloped_parcel",
        "parcel_id": "P-05",
        "building_id": None,
        "asset_name": "Undeveloped Parcel P-05",
        "land_use": "undeveloped",
        "development_phase": None,
        "status": "planned",
        "completion_year": None,
        "target_demographic": "unknown",
        "floor_area_m2": 0,
        "lettable_area_m2": 0,
        "land_area_m2": 3600,
        "capex_initial_rm": 0,
        "opex_annual_rm": 0,
        "maintenance_annual_rm": 0,
        "capacity": 0,
        "data_completeness": 0.55,
        "data_sources": "osm",
    },
    {
        "asset_id": "G-01",
        "asset_type": "green_space",
        "parcel_id": "P-G01",
        "building_id": None,
        "asset_name": "Green Space G-01",
        "land_use": "green_space",
        "development_phase": None,
        "status": "existing",
        "completion_year": None,
        "target_demographic": "public",
        "floor_area_m2": 0,
        "lettable_area_m2": 0,
        "land_area_m2": 5200,
        "capex_initial_rm": 3_000_000,
        "opex_annual_rm": 80_000,
        "maintenance_annual_rm": 40_000,
        "capacity": 0,
        "data_completeness": 0.74,
        "data_sources": "osm;mock_environmental",
    },
    {
        "asset_id": "R-01",
        "asset_type": "residential",
        "parcel_id": "P-R01",
        "building_id": "BLD-R01",
        "asset_name": "Residential Catchment R-01",
        "land_use": "residential",
        "development_phase": 1,
        "status": "existing",
        "completion_year": 2023,
        "target_demographic": "families",
        "floor_area_m2": 42000,
        "lettable_area_m2": 40000,
        "land_area_m2": 14000,
        "capex_initial_rm": 180_000_000,
        "opex_annual_rm": 3_200_000,
        "maintenance_annual_rm": 800_000,
        "capacity": 480,
        "data_completeness": 0.81,
        "data_sources": "property_records;osm",
    },
])

assets.to_csv(MOCK_BUSINESS / "assets.csv", index=False)
print(f"Wrote {MOCK_BUSINESS / 'assets.csv'} ({len(assets)} rows, {len(assets.columns)} cols)")


# ----------------------------------------------------------------
# asset_metrics.csv — critical: define ALL columns in order
# ----------------------------------------------------------------
metric_cols = [
    "asset_id", "year",
    "occupancy_rate", "vacancy_rate", "vacancy_duration_months",
    "footfall_daily", "rental_income_per_visit_proxy",   # renamed
    "utilisation_rate",
    "rental_income_rm", "noi_rm", "noi_yield",
    "accessibility_score", "service_coverage",
    "effective_demand", "effective_demand_m2",           # added
    "effective_supply", "dsr",
    "carbon_operational_tco2e", "energy_kwh",
    "green_coverage", "canopy_coverage", "shade_proxy_score",   # renamed
    "financial_score", "environmental_score", "social_score",
    "performance_score", "delta_score",
    "metric_source", "model_version",
]

# Build each row as a dict; missing keys become NaN automatically
metrics_rows = [
    {
        "asset_id": "B-03", "year": 2026,
        "occupancy_rate": 0.21, "vacancy_duration_months": 14,
        "footfall_daily": 320,
        "rental_income_rm": 960_000,
        "effective_demand": 2100, "effective_supply": 3400,
        "metric_source": "observed", "model_version": "v0.3.0",
    },
    {
        "asset_id": "F-02", "year": 2026,
        "utilisation_rate": 0.22,
        "rental_income_rm": None,
        "effective_supply": 0.45,          # placeholder service target
        "metric_source": "observed", "model_version": "v0.3.0",
    },
    {
        "asset_id": "P-05", "year": 2026,
        "metric_source": "observed", "model_version": "v0.3.0",
    },
    {
        "asset_id": "G-01", "year": 2026,
        "canopy_coverage": 0.08,
        "metric_source": "observed", "model_version": "v0.3.0",
    },
    {
        "asset_id": "R-01", "year": 2026,
        "occupancy_rate": 0.92,
        "metric_source": "observed", "model_version": "v0.3.0",
    },
]

metrics = pd.DataFrame(metrics_rows)
# Reindex to guaranteed column order
metrics = metrics.reindex(columns=metric_cols)
metrics.to_csv(MOCK_BUSINESS / "asset_metrics.csv", index=False)
print(f"Wrote {MOCK_BUSINESS / 'asset_metrics.csv'} ({len(metrics)} rows, {len(metrics.columns)} cols)")


# ----------------------------------------------------------------
# development_projects.csv
# ----------------------------------------------------------------
projects = pd.DataFrame([
    {
        "project_id": "PRJ-P3",
        "parcel_id": "P-PHASE3",
        "asset_id": None,
        "project_name": "Phase 3 Expansion",
        "project_status": "proposed",
        "planned_start_year": 2027,
        "planned_delivery_year": 2030,
        "gfa_m2": 12000,
        "units": 80,
        "land_use": "commercial",
        "capex_rm": 2_700_000,
        "scenario_dependency": "current_plan",
    },
])
projects.to_csv(MOCK_BUSINESS / "development_projects.csv", index=False)
print(f"Wrote {MOCK_BUSINESS / 'development_projects.csv'} ({len(projects)} rows)")


# ----------------------------------------------------------------
# development_candidates.csv
# ----------------------------------------------------------------
candidates = pd.DataFrame([
    {
        "candidate_id": "CAND-P05-01",
        "parcel_id": "P-05",
        "development_type": "childcare_centre",
        "target_gfa_m2": 1200,
        "target_units": 1,
        "target_demographic": "young_families",
        "expected_capex_rm": 1_800_000,
        "expected_completion_year": 2029,
        "expected_demand_coverage": 0.72,
        "expected_utilisation": 0.78,
        "expected_carbon_tco2e": 145,
        "expected_accessibility_delta": 0.08,
        "feasibility_status": "feasible",
        "constraint_notes": "Complies with land use plan",
    },
    {
        "candidate_id": "CAND-P05-02",
        "parcel_id": "P-05",
        "development_type": "community_hub",
        "target_gfa_m2": 900,
        "target_units": 1,
        "target_demographic": "all_residents",
        "expected_capex_rm": 1_200_000,
        "expected_completion_year": 2029,
        "expected_demand_coverage": 0.68,
        "expected_utilisation": 0.72,
        "expected_carbon_tco2e": 110,
        "expected_accessibility_delta": 0.10,
        "feasibility_status": "feasible",
        "constraint_notes": "Complies with land use plan",
    },
    {
        "candidate_id": "CAND-P05-03",
        "parcel_id": "P-05",
        "development_type": "mixed_use_commercial",
        "target_gfa_m2": 4200,
        "target_units": 0,
        "target_demographic": "general",
        "expected_capex_rm": 3_800_000,
        "expected_completion_year": 2031,
        "expected_demand_coverage": 0.31,
        "expected_utilisation": 0.42,
        "expected_carbon_tco2e": 420,
        "expected_accessibility_delta": 0.05,
        "feasibility_status": "constraint_flagged",
        "constraint_notes": "Surrounding commercial supply already saturated",
    },
    {
        "candidate_id": "CAND-P05-04",
        "parcel_id": "P-05",
        "development_type": "affordable_housing",
        "target_gfa_m2": 6800,
        "target_units": 60,
        "target_demographic": "young_families",
        "expected_capex_rm": 5_200_000,
        "expected_completion_year": 2031,
        "expected_demand_coverage": 0.55,
        "expected_utilisation": 0.80,
        "expected_carbon_tco2e": 580,
        "expected_accessibility_delta": 0.06,
        "feasibility_status": "feasible",
        "constraint_notes": "Aligns with housing policy",
    },
    {
        "candidate_id": "CAND-P05-05",
        "parcel_id": "P-05",
        "development_type": "green_space",
        "target_gfa_m2": 3600,
        "target_units": 0,
        "target_demographic": "public",
        "expected_capex_rm": 400_000,
        "expected_completion_year": 2027,
        "expected_demand_coverage": 1.00,
        "expected_utilisation": 0.85,
        "expected_carbon_tco2e": 15,
        "expected_accessibility_delta": 0.15,
        "feasibility_status": "feasible",
        "constraint_notes": "Low CAPEX ecological upgrade",
    },
])
candidates.to_csv(MOCK_BUSINESS / "development_candidates.csv", index=False)
print(f"Wrote {MOCK_BUSINESS / 'development_candidates.csv'} ({len(candidates)} rows)")


# ----------------------------------------------------------------
# interventions.csv — JSON fields handled safely by pandas quoting
# ----------------------------------------------------------------
interventions = pd.DataFrame([
    {
        "scenario_id": "SC-REPURPOSE",
        "intervention_id": "INT-001",
        "target_asset_id": "B-03",
        "intervention_type": "repurpose",
        "parameters_json": json.dumps({
            "from": "commercial_shoplot",
            "to": "community_facility",
            "new_capacity": 200,
        }),
        "expected_derived_json": json.dumps({
            "service_coverage": 0.72,
            "utilisation": 0.78,
            "carbon_operational_tco2e": 145,
            "accessibility_delta": 0.08,
        }),
        "expected_source": "llm_estimate",
        "construction_start_year": 2027,
        "construction_duration_months": 18,
        "activation_year": 2028,
        "during_construction_status": "unavailable",
        "capex_delta_rm": 1_200_000,
        "opex_delta_rm": 60_000,
        "validation_status": "pending",
        "status": "simulated",
    },
    {
        "scenario_id": "SC-REPURPOSE",
        "intervention_id": "INT-002",
        "target_asset_id": "E-R17",
        "intervention_type": "pedestrian_upgrade",
        "parameters_json": json.dumps({}),
        "expected_derived_json": None,
        "expected_source": None,
        "construction_start_year": 2027,
        "construction_duration_months": 6,
        "activation_year": 2028,
        "during_construction_status": "partial",
        "capex_delta_rm": 180_000,
        "opex_delta_rm": 5_000,
        "validation_status": "pending",
        "status": "simulated",
    },
    {
        "scenario_id": "SC-DELAY",
        "intervention_id": "INT-003",
        "target_asset_id": "PRJ-P3",
        "intervention_type": "delay_development",
        "parameters_json": json.dumps({"until": 2033}),
        "expected_derived_json": None,
        "expected_source": None,
        "construction_start_year": 2027,
        "construction_duration_months": 0,
        "activation_year": 2027,
        "during_construction_status": "operational",
        "capex_delta_rm": 0,
        "opex_delta_rm": 0,
        "validation_status": "pending",
        "status": "simulated",
    },
    {
        "scenario_id": "SC-CURRENT",
        "intervention_id": "INT-004",
        "target_asset_id": None,
        "intervention_type": "no_op",
        "parameters_json": json.dumps({}),
        "expected_derived_json": None,
        "expected_source": None,
        "construction_start_year": 2026,
        "construction_duration_months": 0,
        "activation_year": 2026,
        "during_construction_status": "operational",
        "capex_delta_rm": 0,
        "opex_delta_rm": 0,
        "validation_status": "validated",
        "status": "applied",
    },
])
interventions.to_csv(MOCK_BUSINESS / "interventions.csv", index=False)
print(f"Wrote {MOCK_BUSINESS / 'interventions.csv'} ({len(interventions)} rows)")


print("\nAll mock business CSV files generated.")