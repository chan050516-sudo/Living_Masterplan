# Living Masterplan - Backend API Documentation

This document outlines the RESTful APIs provided by the backend for the frontend application. All endpoints are served under the base URL `http://localhost:8000` (or your deployed host).

**Global Features:**
- **CORS**: Fully enabled for all origins.
- **Compression**: Gzip compression is enabled for responses > 1KB (very important for large JSON payloads).
- **JSON Standard**: All requests and responses use `application/json` unless specified otherwise (e.g., file uploads).

**Core Contract:** The API reports data with explicit provenance. Every metric carries a **tier** (`1`, `2`, `3a`, `3b`, `U`) in the `tiers` map of `/api/assets/profiles`, and every simulated value re-tiers itself when read from `/api/map/geometry` for a non-2026 year. See §4 for the tier system.

---

## 1. Run LLM Analysis

**Endpoint:** `POST /api/analyze`
**Content-Type:** `multipart/form-data`
**Purpose:** Submits user queries, selected assets, and optional documents to the LLM pipeline (B7). Returns the full decision reasoning, candidate plans, simulated metrics (B4), and justifications.

### Request Body (Form Data)

| Field | Type | Required | Description |
|---|---|---|---|
| `user_query` | String | Yes | Max 5000 characters. The user's natural language question. |
| `selected_assets` | String | Yes | Comma-separated asset IDs (e.g., `"BLD-0037,BLD-0260"`). Must all exist in `assets.csv`. |
| `files` | File[] | No | Max 3 files, 10 MB each. `.txt`, `.md`, `.csv`, `.json` are read as UTF-8 text (truncated to 10,000 chars). `.pdf` is passed directly to Gemini as multimodal input. |

### Response Schema (200 OK)

```json
{
  "run_id": "LLM-84079015",
  "scenario_id": "SC-LLM-84079015-C1",
  "interventions": [
    {
      "target_asset_id": "BLD-0169",
      "type": "renovation",
      "role": "primary",
      "beneficiary_asset_id": null
    },
    {
      "target_asset_id": "P-VAC-GOLD-01",
      "type": "new_development",
      "role": "catalytic",
      "beneficiary_asset_id": "BLD-0169"
    }
  ],
  "decision": {
    "selected_candidate": "Anchor Community Node & Housing Conversion",
    "reasoning": "Under a balanced objective, rescuing dead capital requires productive occupancy...",
    "key_trade_offs": [
      "Operational carbon rises 15.4% as the asset transitions to full occupancy.",
      "Requires securing an institutional childcare operator before capex deployment."
    ],
    "justification": {
      "summary": "Board-level summary paragraph (≤80 words).",
      "why_this_plan": "Strategic rationale referencing rejected alternatives (≤110 words).",
      "what_simulation_shows": "Concrete numbers across financial / social / environmental (≤120 words).",
      "beyond_the_model": "Domain insight beyond the metrics (optional, may be null).",
      "recommendation": "Under what conditions the user should proceed (≤40 words)."
    }
  },
  "assets_analysis": [
    {
      "asset_id": "BLD-0169",
      "engineering_spec": null,
      "summary_card": {
        "financial": {
          "main_metric": {
            "label": "Annual NOI",
            "baseline": 0.0,
            "intervention": 0.0,
            "unit": "RM"
          },
          "counterfactual": {
            "capex_if_new_build_rm": 16000000.0,
            "capex_if_repurpose_rm": 2381625.0,
            "capex_saved_rm": 13618375.0
          }
        },
        "social": {
          "main_metric": {
            "label": "Space Utilization",
            "baseline": 0.042,
            "intervention": 0.95,
            "unit": "ratio"
          },
          "metrics": {
            "coverage_ratio_15min_walk": { "baseline": 0.324, "intervention": 0.451 },
            "effective_demand_m2": { "baseline": 0.0, "intervention": 3125.9 }
          }
        },
        "environmental": {
          "observed_2026": {
            "surface_temp_delta_c": 2.42,
            "t_asset_c": 41.75,
            "t_township_c": 39.33,
            "label": "2026 observed (Landsat 8 L2)"
          },
          "main_metrics": [
            { "label": "Operational Carbon", "baseline": 327.9, "intervention": 378.4, "unit": "tCO2e/yr" },
            { "label": "Stranded Carbon", "baseline": 327.9, "intervention": 18.9, "unit": "tCO2e/yr" },
            { "label": "Surface Temp ΔT", "baseline": 2.42, "intervention": 1.85, "unit": "°C",
              "cooling_source": "roof", "cooling_from_roof_c": 2.2 },
            { "label": "Perceived Temp (AT)", "baseline": 40.5, "intervention": 39.8, "unit": "°C" }
          ],
          "counterfactual": {
            "embodied_if_new_build_tco2e": 2688.4,
            "embodied_if_repurpose_tco2e": 2623.9,
            "net_carbon_averted_tco2e": 64.5
          }
        },
        "subunits": [
          {
            "subtype": "cafe",
            "area_m2": 325.8,
            "occupancy_baseline": 0.0,
            "occupancy_intervention": 0.85,
            "allocated_carbon_tco2e": 120.0,
            "allocated_noi_rm": 50000.0
          }
        ],
        "authority": "full_control",
        "evaluation_mode": "operating_performance",
        "community": null,
        "counterfactual": null
      },
      "timeline": {
        "years": ["2026", "2027", "2028", "2030", "2033"],
        "metrics": {
          "noi_rm": {
            "baseline":     [0.0, 0.0, 0.0, 0.0, 0.0],
            "intervention": [0.0, -150000.0, 120000.0, 180000.0, 195000.0]
          },
          "carbon_operational_tco2e": {
            "baseline":     [327.9, 328.5, 329.1, 330.2, 331.8],
            "intervention": [327.9, 350.0, 365.0, 372.0, 378.4]
          },
          "surface_temp_delta_c": {
            "baseline":     [2.42, 2.42, 2.42, 2.42, 2.42],
            "intervention": [2.42, 2.42, 2.2, 1.95, 1.85]
          }
        }
      }
    }
  ],
  "township_metrics": {
    "total_carbon_before_tco2e": 130922.25,
    "total_carbon_after_tco2e": 131624.00,
    "carbon_delta_pct": 0.00536,
    "sequestration_by_year_tco2e_year": {
      "2026": 312.4, "2027": 321.8, "2028": 331.5, "2030": 351.2, "2033": 622.4
    },
    "net_carbon_by_year_tco2e_year": {
      "2026": 130609.85, "2027": 130300.00, "2028": 130050.00, "2030": 129800.00, "2033": 131001.60
    }
  },
  "candidates_summary": [
    {
      "name": "Anchor Community Node & Housing Conversion",
      "strategy_summary": "Convert vacant units to residential while adding a childcare anchor on the adjacent parcel.",
      "plan": [
        { "asset_id": "BLD-0169", "type": "renovation" },
        { "asset_id": "P-VAC-GOLD-01", "type": "new_development" }
      ]
    }
  ]
}
```

### Key Response Fields

| Field | Meaning |
|---|---|
| `interventions[].role` | `"primary"` acts on the target asset directly. `"catalytic"` acts on one asset to benefit another (`beneficiary_asset_id`). |
| `engineering_spec` | Optional P1 block (7 physical parameters) that drove the simulation. `null` when the plan used the legacy aggregate-efficiency path. |
| `summary_card.authority` | `full_control` → operating figures are SDP records. `shared` / `advisory` → operating figures are tier-3a proxies or tier-3b counterfactuals. |
| `summary_card.community` | Present only for `advisory` assets. Contains LBS footfall, business presence, and flow-island signal (all tier 3a). |
| `summary_card.counterfactual` | Present only for `advisory` assets. "If SDP had retained this asset" — tier 3b. |
| `timeline.metrics` | Before/after arrays for each metric, aligned to `timeline.years`. `null` values mean the metric is not measured or not visible under the asset's authority. |

### Error Codes

| Status | Condition |
|---|---|
| 400 | Invalid `selected_assets` (unknown ID, empty), > 3 files, file > 10 MB |
| 422 | Pydantic validation error (e.g., `user_query` > 5000 chars) |
| 500 | Pipeline failed (`orchestrate_and_simulate_batch` returned `error` or raised) |

---

## 2. Get All Asset Profiles (Data Dictionary)

**Endpoint:** `GET /api/assets/profiles`
**Purpose:** Returns the 2026 baseline profile of every asset, keyed by `asset_id`. Frontend fetches once on load and caches for O(1) lookup on map clicks.

### Response Schema (200 OK)

```json
{
  "BLD-0037": {
    "identity": {
      "asset_id": "BLD-0037",
      "asset_name": "Mixed-Use Hub BLD-0037",
      "asset_type": "commercial",
      "subtype": "supermarket",
      "land_use": "commercial",
      "status": "existing",
      "completion_year": 2003
    },
    "physical": {
      "floor_area_m2": 8200.0,
      "lettable_area_m2": 6970.0,
      "land_area_m2": 4100.0,
      "capacity": 464,
      "unit_count": 1,
      "developer_held_units": 0,
      "developable_area_m2": null,
      "potential_gfa_m2": null
    },
    "authority": {
      "level": "full_control",
      "ownership_status": "developer_held",
      "data_confidence": "high"
    },
    "financial": {
      "capex_initial_rm": 28700000.0,
      "opex_annual_rm": 2296000.0,
      "maintenance_annual_rm": 717500.0,
      "maintenance_surge_rm": 889736.5,
      "rental_income_rm": 1584512.0,
      "noi_rm": -2011729.78,
      "noi_yield": -0.0701,
      "dsr": 0.354,
      "sale_price_rm": null,
      "sale_date": null,
      "sale_data_source": null,
      "sale_profit_rm": null,
      "sale_return_ratio": null,
      "estimated_revenue_rm": null,
      "survival_opex_floor_rm": null,
      "hemorrhage_ratio": null,
      "cost_per_user_rm": null,
      "demand_supply_gap": null,
      "infrastructure_cost_rm": null
    },
    "social": {
      "occupancy_rate": 0.11,
      "utilisation_rate": null,
      "footfall_daily": 187,
      "vacancy_duration_months": 24,
      "occupied_units": null,
      "service_coverage": null,
      "coverage_ratio_5min_walk": 0.168,
      "coverage_ratio_10min_walk": 0.352,
      "coverage_ratio_15min_walk": 0.446,
      "coverage_ratio_10min_drive": 0.681,
      "median_walk_distance_m": 845,
      "reachable_population_walk": 23499,
      "effective_demand_m2": 1279.2,
      "demographic_mismatch": 0.12,
      "neighborhood_diversity": 0.65,
      "proxied_occupancy": null,
      "proxied_occupancy_source": null,
      "consumer_facing_unit_count": null,
      "capacity_users": null,
      "lbs_unique_users_daily": null,
      "lbs_dwell_minutes": null,
      "lbs_visit_frequency_monthly": null,
      "external_demand_ratio": null,
      "proxied_occupancy_lbs": null,
      "flow_island_ratio": null,
      "traffic_exposure_vpd": null,
      "business_presence_ratio": null,
      "proxied_occupancy_google": null,
      "operational_place_count": null,
      "unit_mix_unit_count": null,
      "business_vitality_score": null,
      "proxied_vacancy_duration": null,
      "business_turnover_count": null
    },
    "environmental": {
      "carbon_operational_tco2e": 865.39,
      "carbon_productive_tco2e": 93.46,
      "carbon_stranded_tco2e": 771.93,
      "stranded_carbon_ratio": 0.892,
      "embodied_carbon_tco2e": 3612.0,
      "energy_kwh_total": 1125356.0,
      "energy_kwh_hvac": 675214.0,
      "energy_kwh_lighting": 281339.0,
      "energy_kwh_base_load": 168803.0,
      "t_asset_c": 41.75,
      "t_township_c": 39.33,
      "surface_temp_delta_c": 2.42,
      "apparent_temp_c": 40.5,
      "surface_temp_provenance": "Observed (Landsat 8 L2)",
      "surface_temp_collection_id": "LANDSAT/LC08/C02/T1_L2",
      "surface_temp_band": "ST_B10",
      "surface_temp_source_catalog": "Google Earth Engine",
      "surface_temp_valid_pixel_count": 47,
      "surface_temp_period_start": "2025-01-01",
      "surface_temp_period_end": "2026-01-01",
      "surface_temp_source_image_count": 12,
      "green_coverage": null,
      "canopy_coverage": 0.18,
      "green_per_capita_m2": null
    },
    "trajectory": {
      "class": "rapid_decline",
      "peak_occupancy": 0.86,
      "years_since_peak": 1,
      "occupancy_trend_3yr": -0.34,
      "vacancy_streak_months": 24,
      "years_below_benchmark": 2
    },
    "deadspace_diagnosis": {
      "status": "deadspace_candidate",
      "intervention_mode": "direct",
      "flags": ["low_occupancy", "negative_noi", "high_stranded_carbon", "rapid_decline"],
      "urgency_index": 9.0,
      "contributing_factors": [
        { "factor": "negative_noi", "contribution": 0.30 },
        { "factor": "rapid_decline", "contribution": 0.20 },
        { "factor": "low_occupancy", "contribution": 0.20 },
        { "factor": "high_stranded_carbon", "contribution": 0.20 },
        { "factor": "below_benchmark_occupancy", "contribution": 0.10 }
      ],
      "evidence": [
        "Subtype: supermarket",
        "Operational carbon: 865.4 tCO2e/yr",
        "Stranded carbon (unused capacity): 771.9 tCO2e/yr (89.2%)",
        "Trajectory: rapid decline (from 86.0% peak, 1 yr ago)",
        "Observed land surface temperature (Observed (Landsat 8 L2)): parcel 41.8 °C; township baseline 39.3 °C; T = Tasset − Ttownship = +2.4 °C"
      ],
      "authority": "full_control",
      "evaluation_mode": "operating_performance",
      "flag_tiers": {
        "low_occupancy": "tier_1_observed",
        "negative_noi": "tier_1_observed",
        "high_stranded_carbon": "tier_2_derived",
        "rapid_decline": "tier_1_observed",
        "below_benchmark_occupancy": "tier_1_observed"
      },
      "layer3a": null
    },
    "leases": {
      "anchor_lease": {
        "end_year": 2031,
        "floor_area_m2": 1226.3
      }
    },
    "subunits": [
      {
        "subtype": "supermarket", "area_m2": 1951.6, "design_count": 1,
        "occupancy": 0.84, "operational_count": null, "presence_ratio": null,
        "vitality_score": null, "allocated_carbon_tco2e": 242.3, "allocated_noi_rm": -563281.0
      },
      {
        "subtype": "kopitiam", "area_m2": 817.6, "design_count": 5,
        "occupancy": 0.11, "operational_count": null, "presence_ratio": null,
        "vitality_score": null, "allocated_carbon_tco2e": 101.4, "allocated_noi_rm": -235562.0
      }
    ],
    "tiers": {
      "identity.completion_year":       { "tier": "1",  "source": "asset_register" },
      "physical.floor_area_m2":         { "tier": "1",  "source": "asset_register" },
      "financial.capex_initial_rm":     { "tier": "1",  "source": "capital_record" },
      "financial.noi_rm":               { "tier": "2",  "source": "derived" },
      "social.occupancy_rate":          { "tier": "1",  "source": "internal_occupancy_record", "mock": true },
      "social.coverage_ratio_10min_walk": { "tier": "2", "source": "derived" },
      "environmental.surface_temp_delta_c": { "tier": "1", "source": "observed" },
      "environmental.carbon_operational_tco2e": { "tier": "2", "source": "derived" },
      "trajectory.class":               { "tier": "2",  "source": "derived_from_occupancy_history" }
    }
  }
}
```

### Surface Temperature Provenance

`t_asset_c` and `t_township_c` are populated from `LANDSAT/LC08/C02/T1_L2` `ST_B10` when `backend/scripts/landsat_lst_pipeline.py` has produced the configured observations file. The API labels valid values `Observed (Landsat 8 L2)` and defines `surface_temp_delta_c = t_asset_c - t_township_c`. Missing clear pixels remain `null` — no proxy fallback is used.

### Authority-Gated Fields

For assets with `authority.level != "full_control"` (sold / public-transferred), the following fields are `null`:

- Commercial: `occupancy_rate`, `vacancy_rate`, `vacancy_duration_months`, `footfall_daily`, `rental_income_rm`, `noi_rm`, `noi_yield`, `energy_kwh`
- Residential: `rental_income_rm`, `noi_rm`, `noi_yield`
- Community facility: `rental_income_rm`, `opex_annual_rm`, `maintenance_annual_rm`, `cost_per_user_rm`

In their place, tier-3a proxy fields are populated: `proxied_occupancy`, `lbs_unique_users_daily`, `flow_island_ratio`, `business_presence_ratio`, `business_vitality_score`, `proxied_vacancy_duration`, `business_turnover_count`, `estimated_revenue_rm`, `survival_opex_floor_rm`, `hemorrhage_ratio`.

**The `tiers` map is the authoritative source** for how to display each field. A field with tier `3a` must be presented as an estimate, never as an observed fact.

---

## 3. Get Map Geometry (For MapLibre)

**Endpoint:** `GET /api/map/geometry`
**Purpose:** Returns a lightweight GeoJSON FeatureCollection combining buildings, undeveloped parcels, and green/blue spaces for rendering on MapLibre GL JS.

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `run_id` | String | No | If provided, overlays the LLM intervention status (`map_status = "intervened"`) on the assets touched by that run. |
| `year` | Integer | No | Target year (default `2026`). For non-2026 years, per-asset metrics come from that year's B4 scenario output. Falls back to 2026 if no scenario exists. |

### Response Schema (200 OK) - GeoJSON FeatureCollection

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[[101.528, 3.109], [101.529, 3.109], [101.529, 3.110], [101.528, 3.109]]] },
      "properties": {
        "asset_id": "BLD-0037",
        "map_status": "deadspace_candidate",
        "flags": ["low_occupancy", "negative_noi", "high_stranded_carbon", "rapid_decline"],
        "urgency_index": 9.0,
        "intervention_mode": "direct",
        "metrics_json": "{\"occupancy_rate\":0.11,\"noi_rm\":-2011729.78,\"coverage_ratio_10min_walk\":0.352}",
        "evidence_json": "[\"Subtype: supermarket\",\"...\"]",
        "factors_json": "[{\"factor\":\"negative_noi\",\"contribution\":0.30},...]",
        "diagnosis_year": 2026,
        "height": 28.0
      }
    }
  ]
}
```

### `map_status` Enum Values (For Styling)

| Status | Meaning | Suggested UI Colour |
|---|---|---|
| `healthy` | Asset is performing well. | Green (`#3FB27F`) |
| `monitor` | Weak or conflicting signals. Light, reversible action only. | Amber (`#F7931D`) |
| `improvement_opportunity` | A green space that could do more. | Amber (`#F7931D`) |
| `development_risk` | Undeveloped parcel at risk. | Orange (`#F15C22`) |
| `deadspace_candidate` | Capital idle. Act now. | Red (`#D71920`) |
| `underperforming_facility` | Public facility under-used. | Red (`#D71920`) |
| `community_value_gap` | Sold asset that is struggling **and** hard to reach. | Red (`#D71920`) |
| `strategic_learning` | Sold asset struggling despite being reachable. | Orange (`#F15C22`) |
| `intervened` | Part of the selected LLM plan (only when `run_id` is provided). | Cyan (`#2196F3`) |
| `vacant` | Undeveloped empty parcel. | Grey (`#9E9E9E`) |

### Frontend Interaction Guide

1. **Cache Profiles**: On load, call `GET /api/assets/profiles` and store as `assetProfiles`.
2. **Render Map**: Call `GET /api/map/geometry` and feed the response into `map.addSource(...)`.
3. **Click Event**:
   ```javascript
   map.on('click', 'assets-layer', (e) => {
       const aid = e.features[0].properties.asset_id;
       const profile = assetProfiles[aid];
       if (profile) showModal(profile);
   });
   ```
4. **Year switch**: `GET /api/map/geometry?year=2033` returns 2033 map_status and per-asset `metrics_json`. The frontend overlays these onto the 2026 profile **with re-tiering** (see §4).
5. **Intervention preview**: `GET /api/map/geometry?run_id=LLM-84079015` marks the plan's target assets `intervened`.

---

## 4. Data Tier System

Every metric carries a tier that describes **how much to trust it**. The frontend renders each tier as a badge (`T1`, `T2`, `3A`, `3B`, `U`) and re-tiers simulated values by their source.

| Tier | Label | Meaning |
|---|---|---|
| `1` | Observed | Direct SDP record or satellite observation. Only valid for `full_control` assets. |
| `2` | Derived | Physics or economic formula on observed data (Huff demand, walkability, operational carbon). |
| `3a` | Operational estimate | External proxy (Google Places, LBS, survival OPEX floor). Valid for deadspace judgement, never stated as fact. |
| `3b` | Counterfactual | Simulation-only ("if SDP had retained this asset"). Never enters deadspace detection. |
| `U` | Unknown | No defensible source for this asset. Frontend renders "Unknown", not a number. |

### Tier Precedence

A field's tier is the **most severe** applicable rule:

1. If the field is null → no tier entry.
2. If the asset's authority gates the field → the tier comes from `field_metadata.yml`'s `authority_tiers[ownership_status]` (e.g., `noi_rm` becomes `3b` for sold assets).
3. Otherwise → the field's base tier.

### Simulated-Year Re-tiering (frontend `applyYearMetrics`)

For a non-2026 year, values read from `metrics_json` replace the profile value and are re-tiered:

| Authority | Tier of simulated value |
|---|---|
| `full_control` (owned) | `2` "simulated {year}" |
| `shared` / `advisory` + has LBS proxy | `3a` "estimated {year}" |
| `shared` / `advisory` + no proxy | `U` "assumed {year}" |

---

## 5. Demo vs. Live Routing (frontend)

The frontend (`frontend/src/api.ts`) routes `/api/analyze` calls by asset selection:

```typescript
routeAnalysis(selectedAssets, userQuery, files)
  // → { kind: 'mock', scenario: 'case1' | 'case2' }  if every asset is in a frozen demo set
  // → { kind: 'live' }                               otherwise
```

**Frozen demo sets** (return instantly from local TypeScript):

| Scenario | Assets | Typical query |
|---|---|---|
| `case1` | `BLD-0037`, `BLD-0260`, `BLD-0004` | "stop the financial bleeding", "PDF feasibility", "budget" |
| `case2` | `BLD-0736`, `BLD-0734`, `BLD-0067` | "tenant matching", "kopitiam", "flow island" |

**Everything else goes to `POST /api/analyze`** — a live Gemini call that takes **1-3 minutes** (2-3 for multi-asset, up to 5 if Vertex retries).

Cross-asset selections (mixing `BLD-0037` with `BLD-0736`), non-demo assets, and case1 assets combined with a case2 query hint all route to **live**.