# Living Masterplan

Living Masterplan is a geospatial decision-support prototype for understanding township assets and exploring how interventions may affect them over time. It combines a Python analysis and simulation backend, a FastAPI service, and a React/TypeScript map dashboard.

The project supports three connected tasks:

1. **Diagnose:** derive asset, accessibility, environmental, and financial metrics, then identify assets that may need attention.
2. **Explore options:** generate and validate candidate intervention plans, including repurposing, retrofits, and development changes.
3. **Compare outcomes:** simulate selected plans over time and review asset-level and township-level changes.

*Supports multi-modal evidence ingestion (accepts PDF/CSV/TXT reports) and zero-shot spatial reasoning via Gemini on Google Cloud Vertex AI.*

## Live Demo

- **Frontend Dashboard:** [https://living-masterplan-beta.vercel.app](https://living-masterplan-beta.vercel.app)
- **Production API:** `https://living-masterplan-api-1071997994154.asia-southeast1.run.app`
- **Interactive API Docs:** [https://living-masterplan-api-1071997994154.asia-southeast1.run.app/docs](https://living-masterplan-api-1071997994154.asia-southeast1.run.app/docs)

The configured backend dataset is Bukit Jelutong. The repository also includes Elmina geometry and frontend demonstration fixtures. Model outputs depend on supplied data and assumptions and should be reviewed before informing real development decisions.

The configured backend dataset is Bukit Jelutong. The repository also includes Elmina geometry and frontend demonstration fixtures. Model outputs depend on supplied data and assumptions and should be reviewed before informing real development decisions.

## Architecture

```text
React + MapLibre Dashboard (Deployed on Vercel)
          │ profiles, geometry, analysis (HTTPS / CORS)
          ▼
FastAPI Backend (Containerized on Google Cloud Run)
          │
          ├── Geospatial Metrics & Deadspace Diagnostics
          ├── Multi-Year Scenario Simulation Engine (2026–2033)
          └── Vertex AI Gemini Client (Multi-Modal Asset Analysis & Reasoning)
```

The LLM layer proposes and explains options. Deterministic validation and simulation calculate the reported scenario results.

## Requirements

- Python 3.10 or later
- Node.js `^20.19.0` or `>=22.12.0`, and npm (for the frontend)
- Google Cloud credentials and a project ID only when using real Gemini analysis

The checked-in Python requirements files cover the geospatial and analysis packages. The API also imports packages that are not listed there, so install the API dependencies separately as shown below.

## Setup

From the repository root, create a Python environment and install the backend and API packages:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r backend/requirements.txt
python -m pip install fastapi "uvicorn[standard]" python-multipart python-dotenv google-genai
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

Install frontend packages:

```bash
cd frontend
npm ci
```

## Prepare or refresh the analysis data

The configured base directory is `bukit_jelutong/processed`, set in [`backend/configs/paths.yml`](backend/configs/paths.yml). From the repository root, the main data workflow is:

```bash
python backend/scripts/run_phase1.py
python backend/scripts/run_phase3.py
python backend/scripts/build_profiles.py
python backend/scripts/run_phase4.py --current-only
```

| Script | Purpose | Main output |
| --- | --- | --- |
| `run_phase1.py` | Derive metrics for 2022–2026 and write the enriched asset metrics | `bukit_jelutong/processed/business/asset_metrics_enriched.csv` |
| `run_phase3.py` | Produce 2026 deadspace diagnoses | `bukit_jelutong/processed/business/deadspace_2026.json` |
| `build_profiles.py` | Build the baseline asset profiles served by the API | `bukit_jelutong/processed/business/asset_profiles_2026.json` |
| `run_phase4.py` | Simulate intervention scenarios and write scenario results | `bukit_jelutong/processed/business/scenarios/` |

### Refresh observed surface temperature

The thermal workflow uses Landsat 8 Collection 2 Level-2 `ST_B10` and keeps
uncovered parcels null. See [`docs/landsat_lst_pipeline.md`](docs/landsat_lst_pipeline.md)
for Earth Engine setup, the cloud mask, date-window defaults, output files, and
the profile regeneration sequence.

Phase 3 and profile generation use the enriched metrics, so run Phase 1 first. The profile build also uses the Phase 3 deadspace output. The checked-in processed dataset already includes these artifacts; rerun the scripts when you change their source data.

`run_phase4.py` runs `SC-CURRENT`, `SC-REPURPOSE`, and `SC-DELAY` by default. Use `--current-only` to run the baseline across the configured years, or `--quick` to run only the baseline for 2026 and 2033. Reruns replace the corresponding generated outputs.

## Start the backend API

After installing the Python packages, start the API from the `backend` directory:

```bash
cd backend
python -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

The interactive API documentation is available at <http://localhost:8000/docs>. The API currently provides:

| Method and path | Purpose |
| --- | --- |
| `POST /api/analyze` | Analyze selected asset IDs, optionally with up to three `.txt`, `.csv`, or `.pdf` files (10 MB each). |
| `GET /api/assets/profiles` | Return the 2026 asset profile dictionary. |
| `GET /api/map/geometry?year=2026` | Return map geometry with status and diagnostic properties; supports a `run_id` overlay. |

See [`API.md`](API.md) for request fields, response shapes, and map integration details.

## Start the frontend

In another terminal:

```bash
cd frontend
npm run dev
```

Vite prints the local dashboard URL. The frontend uses MapLibre GL for the map and reads profile and map geometry data from the backend. 

### Environment Variables & Base Maps

By default, the frontend is configured to point to the production API. If you are developing locally and want to connect to a different API, create a `.env` file in the `frontend` directory:

```env
VITE_API_URL=[https://living-masterplan-api-1071997994154.asia-southeast1.run.app](https://living-masterplan-api-1071997994154.asia-southeast1.run.app)
```

> **Base Map Authentication:** The default map layer uses Stadia Maps raster tiles (`alidade_smooth_dark`). When deploying to new custom domains or production environments on Vercel, ensure your deployment domain (e.g., `living-masterplan-beta.vercel.app`) is added to your Stadia Maps Allowed Domains list to prevent `401 Unauthorized` map loading errors.

The analysis button is currently in live mode: `USE_MOCK_LLM` is set to `false` in `frontend/src/api.ts`, so it sends analysis requests to the backend. Set it to `true` to return local demonstration scenarios instead of calling `POST /api/analyze`.

Frontend checks and production build:

```bash
cd frontend
npm run lint
npm run build
```

## Use real Gemini analysis

The API and real-model scripts use the Vertex AI Gemini client. Install the API dependencies above, authenticate with Google Cloud, and set a project ID before sending real analysis requests:

```bash
gcloud auth application-default login
```

PowerShell:

```powershell
$env:GOOGLE_CLOUD_PROJECT = "your-project-id"
```

macOS or Linux:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

The location can optionally be set with `GOOGLE_CLOUD_LOCATION`; the client defaults to `global`. The frontend must also be switched out of mock mode to use the real API analysis route.

For command-line demos, run `python backend/scripts/run_llm_real2.py --scenario 1`, `--scenario 2`, or `--scenario 3`. The stub-backed `python backend/scripts/run_llm_demo.py` exercises the reasoning flow without calling Gemini. LLM runs append intervention records to the configured processed business data, so preserve or restore that file if you want to discard demo changes.

## Data

The active data paths are defined in `backend/configs/paths.yml`:

- `bukit_jelutong/raw/geometry/` contains the raw Bukit Jelutong geometry layers.
- `bukit_jelutong/processed/geometry/` contains the geometry layers used by the analysis.
- `bukit_jelutong/processed/business/` contains assets, metrics, leases, projects, candidates, interventions, profiles, diagnoses, and scenario results.
- `elmina/geometry/` contains a separate Elmina geometry set; it is not selected by the current default path configuration.
- `frontend/public/data/` and `frontend/src/mockData.ts` contain frontend demonstration data. [`frontend/MOCK_DATA.md`](frontend/MOCK_DATA.md) describes known mock fields and caveats.

The configured spatial layers are parcels, buildings, network edges, green/blue features, amenities, and population. Business tables join to spatial features using stable IDs. Geometry is analyzed in EPSG:32647 and returned to EPSG:4326 where needed for map display.

Review `backend/configs/assumptions.yml`, `taxonomy.yml`, `peer_benchmarks.yml`, and `field_metadata.yml` alongside the data. These settings affect accessibility, demand, carbon, benchmarks, and deadspace results. JSON data contracts are in [`contracts/schemas/`](contracts/schemas/).

## Tests

Run the Python suite from the `backend` directory:

```bash
cd backend
python -m pytest
```

## Repository layout

```text
backend/
  app/api/          FastAPI routes
  app/derived/      Spatial and asset metric calculations
  app/deadspace/    Deadspace diagnoses and urgency
  app/simulation/   Multi-year scenario engine
  app/llm/          Context assembly, prompts, validation, and orchestration
  configs/          Active data paths and model assumptions
  scripts/          Analysis, profile, scenario, and LLM commands
  tests/            Python tests
contracts/schemas/  JSON Schema contracts
bukit_jelutong/     Active raw and processed township data
elmina/             Alternate geometry data
frontend/           React, TypeScript, Vite, and MapLibre dashboard
API.md              API endpoint reference
Living_Masterplan.md  Product and technical design document
```

## Further documentation

- [`API.md`](API.md) — REST endpoints and frontend integration.
- [`Living_Masterplan.md`](Living_Masterplan.md) — product goals, data model, algorithms, simulation, and system design.
- [`frontend/MOCK_DATA.md`](frontend/MOCK_DATA.md) — notes on frontend fixtures and assumptions.
