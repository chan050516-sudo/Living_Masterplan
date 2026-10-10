# Living Masterplan — Schema Documentation

**Version:** 0.2.0
**Status:** Frozen for Phase 0 (aligned with Technical Design v1.1)
**Owner:** Module B (Data, Math Model & Simulation)
**Consumers:** Module A, Module B, Module C, Module D
**Format:** JSON Schema Draft 2020-12
**Storage CRS:** EPSG:4326
**Analysis CRS:** EPSG:32647
**Time Convention:** year = integer (2026, 2028, 2030, 2033)
**Rate Convention:** 0–1 decimal (0.21 = 21%)
**Score Convention:** 0–100 integer

---

## 1. Design Principles (v1.1)

1. **Asset is the atomic unit.** Not Parcel, not Building.
2. **Geometry and business data are separated.**
   - Geometry lives in GeoJSON files (`parcels.geojson`, `buildings.geojson`, etc.)
   - Business data lives in CSV tables (`assets.csv`, `asset_metrics.csv`, etc.)
   - Joined by stable `asset_id`.
3. **Time dimension is stored independently** in `asset_metrics.csv`.
   One row per `(asset_id, year)`. B4 appends rows.
4. **Spatial identity does NOT change during simulation.** B-03 stays B-03
   after repurpose. Only its metrics change.
5. **Field-level Tier / Source / Unit live in `field_metadata.yml`.**
   CSV cells are plain numbers. The config maps field → tier/source/unit.
   This keeps CSV calculation-friendly while preserving Tier provenance.

---

## 2. ID Naming Convention

| Prefix | Entity                | Example       |
|--------|-----------------------|---------------|
| P-     | Parcel                | P-B03         |
| BLD-   | Building              | BLD-B03       |
| E-     | Network Edge          | E-R17         |
| N-     | Network Node          | N-12          |
| G-     | Green / Blue          | G-01          |
| A-     | Amenity               | A-T01         |
| R-     | Residential           | R-01          |
| F-     | Facility              | F-02          |
| B-     | Commercial Asset      | B-03          |
| SC-    | Scenario              | SC-REPURPOSE  |
| INT-   | Intervention          | INT-001       |
| PRJ-   | Development Project   | PRJ-P3        |
| CAND-  | Development Candidate | CAND-P05-01   |

---

## 3. Unit Conventions

| Quantity | Unit    |
|----------|---------|
| Area     | m2      |
| Distance | m       |
| Currency | RM      |
| Carbon   | tCO2e   |
| Energy   | kWh     |
| Time     | year / months |
| Ratio    | 0–1     |
| Score    | 0–100   |

---

## 4. Geometry Layer (GeoJSON)

All geometry files share `metadata` and use `EPSG:4326` storage.

| File                  | Feature ID | Geometry                | Required Properties |
|-----------------------|-----------|-------------------------|---------------------|
| `parcels.geojson`     | `parcel_id` | Polygon / MultiPolygon | `asset_id`, `land_use`, `area_m2`, `geometry_source`, `geometry_confidence` |
| `buildings.geojson`   | `building_id` | Polygon / MultiPolygon | `parcel_id`, `asset_id`, `building_type`, `geometry_source` |
| `network.geojson`     | `edge_id` | LineString / MultiLineString | `edge_type`, `from_node`, `to_node`, `length_m`, `access_type` |
| `green_blue.geojson`  | `green_id` | Polygon / MultiPolygon / LineString | `asset_id`, `green_type`, `area_m2`, `geometry_source` |
| `amenities.geojson`   | `amenity_id` | Point / Polygon | `amenity_type` |

Rule: **no business data lives in GeoJSON.** Only geometry + join keys + basic classification.

---

## 5. Business Layer (CSV)

| File                          | Grain                       | Producer | Consumer |
|-------------------------------|-----------------------------|----------|----------|
| `assets.csv`                  | one row per asset           | A + B1   | B3, B4, B5 |
| `asset_metrics.csv`           | one row per (asset_id, year)| B3, B4, B5 | B5, B6, D |
| `development_projects.csv`    | one row per project         | B1       | B4       |
| `development_candidates.csv`  | one row per candidate       | B1       | C, B4    |
| `interventions.csv`           | one row per intervention    | C        | B4       |

Rule: **B3 writes derived columns to `asset_metrics.csv`. B4 appends new rows per year. B5 fills score columns. B6 reads scores and outputs to `deadspace.schema.json`.**

---

## 6. Field Metadata (Tier / Source / Unit)

Every field in every table is mapped in `backend/configs/field_metadata.yml`:

```yaml
asset_metrics:
  occupancy_rate:
    tier: 1
    source: observed
    unit: ratio
  accessibility_score:
    tier: 2
    source: derived
    unit: 0-100
  effective_demand:
    tier: 3
    source: assumed
    unit: count
```

This is the single source of truth for:
- UI Tier labels (🔵🟡🔴)
- Missing-value validation
- Unit consistency checks
- Q&A defensibility

---

## 7. Schema Versioning

- `schema_version: "0.2.0"` aligned with Technical Design v1.1.
- Breaking changes bump MAJOR.
- Additive fields bump MINOR.
- Every schema change MUST update SCHEMA.md and field_metadata.yml.

---

## 8. Output Schemas

### asset_score.schema.json
- Produced by B5.
- One JSON object per asset per year.
- Contains: overall, financial, environmental, social, risk scores
  + weights_used + component_scores + model_version.

### deadspace.schema.json
- Produced by B6.
- Three-layer detection with explicit reasons.
- `contributing_factors[].contribution` sums to 1.0.
- `layer3.candidate_interventions` is for Module C only; UI must NOT display.

### scenario_result.schema.json
- Produced by B4.
- Multi-year `years` map. Each year contains `assets` and `scores`.
- `comparison` block for the Scenario Comparison screen.
- `map_diff` block for map color rendering (blue / purple / black).

---

## 9. Change Log

| Version | Date       | Change |
|---------|------------|--------|
| 0.2.0   | 2026-10-10 | Redesigned to v1.1 Model Schema (Part 3.5) |
| 0.1.0   | 2026-10-09 | Initial envelope-based schemas |

---


## 10. v0.3.0 Changes (2026-10-10)

Three schema additions, all justified by algorithm layer upgrades:

| Change | File | Reason |
|--------|------|--------|
| Add `canopy_coverage_ratio` | `network.schema.json` | Canopy-adjusted walkability. Enables Planet narrative: shaded corridors reduce perceived walking impedance. |
| Add `population.schema.json` | new | Demographic-weighted demand. Used by Huff gravity model and affinity mismatch detection. |
| Add `footfall_conversion_rm_per_person` | `asset_metrics.schema.json` | Detects "traffic without value" — high footfall but low revenue = Layer 2 Low Value Realisation. |
| Add `maintenance_surge_rm` | `asset_metrics.schema.json` | Aging escalation. Old assets with rising maintenance → retrofit/repurpose trigger. |

Deferred to v0.4.0:
- `tenants.csv` (tenant diversity index)
- `pedestrian_flow` fields (congestion analysis)
- `environmental_observations.csv` (rainfall, flood risk, solar exposure)

### 10.1 Canopy-Adjusted Walkability

The `canopy_coverage_ratio` field on each network edge modifies the *effective* walking distance:
d_effective = length_m * (1 - gamma * canopy_coverage_ratio)

text

Default `gamma = 0.3`. This means a fully shaded edge is perceived as 30% shorter than an unshaded edge of the same physical length.

### 10.2 Huff Gravity Model

Population clusters from `population.geojson` are the demand nodes. Commercial assets from `assets.csv` are the supply nodes. Attractiveness `S_i = lettable_area_m2`.

For each demand node `j` and each supply node `i`:
P(i|j) = (S_i^alpha / d_ij^beta) / sum_k (S_k^alpha / d_kj^beta)
effective_demand_i = sum_j (P(i|j) * population_j)

text

Defaults: `alpha = 1.0`, `beta = 2.0`.

### 10.3 Population-Based Demand

`population.geojson` replaces the flat `capacity` proxy. Each cluster has age bands and household size. B3 uses:

- Total population → Huff gravity demand weight
- Age distribution → affinity mismatch (Phase 2)
- Median income → affordable rent capacity (Phase 2)

```