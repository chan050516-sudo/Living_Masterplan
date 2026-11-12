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

### Demo vs. Live Analysis

`frontend/src/api.ts` exports `routeAnalysis(selectedAssets, userQuery, files)` which decides whether an analysis is served from a **frozen demo scenario** or the **live `/api/analyze`** endpoint.

| Selection | Route | Latency |
|---|---|---|
| Every asset in `{BLD-0037, BLD-0260, BLD-0004}` + case1 query hints | mock case1 | ~1.5 s |
| Every asset in `{BLD-0736, BLD-0734, BLD-0067}` + case2 query hints | mock case2 | ~1.5 s |
| Anything else (mixed selection, non-demo asset, cross-case query) | live | **~1-3 min** |

Case1 hints: `BLD-0037 | feasibility | budget | engineering spec | retrofit`, or any PDF upload. Case2 hints: `tenant | shoplot | flow island | kopitiam | landlord | owner`.

The mock scenarios live in `frontend/src/mockData_case1.ts` and `mockData_case2.ts`. They are frozen B7 outputs from a real run and contain full `summary_card`, `timeline`, and `decision` payloads — no schema divergence from a live response.

Live calls take **1-3 minutes** (2-3 for multi-asset selections, up to 5 if the Vertex API retries on transient errors). The Ask button shows "Analyzing (~1-2 min)…" or "Analyzing (~2-3 min)…" based on asset count.

Frontend checks and production build:

```bash
cd frontend
npm run lint
npm run build
```

## Before the demo (checklist)

```powershell
# 1. Verify the live API endpoint is up (2-3 min round-trip expected)
curl.exe -X POST "https://living-masterplan-api-1071997994154.asia-southeast1.run.app/api/analyze" `
  -F "user_query=test" -F "selected_assets=BLD-0037" --max-time 400

# 2. Verify the six demo asset IDs actually exist in assets.csv
Select-String -Path bukit_jelutong/processed/business/assets.csv `
  -Pattern "BLD-0037|BLD-0260|BLD-0004|BLD-0736|BLD-0734|BLD-0067"

# 3. Confirm BLD-0037 is the designated community centre (largest lettable commercial)
python -c "import pandas as pd; df = pd.read_csv('bukit_jelutong/processed/business/assets.csv'); \
  print(df[df.asset_type=='commercial'].nlargest(3,'lettable_area_m2')[['asset_id','subtype','lettable_area_m2']])"

# 4. Warm up Vertex AI (first call is slow; subsequent calls are 30-60% faster)
python backend\scripts\run_llm_real2.py --scenario 1
```

If any of these fail, demo the mock scenarios only — the six demo asset IDs are the only selection that returns instantly.

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

The location can optionally be set with `GOOGLE_CLOUD_LOCATION`; the client defaults to `global`.

For command-line demos, run `python backend/scripts/run_llm_real2.py --scenario 1`, `--scenario 2`, or `--scenario 3`. The stub-backed `python backend/scripts/run_llm_demo.py` exercises the reasoning flow without calling Gemini. LLM runs append intervention records to the configured processed business data, so preserve or restore that file if you want to discard demo changes.

## Frontend Landing Page

The `#/` route renders a marketing landing page built on the same data:
- `Landing.tsx` — hero, problem framing, five-step pipeline, evidence, glossary.
- `township3d.ts` — a scroll-driven Three.js scene (`township.json`) with five camera "beats" matching the pipeline stages. Buildings rise as the page loads, dead assets pulse orange smoke, the focus building lights up green as the simulated year rings expand.
- `Evidence.tsx` — five cited source layers (Microsoft Footprints, OSM, CIDB + Energy Commission, Huff + Ewing & Cervero + Cervero, UNEP GlobalABC).
- `Pitch.tsx` / `System.tsx` — problem, feasibility, impact, closing sections.

The demo app is at `#/demo` (App.tsx). No backend calls are made by the landing page beyond `fetchProfiles()` for the headline counts.

## Data

The active data paths are defined in `backend/configs/paths.yml`:

- `bukit_jelutong/raw/geometry/` contains the raw Bukit Jelutong geometry layers.
- `bukit_jelutong/processed/geometry/` contains the geometry layers used by the analysis.
- `bukit_jelutong/processed/business/` contains assets, metrics, leases, projects, candidates, interventions, profiles, diagnoses, and scenario results.
- `elmina/geometry/` contains a separate Elmina geometry set; it is not selected by the current default path configuration.
- `frontend/public/data/` and `frontend/src/mockData.ts` contain frontend demonstration data. [`frontend/MOCK_DATA.md`](frontend/MOCK_DATA.md) describes known mock fields and caveats.

The configured spatial layers are parcels, buildings, network edges, green/blue features, amenities, and population. Business tables join to spatial features using stable IDs. Geometry is analyzed in EPSG:32647 and returned to EPSG:4326 where needed for map display.

**Dataset scale (Bukit Jelutong, current):** 916 assets across 5 asset types; 61 flagged `deadspace_candidate`; ~130,900 tCO₂e/yr operational carbon baseline; 312 tCO₂e/yr canopy sequestration. These counts come from `GET /api/assets/profiles` and are refreshed live by `Landing.tsx`.

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