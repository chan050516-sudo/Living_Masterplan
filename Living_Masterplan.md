# Living Masterplan — Product Positioning & System Design Document v3.0

> **Version**: v3.0 (Code-Aligned Architecture & Pitch Strategy)
> **Track**: Planet (Circular Economy & Climate Resilience)
> **Core Principle**: Tools calculate the world. LLM reasons about the world.
> **Tech Stack**: Python (Pandas, GeoPandas, NetworkX), FastAPI, Gemini 3.8 Flash, MapLibre GL JS.

---

# Part 1: Problem Statement & Planet Narrative

## 1.1 The Macro Context & Problem: The Static Masterplan Trap
Townships are planned on static multi-year assumptions. When reality shifts—whether driven by changing demographics, evolving retail habits, or climate pressures—physical assets freeze into **Deadspace**: capital that has been spent across three dimensions but is no longer returning value:
*   **Financial**: Negative NOI, rental losses, and maintenance compounding on idle square footage.
*   **Environmental**: Stranded operational carbon heating/lighting empty floors, plus thousands of tonnes of locked-in embodied carbon.
*   **Social**: Multi-month vacancy streaks (averaging 14+ months) and underused capacity that disconnects residents from essential 15-minute amenities.

**The Industry Blind Spot**:
According to the *Global Status Report for Buildings and Construction*, buildings and construction account for **37% of global energy-related CO₂ emissions** and nearly **50% of global material extraction**. Yet, developers lack quantitative spatial decision engines to audit stranded capital, habitually defaulting to demolition and new construction.

## 1.2 Target Users & Threefold Value Creation
Living Masterplan delivers one decision engine with three distinct layers of value:
1.  **Primary Users (Developers & Master Planners)**:
    *   *Challenge*: High-risk CAPEX commitments, lack of counterfactual simulation tools to compare adaptive reuse against new builds.
    *   *Benefit*: High-confidence, de-risked portfolio decisions before committing capital.
2.  **Beneficiaries (Residents & Local Businesses)**:
    *   *Challenge*: Mismatched local amenities, decaying shoplots, and inaccessible community services.
    *   *Benefit*: Adaptive, demand-driven spaces and restored pedestrian vibrancy within walking catchments.
3.  **Beneficiaries (The Planet & Climate Resilience)**:
    *   *Challenge*: Excessive embodied carbon from new builds and worsening urban heat island (UHI) microclimates.
    *   *Benefit*: Drastic reduction in material extraction, preserved embodied carbon, and cooler urban canopy networks.

## 1.3 The Planet Narrative: Avoided Construction
Our strategy is rooted in the **Circular Economy** and **Climate Resilience**:
*   **The Enemy is Unnecessary Rebuilding**: Demolishing an existing structure emits substantial embodied carbon and wastes prior investments before a new foundation is even poured.
*   **The Lever is Adaptive Reuse**: By preserving the existing structural shell and retrofitting/repurposing targeted zones, we deliver massive **Avoided Embodied Carbon** and lower CAPEX.
*   **Core Guiding Insights**:
    > *"A 15-minute city isn't about building everything closer. It's about using what already exists better."*  
    > *"Reuse, improve, or build? Ask before adding carbon."*
*   **The Execution Loop**: `AUDIT → DIAGNOSE → GENERATE → SIMULATE → DECIDE`.

---

# Part 2: System Architecture

The architecture strictly isolates **Deterministic Physics** from **LLM Reasoning** to prevent hallucination.

```text
[ Data Layer ] OSM GeoJSON (network, buildings) + Business CSVs (assets, leases)
      │
      ▼
[ B3 — Derived Metrics Engine ] (Deterministic)
  - NetworkX: OSM Graph + Bridge Components
  - Huff Gravity: Per-subtype Demand Allocation
  - Environmental: Embodied & Operational Carbon
      │
      ▼
[ B6 — Deadspace Detector ] (Rule-based)
  - L1: Underperformance (Occ, DSR, Carbon)
  - L2: Low Value Realisation (NOI, Coverage)
  - L3: Actionability (Authority & Lease constraints)
      │
      ▼
[ B4 — Future State Simulation ] (Deterministic)
  - Time Anchors: Construction vs. Activation
  - Dynamics: Damped Occupancy + Lease Ceilings
  - Catalytic Spillovers: Re-routing Dijkstra graphs
      │
      ▼
[ B7 — LLM Orchestrator ] (Multi-Candidate Agentic)
  - Context: Spatial Rings & Topology
  - Generation: 2-3 Strategy Plans
  - Simulation: B4 Validates all plans
  - Selection & Justification: Counterfactual comparison
```

---

# Part 3: The B3 Derived Metrics Engine (Algorithms & Citations)

This layer computes the hidden physics of the township.

## 3.1 Accessibility & Network Graph
*   **Algorithm**: Builds a walking/driving graph from OSM. Since OSM extracts are often fragmented, we apply `bridge_components()` using a **KD-Tree** nearest-neighbor search, applying a **1.35x Detour Factor** (standard urban planning ratio) to connect disconnected sub-graphs.
*   **Door-to-Door Distance**: `off_origin + on_network_dijkstra + off_destination`.
*   **Canopy Impedance**: Walking edges are weighted by `effective_length = length * (1 - gamma * canopy)`. Shaded paths are "shorter" in cognitive distance.

## 3.2 Huff Gravity Model (Per-Subtype)
*   **Algorithm**: Instead of treating a mall as one block, we allocate demand *per subtype* (e.g., supermarket vs. F&B).
*   **Formula**: \(D_{st} = \sum (Population \times DemandCoefficient) \times \frac{Attractiveness_i / Distance_i^2}{\sum (Attractiveness / Distance^2)}\).
*   **Fallback**: If a supply node is unreachable due to graph fragmentation, a `FALLBACK_DISTANCE_M = 1500m` is applied based on township-typical distances.

## 3.3 Environmental Accounting
*   **Embodied Carbon**: Sourced from **CIDB Embodied Carbon Inventory Data for Construction Materials (Malaysia)**. Uses taxonomy-specific material intensities and structural lifespans per subtype (e.g., 0.28 tCO₂e/m² / 60-yr terrace vs. 0.42 / 30-yr supermarket). Adaptive reuse reduces the effective intensity to 0.08 tCO₂e/m².
*   **Operational Carbon**: Per-subtype Energy Intensity × Grid Emission Factor (**Suruhanjaya Tenaga 2022-2024: 0.769 kgCO₂e/kWh**). Subtype intensities range from 90 kWh/m²/yr (place of worship) to 420 kWh/m²/yr (supermarket with refrigeration load). Offices above 10 storeys apply a ×1.15 vertical penalty.
*   **Land Surface Temperature (LST)**: An **audited satellite observation**, not a proxy. The pipeline reads `LANDSAT/LC08/C02/T1_L2` `ST_B10` (30 m, clear-pixel median composite, QA-masked for cloud/shadow/snow), computes per-asset mean via zonal statistics (`all_touched=true`), and derives `surface_temp_delta_c = t_asset_c − t_township_c` (township baseline = mean over the union of all asset footprints). Missing clear pixels stay `null` — no proxy fallback.
*   **Canopy → Temperature Coupling (simulated years)**: When a spatial intervention changes canopy, the scenario's `surface_temp_delta_c` is **shifted** from the observed baseline by:
    `ΔT_simulated = baseline_ΔT + (canopy_new − canopy_base) × slope × smoothing`
    where `slope = −1.709 °C/unit`, `smoothing = min(1, years_elapsed / 3)`. This models microclimate response to canopy gain without inventing a new observation.
*   **Canopy Growth**: Asymptotic geometric growth `C(t) = C_ceiling − (C_ceiling − C_0)·(1−r)^t` with `r = 2.5%/yr`, `C_ceiling = 0.60`, from `canopy_growth_start_year = 2026`. Modelled on the **UPM Urban Forest Study (Putrajaya)**.
*   **Carbon Sequestration (township-level)**: Canopy uptake at **0.0015 tCO₂e/m²/year**. Reported alongside operational carbon in `sequestration_by_year` and `net_carbon_by_year`, but **never added to `carbon_operational_tco2e`** — sequestration is a physical removal, not an emission stream.

## 3.4 Trajectory Classification
Analyzes 5-year history to classify assets:
*   `rapid_decline`: >20% occupancy drop in 1 year.
*   `chronic_low`: Below 85% of benchmark for 3+ years.
*   `never_alive`: 0% occupancy since completion.

---

# Part 4: The B6 Deadspace Detector

Deadspace is **not** a single score. It is a 3-layer gate:
1.  **Layer 1 (Underperformance)**: `low_occupancy` (<50%), `high_stranded_carbon` (>50% wasted capacity), `subtype_mix_dead` (a specific floor <10% occupied), `high_uhi_exposure`.
2.  **Layer 2 (Value Failure)**: `negative_noi`, `built_value_not_realized` (developer-held unsold units).
3.  **Layer 3 (Actionability)**: Evaluates `authority` (`full_control` vs `advisory`). A dead asset owned by a third party is merely a `monitor`, not an actionable candidate.

### Authority Model (v6.0)
Three authority levels govern what SDP can execute:
- `full_control` (developer_held): every legal action is executable.
- `shared` (strata_jmb): retrofit executable; repurpose / new_development require JMB / MC approval.
- `advisory` (sold, public_transferred): no execution power. SDP can run **collaborative** services (tenant matching, tactical placemaking, walkway / corridor works on public land) with the owner; every other action is a recommendation.

`decide_intervention_mode()` produces `direct` / `collaborative` / `advisory` — orthogonal to `status`. A sold shop that is genuinely deadspace still gets `status = deadspace_candidate`; the mode tells the frontend how SDP can act.

### Ramp-up Grace
A newly delivered asset is not deadspace because occupancy starts low. Grace windows: residential 3 years, commercial 2 years, community_facility 3 years. During the window, the asset is held at `monitor` unless a hard-failure flag (currently `rapid_decline`) fires — preserving the ability to catch genuine early failure.

---

# Part 5: The B4 Future State Simulation

B4 is the quantitative truth engine. It simulates outcomes over a 5-year horizon.

## 5.1 Dynamics
*   **Damped Occupancy**: `O_t = O_{t-1} + λ(O_t* - O_{t-1})`. Assets do not jump instantly to the new equilibrium. (λ = 0.35).
*   **Weak Coupling**: When accessibility improves, Huff demand shifts. However, a 10% demand shift does not equal a 10% occupancy jump. We apply an `access_to_use_conversion = 0.25`, based on **Cervero (2002) & Ewing & Cervero (2010)** meta-analysis on built environment effects.
*   **Lease Ceilings**: Huff cannot invent a tenant. The simulation dynamically caps occupancy at the total active leased area. Lease renewals are simulated using a 75% renewal probability per 3-year term.
*   **Developer Sell-off**: Unsold residential inventory decays annually (10-20% seeded rate), converting to occupied units.

## 5.2 Time Anchors
Every intervention carries:
*   `construction_start_year` (e.g., 2027)
*   `duration` (e.g., 18 months)
*   `activation_year` (e.g., 2028)
*   `during_construction_status` (capacity drops to 0% for full repurpose, 60% for retrofit).

### 5.2b P1 — Engineering-Spec Path (Optional)
When a retrofit / repurpose supplies `engineering_spec` (7 physical parameters), the simulation replaces the aggregate `energy_efficiency_gain` with a physics-derived model:
- `structure_retention_ratio` → avoided embodied carbon (vs. a rebuild).
- `facade_action` + `primary_material` → facade & structural carbon intensities.
- `roof_intervention` → ambient cooling relief: `cool_roof −1.5°C`, `green_roof −2.2°C`, `solar_canopy −1.8°C`.
- `hvac_cop` → cooling energy scales as `3.0 / COP` vs. a standard split AC.
- `operating_hours_per_week` → linear scaling on cooling energy.
- `rooftop_pv_coverage` → PV yield deducted from operational energy before carbon conversion (`0.18 panel efficiency × 4.2 peak-sun-hours × 365`).

The spec drives both the carbon ledger and the surface-temperature narrative. When absent, the legacy aggregate multiplier is used and `engineering_spec` on the response is `null`.

### 5.2c Interim Solar Farm
`interim_solar_farm` on an undeveloped parcel produces a **negative carbon offset** rather than a load: `annual_kwh = land_area × 0.60 × 0.15 kWp/m² × 1350 kWh/kWp`. The parcel's `carbon_operational_tco2e` becomes the negated offset, and its `subtype` flips to `solar_farm` for map display.

## 5.3 Counterfactual Comparison (The "A+B vs A->B" Mechanism)
When calculating avoided embodied carbon, the engine compares:
*   **Option A**: Keep Asset A as is, build Asset B elsewhere. (New Build Embodied Carbon).
*   **Option B**: Repurpose Asset A into Asset B. (Repurpose Embodied Carbon).
*   **Result**: `Avoided Embodied Carbon = New Build - Repurpose`. This proves the Circular Economy value.

---

# Part 6: The B7 LLM Reasoning Layer

The LLM is an **Architect**, not a Calculator.

## 6.1 Orchestration Pipeline
1.  **Stage 0 (Intent)**: Parses the query (e.g., "Convert BLD-0183, RM 3M budget, no demolition").
2.  **Stage 1 (Context)**: Assembles a deterministic Context Pack (No LLM).
3.  **Stage 2 (Generation)**: Generates 2-3 candidate plans (JSON). Strictly constrained by Action Space and Leases.
4.  **Stage 2.5a/b (Validation & Simulation)**: The Validator checks legality/budget. B4 runs the physics simulation for every candidate.
5.  **Stage 2.7 (Selection & Justification)**: The LLM reads the *actual simulated outcomes*, selects the winner, and writes the board-level justification.

### 6.1b Soft Interventions
Two intervention types require no ownership:
- **`tenant_matching`** — SDP's leasing team finds a footfall-generating tenant for an empty or failing shop. Each candidate tenant type scores a Suitability Index `S = 0.45·demand + 0.30·room + 0.25·anchor`. The best type is picked unless the plan names one. Leasing is a yearly Markov step with `p = clip(0.25 + 0.50·S + 0.20·footfall_percentile, 0.10, 0.90)`, so expected occupancy after n years is `occ_n = bench − (bench − occ_0)·(1−p)^n`. The comparison block reports street survival (share of shops within 300 m at ≥50% occupancy) before and after.
- **`tactical_placemaking`** — A temporary magnet (night market, weekend market, food-truck park, pop-up sports court, community event space) for `duration_years` (default 3). Every commercial asset within 400 m gets an attractiveness / footfall multiplier `1 + mass·(1 − d/radius)`. The effect **ends with the event** — it is a catalyst, not a permanent fix.

Both are listed under `collaborative` for advisory assets: SDP runs them **with** the owner. The LLM is told to phrase them as an offer, not a commitment.

### 6.1c Shared Simulation Cache
`_simulate_candidates_shared()` runs the B3 pipeline, the walking graph, and the Dijkstra distance matrix **once per B7 run** and reuses them across every candidate. Two candidates cost one setup, not two — critical because the graph build is ~15-20 seconds and the simulation is only ~10-15 seconds per candidate.

## 6.2 The Context Pack (Spatial Topology)
To give the LLM "God's eye view" without prompt explosion, we use:
*   **Macro Baseline**: Global oversupplied subtypes (e.g., "F&B is oversupplied at 32% occupancy across the township").
*   **Spatial Rings**: 0-400m, 400-800m, 800-1200m. Summarizes `dead_competitors` and `healthy_anchors` in each ring.
*   **Detailed Neighbors**: A list of top 25 nearby assets with their occupancy, lease expiry, and subtype.
*   **Subtype Mix**: Diagnostic of partial death (e.g., "Supermarket: 95%, F&B: 8%").
*   **Authority**: `developer_held` (full control) vs `sold` (recommendation only).

## 6.3 Catalytic Interventions & Verification
The LLM can act on Asset A to benefit Asset B.
*   **Mechanisms**: `walkability_improvement`, `catchment_growth`, `competition_relief`, `complementary_use`, `footfall_injection`.
*   **Anti-Hallucination**: If the LLM claims a catalytic link is `verified`, `_verify_catalytic_links()` checks the simulation. If the Huff demand or reachable population didn't move, the system **automatically downgrades** the claim to `partially_verified` or `claimed`.

---

# Part 7: The Intervention Space

The LLM must propose plans using this strict vocabulary:

1.  **`repurpose`** — Changes the subtype (e.g., commercial → clinic). Requires `to_subtype`, or `subtype_changes` for a **partial** conversion that preserves the anchor. Partial repurpose: 6-month construction, 80% capacity retained. Full repurpose: 18 months, 0% capacity.
2.  **`renovation`** — Same-class subtype change (e.g., terrace → affordable_housing, convenience_retail → f_and_b). Preserves the shell. 6-month construction, 70% capacity retained.
3.  **`retrofit`** — Energy upgrades (HVAC, LED, cool roof, BMS, envelope, water). Does not change occupancy, but lowers OPEX and operational carbon. When `engineering_spec` is supplied, physics-driven; otherwise aggregate `energy_efficiency_gain`.
4.  **`new_development`** — New build on a vacant parcel. 36-month construction, 0% capacity until activation.
5.  **`pedestrian_upgrade` / `green_corridor`** — Spatial network interventions. Raises canopy on target edges, which lowers the canopy-weighted walking cost and improves accessibility. Optional `new_link: true` adds one footway ≤ 150 m (crossing / footbridge) — **not** the answer to a flow island.
6.  **`delay_development`** — Postpones a pipeline project to `parameters.until`.
7.  **`interim_solar_farm`** — Interim solar on an undeveloped parcel; produces a negative carbon offset.
8.  **`tenant_matching`** — SDP leasing service. `tenant_subtype` optional; engine picks by Suitability Index.
9.  **`tactical_placemaking`** — Temporary event. `kind` ∈ {night_market, weekend_market, food_truck_park, popup_sports_court, community_event_space}; `duration_years` (default 3); `permanent: true` for a lasting public space.

Every item has `role: "primary" | "catalytic"`. A catalytic item needs `catalytic_link` with `mechanism` ∈ {walkability_improvement, catchment_growth, competition_relief, complementary_use, footfall_injection} and a `verification_level` capped by what B4 can measure.

---

# Part 8: Frontend API Contract

We use a 3-API Composite Architecture to feed MapLibre and React/Vue.

1.  **`GET /api/map/geometry`**: Lightweight GeoJSON. Includes `asset_id` and `map_status` (healthy, deadspace, intervened, vacant). Used by MapLibre for coloring.
2.  **`GET /api/assets/profiles`**: Cached dictionary keyed by `asset_id`. Contains all B3/B6 metrics, trajectories, and evidence. Used for instant dashboard popups.
3.  **`POST /api/analyze`**: Triggers the B7 pipeline. Returns the selected plan, reasoning, and the 5-year timeline of before/after metrics (including Counterfactual CAPEX and Avoided Carbon).

---

# Part 9: Data Tier System & Authority Gate

## 9.1 The Tier Ladder

Every metric carries a tier. The frontend renders each as a badge (`T1`, `T2`, `3A`, `3B`, `U`) and uses it to decide presentation (as an observed fact, an estimate, or an unknown).

| Tier | Label | Meaning | Where it comes from |
|---|---|---|---|
| `1` | Observed | Direct SDP record or satellite observation. | SDP's own ledgers (occupancy, NOI), Landsat LST. |
| `2` | Derived | Physics or economic formula on observed data. | Huff demand, walkability, operational carbon, embodied carbon. |
| `3a` | Operational estimate | External proxy, valid for judgement, never stated as fact. | Google Places (presence, turnover, vitality), LBS (unique visitors, dwell, flow island), survival OPEX floor. |
| `3b` | Counterfactual | Simulation-only. Never enters deadspace detection. | "If SDP had retained this asset" NOI. |
| `U` | Unknown | No defensible source for this asset. | Any field where the developer cannot see the underlying record and no proxy exists. |

## 9.2 Authority Gate

The gate (`build_mock_data.py::_apply_authority_data_gate`) clears the operational fields of any asset not held by the developer:

```python
_AUTHORITY_REDACTED_BY_TYPE = {
    "commercial":          ("occupancy_rate", "vacancy_rate", "vacancy_duration_months",
                            "footfall_daily", "noi_rm", "noi_yield", "rental_income_rm",
                            "energy_kwh", ...),
    "residential":         ("rental_income_rm", "noi_rm", "noi_yield", "energy_kwh"),
    "community_facility":  ("rental_income_rm", "opex_annual_rm", "maintenance_annual_rm",
                            "cost_per_user_rm", "energy_kwh"),
}
```

The **pre-gate values survive** in `asset_metrics_pre_gate.csv` and `mock_truth_occupancy.csv`, but only the mock generator reads them. The app never does. The gate is what makes tier 3a and 3b honest: a sold shop's occupancy is not "0%" — it is "not visible to the developer, replaced by an LBS estimate".

## 9.3 Ownership → Authority → Tier

```
ownership_status    →  authority        →  evaluation_mode
developer_held         full_control        operating_performance
strata_jmb             shared              operating_performance (partial)
sold                   advisory            developer_realization
public_transferred     advisory            community_value_gap
```

For `advisory` assets:
- `summary_card.financial.main_metric` is **counterfactual NOI** (tier 3b).
- `summary_card.community` is populated with LBS / Google Places signals (tier 3a).
- The frontend's `applyYearMetrics` re-tiers simulated values as `3a` "estimated" if a proxy exists, `U` "assumed" otherwise.

## 9.4 Why This Matters

A standard developer dashboard would silently present a sold shop's 0% occupancy as if it were an observed fact. We do not. Every number carries its source; every simulated number carries its origin. The board-level justification explicitly says "LBS shows 5 daily visitors (subtype median 23)" — never "occupancy is 12%". This is the difference between a demo and a decision-support tool.

---

# Part 10: Implementation & Scalability Roadmap

1. **Month 0–3: Pilot & Calibrate**
   * Ingest mature township data (Bukit Jelutong) to calibrate the physics engine (Huff gravity parameters, occupancy benchmarks). Validate detection accuracy with SDP asset managers.
   * *Success metric*: Diagnostics and baseline metrics match real operational history.

2. **Month 3–6: Portfolio Optimization (Decide)**
   * Deploy on active township pipelines (e.g., Elmina). Compare the cost and carbon of reusing underperforming spaces versus building new.
   * *Success metric*: Massive CAPEX and embodied carbon savings identified before ground is broken.

3. **Month 6–18: First Catalytic Zone**
   * Execute a cluster of coordinated interventions (e.g., an anchor repurpose paired with walking upgrades). Track verified footfall and demand spillover across the neighbourhood.
   * *Success metric*: Targeted precinct vitality revives as simulated; deadspace eliminated.

4. **Year 2+: Portfolio Scale**
   * Plug in standardized databases from any SDP development (Bukit Raja, Serenia City, and beyond) to automatically maintain climate-resilient, circular living masterplans.
   * *Success metric*: Zero stranded assets across the portfolio.

---
*End of Technical Document v3.0*