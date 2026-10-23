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
*   **Embodied Carbon**: Sourced from **CIDB Embodied Carbon Inventory Data for Construction Materials (Malaysia)**. Uses taxonomy-specific material intensities (e.g., 0.26 tCO2e/m² for affordable housing vs 0.45 for commercial).
*   **Operational Carbon**: Energy Intensity × Grid Emission Factor (**Suruhanjaya Tenaga 2022-2024: 0.769 kgCO2e/kWh**).
*   **UHI Proxy**: Modeled using canopy cooling effects (`UHI_CANOPY_COOLING_C = 4.5°C`).
*   **Canopy Growth**: Uses an asymptotic geometric model based on the **UPM Urban Forest Study (Putrajaya)**, simulating 2.5% annual growth toward a 60% ceiling.

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

1.  **`repurpose`**: Changes the subtype (e.g., commercial → clinic). Requires `to_subtype`.
    *   *Partial Repurpose (`subtype_changes`)*: Converts only a specific dead floor (e.g., 600m² F&B → medical) while preserving the healthy anchor. Takes 6 months, 80% capacity retained.
2.  **`renovation`**: Same-class upgrade (e.g., terrace → affordable housing). Takes 6 months, 70% capacity retained.
3.  **`retrofit`**: Energy upgrades (HVAC, LED, Cool Roof). Does not change occupancy, but lowers OPEX and carbon.
4.  **`new_development`**: New build on a vacant parcel (P-VAC).
5.  **`pedestrian_upgrade` / `green_corridor`**: Spatial network interventions. Modifies the walking graph, improving accessibility.
6.  **`delay_development`**: Postpones a pipeline project to 2033.
7.  **`interim_solar_farm`**: Interim use for undeveloped parcels to generate negative carbon offsets.

---

# Part 8: Frontend API Contract

We use a 3-API Composite Architecture to feed MapLibre and React/Vue.

1.  **`GET /api/map/geometry`**: Lightweight GeoJSON. Includes `asset_id` and `map_status` (healthy, deadspace, intervened, vacant). Used by MapLibre for coloring.
2.  **`GET /api/assets/profiles`**: Cached dictionary keyed by `asset_id`. Contains all B3/B6 metrics, trajectories, and evidence. Used for instant dashboard popups.
3.  **`POST /api/analyze`**: Triggers the B7 pipeline. Returns the selected plan, reasoning, and the 5-year timeline of before/after metrics (including Counterfactual CAPEX and Avoided Carbon).

---

# Part 9: Implementation & Scalability Roadmap

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