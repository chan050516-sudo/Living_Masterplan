# Mock data to replace

## 1. The whole file: public/data/assets.geojson
Replace with real Elmina GeoJSON (Module A).
Everything below is invented.

### Shapes (geometry)
Four hand-drawn squares near 101.50, 3.19. Not real buildings.
Real coordinates come from OSM via Module A.

### Properties per asset (invented, from Module B later)
| Field | B-03 | F-02 | P-05 | A-02 |
|---    |---   |---   |---   |---   |
| name | B-03 Commercial Lot | F-02 Community Facility | P-05 Undeveloped Parcel | A-02 Residential |
| type | commercial | facility | parcel | residential |
| score | 28 | 55 | 45 | 78 |
| occupancy | 21 | 48 | 0 | 91 |
| vacancy_months | 14 | 0 | 0 | 0 |
| score_3y | 22 | 58 | 38 | 82 |
| occupancy_3y | 18 | 52 | 0 | 94 |

## 2. Field names (confirm with Module B)
My names may not match module B's output. Likely renames:
- score -> performance_score?
- score_3y -> how are future years keyed? (per-year object vs flat field)

## 3. Colour thresholds (invented)
< 40 red, 40-59 yellow, >= 60 green.
Doc says benchmarks must come from market data or be labelled as assumptions.

## 4. Data source (D5)
Currently loaded from '/data/assets.geojson'.
Replace with the backend API URL. Owner of that API: TBC.

## 5. Not yet built
- AI options (Module C output) - no mock yet
- Scenario comparison table - no mock yet
- Intervened GeoJSON from C5 - need a sample from Module C

## 6. public/data/options.json (invented)
Fake AI response for B-03 only. Replace with Module C's output
via POST /ask. The 600ms setTimeout in ask() is fake latency: remove it.

## 7. public/data/comparison.json (invented)
Fake simulation results for B-03. Replace with POST /simulate output
from Modules B and C.

## 9. Carbon figures are invented
carbon_avoided = embodied carbon not emitted by reusing instead of
building new. Doc formula: floor_area × material_intensity.
David needs a real Malaysian emission factor and we must cite it —
this is the main Planet claim in the pitch.

## 10. portfolio_position / portfolio_note are invented
Came from the Figma design, not the technical doc. Needs a definition
(percentile against what population?) or it should be dropped.