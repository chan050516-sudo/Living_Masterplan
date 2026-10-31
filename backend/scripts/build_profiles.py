import json
import pandas as pd
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT / "bukit_jelutong" / "processed" / "business"
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.derived.thermal import empty_thermal_metrics, load_thermal_observations

def _safe_float(val, decimals=2):
    """Clean NaN for JSON serialization"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return None

def _parse_json(raw):
    if not raw or pd.isna(raw):
        return None
    try:
        return json.loads(raw)
    except:
        return None

def _calculate_apparent_temp(lst_celsius, asset_type):
    """
    Convert LST to Apparent Temperature using LCZ-based aerodynamic damping,
    calibrated for tropical Malaysia (noontime humidity and baseline Ta).
    """
    if lst_celsius is None or pd.isna(lst_celsius):
        return None
        
    BASE_TA = 32.0 
    
    # 1. Stratified Aerodynamic Damping based on Local Climate Zones (LCZ)
    if asset_type in ['commercial', 'industrial', 'infrastructure']:
        damping = 0.25
        rh = 0.58
    elif asset_type in ['residential', 'community_facility', 'mixed_use', 'religious', 'education', 'facility']:
        damping = 0.35
        rh = 0.60
    elif asset_type in ['green_space', 'undeveloped_parcel']:
        damping = 0.70
        rh = 0.65
    else:
        damping = 0.30
        rh = 0.60

    # 2. Estimate 1.5m Air Temperature (Ta)
    ta = BASE_TA + (lst_celsius - BASE_TA) * damping

    # 3. Calculate Vapour Pressure (e) using WMO standard Magnus-Tetens formula
    e = rh * 6.105 * math.exp((17.27 * ta) / (237.7 + ta))
    
    # 4. Steadman Apparent Temperature (BOM standard)
    wind_speed = 1.5  # m/s
    at = ta + (0.33 * e) - (0.70 * wind_speed) - 4.00
    
    return round(at, 2)

def build_profiles(year=2026):
    print("Loading data sources...")
    assets = pd.read_csv(BASE_DIR / "assets.csv")
    metrics = pd.read_csv(BASE_DIR / "asset_metrics_enriched.csv")
    metrics_yr = metrics[metrics["year"] == year]
    
    leases = pd.read_csv(BASE_DIR / "asset_leases.csv") if (BASE_DIR / "asset_leases.csv").exists() else pd.DataFrame()
    
    with open(BASE_DIR / f"deadspace_{year}.json") as f:
        deadspace_list = json.load(f)
    deadspace_dict = {d["asset_id"]: d for d in deadspace_list}

    thermal_observations = load_thermal_observations(
        BASE_DIR / "thermal_observations.csv"
    )
    
    profiles = {}
    
    for _, a in assets.iterrows():
        aid = a["asset_id"]
        atype = a.get("asset_type")
        
        # Get metrics for this year
        m_df = metrics_yr[metrics_yr["asset_id"] == aid]
        m = m_df.iloc[0].to_dict() if not m_df.empty else {}
        
        # Get deadspace diagnosis
        ds = deadspace_dict.get(aid, {})
        thermal = (
            thermal_observations.get(aid, empty_thermal_metrics())
            if year == 2026
            else empty_thermal_metrics()
        )
        evidence = [
            line for line in ds.get("evidence", [])
            if "UHI proxy" not in str(line)
            and "open-field baseline" not in str(line)
        ]
        if all(
            thermal.get(key) is not None
            for key in ("t_asset_c", "t_township_c", "surface_temp_delta_c")
        ):
            delta = thermal["surface_temp_delta_c"]
            sign = "+" if delta > 0 else ("-" if delta < 0 else "")
            evidence.append(
                "Observed land surface temperature "
                f"({thermal['surface_temp_provenance']}): parcel "
                f"{thermal['t_asset_c']:.1f} °C; township baseline "
                f"{thermal['t_township_c']:.1f} °C; "
                f"T = Tasset − Ttownship = {sign}{abs(delta):.1f} °C"
            )
        
        # Get lease info
        asset_leases = leases[leases["asset_id"] == aid] if not leases.empty else pd.DataFrame()
        anchor_lease = None
        if not asset_leases.empty:
            active = asset_leases[asset_leases["lease_status"] == "active"]
            if not active.empty:
                anchor = active[active["tenant_type"] == "anchor"]
                if not anchor.empty:
                    anchor_lease = {
                        "end_year": int(anchor.iloc[0]["lease_end_year"]),
                        "floor_area_m2": _safe_float(anchor.iloc[0]["floor_area_m2"])
                    }
        
        # Parse unit mix and per-subtype occupancy
        unit_mix = _parse_json(a.get("unit_mix_json"))
        occ_by_subtype = _parse_json(m.get("occupancy_by_subtype_calc_json"))
        
        subunits = []
        if unit_mix and occ_by_subtype:
            for st, info in unit_mix.items():
                area = _safe_float(info.get("area_m2"))
                occ = _safe_float(occ_by_subtype.get(st))
                total_mix_area = sum(float(v.get("area_m2", 0)) for v in unit_mix.values())
                ratio = area / total_mix_area if total_mix_area > 0 else 0
                
                subunits.append({
                    "subtype": st,
                    "area_m2": area,
                    "occupancy": occ,
                    "allocated_carbon_tco2e": _safe_float(m.get("carbon_operational_tco2e", 0) * ratio),
                    "allocated_noi_rm": _safe_float(m.get("noi_rm", 0) * ratio)
                })

        # ==========================================
        # ASSEMBLE THE FULL PROFILE
        # ==========================================
        profiles[aid] = {
            "identity": {
                "asset_id": aid,
                "asset_name": a.get("asset_name"),
                "asset_type": atype,
                "subtype": a.get("subtype"),
                "land_use": a.get("land_use"),
                "status": a.get("status"),
                "completion_year": _safe_float(a.get("completion_year"), 0),
            },
            "physical": {
                "floor_area_m2": _safe_float(a.get("floor_area_m2"), 1),
                "lettable_area_m2": _safe_float(a.get("lettable_area_m2"), 1),
                "land_area_m2": _safe_float(a.get("land_area_m2"), 1),
                "capacity": _safe_float(a.get("capacity"), 0),
            },
            "authority": {
                "level": a.get("authority"),
                "ownership_status": a.get("ownership_status"),
            },
            "financial": {
                "capex_initial_rm": _safe_float(a.get("capex_initial_rm"), 0),
                "opex_annual_rm": _safe_float(a.get("opex_annual_rm"), 0),
                "maintenance_annual_rm": _safe_float(a.get("maintenance_annual_rm"), 0),
                "rental_income_rm": _safe_float(m.get("rental_income_rm")),
                "noi_rm": _safe_float(m.get("noi_rm")),
                "noi_yield": _safe_float(m.get("noi_yield"), 4),
                "dsr": _safe_float(m.get("dsr")),
            },
            "social": {
                "occupancy_rate": _safe_float(m.get("occupancy_rate")),
                "utilisation_rate": _safe_float(m.get("utilisation_rate")),
                "footfall_daily": _safe_float(m.get("footfall_daily"), 0),
                "coverage_ratio_5min_walk": _safe_float(m.get("coverage_ratio_5min_walk"), 3),
                "coverage_ratio_10min_walk": _safe_float(m.get("coverage_ratio_10min_walk"), 3),
                "coverage_ratio_15min_walk": _safe_float(m.get("coverage_ratio_15min_walk"), 3),
                "reachable_population_walk": _safe_float(m.get("reachable_population_walk"), 0),
                "effective_demand_m2": _safe_float(m.get("effective_demand_m2")),
                "demographic_mismatch": _safe_float(m.get("demographic_mismatch"), 3),
                "neighborhood_diversity": _safe_float(m.get("neighborhood_diversity"), 3),
            },
            "environmental": {
                "carbon_operational_tco2e": _safe_float(m.get("carbon_operational_tco2e")),
                "carbon_productive_tco2e": _safe_float(m.get("carbon_productive_tco2e")),
                "carbon_stranded_tco2e": _safe_float(m.get("carbon_stranded_tco2e")),
                "stranded_carbon_ratio": _safe_float(m.get("stranded_carbon_ratio"), 3),
                "embodied_carbon_tco2e": _safe_float(m.get("embodied_carbon_total_tco2e")),
                "energy_kwh_total": _safe_float(m.get("energy_kwh"), 0),
                "energy_kwh_hvac": _safe_float(m.get("energy_kwh_hvac"), 0),
                "energy_kwh_lighting": _safe_float(m.get("energy_kwh_lighting_equipment"), 0),
                "energy_kwh_base_load": _safe_float(m.get("energy_kwh_base_load"), 0),
                "t_asset_c": _safe_float(thermal.get("t_asset_c"), 2),
                "t_township_c": _safe_float(thermal.get("t_township_c"), 2),
                "surface_temp_delta_c": _safe_float(thermal.get("surface_temp_delta_c"), 2),
                "apparent_temp_c": _calculate_apparent_temp(thermal.get("t_asset_c"), atype),
                "surface_temp_provenance": thermal.get("surface_temp_provenance"),
                "surface_temp_collection_id": thermal.get("surface_temp_collection_id"),
                "surface_temp_band": thermal.get("surface_temp_band"),
                "surface_temp_source_catalog": thermal.get("surface_temp_source_catalog"),
                "surface_temp_valid_pixel_count": thermal.get("surface_temp_valid_pixel_count"),
                "surface_temp_period_start": thermal.get("surface_temp_period_start"),
                "surface_temp_period_end": thermal.get("surface_temp_period_end"),
                "surface_temp_source_image_count": thermal.get("surface_temp_source_image_count"),
                "green_coverage": _safe_float(m.get("green_coverage"), 3),
                "canopy_coverage": _safe_float(m.get("canopy_coverage"), 3),
                "green_per_capita_m2": _safe_float(m.get("green_per_capita_m2"), 1),
            },
            "trajectory": {
                "class": m.get("trajectory_class"),
                "peak_occupancy": _safe_float(m.get("peak_occupancy"), 3),
                "years_since_peak": _safe_float(m.get("years_since_peak"), 0),
                "occupancy_trend_3yr": _safe_float(m.get("occupancy_trend_3yr"), 4),
                "vacancy_streak_months": _safe_float(m.get("vacancy_streak_months"), 0),
            },
            "deadspace_diagnosis": {
                "status": ds.get("status", "healthy"),
                # Keep all flags (removed the previous UHI filter)
                "flags": ds.get("flags", []),
                "urgency_index": _safe_float(ds.get("urgency_index"), 1),
                "contributing_factors": ds.get("contributing_factors", []),
                "evidence": evidence
            },
            "leases": {
                "anchor_lease": anchor_lease
            },
            "subunits": subunits if subunits else None
        }
        
    out_path = BASE_DIR / f"asset_profiles_{year}.json"
    with open(out_path, "w") as f:
        json.dump(profiles, f, indent=2)
    print(f"Wrote {len(profiles)} full asset profiles to {out_path}")

if __name__ == "__main__":
    build_profiles()