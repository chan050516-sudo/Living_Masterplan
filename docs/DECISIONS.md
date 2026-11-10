# Decisions: AssetPanel refactor and profile fixes

Branch `mathaba-panel`, 2026-11-10. Scope: backend limited to the profile build behind `GET /api/assets/profiles`; frontend refactored freely. Companion docs: `docs/metrics_matrix.md` (what each metric is and its tier per authority) and `docs/frontend_review.md` (issues found elsewhere in the frontend, not fixed).

## Backend: profile build

### D1. `field_metadata.yml` is the single source of truth for tiers
- **What.** `build_profiles.py` now resolves a tier and source for every non-null metric from `backend/configs/field_metadata.yml`. Each profile carries `tiers: {"<section>.<field>": {"tier", "source", "mock"?}}`.
- **Resolution rules:**
  - Start from the field's `tier`.
  - Override it with `authority_tiers[ownership_status]`, falling back to `authority_tiers[authority]`.
  - Serve metadata tier `4` as `"U"`.
  - A value of the string `"unknown"` (e.g. `trajectory.class`) is always `"U"`.
  - Null values get no entry, so the frontend hides them.
  - `mock: true` mirrors the metadata's `is_mock` flag.
- **Why.** The frontend was hard-coding "3a" spans, and tiers lived only in docs. One YAML file now drives both the API and the UI.
- **Field names.** Profile paths map to metadata keys by leaf name, except a short rename table (`_META_KEY_OF`, e.g. `environmental.embodied_carbon_tco2e` → `embodied_carbon_total_tco2e`) and the `subunits.*` → `subunit_*` convention. The build prints a warning for any served metric without a metadata entry; there are none today.
- **New `profile_fields:` section** in `field_metadata.yml`. It covers fields the profile derives or renames: `proxied_occupancy`, energy split, carbon productive/stranded, `apparent_temp_c`, trajectory, survival floor, sale profit/return, subunit fields.
  - I kept these out of `asset_metrics` on purpose: `generate_mock_data.py` uses that section's keys as its CSV column list, so adding them there would change the mock generator.
  - Nothing else reads `field_metadata.yml` (`config.load_field_metadata()` has no callers).
- **Payload cost.** The raw JSON grew from 3.2 MB to 7.5 MB, but gzip brings it to 0.24 MB, and `GZipMiddleware` is already on. I kept per-asset entries over a shared lookup table so each asset stays self-describing and `profilesData[id]` stays a flat map.
- **Files:** `backend/scripts/build_profiles.py`, `backend/configs/field_metadata.yml`, `bukit_jelutong/processed/business/asset_profiles_2026.json` (regenerated).

### D2. External proxies read from their own tables
- **What.**
  - LBS fields come from `asset_lbs_metrics.csv`, Google Places fields from `asset_business_presence.csv`, both joined by `asset_id`.
  - The four requested keys keep their existing names: `lbs_unique_users_daily`, `lbs_dwell_minutes`, `business_presence_ratio` and `external_demand_ratio` (from `observed_demand_ratio`).
  - Also added: `flow_island_ratio`, `proxied_occupancy_lbs`, `proxied_occupancy_google`, `traffic_exposure_vpd`, `lbs_visit_frequency_monthly`, `operational_place_count`, `unit_mix_unit_count`, `business_vitality_score`, `proxied_vacancy_duration`, `business_turnover_count`. The signals panel and the sold-shop core metrics need these.
- **Why direct CSV reads rather than `deadspace/external.external_for()`.** `external_for` adds peer medians and is cached for B6. The profile only needs the raw values, and reading the CSVs keeps the build self-contained and leaves B6 untouched.
- **Result.** 69 sold commercial assets now carry real proxy values. They were null for all 916 assets before.

### D3. Survival-floor values stay in the profile
- **What.** `deadspace_2026.json` `survival.{estimated_revenue_rm, survival_opex_floor_rm, hemorrhage_ratio}` are served as `financial.*` metrics (tier 3a).
- **Why.** `operating_hemorrhage` is half of the sold-shop deadspace gate, so the panel needs the numbers behind it. They live in `financial`, not inside `deadspace_diagnosis`, so they get a tier and a pillar like any other metric.

### D4. Per-subtype occupancy for the subtype table
- **What.** `subunits[].occupancy` comes from `occupancy_by_subtype_calc_json` (owned only; null for sold, matching the authority gate).
- **Why.** The owned-asset table read `sub.occupancy`, which was never sent, so the column always showed "—". Only `BLD-0037` is an owned asset with a unit mix today. The other owned shops are single-subtype and have no table.

### D5. Type-specific metrics added where data exists
- **Added:**
  - Facility: `social.service_coverage`, `financial.cost_per_user_rm`.
  - Parcel: `financial.demand_supply_gap`, `physical.developable_area_m2`, `physical.potential_gfa_m2`, `financial.infrastructure_cost_rm`.
  - Residential: `physical.unit_count`, `physical.developer_held_units`, `social.occupied_units`.
  - Sold assets: `financial.sale_price_rm`, `sale_date`, `sale_data_source`.
  - Flag inputs: `social.vacancy_duration_months`, `social.coverage_ratio_10min_drive`.
  - Badge colour: `authority.data_confidence`.
- **Derived in the build:** `financial.sale_profit_rm = sale_price − capex` and `sale_return_ratio = profit / capex`, tier 2, mock (it's built on the mock sale price). The old matrix listed both; no code computed them; the ported signals panel shows them.
- **Left out because the data doesn't exist:**
  - `leases.anchor_lease`: no active anchor lease rows.
  - `cost_per_user_rm` for public facilities: null in B3.
  - `residential_population`: not in any table.
  - Counterfactual NOI: produced only on the analyze path, which was out of scope.

### D6. Small profile corrections
- `trajectory.years_since_peak` is now null when there is no peak (no history, or 0%). It used to show e.g. "4 years since peak" on a never-occupied home.
- `deadspace_diagnosis.authority` is filled from the register. The detector record has no such key, so it was always null.
- **Regression check.** I diffed the regenerated JSON against the previous one. The only changed existing fields are the ones listed above. New fields are additive.

## Frontend

### D7. One config file for metric display: `frontend/src/config/metricConfig.ts`
- **What it holds:**
  - `METRICS`: profile path → label, pillar, format, optional `unit`, `types`, `hideZero`, `warn`, `hint`, `signalsPanel`.
  - `CORE_METRICS`: asset type × authority group → 4 keys, copied from the matrix's top-4 table, with a fallback order for combinations that have no assets.
  - `authorityGroup()`: `full_control` → owned; advisory splits into sold / public by `ownership_status`.
  - Formatters: thousands separators, `RM`, `%` (1 decimal under 10%, otherwise 0), signed °C deltas, units rendered separately.
  - `FLAG_TIER`, `SUBUNIT_COLUMNS`, and the simulated-year rules (D9).
- **Why.** The user asked for one config file, with no type or authority if-chains in components. Components ask the config what to show (`resolveMetric`, `pillarMetrics`, `coreMetricKeys`). Tiers are never configured on the frontend; they come from `profile.tiers`.
- **Display rules:**
  - A metric shows only if it has a non-null value, so anything unavailable for the authority is hidden.
  - `U` shows as the word "Unknown" with a U badge (today that's only `trajectory.class` for non-owned assets).
  - `hideZero` hides zero floor area and capex on parcels.
  - `types` restricts unit counts to residential.
  - Core metrics are left out of the pillar lists, and so are the fields the signals panel shows (`signalsPanel`), to avoid showing them twice.
- **Files:** `frontend/src/config/metricConfig.ts` (new), `frontend/src/types.ts`.

### D8. AssetPanel layout (superseded by D13–D15)
- **Order:**
  1. Header: name, ID, subtype, and pills for status, authority group (from `authority.level` + `ownership_status`) and intervention mode.
  2. Core metrics (2×2 tiles).
  3. Evaluation track and external signals.
  4. Subtype tenancy mix.
  5. Diagnosis: flags with a tier badge from `flag_tiers`, plus contributing factors.
  6. Supporting evidence.
  7. All metrics, grouped into four collapsible pillars.
  8. The unchanged analysis result and input area.
- **Why this order.** Decision-relevant numbers first, the explanation (flags, evidence) next, the full detail last.
- **Fixes made along the way:**
  - The authority and mode pills were nested inside the status pill.
  - The "Showing YYYY diagnosis (this year not generated)" warning fired whenever the year wasn't 2026, i.e. exactly when a year *was* generated. It now compares the diagnosis year with the selected year.
  - The evidence header said "2026" for every year.
- **Subtype table.** Columns are data-driven: a column appears when any row has data for it. Each column header carries the served tier badge.
- **Styling.**
  - Shared classes live in `styles.css`: `.metric-row` (a three-column grid, so labels, values and badges line up), `.core-tile`, `.pillar`, `.pill`, `.flag-chip`.
  - No left accent borders anywhere in the panel. I also removed the one in `DeadspaceList`, where the mode badge already encodes the mode.
  - Colours come from the existing theme.
- **Files:** `frontend/src/components/AssetPanel.tsx`, `frontend/src/styles.css`, `frontend/src/components/DeadspaceList.tsx`.

### D9. Simulated years are re-tiered on the client
- **The problem.** For years other than 2026, `/api/map/geometry` sends B4 values in `metrics_json` with no tier or source. Changing that endpoint was out of scope.
- **What `applyYearMetrics()` does:**
  - It copies each value over the 2026 profile and records an override with a tier and a qualifier.
  - **Owned:** keep the served tier, but downgrade T1 to T2, labelled "simulated YYYY". A projection is not an observation.
  - **Non-owned with a proxy occupancy** (sold shops): 3a, "estimated YYYY". Occupancy goes into `social.proxied_occupancy`, so the core metric shows the year's value.
  - **Non-owned without a proxy** (sold homes, public facilities): U, "assumed YYYY", shown as "Unknown". B4 seeds these with no observed baseline (0.5 occupancy for sold homes; e.g. 0.6 utilisation for public facility `A-0002`), which is not evidence.
  - Non-occupancy fields (operational carbon, canopy, walk coverage, demand) keep their served tier and are labelled "simulated YYYY".
- **Limitation.** "Has a proxy" is inferred from `social.proxied_occupancy` being present. The robust fix is for the geometry endpoint to send a source per value (see the team-lead list).
- **Files:** `frontend/src/config/metricConfig.ts`, `frontend/src/App.tsx` (the merge now calls `applyYearMetrics`; `Asset` gains `selectedYear` and `metricOverrides`).

### D10. ExternalSignalsPanel ported, backed by the API
- **What.**
  - `externalSignals.ts` and `ExternalSignalsPanel.tsx` didn't exist on `mathaba-panel`; they live on `mathaba-experimental` and `landing-experimental`. I copied those two files only; I did not merge the branch.
  - The `rows('/mock/...')` fetches are replaced by `signalsFromProfile(profile)`, a pure mapping from the served profile. The exported types are unchanged.
  - The layout is kept: evaluation track, developer realisation, foot traffic, business presence.
- **Changes from the experimental version:**
  - Each row's badge uses the served tier.
  - Profit and return are served by the backend instead of computed in the browser.
  - The "why" text is keyed by authority group: `authority.level` is always `advisory` for non-owned assets, so the old `sold` key never matched.
  - "No external signal data" shows only for sold assets; public assets aren't expected to have proxies.
- **Files:** `frontend/src/externalSignals.ts`, `frontend/src/components/ExternalSignalsPanel.tsx` (both new on this branch).

### D11. TierBadge
- **What.** Kept the compact T1 / T2 / 3A / 3B style from this branch and added U. The tooltip shows the tier meaning, the served source, and "synthetic demo data" when `mock`.
- **Why.** Labelling "mock" on every badge would put it on nearly every owned metric, because the metadata marks all internal records as mock. So it lives in the tooltip instead.
- **Interface.** `ServedTierBadge` takes a `profile.tiers` entry. `DataTier` now also accepts `'1' | '2' | 'U'`, so the analyze card (numeric tiers) keeps working.

### D12. Build fixes
`DeadspaceList.tsx` was missing the `intervened` status colour, which broke `tsc -b` before any of this work. Fixed.

## Panel restructure (second pass)

### D13. Always-visible block plus four tabs
- **Always visible:**
  - The header: name, ID · type · subtype, and badges for authority group, intervention mode, and "Mixed use · N subtypes".
  - One line naming the evaluation lens. It moved here from ExternalSignalsPanel because it applies to every asset.
  - The core-metric cards.
  - A one-line diagnosis: status plus the two highest-weighted flags, e.g. "Deadspace candidate · Negative NOI, Long vacancy".
  - The status sits only in that line, not also as a header pill, so it appears once.
- **Tabs:** Diagnosis | Metrics | Tenancy | Ask AI.
  - The bar is a CSS grid of equal columns with an underline on the active tab and no left borders. It is sticky inside the scroll area and never scrolls sideways.
  - The selected tab lives in `App` (`panelTab`), not localStorage, so it survives selecting another asset.
  - Tenancy is hidden when no selected asset has a unit mix or external signals. A remembered Tenancy tab then falls back to Diagnosis without being forgotten.
  - Asking a question or opening a history item switches to Ask AI, where the result appears.
- **Ask AI** holds the multi-select hint, the analysis result, and the question box, which is pinned at the bottom only on this tab.
- **Files:** `frontend/src/components/AssetPanel.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/config/metricConfig.ts` (`PANEL_TABS`).

### D14. Diagnosis tab: one list, with evidence values from the profile
- **What.** The flag chips and percentage bars are now one list. Each row has a human label, the served flag tier (`flag_tiers`) and a weight bar (`contributing_factors`), sorted by weight. Clicking a row expands the profile values tied to that flag (`FLAG_EVIDENCE` in `metricConfig.ts`). The separate Supporting Evidence section is gone.
- **Why profile values, not evidence strings.** The B6 evidence strings are a frozen snapshot of older metrics (D15) and raw text. Rendering them would contradict the core cards. They stay in the API for the LLM and are no longer parsed by the panel.
- **Evidence values not tied to a flag** are ordinary profile metrics and live in the Metrics tab.
- **Profile additions so that no evidence value is lost:** `social.median_walk_distance_m`, `trajectory.years_below_benchmark` (only when an occupancy record exists) and `financial.maintenance_surge_rm` (tier 2, 3a for non-owned). These were the only evidence values with no profile field.
- **Overlapping flags.** When two flags share evidence (e.g. a parcel's "More supply planned than demand" and "Weak future demand"), the values sit under the higher-weight flag, and the other row says where they are. Subtype-mix flags link to the Tenancy tab, which holds the per-subtype table.

### D15. One value, one home
- **The rule.** `placeMetrics()` gives every value exactly one place below the core cards:
  1. Evidence of a raised flag, highest weight first.
  2. Otherwise, ExternalSignalsPanel (Tenancy tab) for signal fields.
  3. Otherwise, its pillar (Metrics tab).
- **Core metrics** are the only allowed repeat: each keeps its one home as well as its card.
- **ExternalSignalsPanel** takes a `hidden` set and skips rows already shown under a flag.
- **Checked:** across all 916 assets there are 0 duplicate placements, and every served metric has a home, except values hidden on purpose (zero floor area on parcels, unit counts outside residential).

### D16. Metrics tab defaults
- Pillars are collapsible `<details>`. Financial and Social open by default; for parcels, Physical opens instead (`DEFAULT_OPEN_PILLARS`).
- The tier legend line is gone. Every TierBadge tooltip now ends with the legend.

### D17. Human labels
- `metricConfig.ts` holds the label maps: `ASSET_TYPE_LABELS`, `SUBTYPE_LABELS`, `STATUS_LABELS`, `MODE_LABELS`, `TRAJECTORY_LABELS`, and `FLAG_LABELS` (all 41 flags `tiers.py` can raise).
- Anything unlisted goes through `humanize()`, which turns snake_case into sentence case and keeps acronyms upper-case (NOI, DSR, LBS, UHI, GFA, …).
- **Applied to:** the header, flags, summary line, subtype table, trajectory values, the analysis card's spec and subtype rows, and the DeadspaceList cards (status and subtype; their subtype now comes from the register, not the evidence string).
- **Checked:** no snake_case text reaches the screen for any of the 916 assets.

### D18. Inconsistencies found and their causes
1. **BLD-0037 DSR: 1.04 in Core Metrics vs 0.93 in evidence.**
   - The core card reads `financial.dsr`, served from `asset_metrics_enriched.csv` `dsr` = 1.043 (the 2026 row).
   - The evidence line "DSR: 0.93" is a string inside `deadspace_2026.json`. That file was last generated at commit `de87549`, when the metrics file still had `dsr` = 0.932 (`161dffb`). The metrics were regenerated at `6baa3b8` (1.043) without re-running B6, so every evidence string is a snapshot of older metrics.
   - **Decision:** the panel uses the served profile value (1.04) everywhere and no longer shows evidence strings (D14). Re-running B6 is listed for the team lead.
2. **Header "Mixed-Use Commercial" vs evidence subtype "supermarket".**
   - `App.tsx` replaced the subtype with "Mixed-Use Commercial" whenever an asset had a unit mix. The register (`assets.csv`) says `supermarket`, and that is what B6 uses: the occupancy benchmark from `taxonomy.yml`, and the supermarket entry in `DRIVING_CRITICAL_SUBTYPES` that drives the driving-access flag.
   - **Decision:** show the register subtype ("Supermarket") and show the unit mix separately as a "Mixed use · 7 subtypes" badge plus the Tenancy table. The subtype the user sees is then the one the diagnosis was computed for.
   - Note: BLD-0037's unit mix does not contain a supermarket unit at all (team-lead item 12).
3. **Flag tier vs metric tier (negative_noi T1 while noi_rm is T2).**
   - Per `field_metadata.yml`, `noi_rm` is tier 2 (derived: rental − OPEX − maintenance), so a flag computed from it is tier 2. `deadspace/tiers.py` puts `negative_noi` in `tier_1_observed`. **The metric tier (T2) is correct; the flag tier is a backend issue.**
   - The same audit finds more mismatches. Too high: `noi_yield_below` (noi_yield T2), `maintenance_surge_high` (maintenance_surge_rm T2), `rapid_decline` / `falling_from_healthy` / `chronic_stagnation` (trajectory_class T2), all listed as T1. Too low: `high_uhi_exposure` and `uhi_data_anomaly` are T2 while their input `surface_temp_delta_c` is T1 (observed Landsat).
   - The panel shows the served `flag_tiers` unchanged, and the detector code is untouched (team-lead item 11).

### D19. Files touched in this pass
- **Backend:** `backend/scripts/build_profiles.py`, `backend/configs/field_metadata.yml`, the regenerated profile JSON.
- **Frontend:** `AssetPanel.tsx`, `ExternalSignalsPanel.tsx`, `TierBadge.tsx`, `DeadspaceList.tsx`, `App.tsx`, `config/metricConfig.ts`, `styles.css`.

## Third pass

### D20. Ask AI is a pinned bar, not a tab
- **Tabs.** Now three: Diagnosis | Metrics | Tenancy. `PanelTab` no longer has `'ask'`. Any remembered tab that isn't available (Tenancy without data, or a stale "ask") falls back to Diagnosis.
- **The ask bar** (label, file chips, input, Ask button) is pinned below the panel, always visible. It is a **flex sibling** of the scroll area (`.panel-scroll` then `.ask-bar`), not an overlay, so it can never cover content.
  - The scroll area also gets 16 px bottom padding, so the last row isn't flush against the bar.
  - The "Ctrl + click to add assets" hint moved into the bar's label line.
- **For the bar to stay pinned, the sidebar had to change.** The `<aside>` in `App.tsx` used to scroll as a whole (search box + panel together), which would have scrolled the bar away.
  - It is now a flex column: the search box is fixed, and the content below fills the rest.
  - The AssetPanel scrolls internally. DeadspaceList and HistoryPanel scroll in a wrapper, as before.
- **The AI answer** (or error) renders inside the scroll area, after the tab content and directly above the bar, under an "AI analysis" heading. It is no longer inside a tab, and it scrolls into view when a new one arrives.
- **Files:** `AssetPanel.tsx`, `App.tsx`, `config/metricConfig.ts`, `styles.css`.

### D21. Expandable rows share one toggle style
- **Pillar headers** (Metrics tab) and **flag rows** (Diagnosis tab) use the same classes: `.toggle-group` > `.toggle` (+ `.toggle-body`).
  - A full-width row, at least 40 px tall, with a filled background one step lighter than the panel, 8 px radius, and a lighter hover with a pointer cursor.
  - A 14 px chevron on the left, in the title colour, rotating 90° in 0.15 s when open.
  - A bold, normal-case title. The pillar count is a pill ("10 metrics").
  - 6 px gaps between sections. The open body sits directly under its header as one block (header corners squared at the bottom, body on the card surface).
- **Flag rows** keep their tier badge, weight bar and percentage in a grid inside the same toggle. Rows with nothing to expand keep the look but lose the chevron and hover.
- **Tokens.** `styles.css` had no CSS variables, only hex values copied from `theme.ts`. I added a `:root` block that mirrors `theme.ts` (`--panel`, `--card`, `--line`, `--text`, `--muted`, `--faint`, `--accent`), plus two surface steps: `--surface-raised` (#3d3140, the existing `.btn:hover` surface) and `--surface-hover`. The new rules use these.
- No left accent borders.

## How profiles were regenerated
`py -3.14 backend/scripts/build_profiles.py`. The repo's `.venv` and the default Python 3.12 have no pandas on this machine; Python 3.14 has pandas 3.0.5 and PyYAML. The output was checked against the previous JSON (D6) and on five sample assets: `BLD-0037` owned shop, `BLD-0193` sold shop, `BLD-0086` sold home, `A-0002` public facility, `P-VAC-GOLD-01` parcel.

## For team lead

These need a decision or a change outside this task's scope. None were changed.

1. **The deadspace invariant no longer holds.** `plan_v6` §1.3 says only full_control assets can be `deadspace_candidate`. Since v6.1g, `status.decide_sold_commercial_status` lets sold shops reach it when `business_presence_low` and `operating_hemorrhage` both fire: 16 of the 61 candidates in 2026 (15 collaborative, 1 advisory). Either update the plan or restore the invariant in `status.py`.
2. **Survival-constant mismatch on the analyze path.** `simulation/engine.py` computes `_estimated_revenue_rm` with hard-coded 0.05 conversion × RM25 × 365 days, and `_survival_opex_floor_rm` with RM200/m². `deadspace/layer3_survival.py` uses `assumptions.yml` `survival_analysis` (defaults 0.10, RM25, 360 days, RM180/m²). The panel (now showing the B6 values) and the analysis card will disagree for the same shop.
3. **`/api/map/geometry` sends no tier or source per simulated value**, and sold homes get a neutral 0.5 occupancy. The frontend infers the tier (D9). Better: send `{value, tier, source}`, or leave defaults null.
4. **The map preview of an LLM run ignores the run's scenario.** In `main.py`, `scenario_id` is hard-coded to `SC-CURRENT`, and the `run_data` block before it is dead code. A run only recolours its assets as "intervened"; year values still come from the baseline scenario.
5. **B3 data looks wrong.** `reachable_population_walk` is 52,679 and `coverage_ratio_10min_drive` is 0.863 for every asset I sampled (shop, homes, facility, parcel, park). Both look like township totals or a saturated catchment, not per-asset values.
6. **The apparent-temperature model in `build_profiles.py`** gives parks a higher felt temperature than buildings. Example: park `G-0013` has LST 39.1 °C but a felt temperature of 45.3 °C, because of its higher damping and humidity factors. It doesn't affect any flag, but it will look wrong in a demo. Check the LCZ constants, or drop the metric.
7. **The analyze card tags owned NOI as tier "1"**, but `field_metadata.yml` says 2 (NOI is derived).
8. **`shared` (JMB) authority exists in code and docs but not in data.** All non-owned assets are `advisory`. Decide whether to model it.
9. **Sale profit formula.** `sale_price − capex_initial_rm` compares a (mock) sale price with total build cost; for multi-unit residential that may not be like-for-like. Confirm the definition before it's shown to judges.
10. **Backend tests have failures I didn't cause.** `tests/test_normalize.py` fails to import (`ModuleNotFoundError: legacy`) and `tests/test_accessibility.py` errors at collection. `tests/test_accessibility_Profile.py::test_catchment_profile_partial` fails (`assert 0.0 == 100.0`). None of them touch the files changed here. With those two files excluded, the suite gives **21 failed, 81 passed** both on a clean checkout of `ed531e7` and with this change: the same 21 tests (e.g. `test_taxonomy.py::test_energy_intensity`). So the failures predate this work, and none of the tests read the profile build.
11. **Flag tiers in `deadspace/tiers.py` disagree with `field_metadata.yml`** (D18.3).
    - Tagged T1 although their input metric is T2: `negative_noi`, `noi_yield_below`, `maintenance_surge_high`, `rapid_decline`, `falling_from_healthy`, `chronic_stagnation`.
    - Tagged T2 although their input is T1: `high_uhi_exposure`, `uhi_data_anomaly`.
    - Suggest deriving a flag's tier from its input field's metadata tier instead of a hand-kept list.
12. **`deadspace_2026.json` is stale against `asset_metrics_enriched.csv`** (D18.1).
    - B6 was last run at `de87549`; the metrics were regenerated at `6baa3b8`. BLD-0037's evidence says DSR 0.93, but the metrics say 1.04.
    - Re-run B6 (`deadspace/engine.py`), then `build_profiles.py`. Flags and statuses may change.
    - Also: BLD-0037's register subtype is `supermarket`, but its unit mix has no supermarket unit. Confirm which is right.
13. **`DeadspaceList` still shows occupancy and vacancy parsed from the evidence strings**, so it can show the same stale values. It should read the profile fields instead (logged in `docs/frontend_review.md`).
