# Living Masterplan

Living Masterplan is a Python prototype for assessing township assets and exploring how planning decisions may affect them over time. It combines spatial data, business assumptions, deterministic analysis and simulation, and an optional language model reasoning layer.

The project is built around three questions:

1. **Where are assets underperforming?** Derive asset metrics and flag potential deadspace.
2. **What could be changed?** Represent interventions such as repurposing, retrofits, pedestrian upgrades, and delayed or new development.
3. **What might happen next?** Compare scenario outcomes across assets and at township level.

This checkout contains a small mock dataset for the Elmina West area. Results are demonstrations driven by the supplied mock records and model assumptions; they are not measured forecasts or planning advice. There is no web frontend or HTTP API in this repository.

## What is included

- **Spatial analysis:** Walking and driving network accessibility, catchments, canopy effects, demand and supply, Huff competition, demographic mismatch, neighborhood diversity, and asset-level environmental and business metrics.
- **Deadspace analysis:** Evidence-based flags, status, contributing factors, and urgency estimates for assets.
- **Scenario simulation:** Multi-year population, demand, supply, intervention timing, construction periods, carbon, accessibility, and before/after comparisons.
- **LLM reasoning prototype:** A tool-based workflow that gathers project evidence, proposes an intervention plan, validates it, runs the deterministic simulator, and prepares a written explanation. The included command uses a stub client and does not call an external model.
- **Data contracts:** JSON Schemas and documentation for spatial, business, deadspace, and scenario data.

## Requirements

- Python 3.10 or later
- Pip

Python packages are listed in [`backend/requirements.txt`](backend/requirements.txt). The analysis uses GeoPandas and Shapely for spatial operations, NetworkX for network graphs, pandas and NumPy for tabular calculations, and PyYAML and jsonschema for configuration and data contracts.

## Setup

Run these commands from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Run the analysis

Run the available workflows from the repository root:

```bash
python backend/scripts/run_phase1.py
python backend/scripts/run_phase3.py
python backend/scripts/run_phase4.py
```

The scripts use the checked-in 2026 mock data and configuration. Phase 3 expects the enriched metrics produced by Phase 1, so run Phase 1 first. Phase 4 simulates the scenarios defined in the intervention data.

| Command | Purpose | Main output |
| --- | --- | --- |
| `run_phase1.py` | Derive 2026 asset metrics and merge them with the existing metric table | `mock/business/asset_metrics_enriched.csv` |
| `run_phase3.py` | Classify deadspace using the enriched metrics | `mock/business/deadspace_2026.json` |
| `run_phase4.py` | Simulate `SC-CURRENT`, `SC-REPURPOSE`, and `SC-DELAY` | `mock/business/scenarios/SC-*.json` |

Each workflow prints a summary to the terminal. Rerunning a workflow replaces its corresponding generated output. The simulation writes scenario result JSON files using the same IDs and paths as the checked-in scenario files.

### LLM demo

```bash
python backend/scripts/run_llm_demo.py
```

This exercises intent parsing, evidence gathering, proposal validation, simulation, and justification with a deterministic stub client. It does not require a model API key. **It appends generated intervention rows to `mock/business/interventions.csv`.** Restore that file from version control or a backup if you want to remove demo runs.

The repository also contains a Vertex AI Gemini client adapter in `backend/app/llm/clients/vertex_client.py`. Using a real provider requires the `google-genai` package, Google Cloud Application Default Credentials, and a project ID (for example, via `GOOGLE_CLOUD_PROJECT`). The included demo script selects the stub client; it does not switch to Vertex AI through a command-line option.

## Tests

The tests use imports rooted at `backend/app`. After installing the requirements, run them from the `backend` directory:

```bash
cd backend
python -m pytest
```

The suite covers derived metrics, accessibility, deadspace rules, taxonomy, and scenario simulation.

## Repository layout

```text
backend/
  app/
    derived/       Spatial accessibility and asset metric calculations
    deadspace/     Deadspace flags, status, evidence, and urgency
    simulation/    Multi-year scenario and intervention engine
    llm/           Tool service, validation, prompts, and orchestration
    loaders/       GeoJSON and CSV loading
  configs/         Paths, assumptions, taxonomy, benchmarks, field metadata
  scripts/         Analysis, simulation, mock-data, and LLM demo commands
  tests/           Python test suite
contracts/
  schemas/         JSON Schema contracts
  docs/            Schema and data conventions
mock/
  geometry/        GeoJSON layers for the sample township
  business/        Asset tables, interventions, and scenario data/results
Living_Masterplan.md  Full technical design document
```

## Data and configuration

The paths in [`backend/configs/paths.yml`](backend/configs/paths.yml) point to the active dataset under `mock/`.

### Spatial layers

All layers are GeoJSON in `mock/geometry/`:

| File | Contents |
| --- | --- |
| `parcels.geojson` | Parcel boundaries and land-use attributes |
| `buildings.geojson` | Building footprints and asset relationships |
| `network.geojson` | Network edges used for walking and driving analyses |
| `green_blue.geojson` | Green and blue features, including canopy information |
| `amenities.geojson` | Amenity locations and types |
| `population.geojson` | Population and demographic demand locations |

GeoJSON is stored in **EPSG:4326**. The loaders reproject features to **EPSG:32647** for distance and area analysis.

### Business tables and scenarios

The `mock/business/` directory contains:

- `assets.csv`: one row per asset, including asset type and links to parcel/building IDs.
- `asset_metrics.csv`: base metric rows by asset and year.
- `development_projects.csv` and `development_candidates.csv`: committed projects and candidate development options.
- `interventions.csv`: scenario actions, parameters, timing, and cost changes.
- `asset_metrics_enriched.csv`, `deadspace_2026.json`, and `scores_2026.json`: derived or example analysis artifacts.
- `scenarios/`: scenario result JSON files.

Stable IDs join business records to spatial features. The schema documentation describes table grain, units, IDs, CRS, and provenance conventions.

### Model settings

- [`assumptions.yml`](backend/configs/assumptions.yml): population growth, demand, carbon factors, accessibility speeds and thresholds, construction timing, and deadspace thresholds.
- [`taxonomy.yml`](backend/configs/taxonomy.yml): asset subtypes and subtype-specific model values.
- [`peer_benchmarks.yml`](backend/configs/peer_benchmarks.yml): comparison benchmarks.
- [`field_metadata.yml`](backend/configs/field_metadata.yml): field units, sources, and confidence tiers.

These settings materially affect the results. Review them alongside any output used for analysis.

## Data contracts

The JSON Schemas are in [`contracts/schemas/`](contracts/schemas/), with conventions documented in [`contracts/docs/SCHEMA.md`](contracts/docs/SCHEMA.md). The contracts cover geometry, assets, metrics, interventions, development options, deadspace, and simulation results.

For new datasets, preserve the stable IDs and CSV/GeoJSON separation, match the configured file paths, and maintain the documented units and coordinate reference systems. Update the schemas and field metadata when adding or changing fields.

## Current implementation notes

- The current runnable analysis commands are metric derivation, deadspace analysis, simulation, and the stub-backed LLM demo.
- A score schema and example score artifact are present, but this checkout does not include a standalone scoring engine or scoring command. The current deadspace workflow reads `asset_metrics_enriched.csv` directly.
- The mock assumptions and data are intended for demonstration. Replace them with reviewed local data and calibrated assumptions before using results to support a real development decision.

## Further documentation

- [`Living_Masterplan.md`](Living_Masterplan.md) — product and technical design, data model, algorithms, simulation, LLM boundaries, and planned interface.
- [`contracts/docs/SCHEMA.md`](contracts/docs/SCHEMA.md) — field, ID, unit, CRS, and versioning conventions.
