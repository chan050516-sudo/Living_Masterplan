# Living Masterplan - Backend API Documentation

This document outlines the RESTful APIs provided by the backend for the frontend application. All endpoints are served under the base URL `http://localhost:8000` (or your deployed host).

**Global Features:**
- **CORS**: Fully enabled for all origins.
- **Compression**: Gzip compression is enabled for responses > 1KB (very important for large JSON payloads).
- **JSON Standard**: All requests and responses use `application/json` unless specified otherwise (e.g., file uploads).

---

## 1. Run LLM Analysis
**Endpoint:** `POST /api/analyze`
**Content-Type:** `multipart/form-data`
**Purpose:** Submits user queries, selected assets, and optional documents to the LLM pipeline (B7). Returns the full decision reasoning, candidate plans, simulated metrics (B4), and justifications.

### Request Body (Form Data)
| Field | Type | Required | Description |
|---|---|---|---|
| `user_query` | String | Yes | Max 5000 characters. The user's natural language question. |
| `selected_assets` | String | Yes | Comma-separated asset IDs (e.g., `"BLD-0183,BLD-0151"`). |
| `files` | File[] | No | Max 3 files, 10MB each. Supports `.txt`, `.csv`, `.pdf` (PDFs are sent directly to Gemini multimodal). |

### Response Schema (200 OK)
```json
{
  "run_id": "LLM-da8ac14f",
  "scenario_id": "SC-LLM-da8ac14f-C1",
  "decision": {
    "selected_candidate": "Catalytic Family Anchor & Commercial Efficiency",
    "reasoning": "Selected as the sole viable intervention...",
    "key_trade_offs": [
      "Accepts a 1.86% township carbon increase to activate underutilized land."
    ],
    "justification": {
      "summary": "We propose a balanced dual intervention...",
      "why_this_plan": "Standalone retrofitting would leave the catchment unaddressed...",
      "what_simulation_shows": "Effective commercial demand expands from 3125.9 m² to 3825.3 m²...",
      "beyond_the_model": "Childcare facilities generate non-discretionary twice-daily footfall...",
      "recommendation": "Proceed subject to securing an accredited childcare operator."
    }
  },
  "assets_analysis": [
    {
      "asset_id": "BLD-0183",
      "summary_card": {
        "financial": {
          "main_metric": { "label": "Annual NOI", "baseline": -2669929.55, "intervention": -2269450.75, "unit": "RM" },
          "counterfactual": { "capex_if_new_build_rm": 6500000, "capex_if_repurpose_rm": 2150280, "capex_saved_rm": 4349720 }
        },
        "social": {
          "main_metric": { "label": "Space Utilization", "baseline": 0.632, "intervention": 0.632, "unit": "ratio" },
          "metrics": {
            "coverage_ratio_15min_walk": { "baseline": 0.65, "intervention": 0.72 },
            "effective_demand_m2": { "baseline": 3125.9, "intervention": 3825.3 }
          }
        },
        "environmental": {
          "main_metrics": [
            { "label": "Operational Carbon", "baseline": 1660.45, "intervention": 1360.54, "unit": "tCO2e/yr" },
            { "label": "Stranded Carbon", "baseline": 249.06, "intervention": 501.1, "unit": "tCO2e/yr" }
          ],
          "counterfactual": { "embodied_if_new_build_tco2e": 2150.5, "embodied_if_repurpose_tco2e": 220.5, "net_carbon_averted_tco2e": 1930.0 }
        },
        "subunits": [
          { "subtype": "f_and_b", "area_m2": 400, "occupancy_baseline": 0.05, "occupancy_intervention": 0.85, "allocated_carbon_tco2e": 150.2, "allocated_noi_rm": -250000 }
        ]
      },
      "timeline": {
        "years": ["2026", "2027", "2028", "2030", "2033"],
        "metrics": {
          "noi_rm": { "baseline": [ -2669929, -2700000, -2800000, -2600000, -2669929 ], "intervention": [ -2669929, -2500000, -2200000, -2100000, -2269450 ] }
        }
      }
    }
  ],
  "township_metrics": {
    "total_carbon_before_tco2e": 130922.25,
    "total_carbon_after_tco2e": 133355.00,
    "carbon_delta_pct": 0.0186
  }
}
```

---

## 2. Get All Asset Profiles (Data Dictionary)
**Endpoint:** `GET /api/assets/profiles`
**Purpose:** Retrieves a dictionary of all assets containing their comprehensive 2026 baseline metrics. Frontend MUST call this once on page load and cache it in memory (e.g., Redux, Vuex, or a global JS object) for O(1) lookups when a user clicks on the map.

### Response Schema (200 OK)
```json
{
  "BLD-0183": {
    "identity": {
      "asset_id": "BLD-0183",
      "asset_name": "Medical Retail 83",
      "asset_type": "commercial",
      "subtype": "medical_retail",
      "land_use": "commercial",
      "status": "existing",
      "completion_year": 2018
    },
    "physical": {
      "floor_area_m2": 5200.0,
      "lettable_area_m2": 4420.0,
      "land_area_m2": 2600.0,
      "capacity": 346
    },
    "authority": {
      "level": "full_control",
      "ownership_status": "developer_held"
    },
    "financial": {
      "capex_initial_rm": 18200000.0,
      "opex_annual_rm": 1456000.0,
      "maintenance_annual_rm": 455000.0,
      "rental_income_rm": 1500000.0,
      "noi_rm": -2387248.0,
      "noi_yield": -0.1311,
      "dsr": 0.45
    },
    "social": {
      "occupancy_rate": 0.85,
      "utilisation_rate": null,
      "footfall_daily": 450,
      "coverage_ratio_5min_walk": 0.04,
      "coverage_ratio_10min_walk": 0.16,
      "coverage_ratio_15min_walk": 0.65,
      "reachable_population_walk": 26376,
      "effective_demand_m2": 3125.9,
      "demographic_mismatch": 0.12,
      "neighborhood_diversity": 0.65
    },
    "environmental": {
      "carbon_operational_tco2e": 1660.45,
      "carbon_productive_tco2e": 1411.38,
      "carbon_stranded_tco2e": 249.06,
      "stranded_carbon_ratio": 0.15,
      "embodied_carbon_tco2e": 1976.0,
      "energy_kwh_total": 2159100.0,
      "energy_kwh_hvac": 1295460.0,
      "energy_kwh_lighting": 539775.0,
      "energy_kwh_base_load": 323865.0,
      "surface_temp_delta_c": 6.8
    },
    "trajectory": {
      "class": "declining",
      "peak_occupancy": 0.82,
      "years_since_peak": 2,
      "occupancy_trend_3yr": -0.08,
      "vacancy_streak_months": 14
    },
    "deadspace_diagnosis": {
      "status": "deadspace_candidate",
      "flags": ["negative_noi", "high_stranded_carbon"],
      "urgency_index": 5.0,
      "contributing_factors": [
        { "factor": "negative_noi", "contribution": 0.6 },
        { "factor": "high_stranded_carbon", "contribution": 0.4 }
      ],
      "evidence": [
        "Subtype: medical_retail",
        "Operational carbon: 1,660 tCO2e/yr",
        "Stranded carbon (unused capacity): 249.1 tCO2e/yr (15.0%)",
        "Trajectory: declining (peak 82.0% 2 yrs ago)"
      ]
    },
    "leases": {
      "anchor_lease": {
        "end_year": 2031,
        "floor_area_m2": 1226.3
      }
    },
    "subunits": null
  }
}
```

---

## 3. Get Map Geometry (For MapLibre)
**Endpoint:** `GET /api/map/geometry`
**Purpose:** Retrieves a lightweight GeoJSON FeatureCollection combining Buildings, Amenities, Undeveloped Parcels, and Green/Blue Spaces for rendering on MapLibre GL JS.

### Query Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `run_id` | String | No | If provided, overlays the LLM intervention status. |

### Response Schema (200 OK) - GeoJSON FeatureCollection
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[101.528, 3.109], [101.529, 3.109], [101.529, 3.110], [101.528, 3.109]]]
      },
      "properties": {
        "asset_id": "BLD-0183",
        "map_status": "intervened",
        "height_m": 14.0
      }
    }
  ]
}
```

### `map_status` Enum Values (For Styling)
| Status | Meaning | Suggested UI Color |
|---|---|---|
| `healthy` | Asset is performing well. | Green (`#4CAF50`) |
| `deadspace_candidate` | High urgency, failing asset. | Red/Orange (`#FF5722`) |
| `intervened` | Asset is part of the selected LLM plan. | Blue (`#2196F3`) |
| `vacant` | Undeveloped empty parcel. | Grey (`#9E9E9E`) |
| `improvement_opportunity` | Usually Green spaces needing care. | Pink/Magenta (`#E91E63`) |
| `underperforming_facility` | Community facility below its benchmark. | Orange (`#FF9800`) |
| `development_risk` | Pipeline / parcel at risk. | Purple (`#AB47BC`) |
| `monitor` | Underperforming but not actionable (e.g. third-party owned). | Amber (`#ECAA00`) |

Other feature properties:
- `asset_id` matches the keys of `GET /api/assets/profiles`. It is `null` for buildings that are not tracked assets.
- `height_m` is an approximate building height (floors × 3.5 m) for 3D extrusion; `null` for non-buildings.
- Geometry is mostly `Polygon`/`MultiPolygon`; some amenities are `Point` and some blue features are `LineString`.

### Frontend Interaction Guide
1. **Cache Profiles**: On load, call `GET /api/assets/profiles` and store as `assetProfiles`.
2. **Render Map**: Call `GET /api/map/geometry` and feed the response directly into `map.addSource(...)`.
3. **Click Event**: 
   ```javascript
   map.on('click', 'assets-layer', (e) => {
       const aid = e.features[0].properties.asset_id;
       const profile = assetProfiles[aid];
       if (profile) showModal(profile);
   });
   ```
4. **Intervention Toggle**: 
   When the user clicks "View LLM Plan", use the returned `run_id` to update the map source:
   ```javascript
   const res = await fetch(`/api/map/geometry?run_id=${runId}`);
   map.getSource('township').setData(await res.json());
   ```
```