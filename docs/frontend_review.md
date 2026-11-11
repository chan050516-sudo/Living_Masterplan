# Frontend review (outside the AssetPanel)

Branch `mathaba-panel`, 2026-11-10. This covers major issues only: bugs, broken data bindings, and things that would embarrass us in a demo. I reported these and did not fix them. AssetPanel issues I fixed during the refactor are listed at the end for completeness.

Files reviewed: `App.tsx` (map, search, filters, year switching, interventions), `components/DeadspaceList.tsx`, `components/ComparisonModal.tsx`, `components/HistoryPanel.tsx`, `Landing.tsx`, `api.ts`.

## Demo-breaking or clearly wrong

1. **The "Flow island" list filter blanks the map.** `DeadspaceList` filters `flow_island` by flag. The map mirror in `App.tsx` (the effect with `setFilter`) keeps only assets whose `diagnosis.status === listFilter`. No status is called `flow_island`, so every unselected asset disappears from the map. *Fix:* share the list's predicate with the map effect.
2. **The filter chips have no styling.** `DeadspaceList` (and the asset tabs in `ComparisonModal`) use `className="chip"` / `"chip on"`, but no stylesheet defines `.chip` (`styles.css`, `index.css` and `landing.css` don't; `App.css` isn't imported). The chips render as default browser buttons on the dark theme, and the active filter is shown only by font weight.
3. **The deployed API is the default backend.** `api.ts` falls back to a hard-coded Cloud Run URL when `VITE_API_URL` is unset. Without `frontend/.env.local`, a dev build silently talks to production. That backend won't have the new profile fields until it is redeployed, so the panel would show fewer metrics and no tiers.
4. **The basemap may be blank when deployed.** Tiles come from `tiles.stadiamaps.com` with no API key. Stadia serves keyless requests only from localhost; a deployed domain must be registered with Stadia or the map shows no basemap.
5. **Previewing a plan doesn't show its scenario.** "Preview on map" sets `activeRunId`, but `/api/map/geometry` hard-codes `scenario_id = "SC-CURRENT"`. The preview only recolours the run's assets as "intervened"; year values still come from the baseline. (This is a backend issue; it is visible in the demo.)
6. **Search can't find the IDs the panel shows.** The panel displays `FAC-…` / `GRN-…` for `A-…` / `G-…` assets, but search only matches raw IDs and names. Typing what's on screen ("FAC-0002") returns "not found".

## Data binding and consistency

7. **There are two search boxes** (header and sidebar) sharing one state and rendering two `<datalist id="asset-ids">` elements. Duplicate DOM IDs; the second list is dead.
8. **No filter for `development_risk`.** The 9 parcels can only be reached through "All issues".
9. **The landing headline understates stranded carbon.** `Landing.tsx` sums `environmental.carbon_stranded_tco2e`, which is null for every non-owned asset, so the total covers only the 66 owned assets. The deadspace count next to it includes sold shops (16 of 61). The two headline numbers use different populations.
10. **The "intervened" colour differs by view.** It's `#00d2ff` on the map (`STATUS_PAINT` / `STATUS_HEX`) but `#2196f3` in the list and panel.
11. **The production bundle ships mock LLM scenarios.** `api.ts` imports `../../legacy/mockData` (outside `frontend/`), even though `USE_MOCK_LLM = false`. That inflates the 1.2 MB `App` chunk and makes the build depend on a folder outside the frontend.

14. **DeadspaceList occupancy and vacancy text come from stale evidence strings.** The list cards parse `Occupancy:` / `Vacancy:` from `deadspace_diagnosis.evidence`, which an older B6 run generated (see DECISIONS D18.1). They can disagree with the AssetPanel, which uses the served profile. They should read `social.occupancy_rate` and `social.vacancy_duration_months` instead. (Status and subtype on the cards were switched to human labels in this change.)

## Performance

12. **The intervention pulse animation never stops.** `animatePulse()` runs a `requestAnimationFrame` loop from map load onwards and calls `setPaintProperty` on two layers every frame, even with no interventions. It also replaces the zoom-interpolated `circle-radius` with a fixed number, so pulse size no longer scales with zoom.
13. **Changing years refetches the whole geometry.** Every year switch reloads `/api/map/geometry` (all buildings, parcels and parks). Acceptable for a demo; noticeable on slow connections.

## Fixed in this change (AssetPanel)

- The "Showing YYYY diagnosis (this year not generated)" banner fired when a year *was* generated (any non-2026 year). It now compares the diagnosis year with the selected year.
- The evidence header always said "2026".
- The authority and intervention-mode pills were nested inside the status pill.
- The owned subtype table read a field the API never sent, so it always showed "—".
- Sold-asset stranded carbon was computed in the browser as `1 − proxied occupancy` and labelled 3a.
- Simulated-year occupancy for sold assets was shown as plain "Occupancy", with no tier.
- Second pass: the panel is split into an always-visible block and four tabs; flags and their weights are one list; evidence strings are no longer rendered; every value appears once; the subtype shown is the register subtype, not "Mixed-Use Commercial".
- `DeadspaceList` used a left accent border, and was missing the `intervened` colour, which broke `npm run build`.
