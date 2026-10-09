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