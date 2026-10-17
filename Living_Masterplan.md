# Living Masterplan — Complete Technical Design Document v1.1

> **Version**: v1.1
> **Purpose**: Internal team alignment + development reference
> **Track**: Planet
> **One-line definition**: A time-aware township asset performance decision engine that helps developers identify underperforming assets, simulate alternative strategies, and evaluate future business and environmental value.
> **Core principle**: Tools calculate the world. LLM reasons about the world.
> **Planet anchor**: Circular Economy (reuse, don't rebuild) + Climate Resilience (adaptive planning)

**Changes from v1.0**:
- Added Tool Registry (Part 7.4)
- Added Development Candidate Generation (Part 6.1.1)
- Extended `interventions.csv` with `expected_derived_json`, `activation_year`, `construction_*` fields
- Added Time Series comparison mode (Part 8.6.1)
- Clarified any-asset queryability (Part 8.1, Part 7.2, Part 3.5)
- Added Model Schema section (Part 3.5) consolidating all table definitions
- Added Time Anchors for Intervention Simulation (Part 6.2.1)


# Part 1: Project Positioning

## 1.1 Problem Statement

```
Townships are built on assumptions.
When assumptions change (population, climate, demand), assets become stranded.
Developers don't know:
  - Which assets are wasting resources?
  - Which can be repurposed instead of rebuilt?
  - What happens if we change decisions today?
```

## 1.2 Solution

```
Living Masterplan = A time-aware asset performance decision engine

Three core questions:
  1. Where are we underperforming?  → Deadspace Detection
  2. What should we do?             → Scenario Generation
  3. What happens if we do it?      → Future Performance Simulation
```

## 1.3 Differentiation

| Traditional tools | Living Masterplan |
|-------------------|-------------------|
| Tell developers "where the problem is" | Show developers "what happens if we change decisions today" |
| Static reports | Time slider + continuous update |
| Single financial lens | Business × Environmental × Social scoring |
| Planner perspective | Developer perspective (CAPEX, activation time, stranded risk) |
| Diagnosis only | Diagnosis → Simulation → Comparison → Masterplan update |

## 1.4 Planet Narrative (Must use in pitch opening)

```
PLANET ANCHOR
  ↓ Avoided construction → embodied carbon ↓
  ↓ Reuse existing assets → circularity ↑
  ↓ Adaptive planning → climate resilience ↑

PEOPLE CO-BENEFIT (automatic)
  ↓ Cooler public spaces
  ↓ Better facility access

BUSINESS VALUE (automatic)
  ↓ Lower CAPEX
  ↓ Higher asset utilisation
  ↓ Lower stranded-asset risk
```

**Opening line**:
> "Townships are built on assumptions. When assumptions change, assets become stranded. Living Masterplan identifies where resources are wasted, what can be reused instead of rebuilt, and how to adapt before today's plans become tomorrow's liabilities."

## 1.5 Champion Narrative

```
Problem:   Masterplans are static. Townships are not.
Solution:  We turn the masterplan into a continuously adaptive decision system.
Planet:    Build less unnecessarily. Reuse more. Adapt earlier.
Mechanism: AUDIT → DIAGNOSE → GENERATE → SIMULATE → DECIDE
Enabler:   GIS + Township Data + Decision Engine + AI interface
Result:    A township that adapts before today's planning assumptions 
           become tomorrow's stranded assets.
```


# Part 2: System Architecture

## 2.1 Five-Layer Structure

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1: USER INTERFACE                            │
│  Map + Deadspace List + NL Interface + Comparison   │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 2: LLM (Intent + Reasoning + Explanation)    │
│  - Parse intent                                     │
│  - Generate candidate interventions                 │
│  - Explain results                                  │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 3: TOWNSHIP STATE ENGINE                     │
│  Current State + Derived Metrics + Future State     │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 4: DETERMINISTIC SIMULATION TOOLS            │
│  - Apply intervention                               │
│  - Recalculate performance scores                   │
│  - Update township state                            │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 5: SCENARIO COMPARISON + MASTERPLAN UPDATE   │
└─────────────────────────────────────────────────────┘
```

## 2.2 Complete Data Flow

```
USER (Map click / Natural language / Proposal)
  │
  ▼
LLM Intent Parser
  → Target + Objective + Constraints + Proposed Interventions
  │
  ▼
Township State Engine
  → Current State + Derived Metrics + Future State at Selected Year
  │
  ▼
LLM Reasoning
  → Interpret problem + Generate candidate interventions
  │
  ▼
Intervention Validation
  → Valid asset types + Land-use constraints + Budget + Feasibility
  │
  ▼
Deterministic Simulation Tools
  → Apply intervention + Update state + Recalculate scores
  │
  ▼
Scenario Comparison
  → Current Plan / Option A / Option B / Option C
  │
  ▼
LLM Explanation
  → Compare trade-offs + Explain assumptions + Recommend
  │
  ▼
Map Visualization + User Decision + Masterplan Update
```

## 2.3 Core Architecture Principles

```
❌ LLM must NOT directly modify township data
✅ LLM generates structured intervention proposals
✅ System validates legality + budget + action space
✅ Simulation tools genuinely transform state based on interventions
✅ Performance Score is terminal node — does NOT feed back into Demand or Supply
```


# Part 3: Data Layer

## 3.1 Seven Raw Data Categories (Township Data)

| Category | Fields |
|----------|--------|
| **Spatial** | Parcel, Building, Road, Pedestrian path, Green space, Water, Drainage, Transit, Building height, Land use |
| **Population** | Population, Age distribution, Household size, Income bands, Occupancy, Population growth |
| **Property** | Property type, Unit count, Occupancy, Vacancy, Completion date, Development phase, Price band, Target demographic |
| **Business** | Tenant, Business type, Footfall, Operating hours, Revenue proxy, Capacity, Utilisation, Vacancy |
| **Environment** | Temperature, Surface temperature, Rainfall, Flood risk, Canopy, Solar exposure, Energy, Water, Waste |
| **Mobility** | Road network, Pedestrian network, Transit, Walking distance, Travel time, Parking, Pedestrian flow |
| **External** | Weather, Population trends, Property market, Nearby schools/hospitals/transit, Government planning |

## 3.2 Data Source Layering (Critical!)

```
OBSERVED     → Actual measurement / record (e.g., current occupancy)   → Tier 1
DERIVED      → Computed from existing data (e.g., walkability)         → Tier 2
ASSUMED      → Planning assumption (e.g., demand coefficient 0.45)     → Labeled as assumption
SIMULATED    → What-if scenario result (e.g., post-repurpose utilisation) → Tier 3
```

**Every number must be tagged with its source.** This is the foundation of technical credibility.

## 3.3 Three-Tier Confidence System

| Tier | Type | Examples | UI Label |
|------|------|----------|----------|
| **Tier 1** | Direct Calculation | Occupancy rate, vacancy rate, floor area, land area | Observed |
| **Tier 2** | Derived Estimation | Carbon estimate, service coverage, LCCA, demand proxy | Estimated |
| **Tier 3** | Scenario Projection | Future population, future demand, future occupancy | Scenario |

**All three tiers can appear on the same map and same comparison table, but must NOT be conflated.**

## 3.4 Data Dictionary Example

```
Field               | Tier | Source         | Unit    | Update Frequency
--------------------|------|----------------|---------|------------------
occupancy_rate      | 1    | Property records | %     | Monthly
vacancy_duration    | 1    | Lease history  | months  | Monthly
noi                 | 2    | Rent - OpEx    | RM      | Annual
accessibility_score | 2    | Walk network   | 0-100   | Static
carbon_operational  | 2    | Emission factor| tCO2e   | Annual
population_2030     | 3    | Growth scenario| people  | Scenario
demand_2030         | 3    | Demand model   | units   | Scenario
```

## 3.5 Model Schema (v1.1 Consolidated)

### 3.5.1 Design Principles

```
1. Asset is the atomic unit (not Parcel, not Building)
2. Geometry (GeoJSON) and business data (CSV/JSON) are fully separated
3. Time dimension is stored independently in asset_metrics
4. Spatial identity does NOT change during simulation (B-03 stays B-03)
5. Demo requires 5 core tables + 1 network table
```

### 3.5.2 Spatial Layer (GeoJSON)

**parcels.geojson**
```json
{
  "properties": {
    "parcel_id": "P-B03",
    "asset_id": "B-03",
    "land_use": "commercial",
    "area_m2": 2400,
    "development_phase": 2,
    "geometry_source": "OpenStreetMap",
    "geometry_confidence": "high"
  }
}
```

**buildings.geojson**
```json
{
  "properties": {
    "building_id": "BLD-B03",
    "parcel_id": "P-B03",
    "asset_id": "B-03",
    "building_type": "commercial",
    "floors": 2,
    "gfa_m2": 1800,
    "completion_year": 2027,
    "geometry_source": "Microsoft Building Footprints"
  }
}
```

**network.geojson**
```json
{
  "properties": {
    "edge_id": "E-R17",
    "edge_type": "pedestrian",
    "from_node": "N-12",
    "to_node": "N-15",
    "length_m": 320,
    "walk_speed_kmh": 4.5,
    "access_type": "public"
  }
}
```

**green_blue.geojson**
```json
{
  "properties": {
    "green_id": "G-01",
    "asset_id": "G-01",
    "green_type": "park",
    "area_m2": 5200,
    "canopy_m2": 416,
    "geometry_source": "OpenStreetMap"
  }
}
```

**amenities.geojson**
```json
{
  "properties": {
    "amenity_id": "A-T01",
    "amenity_type": "transit_station",
    "capacity": 500
  }
}
```

### 3.5.3 Business Layer (CSV)

**assets.csv** — Core table

```csv
asset_id, asset_type, parcel_id, building_id, asset_name,
land_use, development_phase, status, completion_year,
target_demographic,
floor_area_m2, lettable_area_m2, land_area_m2,
capex_initial_rm, opex_annual_rm, maintenance_annual_rm,
capacity,
data_completeness, data_sources
```

**All assets are queryable by default. No field restriction on query targets.**

**asset_metrics.csv** — Time series

```csv
asset_id, year,
occupancy_rate, vacancy_rate, vacancy_duration_months,
footfall_daily, utilisation_rate,
rental_income_rm, noi_rm, noi_yield,
accessibility_score, service_coverage,
effective_demand, effective_supply, dsr,
carbon_operational_tco2e, energy_kwh,
green_coverage, canopy_coverage, thermal_exposure,
financial_score, environmental_score, social_score,
performance_score, delta_score,
metric_source, model_version
```

**development_projects.csv**

```csv
project_id, parcel_id, asset_id, project_name,
project_status, planned_start_year, planned_delivery_year,
gfa_m2, units, land_use, capex_rm,
scenario_dependency
```

**development_candidates.csv** (NEW in v1.1)

```csv
candidate_id, parcel_id, development_type,
target_gfa_m2, target_units, target_demographic,
expected_capex_rm, expected_completion_year,
expected_demand_coverage, expected_utilisation,
expected_carbon_tco2e, expected_accessibility_delta,
feasibility_status, constraint_notes
```

Example:
```csv
candidate_id: CAND-P05-01
parcel_id: P-05
development_type: childcare_centre
target_gfa_m2: 1200
target_units: 1
target_demographic: young_families
expected_capex_rm: 1800000
expected_completion_year: 2029
expected_demand_coverage: 0.72
expected_utilisation: 0.78
expected_carbon_tco2e: 145
expected_accessibility_delta: 0.08
feasibility_status: feasible
constraint_notes: "Complies with land use plan"
```

**interventions.csv** (EXTENDED in v1.1)

```csv
scenario_id, intervention_id, target_asset_id, intervention_type,
parameters_json,
expected_derived_json, expected_source,
construction_start_year, construction_duration_months, activation_year,
during_construction_status,
capex_delta_rm, opex_delta_rm,
validation_status, status
```

Example:
```csv
scenario_id: SC-REPURPOSE
intervention_id: INT-001
target_asset_id: B-03
intervention_type: repurpose
parameters_json: {"from": "commercial_shoplot", "to": "community_facility", "new_capacity": 200}
expected_derived_json: {"service_coverage": 0.72, "utilisation": 0.78, "carbon_operational_tco2e": 145, "accessibility_delta": 0.08}
expected_source: "llm_estimate"
construction_start_year: 2027
construction_duration_months: 18
activation_year: 2028
during_construction_status: "unavailable"
capex_delta_rm: 1200000
opex_delta_rm: 60000
validation_status: pending
status: simulated
```

### 3.5.4 Table Relationships

```
parcels.geojson ──┐
buildings.geojson ┤
network.geojson   ├──► assets.csv ──┬──► asset_metrics.csv
green_blue.geojson┤                 ├──► interventions.csv
amenities.geojson ┘                 └──► development_projects.csv
                                            development_candidates.csv
```

### 3.5.5 ID Naming Convention

```
P-     → Parcel          (P-B03)
BLD-   → Building        (BLD-B03)
E-     → Edge (network)  (E-R17)
N-     → Node            (N-12)
G-     → Green/Blue      (G-01)
A-     → Amenity         (A-T01)
R-     → Residential     (R-01)
F-     → Facility        (F-02)
SC-    → Scenario        (SC-REPURPOSE)
INT-   → Intervention    (INT-001)
PRJ-   → Development     (PRJ-P3)
CAND-  → Development Candidate (CAND-P05-01)
```

### 3.5.6 Unit Conventions

```
Display:  EPSG:4326 (WGS84)
Compute:  EPSG:32647 (UTM Zone 47N) or EPSG:3375/3376 (GDM2000)

Area:     m2
Distance: m
Currency: RM
Carbon:   tCO2e
Energy:   kWh
Time:     year / months
Ratio:    0-1 decimal (0.21 = 21%)
Score:    0-100 integer
```


# Part 4: Algorithm Layer — Derived Data Engine

## 4.1 Unified Mathematical Framework

```
Raw Data → Derived Metrics → Performance Scores → Overall Score
```

Asset data structure:

```python
Asset:
  Identity: {asset_id, asset_type, parcel_id, location}
  Raw Data: {physical, financial, operational, population, environmental}
  Derived Metrics: {utilisation, demand_supply_ratio, accessibility, lifecycle_cost}
  Financial Evaluation: {NPV, NOI, NOI_Yield}
  Performance Scores: {business_score, environmental_score, social_score, risk_score}
  Overall Score: {score, confidence, data_completeness}
```

## 4.2 Three Normalization Functions

**All metrics must first be converted to 0-100 scores for comparison.**

### Higher is better (benefit)

```python
S_benefit(x) = 100 * clip((x - L) / (U - L), 0, 1)
```

Applies to: Occupancy rate, facility utilisation, green coverage, service coverage population

### Lower is better (cost)

```python
S_cost(x) = 100 * clip((U - x) / (U - L), 0, 1)
```

Applies to: Vacancy rate, energy intensity, operating cost, carbon emissions, walking time, flood risk

### Target range (target)

```python
S_target(x):
  x < L:     100 * x / L
  L ≤ x ≤ U: 100
  U < x < H: 100 * (H - x) / (H - U)
  x ≥ H:     0
```

Applies to: Facility utilisation (too low = idle resources, too high = capacity shortage)

**L and U must come from: developer historical projects, market research, or explicitly labeled as scenario assumptions.**

## 4.3 Derived Metrics for Five Asset Types

### Commercial Property (B-03 Demo Core)

```
Occupancy Rate      O = A_occupied / A_lettable
Vacancy Rate        V = 1 - O
Vacancy Duration    D = t_current - t_vacant
Effective Rental    R_effective = R_actual
NOI                 NOI = R_effective - C_opex - C_maintenance
Demand-Supply Ratio DSR = D_commercial / S_effective
Accessibility       A = Σ_j w_j · f(d_j)
```

**Warnings**:
- Do NOT treat Footfall as a synonym for commercial success
- DSR is a planning model, not actual demand
- If tenant revenue is unavailable, use occupancy + vacancy duration + footfall as proxy

### Community Facility

```
Capacity Utilisation  U_r = Actual Usage / Available Capacity
Service Coverage      C = Target Population Served / Target Population
Cost per User         CPU = (C_opex + C_maintenance) / Annual Unique Users
Accessibility         Walk network calculation
```

**Warnings**:
- Low utilisation does NOT necessarily mean the facility should close
- Annual average utilisation may mask peak/off-peak issues

### Green Space / Park

```
Green Coverage        G = A_green / A_land
Canopy Coverage       C = A_canopy / A_land
Green Space per Capita G_pc = A_green / P_served
Accessibility Coverage Residents within walking distance
Thermal Exposure      f(surface_temp, canopy, impervious_ratio)
```

**Warnings**:
- Do NOT force a Financial ROI calculation
- Do NOT claim temperature reduction from canopy area alone

### Undeveloped Parcel

```
Developable Area      A_dev = A_land - A_restricted
Potential GFA         A_GFA = A_dev × FAR
Infrastructure Cost   Distance-based connection cost estimate
Demand-Supply Gap     Gap = D - S_effective
```

### Residential Property

```
Sell-through          N_sold / N_total
Occupancy             N_occupied / N_available
Sales Revenue         Σ P_sale,i × N_sold,i
NOI                   Rental Income - Operating Expenses
Energy Intensity      E_energy / A_floor
```

## 4.4 Asset Performance Score Formulas

### Commercial Performance Score

```python
S_commercial = 0.35·S_financial 
             + 0.25·S_occupancy 
             + 0.20·S_demand 
             + 0.10·S_accessibility 
             + 0.10·S_environment
```

### Community Facility Score

```python
S_facility = 0.25·S_utilisation 
           + 0.25·S_coverage 
           + 0.20·S_accessibility 
           + 0.15·S_cost_efficiency 
           + 0.15·S_environment
```

### Green Space Score

```python
S_green = 0.25·S_green_coverage 
        + 0.20·S_canopy 
        + 0.20·S_accessibility 
        + 0.20·S_thermal 
        + 0.15·S_usage
```

### Undeveloped Parcel Score

```python
S_parcel = w_f·S_development_feasibility 
         + w_d·S_demand 
         + w_a·S_accessibility 
         + w_e·S_environment 
         + w_r·S_risk
```

**Note: Different asset types must NOT use identical weights and benchmarks.**

## 4.5 Deadspace Detection — Three-Layer Detection

```
❌ Do NOT simply: S_overall < 40 → Deadspace
```

### Layer 1: Underperformance
Determine whether asset is significantly below applicable benchmark

### Layer 2: Low Value Realisation
Determine whether asset is failing to realise its intended value

### Layer 3: Actionability
Determine whether actionable improvement strategies exist

### UI Output (Three States)

| Asset | Trigger | Status |
|-------|---------|--------|
| B-03 | Persistent vacancy, low occupancy | Deadspace Candidate |
| F-02 | Low utilisation, insufficient coverage | Underperforming Facility |
| P-05 | Weak future demand, planned oversupply | Development Risk |
| G-01 | Poor accessibility, but high ecological value | Improvement Opportunity |


# Part 5: Algorithm Layer — Future State Simulation

## 5.1 Six Sub-Models

| Model | Prediction Target | Demo Implementation |
|-------|-------------------|---------------------|
| Population Model | Population & households | ✅ Fixed growth rate |
| Demand Model | Residential, commercial, facility demand | ✅ Category-specific proxy model |
| Supply Model | Future buildings & facility supply | ✅ Development schedule accumulation |
| Asset Model | Occupancy, utilisation, operating cost | ✅ Damped adjustment |
| Spatial Model | Accessibility, green coverage | ⚠️ Only update intervention-affected parts |
| Environmental Model | Energy, carbon emissions | ✅ Emission factor estimation |

## 5.2 Population Model

```python
P_t = P_0 * (1 + g)^t
H_t = P_t / h_avg
```

- g: Annual growth rate (user-selectable low/medium/high scenarios)
- h_avg: Average household size

**Do NOT implement Cohort-Component Model.**

## 5.3 Demand Model

```python
# Residential
D_housing,t = H_t * q_target

# Commercial
D_commercial,t = Σ_k P_k,t * e_k

# Facility
D_facility,t = P_target,t * q_service
```

**Critical warnings**:
- e_k must NOT be fabricated
- Must come from developer historical projects, market research, or be labeled as scenario parameter
- Different commercial categories (convenience retail / F&B / medical / office) require different demand models

## 5.4 Supply Model

```python
S_t = S_0 + Σ_i A_i · I(t >= T_i)
```

**Project status distinction**:
```
Committed / Approved / Proposed / Hypothetical
→ Only projects matching the selected scenario are included in supply
```

## 5.5 Occupancy Model (Damped Adjustment)

```python
O_t = O_{t-1} + λ(O_t* - O_{t-1})

O_t* = f(D_t, S_t)  # Target occupancy
λ = Adjustment speed (requires historical calibration or labeled as assumption)
```

**Why damped model**: Occupancy doesn't jump to new equilibrium instantly when demand changes.

## 5.6 Environmental Model

```python
# Operational carbon
C_operational = E_energy × EF_energy

# If no measured energy data
E_energy = A_floor × I_energy

# Embodied carbon (new construction)
Embodied_Carbon = Floor_Area × Material_Intensity
```

**All labeled as Tier 2 (Derived Estimation).**

## 5.7 Spatial Model (Simplified)

**Only update intervention-affected parts**:

```
- Intervention changes walk network → Recalculate Accessibility
- Intervention changes green space → Recalculate Green Coverage
- Intervention changes land use → Recalculate Demand-Supply
- Everything else remains static
```

## 5.8 DAG — Avoiding Circular Calculation

```
Population → Households → Demand → Occupancy → Performance Score
                ↑
            Supply ──────┘
```

**Key principle**: Performance Score is used only for evaluation and ranking. It must **NOT** feed back into Demand or Supply automatically.


# Part 6: Interventions & Simulation

## 6.1 Intervention Library

| Intervention | Data to Modify | Metrics to Recalculate |
|-------------|----------------|----------------------|
| **Repurpose** | Land use, capacity, operating cost, retrofit cost | Utilisation, service coverage, financial performance |
| **Retrofit** | Energy consumption, maintenance cost, CAPEX | LCCA, carbon emissions, financial performance |
| **Green Corridor** | Green layout, walk network, land use | Accessibility, green coverage, thermal exposure |
| **Pedestrian Upgrade** | Walk network connections, travel time | Accessibility, service coverage |
| **New Development** | Floor area, supply volume, development cost, delivery time | Demand-supply, financial performance, environmental metrics |
| **Delay Development** | Project delivery time, cost timing | Future supply, cash flow, opportunity cost |

## 6.1.1 Development Candidate Generation (NEW in v1.1)

For undeveloped parcels, the system generates **specific development types**, not just "new development".

### development_candidates.csv

| Field | Description |
|-------|-------------|
| candidate_id | Unique ID |
| parcel_id | Target parcel |
| development_type | childcare_centre / community_hub / mixed_use_commercial / affordable_housing / etc. |
| target_gfa_m2 | Gross floor area |
| target_units | Number of units |
| target_demographic | Intended user group |
| expected_capex_rm | Estimated CAPEX |
| expected_completion_year | Expected completion |
| expected_demand_coverage | 0-1 |
| expected_utilisation | 0-1 |
| expected_carbon_tco2e | Estimated operational carbon |
| expected_accessibility_delta | Change in accessibility score |
| feasibility_status | feasible / infeasible / constraint_flagged |
| constraint_notes | Planning constraints |

### Example

```csv
candidate_id: CAND-P05-01
parcel_id: P-05
development_type: childcare_centre
target_gfa_m2: 1200
target_units: 1
target_demographic: young_families
expected_capex_rm: 1800000
expected_completion_year: 2029
expected_demand_coverage: 0.72
expected_utilisation: 0.78
expected_carbon_tco2e: 145
expected_accessibility_delta: 0.08
feasibility_status: feasible
constraint_notes: "Complies with land use plan"
```

```csv
candidate_id: CAND-P05-02
parcel_id: P-05
development_type: mixed_use_commercial
expected_capex_rm: 3800000
expected_completion_year: 2031
expected_demand_coverage: 0.31
expected_utilisation: 0.42
feasibility_status: feasible
constraint_notes: "Surrounding commercial supply already saturated"
```

### How LLM uses this

When user asks "What should we build on P-05?", the LLM:
1. Calls `get_development_candidates("P-05")` → returns list
2. Filters by feasibility_status = "feasible"
3. Generates options from candidates
4. User selects → triggers simulation

## 6.2 Simulation Execution Flow

User proposes: "Repurpose B-03 into a community hub and improve pedestrian access."

System executes:

```
1. Check if B-03 can change land use
2. Calculate retrofit CAPEX
3. Update facility type and design capacity
4. Update expected opening time
5. Recalculate walk accessibility
6. Recalculate service coverage population
7. Update operating cost
8. Update relevant environmental metrics
9. Recalculate Performance Score for each future year
10. Compare LLM expected values with simulated actual values
    - If close → validation_status: "validated"
    - If large deviation → validation_status: "corrected"
    - UI displays: LLM estimate vs Model calculation
```

## 6.2.1 Time Anchors for Intervention Simulation (NEW in v1.1)

Each intervention has:

```
construction_start_year      → When construction begins
construction_duration_months → How long construction takes
activation_year              → When new state becomes operational
during_construction_status   → "unavailable" / "partial" / "operational"
```

### Simulation logic

```python
def simulate_intervention(asset_id, intervention, horizon):
    # 1. Get current state
    current_state = get_asset_state(asset_id, current_year)
    
    # 2. Determine time anchors
    start = intervention.construction_start_year
    activation = intervention.activation_year
    
    # 3. During construction: asset unavailable
    for year in range(start, activation):
        state[year] = apply_construction_state(current_state)
    
    # 4. After activation: new state
    for year in range(activation, horizon):
        state[year] = apply_post_intervention_state(current_state, intervention)
    
    # 5. Calculate performance for each year
    for year in state:
        state[year].performance_score = calculate_score(state[year])
    
    return state
```

### Example

```
B-03 diagnosed as deadspace in 2026
User selects "Repurpose" option
Construction: 2027-01 → 2028-06 (18 months)
Activation: 2028-06

Simulation output:
  Metric              | 2026 | 2027 | 2028 | 2030 | 2033
  --------------------|------|------|------|------|------
  Performance Score   | 28   | —    | 45   | 74   | 72
                              ↑      ↑
                          construction  activation
                          (unavailable) (ramp-up)
```

## 6.3 LLM Output Format (EXTENDED in v1.1)

```json
{
  "interventions": [
    {
      "type": "repurpose",
      "target": "B-03",
      "expected_derived": {
        "service_coverage": 0.72,
        "utilisation": 0.78,
        "carbon_operational_tco2e": 145,
        "accessibility_delta": 0.08
      },
      "expected_source": "llm_estimate"
    },
    {
      "type": "pedestrian_upgrade",
      "target": "E-R17"
    },
    {
      "type": "delay_development",
      "target": "PRJ-P3",
      "until": 2033
    }
  ]
}
```

**Note**: `expected_derived` is Tier 3 (Scenario Projection). It will be validated against simulation output.

## 6.4 Scenario Comparison Output

| Metric | Current Plan | Option A | Option B | Option C |
|--------|-------------|----------|----------|----------|
| CAPEX | — | RM1.2m | RM0.8m | RM0.1m |
| Projected Utilisation | 35% | 78% | 60% | 35% |
| Financial (NPV) | — | RM2.1m | RM1.8m | RM0.3m |
| Environmental Score | 45 | 72 | 68 | 50 |
| Social Score | 62 | 81 | 70 | 62 |
| **Performance Score** | 28 | 74 | 66 | 31 |
| **Δ Performance Score** | — | +46 | +38 | +3 |
| Time to Impact | — | 8mo | 6mo | 0mo |


# Part 7: LLM vs Deterministic Algorithm Division

## 7.1 Division Table

| Component | Responsibility |
|-----------|---------------|
| **LLM** | Intent Parsing / Generate Hypotheses / Generate Combinations / Compare Trade-offs / Explain |
| **Deterministic Tools** | Distance / Network routing / Catchment / Population projection / Energy / Carbon / CAPEX / OPEX / Utilisation / Performance Score |
| **Simulation** | "What happens if..." |

## 7.2 LLM's Three Positions

```
① Intent Parser
   "What if the budget is only 2 million and we can't demolish existing buildings?"
   ↓
   {target: "B-03", action: "optimize", 
    constraints: {capex: 2000000, demolition: false}}

   Note: Target can be ANY asset_id in the township, not just deadspace candidates.
   Examples:
     - Well-performing asset: "How can this be further optimised?"
     - Undeveloped parcel: "What should we build here?"
     - Planned project: "What if we delay this?"

② Option Generator
   Based on diagnosis + township state
   Generate 3-4 candidate interventions
   (Combined from predefined Intervention Library + Development Candidates, 
    does NOT invent new types)

③ Explanation Generator
   Translate simulation results into natural language
```

## 7.3 Tool Calling Example

User: "Would repurposing B-03 into a community facility be better?"

LLM calls:
```python
get_asset_state("B-03")
get_population_projection(2030)
simulate_repurpose("B-03", "community_facility")
calculate_carbon()
calculate_accessibility()
calculate_utilisation()
```

Then synthesizes:
> "Repurposing is preferable under the current environmental weighting..."

User: "What if I prioritise commercial return?"

LLM:
```python
simulate(...)              # Re-simulate
change_objective_weights() # Change weights
compare()                  # Re-compare
```

## 7.4 Tool Registry (NEW in v1.1)

The LLM does NOT know answers directly. It calls deterministic tools to retrieve data.

### Read Tools

```python
get_asset_state(asset_id, year) → AssetState
get_asset_metrics(asset_id, year) → Metrics
get_derived_metrics(asset_id, year) → DerivedMetrics
get_population_projection(year) → PopulationState
get_development_projects(parcel_id) → List[Project]
get_development_candidates(parcel_id) → List[Candidate]
```

### Diagnosis Tools

```python
diagnose_asset(asset_id) → DiagnosisResult
detect_deadspace(zone_id) → List[DeadspaceCandidate]
```

### Simulation Tools

```python
simulate_intervention(asset_id, intervention) → ScenarioState
simulate_new_development(parcel_id, development_type, params) → ScenarioState
calculate_performance_score(state, asset_type) → Score
```

### Comparison Tools

```python
compare_scenarios(scenarios, weights) → ComparisonTable
```


# Part 8: UI Design (Five Screens)

## 8.1 Core Interaction Principles

```
Principle 1: Any asset on the map is clickable AND queryable
  - Deadspace List is a shortcut entry, NOT the only entry
  - Users can query ANY asset:
    * Underperforming assets → "Why is this underperforming?"
    * Well-performing assets → "How can this be further optimised?"
    * Undeveloped parcels → "What should we build here?"
    * Planned projects → "What if we delay this?"
  - LLM Intent Parser does NOT restrict target to deadspace candidates

Principle 2: Clicking an asset → show diagnosis first, NOT recommendations
Principle 3: LLM only intervenes after user actively initiates a query
Principle 4: Clicking a scenario card → map visualizes corresponding changes (color-coded)
```

## 8.2 Screen 1: Township Map + Deadspace List (Side-by-Side Layout)

```
┌─────────────────────────────────────────────────────────────┐
│  LIVING MASTERPLAN                    [Current] [+3y] [+5y] │
├──────────────────────────────────────┬──────────────────────┤
│                                      │  DEADSPACE CANDIDATES│
│                                      │  ───────────────────│
│         TOWNSHIP MAP                 │  ⚠ B-03 Commercial  │
│                                      │     Score: 28        │
│    ┌────┐  ┌────┐  ┌────┐           │     Vacancy 14mo     │
│    │ A-02│  │ B-03│  │ C-04│           │     [View Details]   │
│    │ 🟢 │  │ 🔴 │  │ 🟡 │           │                      │
│    └────┘  └────┘  └────┘           │  ⚠ F-02 Facility    │
│                                      │     Score: 35        │
│    ┌────┐  ┌────┐  ┌────┐           │     Utilisation 22%  │
│    │ D-01│  │ E-05│  │ F-02│           │     [View Details]   │
│    │ 🟢 │  │ 🟢 │  │ 🟡 │           │                      │
│    └────┘  └────┘  └────┘           │  ⚠ P-05 Undeveloped │
│                                      │     Score: 31        │
│    ┌────┐  ┌────┐                    │     Weak demand      │
│    │ G-01│  │ P-05│                    │     [View Details]   │
│    │ 🟢 │  │ 🟡 │                    │                      │
│    └────┘  └────┘                    │  ───────────────────│
│                                      │  View: [All Assets ▾]│
│  Legend: 🟢 Good  🟡 Attention       │                      │
│          🔴 Low   ⚪ Insufficient     │                      │
└──────────────────────────────────────┴──────────────────────┘
```

**Key design**:

- **Any asset on the map is clickable and queryable** (A-02, B-03, C-04... all clickable)
- Deadspace List is a **shortcut entry point**, not the only entry point
- Deadspace List "View" can switch to "All Assets" to see everything
- Color coding: 🟢 Good / 🟡 Attention / 🔴 Low / ⚪ Insufficient Data

## 8.3 Screen 2: Asset Diagnosis Card (After Clicking an Asset)

**Show diagnosis only, NOT recommendations.**

```
┌─────────────────────────────────────────────────────────────┐
│  B-03 COMMERCIAL LOT                              [×] Close │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PERFORMANCE SCORE: 28 / 100        🔴 Low                  │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Financial      28  🔴                                      │
│  Environmental  45  🟡                                      │
│  Social         62  🟢                                      │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  DIAGNOSIS                                                  │
│  Why is this asset underperforming?                         │
│                                                             │
│  Contributing factors:                                      │
│    01  Accessibility friction        38%                    │
│    02  Demand-supply mismatch        27%                    │
│    03  Thermal exposure              21%                    │
│    04  Tenant mix saturation         14%                    │
│                                                             │
│  Evidence:                                                  │
│    • Average walking distance: 920m                         │
│    • 5-min catchment population: 420                        │
│    • Effective demand: 2,100                                │
│    • Effective supply: 3,400                                │
│    • Occupancy: 21% (14 months vacancy)                     │
│    • Surface temperature: 42°C, Canopy 8%                   │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  💬 Ask a question about B-03...                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ e.g. "What should we do with this asset?"           │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  [ Ask ]                                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key design**:

- **Diagnosis only**: Why it's underperforming, supported by evidence
- **No recommendations displayed**
- Bottom has an **open input field** for user-initiated queries
- Can click suggested questions or type freely

**Why this design**:

> Diagnosis is fact. Recommendation is opinion. The system first tells the user "what happened and why," letting the user decide whether to explore solutions. This prevents the system from prematurely steering the user toward a specific direction.

## 8.4 Screen 3: NL Decision Interface (After User Initiates Query)

After user submits a query, LLM intervenes:

```
┌─────────────────────────────────────────────────────────────┐
│  B-03 COMMERCIAL LOT                              [×] Close │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  YOUR QUESTION:                                             │
│  "What should we do with this asset?"                       │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  LLM ANALYSIS:                                              │
│                                                             │
│  Based on the diagnosis, B-03 is primarily affected by      │
│  accessibility friction and demand-supply mismatch.         │
│  Three candidate strategies have been generated:            │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  CANDIDATE OPTIONS:                                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Option A — Repurpose                                │    │
│  │ Convert to community facility                       │    │
│  │ [Preview on Map]  [Simulate]                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Option B — Retrofit + Green                         │    │
│  │ Improve building performance + add green corridor   │    │
│  │ [Preview on Map]  [Simulate]                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Option C — Delay + Replan                           │    │
│  │ Postpone Phase 3 expansion until demand threshold   │    │
│  │ [Preview on Map]  [Simulate]                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  💬 Follow-up question...                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ "What if I prioritise environmental return?"        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key design**:

- LLM generates options **only after user actively initiates query**
- Each option has **[Preview on Map]** button → clicking changes asset color on map
- Each option has **[Simulate]** button → triggers deterministic simulation

## 8.5 Screen 4: Map Preview (After Clicking "Preview on Map")

**Clicking an option card → map visualizes corresponding changes (color-coded).**

```
┌─────────────────────────────────────────────────────────────┐
│  PREVIEW: Option A — Repurpose B-03              [×] Close  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│         TOWNSHIP MAP (Preview Mode)                         │
│                                                             │
│    ┌────┐  ┌────┐  ┌────┐                                  │
│    │ A-02│  │ B-03│  │ C-04│                                  │
│    │ 🟢 │  │ 🔵 │  │ 🟡 │                                  │
│    └────┘  └────┘  └────┘                                  │
│              ↑                                              │
│         Changed to Blue                                     │
│         (Repurposed)                                        │
│                                                             │
│    ┌────┐  ┌────┐  ┌────┐                                  │
│    │ D-01│  │ E-05│  │ F-02│                                  │
│    │ 🟢 │  │ 🟢 │  │ 🟡 │                                  │
│    └────┘  └────┘  └────┘                                  │
│                                                             │
│  Legend:                                                    │
│    🟢 Unchanged (Good)                                      │
│    🟡 Unchanged (Attention)                                 │
│    🔴 Unchanged (Low)                                       │
│    🔵 Intervention Applied                                  │
│    🟣 Intervention + Positive Spillover                     │
│    ⚫ Intervention + Negative Impact                        │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  CHANGES FROM CURRENT:                                      │
│    B-03: Commercial → Community Facility     🔵             │
│    Phase 3: Cancelled                        🔵             │
│    Nearby pedestrian route: Upgraded         🟣             │
│                                                             │
│  [ Back to Options ]  [ Simulate This Option ]              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key design**:

- Clicking option card → **asset color changes on map**
- Blue = Direct intervention change
- Purple = Positive spillover (e.g., nearby accessibility improvement)
- Black = Negative impact from intervention
- Below map: **specific change list**

## 8.6 Screen 5: Scenario Comparison (After Simulation)

After user clicks "Simulate This Option":

```
┌─────────────────────────────────────────────────────────────┐
│  SCENARIO COMPARISON                        [Current] [+3y] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Metric              Current  Option A  Option B  Option C  │
│  ─────────────────────────────────────────────────────────  │
│  CAPEX               —        RM1.2m    RM0.8m    RM0.1m    │
│  Projected Util.     35%      78%       60%       35%       │
│  Financial (NPV)     —        RM2.1m    RM1.8m    RM0.3m    │
│  Environmental       45       72        68        50        │
│  Social              62       81        70        62        │
│  ─────────────────────────────────────────────────────────  │
│  PERFORMANCE SCORE   28       74        66        31        │
│  Δ Score             —        +46       +38       +3        │
│  ─────────────────────────────────────────────────────────  │
│  Time to Impact      —        8mo       6mo       0mo       │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  RECOMMENDED: Option A — Repurpose                          │
│  "Highest performance improvement, moderate CAPEX,          │
│   strong environmental and social co-benefits."             │
│                                                             │
│  [ Adjust Weights ]  [ View Map Diff ]  [ Apply to Plan ]   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key design**:

- Clicking any Option in the table → map visualizes that scenario's color changes
- [View Map Diff] → Side-by-side comparison of Current vs Selected Scenario
- [Apply to Plan] → Masterplan updates

## 8.6.1 Two Comparison Modes (NEW in v1.1)

```
[Single Year]  → Horizontal comparison at current slider year
[Time Series]  → Vertical comparison across years
```

### Time Series Example

```
Metric              | 2026 | 2028 | 2030 | 2033
--------------------|------|------|------|------
Current Plan Score  | 28   | 24   | 22   | 20
Option A Score      | 28   | 45   | 74   | 72
Option B Score      | 28   | 62   | 66   | 64
Option C Score      | 28   | 28   | 30   | 35

Note: 2028 is activation year for Option A; score ramps up after opening.
```

**UI toggle**:
```
Comparison Mode:  [Single Year]  [Time Series]
```

## 8.7 Complete Interaction Flow

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [1] Township Map + Deadspace List                          │
│       │                                                     │
│       ├── Click any asset on map ──────────┐                │
│       │                                    │                │
│       └── Click Deadspace List card ───────┤                │
│                                            ▼                │
│  [2] Asset Diagnosis Card                                   │
│       • Diagnosis only                                      │
│       • NO recommendations                                  │
│       • Open input field at bottom                          │
│       │                                                     │
│       │ User actively initiates query                       │
│       ▼                                                     │
│  [3] NL Decision Interface                                  │
│       • LLM generates candidate options                     │
│       • Each option has [Preview] [Simulate]                │
│       │                                                     │
│       ├── Click [Preview] ──────┐                           │
│       │                         ▼                           │
│       │              [4] Map Preview                        │
│       │               • Map color changes                   │
│       │               • Change list displayed               │
│       │               • [Simulate This Option]              │
│       │                         │                           │
│       └── Click [Simulate] ─────┤                           │
│                                 ▼                           │
│  [5] Scenario Comparison                                    │
│       • Multi-scenario comparison table                     │
│       • Toggle [Single Year] / [Time Series]                │
│       • Click any option → map visualizes                   │
│       • [Apply to Plan] → Masterplan updates                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 8.8 Time Slider (Persists Across All Screens)

```
[Current] [+1y] [+3y] [+5y]
```

- Changing time → All screen data recalculates
- Map colors, Diagnosis, Scenario Comparison all sync
- Comparison is: **Performance(t, scenario)**

## 8.9 Tier Labels in UI

```
Each number is displayed with:
  🔵 Observed (Tier 1) — From property records, lease history
  🟡 Estimated (Tier 2) — From formula derivation, emission factors
  🔴 Scenario (Tier 3) — From future assumptions, simulation models

Example:
  Occupancy: 21% 🔵
  Carbon: 1,820 tCO2e 🟡
  Population 2030: 11,000 🔴
```

## 8.10 UI Correction Summary

| Original Design | Corrected Design |
|-----------------|------------------|
| Only Deadspace List clickable | **Any asset on map is clickable and queryable** |
| Clicking shows diagnosis + recommendations | **Clicking shows diagnosis only, NO recommendations** |
| LLM auto-generates options | **LLM only intervenes after user initiates query** |
| Scenario Comparison is table only | **Clicking Option card → map color visualization** |
| Layer switching unclear | **Map + Deadspace List side-by-side, no layer switching needed** |
| Only single-year comparison | **Toggle between Single Year and Time Series** |

**Core principle**:

> **Diagnosis is fact. Recommendation is opinion. The system first tells the user "what happened and why," letting the user decide whether to explore solutions. LLM does not proactively intervene—it only participates after the user initiates a query.**


# Part 9: Demo Scope

## 9.1 Scope

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zone:        Elmina West (fictional but based on real layout)
Assets:      5
  - B-03 Commercial Lot (deep demo)
  - F-02 Community Facility
  - P-05 Undeveloped Parcel
  - G-01 Green Space
  - R-01 Residential Catchment
Deep-dive:   B-03 only (complete loop)
Horizons:    Current (2026) / +3 years (2030) / +5 years (2033)
Scenarios:   Current Plan / Repurpose / Delay
Score:       Financial + Environmental + Social
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 9.2 3-Minute Demo Script

```
[0:00] Map shows Elmina West, B-03 highlighted in red
[0:15] Click B-03 → "View Details"
[0:30] Diagnosis Card displays:
        - 5min/10min/15min population
        - Demand vs Effective Supply
        - Occupancy 21%, Vacancy 14 months
        - Performance Score: 28
          (Financial 28, Env 45, Social 62)
[0:50] User types: "What should we do with this asset?"
[1:00] LLM reasoning:
        "Current demand doesn't justify expansion..."
[1:20] LLM generates 3 options:
        A. Repurpose to community facility
        B. Retrofit + green corridor
        C. Delay Phase 3 expansion
[1:40] User selects A → clicks [Preview]
        → Map: B-03 turns blue, Phase 3 turns blue
        → Change list: "B-03 Commercial → Community Facility"
[1:55] User clicks [Simulate]
        → Tool calling: simulate_repurpose(), calculate_carbon()
[2:10] Scenario comparison appears:
        Current / Repurpose / Retrofit / Delay
        Financial × Environmental × Social
        Time Series: 2026 | 2028 | 2030 | 2033
[2:30] User asks: "What if I prioritise environmental return?"
        → Weights change → Repurpose becomes top recommendation
[2:50] Click "Apply" → Map updates
        "Phase 3 expansion ↓ Cancelled"
        "B-03 → Community Facility (2028 activation)"
        "Avoided construction: RM2.7m CAPEX"
[3:00] End
```

## 9.3 Explicitly NOT Doing

- ❌ Full real-time integration of all 7 data categories
- ❌ True 3D rendering
- ❌ PDF parser
- ❌ Multi-township support
- ❌ Complex causal knowledge base
- ❌ Full lifecycle NPV cash flow discounting
- ❌ IRR
- ❌ Climate scenario simulation
- ❌ Tree canopy growth model
- ❌ Cohort-Component population model
- ❌ Rent and land price feedback mechanism


# Part 10: Tech Stack

## 10.1 Recommended Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| **GIS/Spatial** | osmnx + geopandas | Data download + geometry processing |
| **Spatial Database** | PostGIS (optional) | Spatial queries |
| **Decision Analysis** | pymcdm | Multi-criteria decision making |
| **LLM Agent** | air-agent / openai-agents-python | Tool calling |
| **Frontend Map** | MapLibre GL JS | WebGIS rendering |
| **Visualization** | Custom React components | Scenario Comparison |

## 10.2 Integration Path

```
osmnx/geopandas (Data layer)
    ↓
air-agent (LLM orchestration layer)
    ↓
pymcdm (Decision kernel)
    ↓
MapLibre GL JS (Interactive presentation)
```


# Part 11: Q&A Preparation

**Q1: "Where is the AI?"**
> "AI is at the interface: parsing intent, orchestrating tool calls, and explaining results. The decision kernel is deterministic—because developers need reproducible decisions, not hallucinations."

**Q2: "How is this different from CityEngine?"**
> "CityEngine produces plans. Living Masterplan produces decisions. We speak in CAPEX, activation time, and stranded-asset risk. And we close the loop: plan → build → observe → re-plan."

**Q3: "Where does your data come from?"**
> "Three tiers: observed data (Tier 1), derived estimation (Tier 2), and scenario projection (Tier 3). Every number is tagged with its source."

**Q4: "How do you calculate ROI for a park?"**
> "We don't use financial ROI for non-commercial assets. We use multi-dimensional scoring—Financial, Environmental, Social—combined into an Asset Performance Score via MCDA. A park has Financial 0, but high Environmental and Social scores."

**Q5: "Why not just use machine learning to predict everything?"**
> "ML requires training data we don't have. We use established methods—population growth models, demand coefficients, emission factors—and clearly label their confidence tier. LLM handles reasoning; deterministic tools handle calculation."


# Part 12: Team Roles & Timeline

## 12.1 Suggested Roles

| Role | Responsibility |
|------|---------------|
| **Algorithm/Backend** | Derived Data Engine + Future Simulation + Performance Scoring |
| **LLM/Agent** | Intent Parser + Option Generator + Explanation + Tool Calling |
| **Frontend** | 5 screens + Map + Scenario Comparison + Time Slider |
| **Data** | Mock township dataset + Data dictionary + Tier labels |
| **Pitch** | Narrative + Demo script + Q&A + Rehearsal |

## 12.2 Timeline (Assuming 6 Weeks)

**Week 1-2: Foundation**
- [ ] Lock demo scope
- [ ] Build mock township dataset (5 assets)
- [ ] Define scoring formulas for 4 asset types
- [ ] Establish data dictionary (Tier labels)
- [ ] Set up Model Schema tables

**Week 3-4: Core Implementation**
- [ ] Derived Data Engine (Python)
- [ ] Future Simulation (4 models + time anchors)
- [ ] Intervention Library + Development Candidates
- [ ] LLM Agent (Intent + Option + Explanation + Tool Registry)
- [ ] Frontend 5 screens

**Week 5: Integration + Testing**
- [ ] End-to-end integration
- [ ] User testing (3-5 people)
- [ ] Record demo video (backup)

**Week 6: Pitch Preparation**
- [ ] Write pitch script
- [ ] Build deck
- [ ] Prepare Q&A
- [ ] Rehearse at least 5 times


# Part 13: Core Narrative Summary

## 13.1 One-liner

> **Living Masterplan continuously evaluates the return of township assets, identifies underperforming spaces, and simulates how alternative development decisions reshape future business, environmental, and social value.**

## 13.2 Planet-first Tagline

> "Don't just build greener. Build only what the future still needs."

## 13.3 Champion Narrative

```
Problem:   Masterplans are static. Townships are not.
Solution:  We turn the masterplan into a continuously adaptive decision system.
Planet:    Build less unnecessarily. Reuse more. Adapt earlier.
Mechanism: AUDIT → DIAGNOSE → GENERATE → SIMULATE → DECIDE
Enabler:   GIS + Township Data + Decision Engine + AI interface
Result:    A township that adapts before today's planning assumptions 
           become tomorrow's stranded assets.
```

## 13.4 Engineering Boundary

```
Different asset types may use different calculation methods,
but each method must have explicit:
  - Inputs
  - Outputs
  - Assumptions
  - Applicable scope
  - Confidence Tier

This is the source of system credibility.
```


# Appendix A: v1.1 Change Log

| Section | Change | Reason |
|---------|--------|--------|
| Header | Version 1.0 → 1.1 | Track changes |
| Part 3.5 | Added Model Schema (consolidated) | Schema was scattered |
| Part 3.5.3 | Added `development_candidates.csv` | Ability 3 |
| Part 3.5.3 | Extended `interventions.csv` fields | Abilities 4, 5 |
| Part 6.1.1 | Added Development Candidate Generation | Ability 3 |
| Part 6.2 | Added step 10: LLM expected vs simulated | Ability 4 |
| Part 6.2.1 | Added Time Anchors for Intervention | Ability 5 |
| Part 6.3 | Extended LLM Output JSON | Ability 4 |
| Part 7.2 | Clarified Intent Parser target scope | Ability 1 |
| Part 7.4 | Added Tool Registry | Ability 2 |
| Part 8.1 | Clarified any-asset queryability | Ability 1 |
| Part 8.6.1 | Added Two Comparison Modes | Ability 6 |
| Part 9.1 | Assets: 3 → 5 | Align with schema |
| Part 9.2 | Updated demo script | Include Preview + Time Series |
| Part 10.1 | QGIS → osmnx; MapStore → MapLibre | Lighter stack |
| Part 12.2 | Added schema setup to Week 1-2 | Align with v1.1 |


**This is Complete Technical Design Document v1.1.**