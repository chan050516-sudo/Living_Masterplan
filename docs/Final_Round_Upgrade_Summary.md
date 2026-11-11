# Living Masterplan — Final Round Upgrade Summary

*Sime Darby Property University Hackathon 2026 · Team Airost*

---

## 1. Executive Summary

Living Masterplan has always been a **deterministic township decision engine** — physics and economics computed by models, reasoning performed by the LLM. The final round was not about adding features. It was about making the engine **defensible in front of an auditor, a board member, and a real township's ownership map**.

The final round delivered four structural shifts:

1. **Every number is now auditable.** Synthetic proxies for temperature and canopy were replaced with satellite observations (Landsat 8 L2, Sentinel-2 via WRI, WorldPop). Operating signals for assets the developer does not own were replaced with two independent external data feeds (Google Places and LBS mobile location data). Every served metric now carries a provenance tier — Observed, Derived, Operational Estimate, Counterfactual, or Unknown — that the UI and the LLM both respect.

2. **The system now respects what Sime Darby actually controls.** A mentorship session during the final round revealed that, outside of integrated developments, most SDP assets are sold, strata-titled, or transferred to a public authority. The engine was rebuilt around this reality: three authority levels instead of two, a proxy-diagnostic layer for sold assets, a survival-floor test that does not require internal records, and a soft-intervention vocabulary that matches SDP's real operating services (tenant matching, interior design consultancy, placemaking).

3. **The simulation now couples physics to time and authority.** Construction phases carry an explicit capacity ratio; leases renew with a 75% probability per three-year term rather than expiring cleanly; unsold residential inventory decays cumulatively; intervention effects are damped by an empirically supported access-to-use conversion (Ewing & Cervero meta-analysis); canopy cooling is derived from a 679-asset Landsat regression; and every simulated year is re-diagnosed by the detector, not inherited from 2026.

4. **The LLM was demoted from "plan generator" to "plan advocate."** In the final round it produces two-to-three candidates, all of which are validated against twenty-plus rules and physically simulated. A catalytic claim that does not move a measurable metric is automatically downgraded. The LLM then selects the winner and writes the board-level justification from the simulated outcomes, not from imagination.

The product story is unchanged: **reuse before rebuild**. What changed is that the story now rests on satellites, not assumptions.

---

## 2. The Anchor Insight: Authority as a First-Class Constraint

The final round's most consequential change came from a mentorship conversation, not a code review.

Outside integrated developments, most Sime Darby Property assets are **not under SDP's direct control**. Shoplots have been sold to individual investors. Office floors are strata-titled and governed by a JMB. Community halls and clinics have been handed to the local authority. In all these cases the developer:

- **cannot see** internal occupancy, leases, footfall, income, or energy records; and
- **cannot execute** structural interventions without third-party approval.

The pre-final system treated authority as a filter applied after diagnosis. The final system treats it as a **first-class data problem**:

- A dedicated **proxy diagnostic layer** was added that judges sold assets using only what SDP can obtain externally.
- The data gate that withholds operational records from sold and public-transferred assets is enforced at the mock-data generation stage — the app never receives what the developer should not see.
- The intervention vocabulary was expanded with two **soft interventions** modelled on SDP's real business services. When SDP cannot repurpose a sold shoplot, it can still offer the landlord a tenant match from SDP's tenant pool, or an interior design and fit-out consultation, or a placemaking event on adjacent land. These are now simulation-native, not footnotes.

The narrative consequence: the engine no longer pretends the developer is omnipotent. It shows exactly what SDP can do, what SDP can recommend, and what SDP can only learn from.

---

## 3. Data Authenticity Upgrade

### 3.1 Landsat 8 Collection 2 Level-2 Thermal Observations

The previous UHI signal was a synthetic formula. The final engine reads **observed land surface temperature** per asset footprint from Landsat 8 Level-2 surface temperature bands (Collection `LANDSAT/LC08/C02/T1_L2`, band `ST_B10`), composited from multiple clear-sky acquisitions into a per-pixel median, converted to Celsius with the published calibration `(DN × 0.00341802 + 149.0) − 273.15`. Cloud, cirrus, and shadow pixels are masked via the QA band. Zonal statistics against each asset's building footprint produce:

- parcel mean surface temperature,
- township baseline (union of all footprints),
- per-asset deviation ΔT = T_asset − T_township.

Every served temperature carries the acquisition window, valid pixel count, and source catalog so that any figure can be traced back to a specific scene list.

### 3.2 WRI Tropical Tree Cover

Tree canopy in Malaysian townships is rarely mapped by OpenStreetMap. The previous system reported **89.8% of assets at exactly 0% canopy**, and mislabelled grassland parks as fully shaded — physically impossible, as those parks measured *hotter* than the township baseline. The final engine replaces OSM canopy with the **WRI Tropical Tree Cover** dataset (Sentinel-1 / Sentinel-2 fusion, 10 m resolution, 2020), extracted via Google Earth Engine and aggregated per footprint. Zero-canopy assets dropped from 89.8% to 33.1%; the median asset now carries 40% canopy, with green spaces at 51% and commercial assets at 22% — both physically plausible.

### 3.3 WorldPop Population

Population exposure is now sourced from **WorldPop Malaysia 2026** (constrained, 100 m), aggregated to the township's 400 m grid and scaled by the residential unit capacity of each cell. This replaced the previous synthetic population layer entirely.

### 3.4 External Operating Signals (Google Places + Kido LBS)

For assets the developer does not own, the engine reads two independent external feeds:

- **Google Places** — quarterly snapshots of every consumer-facing unit in a sold commercial asset: business status (operational / closed / replaced), rating, review count, and category. From these we derive *business presence ratio*, *vitality score* (rating × log of review count, min-max normalised), *turnover count*, and a *proxied occupancy* figure.
- **Kido-style mobile location data (LBS)** — weekly foot traffic at both the asset's point-of-interest and the surrounding 400 m grid: daily unique visitors, average dwell time, hourly distribution, visitor age and socioeconomic mix, and vehicle traffic flow.

A third derived signal, the **flow-island ratio**, compares footfall reachable through the mapped street network against footfall present in the surrounding neighbourhood. Below 0.3 the asset is *network-isolated*: people are nearby, but streets, walls, or drains do not let them reach the shop.

These feeds agree with the internal record by construction (the mock generator seeds them from a hidden pre-gate occupancy truth), but the app itself never sees that truth. This is what makes the proxy layer honest.

### 3.5 Data Provenance Tiering

Every served metric is tagged with one of five tiers:

| Tier | Meaning |
|---|---|
| **T1 — Observed** | Direct record or measurement (SDP's own records, Landsat, WorldPop) |
| **T2 — Derived** | Computed from Tier 1 inputs by a documented formula |
| **3A — Operational estimate** | External proxy (Google Places, LBS) used for judgement, never stated as fact |
| **3B — Counterfactual** | "If SDP had retained the asset" — simulation narrative only |
| **U — Unknown** | No defensible source for this asset |

Tiers are resolved per asset, per authority level: the same field is Tier 1 for a developer-held asset and Tier 3A for a sold one. The front end displays a small badge next to every figure, and the LLM prompt is instructed never to present a 3A estimate as observed fact.

---

## 4. Diagnostic Engine: From Two Layers to Four

The deadspace detector was rebuilt into four ordered layers.

### 4.1 Layer 1 — Underperformance (expanded)

The existing occupancy, vacancy, demand-supply-ratio, stranded-carbon, and demographic checks were joined by:

- **Early-warning occupancy band** — assets below 85% of their subtype's benchmark but above the hard 50% floor now surface as *below-benchmark occupancy*, catching gradual decline before it becomes failure.
- **Green-space diagnostics** — `low_green_coverage`, `low_canopy_coverage`, `low_green_per_capita`. Previously green space was exempt from all "below benchmark" diagnosis.
- **Subtype-mix diagnostics** — a mall whose supermarket is at 95% but whose entire F&B floor is at 8% now raises `subtype_mix_dead`, because the aggregate occupancy hides a real partial death.
- **UHI exposure** — the observed Landsat ΔT threshold was recalibrated from a synthetic 7.0 °C (never reachable on real data) to a data-driven **3.0 °C**, based on the P90 and P95 of the observed ΔT distribution. Approximately 50 assets (7.4% of the township) now correctly flag as severe UHI hotspots.

### 4.2 Layer 2 — Low Value Realisation (expanded)

- **Residential branch** — a built unit that houses no one (`built_value_not_realized`) now correctly fails Layer 2. Previously residential could never satisfy the L1-and-L2 gate and could never reach a deadspace status.
- **Community-facility gate** — the facility now requires both Layer 1 and Layer 2 (utilisation *and* service coverage), not just a single utilisation flag. A small facility serving a small catchment has low utilisation *by construction*, not by failure.

### 4.3 Layer 3a — Proxy Diagnostics (new)

A dedicated layer that runs only on sold or advisory commercial assets, using the external signals described in §3.4:

- **Business presence low** — most units are empty per Google Places.
- **Footfall low** — LBS daily visitors well below the subtype peer median.
- **Dwell short** — visitors leave faster than the subtype's peers.
- **Flow island** — footfall is nearby but the street network does not deliver it.
- **Operating haemorrhage** — the shop cannot physically pay its costs (see §4.4).
- **Data conflict** — Google Places and LBS disagree, so neither can be trusted alone.

### 4.4 Survival Floor (new)

A standalone economic test that does not require internal records:

- **Estimated annual revenue** = daily LBS visitors × conversion rate (per subtype) × average spend (per subtype) × operating days (per subtype).
- **Survival OPEX floor** = lettable area × minimum cost per m² (per subtype, Klang Valley levels) × inflation index.

When estimated revenue falls below the floor, the flag **`operating_hemorrhage`** fires. This is a first-of-its-kind early-warning for a bleeding shop that no occupancy record would have caught, because the developer cannot see the record.

### 4.5 Authority, Status, and Intervention Mode

Three changes to the authority model:

- Authority levels expanded from two (`full_control` / `advisory`) to **three**: `full_control`, `shared` (strata/JMB), and `advisory`.
- Two new statuses were added for sold assets whose proxy evidence shows real operating trouble:
  - **`community_value_gap`** — the asset is struggling *and* hard to reach; a concrete collaboration path exists (walkway or placemaking).
  - **`strategic_learning`** — the asset is struggling although it is easy to reach; the cause is demand or design, not reachability, so the lesson is architectural.
- **`intervention_mode`** became a first-class field, orthogonal to status: `direct` (SDP can execute), `collaborative` (SDP can act with the owner), `advisory` (SDP can only recommend). A genuine deadspace whose mode is `advisory` is still deadspace — the mode tells you *what SDP can do*, not *whether it is a problem*.

---

## 5. Simulation Engine: Physics, Authority, and Time

### 5.1 Construction Capacity Ratio

The pre-final model represented construction as "occupancy drops to zero while under construction," which is physically false — existing tenants and residents do not disappear when scaffolding goes up. The final model separates two independent fields:

- **`occupancy_rate`** — how many people use the asset.
- **`operational_capacity_ratio`** — how much of the physical asset is usable during the intervention (0% for a full repurpose, 60% for a retrofit, 100% for a walkway upgrade).

Effective utilisation during construction is `min(occupancy, operational_capacity_ratio)`. An 18-month repurpose no longer wipes the asset's occupancy record.

### 5.2 Lease Renewal and Developer Sell-Off

Two decay bugs were fixed:

- **Lease renewals.** Every lease that expired was previously treated as "tenant leaves," which cascaded a well-let mall from 86% to 15% occupancy over seven years. In real townships 70–80% of commercial tenants renew. The engine now simulates a **75% renewal probability per three-year term**, seeded per lease so it is stable across runs.
- **Developer sell-off.** The pre-final iterative decay `round(2 × 0.85) = 2` never cleared a two-unit unsold inventory. The final engine uses a **cumulative decay**, so `2 × 0.85⁷ = 0.64 → 1 remaining`, and `2 × 0.85⁸ = 0.32 → 0 remaining`. The unsold stock now monotonically drains as it should.

### 5.3 Per-Subtype Huff Pools

A mall's supermarket and its F&B shops compete in independent Huff pools with different competition radii. The pre-final simulator collapsed every subtype in a mall into the *primary* subtype's pool, silently doubling the mall's effective demand between 2026 and 2027. The final engine rebuilds the Huff supply pool from the **effective** mix each simulated year, so 2026 (baseline) and 2027 (post-intervention) are directly comparable.

### 5.4 Engineering-Spec Cooling and Rooftop PV (new)

Interventions can now carry a **seven-field engineering specification**:

- *Structure retention ratio* (0–1)
- *Facade action* (retain / insulated overclad / curtain wall / timber clad)
- *Primary material* (standard concrete / GGBS concrete / mass timber / recycled steel)
- *Roof intervention* (none / cool roof / green roof / solar canopy)
- *HVAC coefficient of performance* (2.0–6.0)
- *Weekly operating hours* (20–168)
- *Rooftop PV coverage* (0–0.9)

Two physical models are driven by this spec:

- **Cooling load** scales with `(T_ambient − setpoint) / 19 °C` × `(3.0 / HVAC_COP)` × `(hours / 70)`. A retrofit with COP 4.2 and cool roof on a 43.7 °C surface consequently reduces cooling energy by ~30–40%, not by an arbitrary multiplier.
- **Rooftop PV** generates `footprint × coverage × 0.18 panel efficiency × 4.2 kWh/m²/day × 365`, which is directly deducted from operational energy before carbon conversion.
- **Roof cooling relief** reduces the local ambient temperature by 1.5 °C (cool roof), 2.2 °C (green roof), or 1.8 °C (solar canopy) before the cooling load is computed.
- **Avoided embodied carbon** becomes spec-aware: when a "repurpose" retains less than 10% of the structure, the engine honestly claims *zero* avoided carbon — the intervention is, in physics terms, a rebuild.

### 5.5 Soft Interventions (new)

Two intervention types were added, modelled on SDP's documented business services:

**Tenant matching.** For a single failing shoplot, the engine ranks candidate tenant types by a **Suitability Index**:

- 45% demand — the Huff demand-to-supply ratio for that tenant type at the location
- 30% room — how few same-type shops already sit inside the type's competition radius
- 25% anchor — a footfall-generating type (café, kopitiam, convenience store, restaurant) scores higher

The engine then simulates leasing as a yearly *vacant → leased* Markov step with success probability `p = clip(0.25 + 0.50·S + 0.20·footfall_percentile, 0.10, 0.90)`. A leased anchor also lifts the Huff attractiveness of shops within 200 m. Every soft outcome reports the **street survival rate** (share of shops within 300 m at ≥ 50% occupancy) before and after — a measurable pitch for the landlord.

**Tactical placemaking.** A temporary magnet (night market, weekend market, food-truck park, pop-up sports court, community event space) placed at or next to the target for three years by default. Every commercial asset within 400 m receives a footfall multiplier `1 + mass·(1 − d/radius)`, where `mass` depends on the event kind. When the event ends, the effect ends — the model is explicit about the temporary nature of placemaking.

### 5.6 Proxy State for Sold Assets (new)

Without this change, a sold asset's LBS footfall would freeze at its 2026 snapshot, and any `walkability_improvement` catalytic claim would be unverifiable in later years. The engine now writes a proxy state per year for every sold commercial asset, propagating footfall from walking-access change with the same access-to-use conversion used elsewhere:

`users_y = users_base × (1 + conversion × Δcoverage_10min_walk / coverage_base)`

### 5.7 New Development as Dual Supply-and-Demand

A new residential project now contributes **residents** to the Huff demand pool (previously it only contributed carbon to the ledger and nothing else). A new commercial project contributes **competing supply**. Both roles are needed before a `catchment_growth` catalytic claim can be measured.

### 5.8 Per-Year Diagnosis Re-Run (new)

The detector is now re-run against every simulated year, not just 2026. Trajectory features (peak, trend, years-since-peak) are rebuilt from the *simulated* history, and every year's record is written to `deadspace_{scenario}_{year}.json` so the year selector in the UI has a full diagnosis to display. Previously a two-flag placeholder branch on the map endpoint collapsed a two-hundred-asset flagged population on 2026 to fewer than eighty on 2027, telling the opposite story from the one the demo needs.

### 5.9 Carbon Sequestration and Net Carbon (new)

The township metric block now reports, in addition to operational and embodied carbon:

- **Yearly sequestration** — `canopy area × 0.0015 tCO2e/m²/year` (IPCC tropical forest NPP, conservative urban soil correction)
- **Cumulative sequestration** over the simulation window
- **Net carbon** = operational − sequestration, per year

Sequestration is deliberately kept *outside* `carbon_operational_tco2e`, because removing CO₂ is a physical process, not an emission stream; mixing them would corrupt the primary comparison.

### 5.10 Counterfactual NOI for Sold Assets (new)

The developer cannot see a sold asset's actual income. The simulation therefore computes a **counterfactual NOI** for sold assets — "if SDP had retained this asset, its NOI would be …" — using market rent per m² (from the taxonomy), a location factor derived from walkable coverage, estimated OPEX, and estimated maintenance. The metric is labeled Tier 3B (counterfactual) throughout, and the LLM prompt explicitly forbids describing it as the owner's real income.

---

## 6. LLM Orchestrator: Generate → Validate → Simulate → Select → Defend

The four-stage pipeline (intent → generate → validate-and-simulate → select-and-justify) is unchanged in structure. Every stage was substantially strengthened.

### 6.1 Expanded Context Pack

The context pack that the LLM receives now includes:

- **Township baseline** — asset counts, oversupplied subtypes (by mean occupancy across at least three shops), commercial average occupancy split between *developer-held* and *sold-estimate*, deadspace candidate count, walk coverage, total operational carbon.
- **Spatial rings** — 0–400 m, 400–800 m, 800–1200 m; each ring lists *dead competitors* and *healthy anchors* with subtypes, occupancy, and distance.
- **Detailed neighbours** — up to 25 non-residential neighbours with subtype, occupancy (or proxy), status, floor area, lease expiry, and authority.
- **Subtype mix** — for mixed-use assets, both the *actual* and the *target* occupancy per subtype (the target is what Huff demand says the subtype *could* sustain today), plus a per-subtype failure diagnosis: **healthy**, **supply-side** (demand exists, but tenants are not there), **demand-side** (the target is itself low — no amount of tenant churn will fix it), or **unknown**.
- **Trajectory** — structured block: class, peak, years-since-peak, 3-year occupancy trend, vacancy streak.
- **Lease schedule** — total leases, next expiry year, anchor lease details, expiry calendar.
- **Authority split** — executable / requires approval / collaborative / recommendation only, plus a short note explaining why some actions are not executable.
- **External signals** — every proxy field with an explicit *source* string, so the LLM cites "LBS shows X" rather than "occupancy is X%."
- **Engineering-spec vocabulary** — allowed enum values and typical magnitudes for each of the seven P1 fields.
- **Soft-intervention vocabulary** — what tenant matching and placemaking take, and what the simulation measures.

### 6.2 Validator Expansion (20+ checks)

The proposal validator now enforces:

- Subtype legality and budget.
- Construction start not earlier than the base year.
- No duplicate asset in a single plan.
- No two repurposes of the same subtype within shared competition radius.
- Authority boundaries: hard actions on non-full_control assets raise a warning tied to the correct authority tier.
- Mixed-ownership warnings when a repurpose targets a multi-unit asset with some units already sold.
- The seven-field engineering spec — each field range, each enum, plus physics warnings (e.g. `structure_retention_ratio < 0.20` suggests `new_development` instead of `repurpose`).
- Measure-level retrofit breakdown — CAPEX ranges, energy-gain ranges, subsystem enums.
- Partial repurpose via `subtype_changes` — same asset class on both ends, area within current, primary subtype does not flip the asset class.
- `tenant_matching` restricted to single shoplots (a mall must use `subtype_changes`).
- Placemaking kind enum.
- **Catalytic link coherence** — the mechanism must match the delivering intervention. A `walkability_improvement` delivered by a non-spatial intervention is automatically downgraded to `partially_verified`; a `competition_relief` delivered by an intervention that leaves the competitor in the pool is downgraded to `claimed`.
- **"We will" phrasing warning** on non-full-control assets.

### 6.3 Catalytic Effect Scoring (new)

Every catalytic plan item is verified against the simulation after it runs. The verification produces a structured effect score:

`effect_score = (primary_delta_pct × 0.6 + secondary_delta_pct × 0.4) × verification_weight`

where `verification_weight` is 1.0 for *verified*, 0.5 for *partially_verified*, and 0.1 for *claimed*. A candidate whose catalytic claim cannot be measured receives a tenth of the weight of a verified claim with the same delta. This is what prevents an unmeasurable "hoped-for" claim from dominating the selection stage.

### 6.4 PDF Attachments (new)

`POST /api/analyze` now accepts PDF attachments alongside the query. PDFs are passed to the LLM as multimodal input; text/CSV/MD are parsed locally and prepended to the prompt. The demo scenario attaches a feasibility-and-constraints summary (CAPEX ceiling, continuous-operation mandate, anchor lease through 2031, structural-retention mandate, MEP limits) and the LLM generates a plan that explicitly respects all of them.

### 6.5 Validator Feedback Loop (new)

If all candidates fail validation, the orchestrator collects the rejection reasons, feeds them back to the generator, and re-prompts once (up to two attempts). If the second attempt also fails, the run returns a structured error rather than a silent empty plan.

### 6.6 Structured Output Reliability

The structured-output path was reworked to remove a hard hang that occasionally occurred with the previous server-side schema submission. The engine now serialises the schema as text, sets JSON-mode, and recovers the JSON from the response defensively (clean, fenced, or embedded). This trades strict decoding for predictable latency and does not change plan quality.

---

## 7. Intervention Vocabulary: 7 → 10

| Intervention | Pre-final | Final | Notes |
|---|---|---|---|
| Repurpose | ✅ | ✅ | **+ partial repurpose** via `subtype_changes`, which converts only the dead subtype area while preserving the healthy anchor |
| Retrofit | ✅ | ✅ | **+ measure breakdown** and **+ engineering spec** for physics-driven energy and carbon |
| **Renovation** | ❌ | ✅ | Same-class subtype change (terrace → affordable housing, shoplot → kopitiam, hall → library); six months, 70% capacity retained |
| New development | ✅ | ✅ | **+ dual role** — delivers residents to demand and GFA to supply |
| Pedestrian upgrade | ✅ | ✅ | **+ new link** option (adds one ≤150 m footway to bridge a flow island) |
| Green corridor | ✅ | ✅ | Same as pedestrian upgrade |
| Delay development | ✅ | ✅ | Asset-id targeting via parcel resolution |
| Interim solar farm | ✅ | ✅ | Unchanged |
| **Tenant matching** | ❌ | ✅ | Soft intervention modelled on SDP's real tenant-matching service |
| **Tactical placemaking** | ❌ | ✅ | Soft intervention modelled on SDP's real placemaking / interior design offerings |

---

## 8. Frontend Upgrades (four items)

The front-end received four focused enhancements in the final round; the 3D map, year selector, Ask-AI flow, history panel, and comparison modal were already present in the pre-final build.

1. **Intervention visualisation.** Every accepted or previewed intervention now renders its physical footprint on the 3D map — scaffolding for renovation, a rooftop terrace for repurpose, a rooftop garden and tree ring for green corridor, a paved forecourt for pedestrian upgrade, a solar-panel array for retrofit, an outline for new development, a hatched ground for delay, and large-scale panels for interim solar farm. A ground-level **cooling halo** is drawn around each intervention, sized by the simulated surface-temperature reduction. Catalytic links are drawn as dashed arcs from the acting site to the beneficiary.

2. **Asset Panel with three tabs.** The panel now separates **Diagnosis** (flag-by-flag evidence, weighted, expandable), **Metrics** (four collapsible pillars: Physical / Environmental / Financial / Social), and **Tenancy** (subtype occupancy mix and external operating signals for sold assets). The change makes a two-hundred-item diagnosis readable on a laptop screen.

3. **Deadspace list grouped by execution mode.** The flagged-asset list now leads with the assets SDP can act on *directly*, followed by those where SDP can *collaborate*, followed by those where SDP can only *advise*. A small legend at the top of the list states the three counts. This directly reflects the mentorship insight that the developer's execution power is not uniform.

4. **Mobile adaptation.** Bottom-sheet asset panel, side-drawer for the flagged list and history, reduced 3D pixel ratio, and reduced tree instance count — so a decision-maker can open the map on a phone during a site walk.

---

## 9. Engineering Robustness

The final round also paid down engineering debt that had become visible during the demo:

- **Cross-candidate shared cache** — pipelines, geometry, derived metrics, and baseline diagnostics are computed once per run and reused by every candidate, so the cost of generating three candidates is closer to one.
- **Network-version tagging by parameter hash** — two candidates that both label their first intervention `INT-LLM-001` no longer collide on the same pipeline cache.
- **NaN-safe arithmetic throughout** — Huff attractiveness, comparison blocks, and JSON output all pass through NaN guards, so a single missing field cannot blank an entire board-level report.
- **Authority gate at the mock-data generation stage** — sold-asset operational records never enter the app process; they are never withheld at the API boundary, because they are never generated.
- **Per-year diagnosis cache** — for candidate scenarios, only the intervened assets are re-diagnosed each year; the rest reuse the baseline diagnosis.

---

## 10. Closing

The pre-final story was: **deadspace is capital that has been spent and is not returning value.** The final-round story is the same, but the word *capital* now carries three specific, auditable kinds:

- **Financial** — computed from leases, occupancy, OPEX, and market rent.
- **Environmental** — derived from Landsat surface temperature, WRI canopy, CIDB material intensities, and Suruhanjaya Tenaga grid factors.
- **Social** — derived from WorldPop residents, the Huff demand model, and the survival-floor test for sold commercial assets.

And crucially, the final-round story acknowledges that **the developer does not always have the power to act.** The engine is honest about which interventions SDP can execute, which require the owner's consent, and which are recommendations only. Where SDP cannot rebuild, it can still match a tenant, offer an interior design consultation, or run a placemaking event — because those are the services a real township operator runs.

The product claim is unchanged in spirit and stronger in evidence:

> *"Reuse, improve, or build? Ask before adding carbon."*

The final-round upgrade made the answer to that question reachable even for the assets SDP no longer owns.