"""Build the per-asset profiles served by GET /api/assets/profiles.

Output: bukit_jelutong/processed/business/asset_profiles_{year}.json

Inputs (all under bukit_jelutong/processed/business/):
  assets.csv                     asset register (physical, authority, sale)
  asset_metrics_enriched.csv     B3 metrics for the year
  deadspace_{year}.json          B6 diagnosis (flags, layer3a proxy, survival)
  asset_lbs_metrics.csv          LBS / Kido proxy table (sold commercial)
  asset_business_presence.csv    Google Places proxy table (sold commercial)
  asset_leases.csv               lease schedule (owned)
  thermal_observations.csv       Landsat LST
and backend/configs/field_metadata.yml for the tier and source of every
served metric (the single source of truth; see `_build_tiers`).

Each profile carries a `tiers` map: {"<section>.<field>": {"tier", "source"
[, "mock"]}} for every non-null metric, with the tier already resolved for
the asset's authority. Tiers are "1", "2", "3a", "3b" or "U" (field_metadata
tier 4). Fields that are null for an asset get no tier entry.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT / "bukit_jelutong" / "processed" / "business"
FIELD_METADATA = REPO_ROOT / "backend" / "configs" / "field_metadata.yml"
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.derived.thermal import empty_thermal_metrics, load_thermal_observations

# Sections of field_metadata.yml searched for a field, in priority order.
_META_SECTIONS = ("profile_fields", "assets", "asset_metrics", "external_data")

# Profile paths whose field_metadata key differs from the leaf name.
_META_KEY_OF = {
    "social.lbs_dwell_minutes": "lbs_dwell_time_minutes",
    "social.external_demand_ratio": "observed_demand_ratio",
    "environmental.energy_kwh_total": "energy_kwh",
    "environmental.energy_kwh_lighting": "energy_kwh_lighting_equipment",
    "environmental.embodied_carbon_tco2e": "embodied_carbon_total_tco2e",
    "trajectory.class": "trajectory_class",
}

# Profile sections whose fields are metrics (get a tier entry).
_METRIC_SECTIONS = ("physical", "financial", "social", "environmental", "trajectory")

# Values that are labels, not metrics: never tiered.
_NOT_METRICS = {
    "social.proxied_occupancy_source",
    "financial.sale_data_source",
}


def _safe_float(val, decimals=2):
    """Clean NaN for JSON serialization"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return round(f, decimals)


def _safe_str(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    s = str(val).strip()
    return s or None


def _parse_json(raw):
    if raw is None or (isinstance(raw, float) and math.isnan(raw)) or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
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


# ------------------------------------------------------------------
# Tier resolution (field_metadata.yml)
# ------------------------------------------------------------------

def _load_field_meta() -> dict:
    with open(FIELD_METADATA, encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    flat = {}
    for section in _META_SECTIONS:
        for key, entry in (meta.get(section) or {}).items():
            if isinstance(entry, dict) and key not in flat:
                flat[key] = entry
    return flat


def _meta_key(path: str) -> str:
    if path in _META_KEY_OF:
        return _META_KEY_OF[path]
    section, leaf = path.split(".", 1)
    if section == "subunits":
        return f"subunit_{leaf}"
    return leaf


def _resolve_tier(entry: dict, authority, ownership):
    """Base tier, overridden by `authority_tiers` keyed by ownership_status
    (sold / shared / public_transferred) or authority (full_control)."""
    by_auth = entry.get("authority_tiers") or {}
    tier = by_auth.get(ownership, by_auth.get(authority, entry.get("tier")))
    if tier is None:
        return None
    tier = str(tier)
    return "U" if tier == "4" else tier


def _build_tiers(profile: dict, field_meta: dict, authority, ownership, unmapped: set) -> dict:
    """Tier + source for every non-null metric in the profile."""
    candidates = []
    for section in _METRIC_SECTIONS:
        for field, value in (profile.get(section) or {}).items():
            candidates.append((f"{section}.{field}", value))
    candidates.append(("identity.completion_year", profile["identity"].get("completion_year")))
    for sub in profile.get("subunits") or []:
        for field, value in sub.items():
            if field != "subtype":
                candidates.append((f"subunits.{field}", value))

    tiers = {}
    for path, value in candidates:
        if value is None or path in _NOT_METRICS or path in tiers:
            continue
        entry = field_meta.get(_meta_key(path))
        if entry is None:
            unmapped.add(path)
            continue
        tier = _resolve_tier(entry, authority, ownership)
        if tier is None:  # provenance / metadata field
            continue
        # A value the pipeline itself marks as unknown is Unknown,
        # whatever the field's nominal tier.
        if isinstance(value, str) and value.lower() == "unknown":
            tier = "U"
        item = {"tier": tier, "source": entry.get("source")}
        if entry.get("is_mock"):
            item["mock"] = True
        tiers[path] = item

    # The proxy occupancy's source is per asset (LBS or Google).
    src = profile["social"].get("proxied_occupancy_source")
    if src and "social.proxied_occupancy" in tiers:
        tiers["social.proxied_occupancy"]["source"] = src
    return tiers


# ------------------------------------------------------------------
# External proxy tables (Google Places, LBS)
# ------------------------------------------------------------------

def _load_external() -> dict:
    """asset_id -> merged row of the LBS and Google Places proxy tables."""
    out: dict = {}
    for name in ("asset_lbs_metrics.csv", "asset_business_presence.csv"):
        path = BASE_DIR / name
        if not path.exists():
            print(f"  (external table {name} not found; proxy fields stay null)")
            continue
        for row in pd.read_csv(path).to_dict("records"):
            out.setdefault(row["asset_id"], {}).update(row)
    return out


def build_profiles(year=2026):
    print("Loading data sources...")
    field_meta = _load_field_meta()
    assets = pd.read_csv(BASE_DIR / "assets.csv")
    metrics = pd.read_csv(BASE_DIR / "asset_metrics_enriched.csv")
    metrics_yr = metrics[metrics["year"] == year]

    leases = pd.read_csv(BASE_DIR / "asset_leases.csv") if (BASE_DIR / "asset_leases.csv").exists() else pd.DataFrame()
    external_by_asset = _load_external()

    with open(BASE_DIR / f"deadspace_{year}.json", encoding="utf-8") as f:
        deadspace_list = json.load(f)
    deadspace_dict = {d["asset_id"]: d for d in deadspace_list}

    thermal_observations = load_thermal_observations(
        BASE_DIR / "thermal_observations.csv"
    )

    profiles = {}
    unmapped: set = set()

    for _, a in assets.iterrows():
        aid = a["asset_id"]
        atype = a.get("asset_type")
        authority = _safe_str(a.get("authority"))
        ownership = _safe_str(a.get("ownership_status"))

        # Get metrics for this year
        m_df = metrics_yr[metrics_yr["asset_id"] == aid]
        m = m_df.iloc[0].to_dict() if not m_df.empty else {}

        # External proxies exist only for sold commercial assets.
        ext = external_by_asset.get(aid, {})

        # Get deadspace diagnosis
        ds = deadspace_dict.get(aid, {})
        survival = ds.get("survival") or {}
        thermal = (
            thermal_observations.get(aid, empty_thermal_metrics())
            if year == 2026
            else empty_thermal_metrics()
        )
        # Thermal evidence is injected ONCE at API time (main.py).
        # Do not write it into the profile here — doing so produced
        # three identical "Observed land surface temperature" lines
        # in the AssetPanel evidence block (one from B6's evidence
        # builder, one from this builder, one from main.py).
        evidence = [
            line for line in ds.get("evidence", [])
            if "UHI proxy" not in str(line)
            and "open-field baseline" not in str(line)
            and "Observed land surface temperature" not in str(line)
        ]

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

        # Parse unit mix
        unit_mix = _parse_json(a.get("unit_mix_json"))

        # Tier 3a proxies
        # If the asset is full_control, external CSV will not have a row for it.
        # We should distinguish "No external data" (None) from "0 operational" (0).
        biz_counts = _parse_json(m.get("business_subtype_counts_json"))
        biz_vitalities = _parse_json(m.get("business_subtype_vitality_json")) or {}
        # Observed per-subtype occupancy (owned assets only; null for sold).
        occ_by_subtype = _parse_json(m.get("occupancy_by_subtype_calc_json")) or {}

        subunits = []
        if unit_mix:
            total_mix_area = sum(float(v.get("area_m2", 0)) for v in unit_mix.values()) or 1.0

            for st, info in unit_mix.items():
                area = _safe_float(info.get("area_m2"))
                design_count = int(info.get("count", 1))
                if biz_counts is not None:
                    operational_count = int(biz_counts.get(st, 0))
                else:
                    operational_count = None  # N/A for full_control assets

                # Calculate presence ratio based on actual operational units
                if operational_count is not None and design_count > 0:
                    presence_ratio = min(1.0, operational_count / design_count)
                else:
                    presence_ratio = None

                ratio = (area or 0) / total_mix_area if total_mix_area > 0 else 0

                subunits.append({
                    "subtype": st,
                    "area_m2": area,
                    "design_count": design_count,
                    "occupancy": _safe_float(occ_by_subtype.get(st), 3),
                    "operational_count": operational_count,
                    "presence_ratio": presence_ratio,
                    "vitality_score": _safe_float(biz_vitalities.get(st), 3),
                    "allocated_carbon_tco2e": _safe_float(m.get("carbon_operational_tco2e", 0) * ratio),
                    "allocated_noi_rm": (
                        _safe_float(_safe_float(m.get("noi_rm")) * ratio)
                        if _safe_float(m.get("noi_rm")) is not None else None
                    ),
                })

        # Developer realisation (sold assets carry a sale record).
        sale_price = _safe_float(a.get("sale_price_rm"), 0)
        capex = _safe_float(a.get("capex_initial_rm"), 0)
        sale_profit = sale_price - capex if sale_price is not None and capex is not None else None
        sale_return = sale_profit / capex if sale_profit is not None and capex else None

        # Trajectory: years_since_peak means nothing without a peak (none, or 0%).
        peak_occ = _safe_float(m.get("peak_occupancy"), 3)

        # ==========================================
        # ASSEMBLE THE FULL PROFILE
        # ==========================================
        profile = {
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
                "unit_count": _safe_float(a.get("unit_count"), 0),
                "developer_held_units": _safe_float(a.get("developer_held_units"), 0),
                # Undeveloped parcels
                "developable_area_m2": _safe_float(m.get("developable_area_m2"), 1),
                "potential_gfa_m2": _safe_float(m.get("potential_gfa_m2"), 1),
            },
            "authority": {
                "level": authority,
                "ownership_status": ownership,
                "data_confidence": _safe_str(a.get("data_confidence")),
            },
            "financial": {
                "capex_initial_rm": capex,
                "opex_annual_rm": _safe_float(a.get("opex_annual_rm"), 0),
                "maintenance_annual_rm": _safe_float(a.get("maintenance_annual_rm"), 0),
                "maintenance_surge_rm": _safe_float(m.get("maintenance_surge_rm"), 0),
                "rental_income_rm": _safe_float(m.get("rental_income_rm")),
                "noi_rm": _safe_float(m.get("noi_rm")),
                "noi_yield": _safe_float(m.get("noi_yield"), 4),
                "dsr": _safe_float(m.get("dsr")),
                # Developer realisation (sold)
                "sale_price_rm": sale_price,
                "sale_date": _safe_str(a.get("sale_date")),
                "sale_data_source": _safe_str(a.get("sale_data_source")),
                "sale_profit_rm": _safe_float(sale_profit, 0),
                "sale_return_ratio": _safe_float(sale_return, 4),
                # Survival OPEX floor (B6 layer3_survival; sold commercial)
                "estimated_revenue_rm": _safe_float(survival.get("estimated_revenue_rm"), 0),
                "survival_opex_floor_rm": _safe_float(survival.get("survival_opex_floor_rm"), 0),
                "hemorrhage_ratio": _safe_float(survival.get("hemorrhage_ratio"), 3),
                # Community facility / parcel
                "cost_per_user_rm": _safe_float(m.get("cost_per_user_rm")),
                "demand_supply_gap": _safe_float(m.get("demand_supply_gap"), 1),
                "infrastructure_cost_rm": _safe_float(m.get("infrastructure_cost_rm"), 0),
            },
            "social": {
                "occupancy_rate": _safe_float(m.get("occupancy_rate")),
                "utilisation_rate": _safe_float(m.get("utilisation_rate")),
                "footfall_daily": _safe_float(m.get("footfall_daily"), 0),
                "vacancy_duration_months": _safe_float(m.get("vacancy_duration_months"), 0),
                "occupied_units": _safe_float(m.get("occupied_units"), 0),
                "service_coverage": _safe_float(m.get("service_coverage"), 3),
                "coverage_ratio_5min_walk": _safe_float(m.get("coverage_ratio_5min_walk"), 3),
                "coverage_ratio_10min_walk": _safe_float(m.get("coverage_ratio_10min_walk"), 3),
                "coverage_ratio_15min_walk": _safe_float(m.get("coverage_ratio_15min_walk"), 3),
                "coverage_ratio_10min_drive": _safe_float(m.get("coverage_ratio_10min_drive"), 3),
                "median_walk_distance_m": _safe_float(m.get("median_walk_distance_m"), 0),
                "reachable_population_walk": _safe_float(m.get("reachable_population_walk"), 0),
                "effective_demand_m2": _safe_float(m.get("effective_demand_m2")),
                "demographic_mismatch": _safe_float(m.get("demographic_mismatch"), 3),
                "neighborhood_diversity": _safe_float(m.get("neighborhood_diversity"), 3),
                # Tier-3a proxy fields (sold commercial only)
                "proxied_occupancy": (
                    _safe_float((ds.get("layer3a") or {}).get("proxied_occupancy"), 3)
                ),
                "proxied_occupancy_source": (
                    (ds.get("layer3a") or {}).get("proxied_occupancy_source")
                ),
                # LBS / Kido (asset_lbs_metrics.csv)
                "lbs_unique_users_daily": _safe_float(ext.get("lbs_unique_users_daily"), 0),
                "lbs_dwell_minutes": _safe_float(ext.get("lbs_dwell_time_minutes"), 1),
                "lbs_visit_frequency_monthly": _safe_float(ext.get("lbs_visit_frequency_monthly"), 2),
                "external_demand_ratio": _safe_float(ext.get("observed_demand_ratio"), 3),
                "proxied_occupancy_lbs": _safe_float(ext.get("proxied_occupancy_lbs"), 3),
                "flow_island_ratio": _safe_float(ext.get("flow_island_ratio"), 3),
                "traffic_exposure_vpd": _safe_float(ext.get("traffic_exposure_vpd"), 0),
                # Google Places (asset_business_presence.csv)
                "business_presence_ratio": _safe_float(ext.get("business_presence_ratio"), 3),
                "proxied_occupancy_google": _safe_float(ext.get("proxied_occupancy_google"), 3),
                "operational_place_count": _safe_float(ext.get("operational_place_count"), 0),
                "unit_mix_unit_count": _safe_float(ext.get("unit_mix_unit_count"), 0),
                "business_vitality_score": _safe_float(ext.get("business_vitality_score"), 3),
                "proxied_vacancy_duration": _safe_float(ext.get("proxied_vacancy_duration"), 0),
                "business_turnover_count": _safe_float(ext.get("business_turnover_count"), 0),
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
                "class": _safe_str(m.get("trajectory_class")),
                "peak_occupancy": peak_occ,
                "years_since_peak": (
                    _safe_float(m.get("years_since_peak"), 0) if peak_occ else None
                ),
                "occupancy_trend_3yr": _safe_float(m.get("occupancy_trend_3yr"), 4),
                "vacancy_streak_months": _safe_float(m.get("vacancy_streak_months"), 0),
                # B3 fills this for every asset; it only means something
                # when there is an occupancy record behind it.
                "years_below_benchmark": (
                    _safe_float(m.get("years_below_benchmark"), 0)
                    if _safe_float(m.get("occupancy_rate")) is not None else None
                ),
            },
            "deadspace_diagnosis": {
                "status": ds.get("status", "healthy"),
                "intervention_mode": ds.get("intervention_mode"),
                "flags": ds.get("flags", []),
                "urgency_index": _safe_float(ds.get("urgency_index"), 1),
                "contributing_factors": ds.get("contributing_factors", []),
                "evidence": evidence,
                # The B6 record has no authority key; fill it from the register.
                "authority": ds.get("authority") or authority,
                "evaluation_mode": ds.get("evaluation_mode"),
                "flag_tiers": ds.get("flag_tiers", {}),
                # Tier-3a proxy evidence (sold/advisory only)
                "layer3a": (
                    {
                        "proxied_occupancy": _safe_float(ds["layer3a"].get("proxied_occupancy"), 3),
                        "proxied_occupancy_source": ds["layer3a"].get("proxied_occupancy_source"),
                        "triggered": ds["layer3a"].get("triggered"),
                        "reasons": ds["layer3a"].get("reasons", []),
                        "flow_island_threshold": ds["layer3a"].get("flow_island_threshold"),
                    }
                    if ds.get("layer3a") else None
                ),
            },
            "leases": {
                "anchor_lease": anchor_lease
            },
            "subunits": subunits if subunits else None
        }
        profile["tiers"] = _build_tiers(profile, field_meta, authority, ownership, unmapped)
        profiles[aid] = profile

    if unmapped:
        print(f"WARNING: no field_metadata entry for {sorted(unmapped)}; served without a tier")

    out_path = BASE_DIR / f"asset_profiles_{year}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    print(f"Wrote {len(profiles)} full asset profiles to {out_path}")

if __name__ == "__main__":
    build_profiles()
