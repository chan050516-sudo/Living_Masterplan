# Metrics × Authority Tier Matrix (current code)

Generated 2026-11-10 from the code and data on branch `mathaba-panel` (HEAD `ed531e7`).
Replaces `docs/matrix_old.md`. Where this file and `docs/plan_v6.md` disagree, this file reflects what the code does.

> **Updated after the profile fixes (same day).** The tables below describe the profile as it is now served. Tiers are no longer only documented here: every profile carries a `tiers` map (`"<section>.<field>": {tier, source, mock?}`) resolved from `backend/configs/field_metadata.yml`, which is now the single source of truth. Rows changed by the fixes are marked **(fixed)** or **(new)**. See `docs/DECISIONS.md` for what changed and why.

## Sources read

| Area | Files |
|---|---|
| API | `backend/app/api/main.py` (`GET /api/assets/profiles`, `GET /api/map/geometry`, `POST /api/analyze`) |
| Profile builder | `backend/scripts/build_profiles.py` (writes `business/asset_profiles_2026.json`, which the profiles endpoint serves with thermal fields refreshed) |
| B6 deadspace | `backend/app/deadspace/{detector,engine,layer1,layer2,layer3_lbs,layer3_survival,external,status,tiers}.py` |
| B3 derived metrics | `backend/app/derived/engine.py` (column list), `backend/configs/field_metadata.yml` (declared tiers and `authority_tiers`) |
| B4 simulation / analyze card | `backend/app/simulation/engine.py` (`_SOLD_METRIC_TIERS`, `_attach_proxy_state`, counterfactual NOI), `backend/app/llm/orchestrator.py` (summary_card tiers) |
| Frontend | `frontend/src/types.ts`, `frontend/src/components/AssetPanel.tsx`, `frontend/src/components/TierBadge.tsx`, `frontend/src/App.tsx` (metrics_json merge) |
| Data | `bukit_jelutong/processed/business/{assets.csv, asset_metrics_enriched.csv, asset_profiles_2026.json, deadspace_2026.json, asset_business_presence.csv, asset_lbs_metrics.csv, scenarios/SC-CURRENT.json}` |
| Docs | `docs/matrix_old.md`, `docs/plan_v6.md` §0–1 |

## Authority groups that actually exist

`authority` takes only two values in the data: `full_control` and `advisory`. The finer split comes from `ownership_status`, which `field_metadata.yml` also uses for its `authority_tiers` keys.

| Column used below | authority | ownership_status | Assets | intervention_mode | evaluation_mode |
|---|---|---|---|---|---|
| **Owned** | full_control | developer_held | 66 | always `direct` | operating_performance |
| **Sold** | advisory | sold | 778 | `collaborative` if an access flag fires, otherwise `advisory` | developer_realization |
| **Public** | advisory | public_transferred | 72 | same rule as Sold | developer_realization |

`shared` (JMB) appears in `status.decide_intervention_mode`, `field_metadata.yml` and the AssetPanel colour logic, but no asset has it. `sold` and `public_transferred` are ownership values, not authority values. Code that checks `authority == "sold"` will never match.

## Tier legend

`1` Observed · `2` Derived · `3a` Operational estimate (proxy) · `3b` Counterfactual · `U` Unknown (the field is populated but carries no information for this group) · `n/a` not available (null in the API for this group, either because of the authority gate or because the field does not apply to the asset types in that group).

Type scope is shown in [brackets] in the Source column. Tiers follow `field_metadata.yml` where it defines them, corrected for what the profile actually serves.

## Matrix — `GET /api/assets/profiles`

| Metric key (API path) | Label | Unit | How it's computed / source | Owned | Sold | Public | Pillar |
|---|---|---|---|---|---|---|---|
| `physical.floor_area_m2` | Floor area | m² | Asset register (`assets.csv`) | 1 | 1 | 1 | Physical |
| `physical.lettable_area_m2` | Lettable area | m² | Asset register; also feeds the survival OPEX floor | 1 | 1 | 1 | Physical |
| `physical.land_area_m2` | Land area | m² | Cadastral record | 1 | 1 | 1 | Physical |
| `physical.capacity` | Design capacity | count | Asset register | 1 | 1 | 1 | Physical |
| `identity.completion_year` | Completion year | year | Asset register; drives the ramp-up grace window in `status.py` | 1 | 1 | 1 | Physical |
| `financial.capex_initial_rm` | Initial CAPEX | RM | Capital record | 1 | 1 | 1 | Financial |
| `financial.opex_annual_rm` | Annual OPEX | RM | Operating record (owned); capex × fraction for others (`authority_tiers`) | 1 | 3a | 3a | Financial |
| `financial.maintenance_annual_rm` | Annual maintenance | RM | Maintenance record (owned); capex × fraction for others | 1 | 3a | 3a | Financial |
| `financial.rental_income_rm` | Rental income | RM | Internal lease record [commercial] | 1 | n/a | n/a | Financial |
| `financial.noi_rm` | Annual NOI | RM | rental − opex − maintenance [commercial]; L2 `negative_noi` | 2 | n/a ¹ | n/a | Financial |
| `financial.noi_yield` | NOI yield | ratio | noi_rm / capex [commercial] | 2 | n/a ¹ | n/a | Financial |
| `financial.dsr` | Demand–supply ratio | ratio | Huff effective demand / effective supply [commercial; 63/69 sold populated]; L1 `dsr_below_threshold` < 0.8 | 2 | 2 | n/a | Financial |
| `social.occupancy_rate` | Occupancy | ratio | Internal occupancy record [commercial, residential]; L1 `low_occupancy` < 0.5 | 1 | n/a ² | n/a | Social |
| `social.utilisation_rate` | Utilisation | ratio | Internal utilisation record [community_facility]; L1 `low_utilisation` < 0.4 | 1 | n/a | n/a | Social |
| `social.footfall_daily` | Daily footfall | person/day | Internal counter [commercial] | 1 | n/a | n/a | Social |
| `social.proxied_occupancy` | Proxied occupancy | ratio | B6 `layer3a`: LBS `proxied_occupancy_lbs`, falling back to Google `proxied_occupancy_google` [commercial] | n/a | 3a | n/a | Social |
| `social.proxied_occupancy_source` | Proxy source | enum | `kido_dynamics_mock` (all 69 today) / `google_places_mock` | n/a | 3a | n/a | Social |
| `social.lbs_unique_users_daily` | LBS daily visitors | person/day | **(fixed)** `asset_lbs_metrics.csv` [sold commercial] | n/a | 3a | n/a | Social |
| `social.lbs_dwell_minutes` | LBS dwell time | min | **(fixed)** `asset_lbs_metrics.csv` `lbs_dwell_time_minutes` | n/a | 3a | n/a | Social |
| `social.business_presence_ratio` | Business presence | ratio | **(fixed)** `asset_business_presence.csv`: operating places / designed units; half of the sold deadspace gate | n/a | 3a | n/a | Social |
| `social.external_demand_ratio` | Observed demand ratio | ratio | **(fixed)** `asset_lbs_metrics.csv` `observed_demand_ratio` (LBS users / capacity) | n/a | 3a | n/a | Social |
| `social.coverage_ratio_5min_walk` · `_10min_walk` · `_15min_walk` | Walk coverage 5/10/15 min | ratio | Share of catchment population inside the walking isochrone (OSM network). The 5-min value feeds L1 `walking_accessibility_deficit` and the 10-min value feeds green L2 | 2 | 2 | 2 | Social |
| `social.reachable_population_walk` | Reachable population (walk) | persons | Network isochrone × WorldPop | 2 | 2 | 2 | Social |
| `social.effective_demand_m2` | Effective demand | m² | Huff model allocation [commercial] | 2 | 2 | n/a | Social |
| `social.demographic_mismatch` | Demographic mismatch | 0–1 | Catchment demographics vs target demographic [commercial, community_facility]; L1 > 0.4 | 2 | 2 | 2 | Social |
| `social.neighborhood_diversity` | Neighbourhood diversity | 0–1 | Mix index around the asset [commercial, community_facility, green_space]; L1 < 0.3 | 2 | 2 | 2 | Social |
| `environmental.energy_kwh_total` | Annual energy | kWh | Meter (owned, mock); intensity × floor area for others [buildings] | 1 | 3a | 3a | Environmental |
| `environmental.energy_kwh_hvac` · `_lighting` · `_base_load` | Energy end-use split | kWh | End-use share model on total energy [buildings] | 2 | 3a | 3a | Environmental |
| `environmental.carbon_operational_tco2e` | Operational carbon | tCO₂e/yr | energy × grid factor [buildings]; null for green and parcels | 2 | 2 | 2 | Environmental |
| `environmental.carbon_productive_tco2e` | Productive carbon | tCO₂e/yr | operational × occupancy | 2 | n/a ⁴ | n/a | Environmental |
| `environmental.carbon_stranded_tco2e` | Stranded carbon | tCO₂e/yr | operational × (1 − occupancy); L1 `high_stranded_carbon` | 2 | n/a ⁴ | n/a | Environmental |
| `environmental.stranded_carbon_ratio` | Stranded carbon ratio | ratio | 1 − occupancy; L1 threshold 0.5 | 2 | n/a ⁴ | n/a | Environmental |
| `environmental.embodied_carbon_tco2e` | Embodied carbon | tCO₂e | Renamed from `embodied_carbon_total_tco2e`; taxonomy intensity × floor area (synthetic, same per subtype) | 2 | 2 | 2 | Environmental |
| `environmental.t_asset_c` | Surface temp (parcel) | °C | Landsat 8 L2 LST zonal mean (`thermal_observations.csv`, refreshed at request time); null where pixels are masked (245 assets, incl. all parcels) | 1 | 1 | 1 | Environmental |
| `environmental.t_township_c` | Township baseline temp | °C | Landsat township footprint mean | 1 | 1 | 1 | Environmental |
| `environmental.surface_temp_delta_c` | ΔT vs township | °C | t_asset − t_township; L1 `high_uhi_exposure` ≥ 3.0 °C [buildings] | 1 | 1 | 1 | Environmental |
| `environmental.apparent_temp_c` | Apparent (felt) temp | °C | LST → 1.5 m air temp (LCZ damping by type) → Steadman AT with fixed RH and wind; not used in flags | 2 | 2 | 2 | Environmental |
| `environmental.surface_temp_provenance`, `_collection_id`, `_band`, `_source_catalog`, `_valid_pixel_count`, `_period_start`, `_period_end`, `_source_image_count` | LST provenance | meta | Landsat metadata (tier null in field_metadata) | meta | meta | meta | Environmental |
| `environmental.green_coverage` | Green coverage | ratio | Green area / parcel [green_space; 39/51 populated]; L1 < 0.2 | n/a | n/a | 2 | Environmental |
| `environmental.canopy_coverage` | Canopy coverage | ratio | WRI canopy over footprint [residential, green_space]; L1 green < 0.15 | 2 | 2 | 2 | Environmental |
| `environmental.green_per_capita_m2` | Green per capita | m²/person | Green area / served population [green_space; 42/51]; L1 < 2.0 | n/a | n/a | 2 | Environmental |
| `trajectory.class` | Trajectory class | enum | 5-year occupancy history classification (`rapid_decline`, `declining`, `chronic_low`, `never_alive`, …). Feeds trajectory flags | 2 | U (always `unknown`) | U | Social |
| `trajectory.peak_occupancy` | Peak occupancy | ratio | Max occupancy over history | 2 | n/a | n/a | Social |
| `trajectory.years_since_peak` | Years since peak | years | **(fixed)** Null when there is no occupancy peak (no history, or peak 0%) | 2 | n/a | n/a | Social |
| `trajectory.occupancy_trend_3yr` | 3-yr occupancy trend | ratio/yr | Slope of occupancy | 2 | n/a | n/a | Social |
| `trajectory.vacancy_streak_months` | Vacancy streak | months | Consecutive vacancy [commercial] | 2 | n/a | n/a | Social |
| `subunits[].occupancy` | Unit occupancy | ratio | **(new)** `occupancy_by_subtype_calc_json` [owned commercial with a unit mix] | 1 | n/a | n/a | Social |
| `subunits[].area_m2`, `.design_count` | Unit mix: area / designed units | m² / count | `unit_mix_json` [commercial; 1 owned, 27 sold] | 1 | 1 | n/a | Physical |
| `subunits[].operational_count` | Operating units | count | Google Places `business_subtype_counts_json` | n/a (null) | 3a | n/a | Social |
| `subunits[].presence_ratio` | Unit presence | ratio | operational / design | n/a | 3a | n/a | Social |
| `subunits[].vitality_score` | Unit vitality | 0–1 | Google rating × log(reviews) per subtype | n/a | 3a | n/a | Social |
| `subunits[].allocated_carbon_tco2e` | Allocated carbon | tCO₂e/yr | Operational carbon × area share | 2 | 2 | n/a | Environmental |
| `subunits[].allocated_noi_rm` | Allocated NOI | RM | NOI × area share | 2 | n/a | n/a | Financial |
| `leases.anchor_lease` | Anchor lease end / area | year, m² | Active anchor row in `asset_leases.csv`; **null for every asset** in the current data | 1 (empty) | U | U | Financial |

Footnotes:

1. Sold NOI exists only on the analyze path, as the 3b fields `_noi_rm` / `_noi_yield` in `summary_card.financial.main_metric` and `summary_card.counterfactual`. The profiles endpoint never serves it.
2. Sold commercial occupancy is served as `social.proxied_occupancy` (3a), not `occupancy_rate`. In simulated years, however, `/api/map/geometry` `metrics_json` writes a proxy-seeded value into `occupancy_rate` for sold commercial assets and a **neutral 0.5 default** for sold residential (effectively U). `App.tsx` then merges that into `social.occupancy_rate` with no tier.
3. **Fixed.** `build_profiles.py` used to read these from `asset_metrics_enriched.csv`, which has no such columns. It now reads `asset_lbs_metrics.csv` and `asset_business_presence.csv` (69 sold commercial rows).
4. Null in the 2026 profile because occupancy is gated. In simulated years `metrics_json` carries 3a values for sold commercial assets (from proxy occupancy) and 0.5-default values for sold residential (U). The AssetPanel currently computes a 2026 stranded ratio on the client as `1 − proxied_occupancy` and labels it 3a.

### Fields added to the profile by the fixes

| Metric key (API path) | Label | Unit | Source | Owned | Sold | Public | Pillar |
|---|---|---|---|---|---|---|---|
| `physical.unit_count` | Units | count | Register [shown for residential] | 1 | 1 | 1 | Physical |
| `physical.developer_held_units` | Unsold units | count | Register [shown for residential] | 1 | 1 | 1 | Physical |
| `physical.developable_area_m2` | Developable area | m² | B3 [parcel] | 2 | n/a | n/a | Physical |
| `physical.potential_gfa_m2` | Buildable floor area | m² | B3 [parcel] | 2 | n/a | n/a | Physical |
| `authority.data_confidence` | Data confidence | enum | Register (high / low) | meta | meta | meta | — |
| `financial.sale_price_rm`, `financial.sale_date` | Sale price / date | RM / date | Register (synthetic transaction mock) | n/a | 1 | n/a | Financial |
| `financial.sale_profit_rm` | Profit vs build cost | RM | sale_price − capex | n/a | 2 | n/a | Financial |
| `financial.sale_return_ratio` | Return on build cost | ratio | profit / capex | n/a | 2 | n/a | Financial |
| `financial.estimated_revenue_rm` | Estimated revenue | RM/yr | B6 survival floor [sold commercial] | n/a | 3a | n/a | Financial |
| `financial.survival_opex_floor_rm` | Survival cost floor | RM/yr | B6 survival floor | n/a | 3a | n/a | Financial |
| `financial.hemorrhage_ratio` | Revenue / survival cost | ratio | B6 survival floor; < 1 raises `operating_hemorrhage` | n/a | 3a | n/a | Financial |
| `financial.cost_per_user_rm` | Cost per user | RM | B3 [community facility; owned only in data] | 2 | n/a | n/a | Financial |
| `financial.demand_supply_gap` | Demand – supply gap | m² | B3 [parcel] | 2 | n/a | n/a | Financial |
| `financial.infrastructure_cost_rm` | Infrastructure cost | RM | B3 [parcel] | 2 | n/a | n/a | Financial |
| `social.service_coverage` | Service coverage | ratio | B3 [community facility] | 2 | n/a | 2 | Social |
| `social.occupied_units` | Occupied units | count | Inventory register [residential] | 1 | n/a | n/a | Social |
| `social.vacancy_duration_months` | Vacant for | months | Internal record [commercial] | 1 | n/a | n/a | Social |
| `social.coverage_ratio_10min_drive` | Drive coverage 10 min | ratio | Network isochrone | 2 | 2 | 2 | Social |
| `social.flow_island_ratio`, `proxied_occupancy_lbs`, `traffic_exposure_vpd`, `lbs_visit_frequency_monthly` | LBS signals | various | `asset_lbs_metrics.csv` | n/a | 3a | n/a | Social |
| `social.proxied_occupancy_google`, `operational_place_count`, `business_vitality_score`, `proxied_vacancy_duration`, `business_turnover_count` | Google Places signals | various | `asset_business_presence.csv` | n/a | 3a | n/a | Social |
| `social.unit_mix_unit_count` | Consumer-facing units | count | Register, via the Places table | n/a | 1 | n/a | Social |
| `social.median_walk_distance_m` | Median walk to reach it | m | Network isochrone (was evidence-only) | 2 | 2 | 2 | Social |
| `trajectory.years_below_benchmark` | Years below benchmark | years | B3; null without an occupancy record (was evidence-only) | 2 | n/a | n/a | Social |
| `financial.maintenance_surge_rm` | Maintenance this year | RM | B3 [commercial]; input to `maintenance_surge_high` | 2 | 3a | n/a | Financial |

Still not served, because the data doesn't exist in this checkout: `leases.anchor_lease` is null for every asset (no active anchor lease rows); `cost_per_user_rm` is null for public facilities; `residential_population` exists nowhere. `lbs_hourly_splits` and `lbs_visitor_demographics` exist but are JSON blobs, so I left them out of the profile.

### Simulated years (frontend re-tiering)

`/api/map/geometry` still sends untiered simulation values for years other than 2026 (that endpoint was out of scope). The frontend re-tiers them in `frontend/src/config/metricConfig.ts` (`applyYearMetrics`):

| Asset | Occupancy-based values (occupancy, utilisation, stranded carbon, NOI) | Other values (operational carbon, canopy, walk coverage, demand) |
|---|---|---|
| Owned | served tier, T1 → T2, labelled "simulated YYYY" | served tier, "simulated YYYY" |
| Sold / public with a proxy occupancy | 3a, "estimated YYYY"; the sold-shop occupancy goes to `social.proxied_occupancy` | served tier, "simulated YYYY" |
| Sold / public without a proxy | U, "assumed YYYY", shown as "Unknown" (the simulation used a neutral 0.5 default) | served tier, "simulated YYYY" |

### Evidence strings vs profile values

The `deadspace_diagnosis.evidence` strings were generated by an older B6 run against older metrics (e.g. BLD-0037 evidence says DSR 0.93; the served `financial.dsr` is 1.04). The AssetPanel no longer renders them: each flag's evidence is the matching profile fields (`FLAG_EVIDENCE` in `frontend/src/config/metricConfig.ts`). The strings remain in the API for the LLM.

### Flag tier vs input-metric tier

| Flag | `tiers.py` | Input metric (field_metadata tier) | Correct per field_metadata |
|---|---|---|---|
| `negative_noi`, `noi_yield_below` | 1 | `noi_rm`, `noi_yield` (2) | 2 |
| `maintenance_surge_high` | 1 | `maintenance_surge_rm` (2) | 2 |
| `rapid_decline`, `falling_from_healthy`, `chronic_stagnation` | 1 | `trajectory_class` (2) | 2 |
| `high_uhi_exposure`, `uhi_data_anomaly` | 2 | `surface_temp_delta_c` (1) | 1 |

The panel shows the served `flag_tiers` unchanged; the fix belongs in `deadspace/tiers.py` (DECISIONS team-lead item 11).

### Diagnosis fields (`deadspace_diagnosis.*`): outputs, not metrics

| Key | What it is | Notes |
|---|---|---|
| `status` | healthy / monitor / deadspace_candidate / underperforming_facility / development_risk / improvement_opportunity / community_value_gap / strategic_learning | Sold commercial assets use `decide_sold_commercial_status` (proxy rules) |
| `intervention_mode` | direct / collaborative / advisory | Independent of status |
| `evaluation_mode` | operating_performance / developer_realization | Based only on full_control vs not |
| `flags`, `flag_tiers` | Raised flags; each mapped to `tier_1_observed` / `tier_2_derived` / `tier_3a_proxied` / `tier_3b_counterfactual` | The only per-item tier data the profile carries |
| `urgency_index`, `contributing_factors`, `evidence` | Weighted flag score, factor shares, human-readable lines | Thermal evidence line is injected at request time |
| `layer3a` | `proxied_occupancy`, `_source`, `triggered`, `reasons`, `flow_island_threshold` | Sold commercial only |
| `authority` | full_control / advisory | **(fixed)** Filled from the asset register by the profile builder (the B6 record still has no `authority` key). The frontend uses `authority.level` |

### Used by B6 flags but not exposed in the profile

| Field | Tier (Owned / Sold / Public) | Used for |
|---|---|---|
| `vacancy_duration_months` | 1 / n/a / n/a | L1 `long_vacancy`, residential L2 |
| `coverage_ratio_10min_drive` | 2 / 2 / 2 | L1 `driving_accessibility_deficit` (supermarket, restaurant, school, …) |
| `maintenance_surge_rm` | 2 / 2 / n/a | L2 `maintenance_surge_high` |
| `occupancy_by_subtype_calc_json` | 1 / n/a / n/a | L1 `subtype_mix_dead` / `_low` |
| `service_coverage` | 2 / n/a / 2 | Facility L2 `insufficient_coverage` (required for `underperforming_facility` unless `rapid_decline`; 22 of 23 facilities have that status) |
| `cost_per_user_rm` | 2 / n/a / n/a | Not used in flags (facility efficiency) |
| `demand_supply_gap`, `developable_area_m2`, `potential_gfa_m2`, `infrastructure_cost_rm` | 2 / n/a / n/a | Parcel L1 and L2 (`negative_demand_supply_gap`, `weak_future_demand`) |
| `proxied_vacancy_duration`, `business_turnover_count`, `business_vitality_score` | n/a / 3a / n/a | 3a flags `long_vacancy_proxied`, `business_turnover_high`, `business_vitality_low` |
| `flow_island_ratio`, `lbs_peer_*_median` | n/a / 3a / n/a | `flow_island` (an access flag, so it switches the asset to collaborative), `low_footfall_lbs`, `short_dwell_lbs` |
| `survival.estimated_revenue_rm`, `survival.survival_opex_floor_rm`, `survival.hemorrhage_ratio` | n/a / 3a / n/a | `operating_hemorrhage`, half of the sold deadspace_candidate gate |
| `unit_count`, `developer_held_units`, `occupied_units` | 1 / 1 / n/a | Not used in flags (residential inventory) |
| `sale_price_rm`, `sale_date` | n/a / 1 (mock) / n/a | Not used anywhere: the developer_realization lens has no numbers behind it |

### Analyze-path tiers (`POST /api/analyze` → `summary_card`)

| Card item | Owned | Sold / Public |
|---|---|---|
| `financial.main_metric` | "Annual NOI", tagged **tier "1"**, though field_metadata says 2 | "Counterfactual NOI (if SDP had retained)", 3b |
| `counterfactual.metrics` | — | Counterfactual NOI 3b, NOI yield 3b, Estimated revenue 3a, Survival OPEX floor 3a |
| `social.main_metric` (Space utilisation) | untagged | 3a |
| `community.lbs.*`, `business_presence_ratio`, `business_turnover_count` | — | 3a (sold commercial) |
| `environmental.main_metrics` | untagged | untagged |
| B4 comparison `_SOLD_METRIC_TIERS` | — | occupancy/utilisation/carbon productive/stranded/ratio/LBS/flow_island → 3a; noi_rm/noi_yield → 3b |

## Differences from old matrix

**Structural**

- **The deadspace invariant no longer holds.** `matrix_old` Note 1 and `plan_v6` §1.3 say only full_control can reach `deadspace_candidate`. Since v6.1g, sold commercial assets reach it when `business_presence_low` + `operating_hemorrhage` both fire (`status.decide_sold_commercial_status`). In 2026, 16 of the 61 candidates are sold commercial (15 collaborative, 1 advisory). Authority now controls only `intervention_mode`.
- **Authority columns changed.** The old columns were full_control / sold / shared / public_transferred. The real values are `full_control` and `advisory`; sold vs public comes from `ownership_status`. No asset is `shared`.
- **Sold residential** is capped at `monitor` (no proxy layer). Proxy (3a) evaluation exists only for sold **commercial** assets.

**Renamed in the API**

- `occupancy_rate` (sold, 3a) → `social.proxied_occupancy` + `social.proxied_occupancy_source`. LBS is tried first, then Google.
- `embodied_carbon_total_tco2e` → `environmental.embodied_carbon_tco2e`
- `energy_kwh` / `energy_kwh_lighting_equipment` → `energy_kwh_total` / `energy_kwh_lighting`
- `observed_demand_ratio` → `social.external_demand_ratio` (always null)
- `lbs_dwell_time_minutes` → `social.lbs_dwell_minutes` (always null)

**Tier changed**

- `noi_rm`, `noi_yield` (sold): old 3b; now **not available** in profiles. 3b exists only on the analyze path as `_noi_rm` / `_noi_yield`.
- `rental_income_rm` (sold): old 3a; now n/a. No market-rent proxy is served.
- `footfall_daily` (sold): old 3a via LBS; now n/a. The LBS replacement key exists but is always null.
- `vacancy_duration_months`, `occupied_units` (sold): old 3a; now not exposed. `proxied_vacancy_duration` is used only inside B6.
- `carbon_productive/stranded`, `stranded_carbon_ratio` (sold): old 3a; now n/a in 2026. They are 3a in simulated years only (sold commercial) or U (sold residential, 0.5 default).
- `utilisation_rate` (public): old 3a; now n/a.
- `canopy_coverage`: old 1 (observed); now 2 (field_metadata and WRI-derived).
- `trajectory.*` did not exist in the old matrix. For non-owned assets the class is U (`unknown`).

**Added (not in old matrix)**

`environmental.apparent_temp_c` (2), the eight `surface_temp_*` provenance fields, `green_per_capita_m2` (2), `trajectory.*` (5 fields), `subunits[]` with `operational_count`, `presence_ratio`, `vitality_score` (3a), `allocated_carbon_tco2e`, `allocated_noi_rm`, `proxied_occupancy_source`, and the diagnosis fields `intervention_mode`, `evaluation_mode`, `flag_tiers`, `layer3a`.

**Removed from the API (in old matrix, still computed or stored, but not served by profiles)**

`unit_count`, `developer_held_units`, `occupied_units`, `unit_mix_json` (served only as `subunits`), `sale_price_rm`, `sale_date`, `embodied_carbon_amortised_tco2e`, `maintenance_carbon_tco2e`, `coverage_ratio_*_drive`, `median_walk_distance_m`, `service_coverage`, `lease_schedule` (only `anchor_lease`, empty), the Category G proxies (`business_vitality_score`, `business_turnover_count`, `proxied_vacancy_duration`, `lbs_visit_frequency_monthly`, `lbs_hourly_splits`, `lbs_visitor_demographics`, `traffic_exposure_vpd`, `flow_island_ratio`), and survival numbers `estimated_revenue_rm`, `survival_opex_floor_rm`.

**Never implemented**

`sale_profit_rm` and `sale_return_ratio` (old 2 for sold) are not computed anywhere. `residential_population` (field_metadata 3a) is not in assets, metrics or profiles.

## Asset types

All 916 assets have `status = existing`. Eight type × authority combinations exist:

| asset_type | subtypes (count) | Owned | Sold | Public |
|---|---|---|---|---|
| commercial | kopitiam 24, restaurant 21, cafe 11, convenience_retail 8, services 5, medical_retail 4, supermarket 1 | 5 | 69 | — |
| residential | terrace 352, detached 238, semidetached 159, apartment_lowrise 10 | 50 | 709 | — |
| community_facility | school 9, clinic 8, community_hall 3, place_of_worship 3 | 2 | — | 21 |
| green_space | park 51 | — | — | 51 |
| undeveloped_parcel | vacant 9 | 9 | — | — |

`taxonomy.yml` defines more subtypes that have no assets yet: f_and_b, office, entertainment, showroom, other_commercial, library, childcare, sports_centre, public_service, apartment_highrise, affordable_housing, pocket_park, green_corridor, sports_field, water_body, solar_farm.

### Proposed top-4 core metrics (most decision-relevant first)

⚠ = not currently served by `/api/assets/profiles` (see next section).

**Commercial × Owned** (direct, operating performance)
1. `social.occupancy_rate` (1): the main L1 trigger and the input to NOI and stranded carbon.
2. `financial.noi_rm` (2): the L2 "is it earning" test; together with low occupancy it makes a deadspace_candidate.
3. `financial.dsr` (2): separates "no demand here" (repurpose) from "wrong tenant" (tenant matching).
4. `environmental.stranded_carbon_ratio` (2): the ESG cost of the empty floor space, and its own L1 flag.

**Commercial × Sold** (collaborative / advisory, proxy-judged)
1. `social.proxied_occupancy` (3a): replaces occupancy; source shown alongside.
2. `business_presence_ratio` ⚠ (3a): one half of the sold deadspace_candidate gate (`business_presence_low`).
3. `survival.hemorrhage_ratio` ⚠ (3a): the other half (`operating_hemorrhage`); answers "can the shop pay its costs?"
4. `flow_island_ratio` ⚠ (3a): an access-cause flag. It decides collaborative vs advisory, i.e. whether SDP can act (walkway) or only advise.

**Residential × Owned** (developer-held, unsold stock)
1. `social.occupancy_rate` (1): sell-through / take-up; ≤ 0.05 triggers `built_value_not_realized`.
2. `trajectory.class` (2): `rapid_decline` overrides the ramp-up grace and escalates straight to candidate.
3. `developer_held_units` / `unit_count` ⚠ (1): unsold inventory in units, which is what a sales team acts on.
4. `environmental.stranded_carbon_ratio` (2): the carbon cost of empty units while they are held.

**Residential × Sold** (advisory, capped at monitor)
1. `environmental.surface_temp_delta_c` (1): `high_uhi_exposure` is one of the few flags that can still fire here.
2. `environmental.canopy_coverage` (2): the shade/tree-planting lever SDP controls in the public realm.
3. `social.coverage_ratio_10min_walk` (2): amenity access, which SDP influences through nearby assets.
4. `sale_price_rm` ⚠ (1): the only realised-value figure under the developer_realization lens.

**Community facility × Owned** (direct)
1. `social.utilisation_rate` (1): L1 `low_utilisation`.
2. `service_coverage` ⚠ (2): L2 `insufficient_coverage`; both are needed for underperforming_facility.
3. `social.coverage_ratio_5min_walk` (2): walking access is the usual fixable cause.
4. `cost_per_user_rm` ⚠ (2): the efficiency figure needed to justify keeping, merging or repurposing the facility.

**Community facility × Public** (collaborative with MBSJ)
1. `service_coverage` ⚠ (2): the reason 20 of 21 are flagged underperforming; utilisation is gated.
2. `social.coverage_ratio_5min_walk` (2): an access deficit makes the asset collaborative (walkway fix).
3. `social.demographic_mismatch` (2): whether the service matches the catchment (e.g. school vs ageing area).
4. `environmental.surface_temp_delta_c` (1): heat exposure for users of a public building.

**Green space × Public**
1. `environmental.canopy_coverage` (2): L1 `low_canopy_coverage`, and the main cooling driver.
2. `environmental.green_per_capita_m2` (2): adequacy against the population served.
3. `social.coverage_ratio_10min_walk` (2): L2 `low_accessibility(_high_ecological_value)`.
4. `environmental.surface_temp_delta_c` (1): shows whether the park actually cools its parcel.

**Undeveloped parcel × Owned** (development_risk)
1. `demand_supply_gap` ⚠ (2): fires both L1 and L2; the build / don't-build signal.
2. `potential_gfa_m2` ⚠ (2): the scale of what can be built.
3. `social.reachable_population_walk` (2): the catchment that future use would serve.
4. `infrastructure_cost_rm` ⚠ (2): the cost side of the development decision.

For combinations with no assets today (e.g. commercial × public, any `shared`), fall back to the Sold set for that type.

## Frontend needs the API does not currently provide

> **Status after the fixes.** Resolved in the profile: items 1, 2, 3 (profile side), 6, 7, 8 (sale price, profit and return now served), 10, 11. Still open: 3 (the analyze path uses different constants), 4 (counterfactual NOI exists only on the analyze path), 5 (sold stranded carbon for 2026 is still null; the panel no longer fakes it), 9 (the geometry endpoint has no per-value source, so the frontend infers it), 12, 13 (the Landsat gaps are real data gaps).

1. **Per-metric tier in the profile.** Only `flag_tiers` exists. AssetPanel hard-codes "3a" spans. `field_metadata.yml` already has `tier` + `authority_tiers`; serve a `tiers: {path: tier}` map per asset, or the metadata file itself.
2. **LBS / Google proxy fields are always null** (`lbs_unique_users_daily`, `lbs_dwell_minutes`, `business_presence_ratio`, `external_demand_ratio`). `build_profiles.py` reads them from the wrong CSV. Also missing entirely: `flow_island_ratio`, `business_turnover_count`, `business_vitality_score`, `proxied_vacancy_duration`.
3. **Survival floor numbers** (`estimated_revenue_rm`, `survival_opex_floor_rm`, `hemorrhage_ratio`) are in `deadspace_2026.json` → `survival` but dropped by build_profiles. The analyze path computes the same labels with hard-coded constants (0.05 × RM25 × 365; RM200/m²) instead of `assumptions.yml` `survival_analysis` (defaults 0.10, RM25, 360 days, RM180/m²), so the panel and the analysis card would show different numbers.
4. **Counterfactual NOI for sold assets** exists only in `/api/analyze`. The panel's "Annual NOI" shows "—" for 850 assets.
5. **Sold stranded carbon** is null in 2026; the frontend computes `1 − proxied_occupancy` itself. The API should serve this as a 3a value.
6. **Subunit occupancy for owned assets.** AssetPanel reads `sub.occupancy` for full_control, which the API never emits, so the column always shows "—". The data exists as `occupancy_by_subtype_calc_json`.
7. **Type-specific decision metrics are missing:** `service_coverage`, `cost_per_user_rm` (facilities); `demand_supply_gap`, `developable_area_m2`, `potential_gfa_m2`, `infrastructure_cost_rm` (parcels); `unit_count`, `developer_held_units`, `occupied_units` (residential); `vacancy_duration_months`, `coverage_ratio_10min_drive`, `maintenance_surge_rm` (commercial flag inputs). Undeveloped parcels currently have almost nothing decision-relevant in the panel.
8. **Developer-realization data:** `sale_price_rm` and `sale_date` aren't served, and `sale_profit_rm` / `sale_return_ratio` aren't computed. `evaluation_mode = developer_realization` has no numbers to show.
9. **Year switching mislabels tiers.** `/api/map/geometry` `metrics_json` for 2027+ puts simulated proxy occupancy (sold commercial) and a 0.5 default (sold residential) into `occupancy_rate`, and App.tsx shows it as plain "Occupancy". The endpoint needs a tier/source per value, or separate proxy keys. It also sends only 9 metrics per year, so every other field stays frozen at 2026.
10. **`deadspace_diagnosis.authority` is always null.** Use `authority.level` or populate it in the detector.
11. **`data_confidence`** (high/low per asset) exists in `assets.csv` and plan §2.3 intends it for badge colour, but it is not served. The AssetPanel colour branch for `shared` is dead code.
12. **Inconsistent tier on owned NOI:** the analyze card tags it "1"; field_metadata says 2.
13. **Display hints:** `trajectory.class = "unknown"` and `years_since_peak` are populated for all non-owned assets. The API should send null, or the UI should hide them. 245 assets have no Landsat reading (`t_asset_c` null), including all parcels.
