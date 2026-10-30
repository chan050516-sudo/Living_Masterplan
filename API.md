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
| `selected_assets` | String | Yes | Comma-separated asset IDs (e.g., `"BLD-0183,BLD-0151"`). Max 3 files allowed. |
| `files` | File[] | No | Max 3 files, 10MB each. Supports `.txt`, `.csv`, `.pdf` (PDFs are sent directly to Gemini multimodal). |

### Response Schema (200 OK)
```json
{
  "run_id": "LLM-da8ac14f",
  "scenario_id": "SC-LLM-da8ac14f-C1",
  "interventions": [
    {
      "target_asset_id": "BLD-0183",
      "type": "repurpose",
      "role": "catalytic",
      "beneficiary_asset_id": "BLD-0151"
    }
  ],
  "decision": {
    "selected_candidate": "Catalytic Family Anchor & Commercial Efficiency",
    "reasoning": "Selected as the sole viable intervention..."
  },
  "assets_analysis": [
    {
      "asset_id": "BLD-0183",
      "summary_card": { ... }
    }
  ],
  "township_metrics": {
    "total_carbon_before_tco2e": 130922.25,
    "total_carbon_after_tco2e": 133355.00,
    "carbon_delta_pct": 0.0186
  },
  "candidates_summary": [
    {
      "name": "Catalytic Family Anchor & Commercial Efficiency",
      "strategy_summary": "Repurpose the dead F&B floor to childcare to drive footfall.",
      "plan": [
        {
          "asset_id": "BLD-0183",
          "type": "repurpose"
        }
      ]
    }
  ]
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
      "t_asset_c": null,
      "t_township_c": null,
      "surface_temp_delta_c": null,
      "surface_temp_provenance": null,
      "surface_temp_collection_id": null,
      "surface_temp_band": null,
      "surface_temp_source_catalog": null,
      "surface_temp_valid_pixel_count": null,
      "surface_temp_period_start": null,
      "surface_temp_period_end": null,
      "surface_temp_source_image_count": null
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

Surface-temperature fields are populated from `LANDSAT/LC08/C02/T1_L2` when
`backend/scripts/landsat_lst_pipeline.py` has produced the configured thermal
observations file. The API labels valid values `Observed (Landsat 8 L2)` and
defines `surface_temp_delta_c = t_asset_c - t_township_c`. Missing clear pixels
remain `null`; the previous canopy-based temperature proxy is not used as a
fallback.

---

## 3. Get Map Geometry (For MapLibre)
**Endpoint:** `GET /api/map/geometry`
**Purpose:** Retrieves a lightweight GeoJSON FeatureCollection combining Buildings, Undeveloped Parcels, and Green/Blue Spaces for rendering on MapLibre GL JS.

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
        "map_status": "intervened"
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
