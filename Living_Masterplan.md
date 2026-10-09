# Living Masterplan — Complete Technical Design Document

> **Version**: v1.0
> **Purpose**: Internal team alignment + development reference
> **Track**: Planet
> **One-line definition**: A time-aware township asset performance decision engine that helps developers identify underperforming assets, simulate alternative strategies, and evaluate future business and environmental value.
> **Core principle**: Tools calculate the world. LLM reasons about the world.
> **Planet anchor**: Circular Economy (reuse, don't rebuild) + Climate Resilience (adaptive planning)


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
```

## 6.3 LLM Output Format

```json
{
  "interventions": [
    {"type": "repurpose", "target": "B-03"},
    {"type": "pedestrian_upgrade", "target": "route-R17"},
    {"type": "green_corridor", "target": "corridor-C2"},
    {"type": "delay_development", "target": "phase-3", "until": 2031}
  ]
}
```

## 6.4 Scenario Comparison Output

| Metric | Current Plan | Option A | Option B | Option C |
|--------|-------------|----------|----------|----------|
| CAPEX | — | RM1.2m | RM0.8m | RM0.1m |
| Projected Utilisation | 35% | 78% | 60% | 35% |
| Financial (NPV) | — | — | — | — |
| Environmental Score | — | — | — | — |
| Social Score | — | — | — | — |
| **Performance Score** | — | — | — | — |
| **Δ Performance Score** | — | — | — | — |
| Time to Impact | — | — | — | — |


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

② Option Generator
   Based on diagnosis + township state
   Generate 3-4 candidate interventions
   (Combined from predefined Intervention Library, does NOT invent new types)

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


# Part 8: UI Design (Five Screens)

## 8.1 Core Interaction Principles

```
Principle 1: Any asset on the map is clickable (not just those in Deadspace List)
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

- **Any asset on the map is clickable** (A-02, B-03, C-04... all clickable)
- Deadspace List is a **shortcut entry point**, not the only entry point
- Deadspace List "View" can switch to "All Assets" to see everything
- Color coding: 🟢 Good / 🟡 Attention / 🔴 Low / ⚪ Insufficient Data

## 8.3 Screen 2: Asset Diagnosis Card (After Clicking an Asset)

**This is the key correction: Show diagnosis only, NOT recommendations.**

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

**This is the key correction: Clicking an option card → map visualizes corresponding changes (color-coded).**

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
| Only Deadspace List clickable | **Any asset on map is clickable** |
| Clicking shows diagnosis + recommendations | **Clicking shows diagnosis only, NO recommendations** |
| LLM auto-generates options | **LLM only intervenes after user initiates query** |
| Scenario Comparison is table only | **Clicking Option card → map color visualization** |
| Layer switching unclear | **Map + Deadspace List side-by-side, no layer switching needed** |

**Core principle**:

> **Diagnosis is fact. Recommendation is opinion. The system first tells the user "what happened and why," letting the user decide whether to explore solutions. LLM does not proactively intervene—it only participates after the user initiates a query.**


# Part 9: Demo Scope

## 9.1 Scope

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zone:        Elmina West (fictional but based on real layout)
Assets:      3
  - B-03 Commercial Lot (deep demo)
  - F-02 Community Facility
  - P-05 Undeveloped Parcel
Deep-dive:   B-03 only (complete loop)
Horizons:    Current / +3 years
Scenarios:   Current Plan / Repurpose / Delay
Score:       Financial + Environmental + Social
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 9.2 3-Minute Demo Script

```
[0:00] Map shows Elmina West, B-03 highlighted in red
[0:15] Click B-03 → "Investigate"
[0:30] Decision Context displays:
        - 5min/10min/15min population
        - Demand vs Effective Supply
        - Occupancy 21%, Vacancy 14 months
        - Performance Score: 28
          (Financial 28, Env 45, Social 62)
[0:50] User types: "Should we proceed with Phase 3?"
[1:00] LLM reasoning:
        "Current demand doesn't justify expansion..."
[1:20] LLM generates 3 options:
        A. Build as planned
        B. Repurpose B-03 + reduce Phase 3
        C. Delay until demand threshold
[1:40] User selects B → triggers tool calling
        → simulate_repurpose()
        → calculate_carbon()
        → calculate_accessibility()
[2:10] Scenario comparison:
        Build / Repurpose / Delay
        Financial × Environmental × Social
[2:30] User asks: "What if I prioritise environmental return?"
        → Weights change → Repurpose becomes top recommendation
[2:50] Click "Apply" → Map updates
        "Phase 3 expansion ↓ Cancelled"
        "B-03 → Community + low-carbon mixed use"
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
| **GIS/Spatial** | QGIS + BlocksNet | Data processing + accessibility calculation |
| **Spatial Database** | PostGIS | Spatial queries |
| **Decision Analysis** | pymcdm | Multi-criteria decision making |
| **LLM Agent** | air-agent / openai-agents-python | Tool calling |
| **Frontend Map** | MapStore | WebGIS dashboard |
| **Visualization** | Custom React components | Scenario Comparison |

## 10.2 Integration Path

```
QGIS/BlocksNet (Data layer)
    ↓
air-agent (LLM orchestration layer)
    ↓
pymcdm (Decision kernel)
    ↓
MapStore (Interactive presentation)
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
- [ ] Build mock township dataset (3 assets)
- [ ] Define scoring formulas for 3 asset types
- [ ] Establish data dictionary (Tier labels)

**Week 3-4: Core Implementation**
- [ ] Derived Data Engine (Python)
- [ ] Future Simulation (4 models)
- [ ] Intervention Library
- [ ] LLM Agent (Intent + Option + Explanation)
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


**This is Complete Technical Design Document v1.0 (English).**