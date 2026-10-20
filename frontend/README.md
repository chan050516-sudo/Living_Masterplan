# Living Masterplan — Frontend

React + TypeScript + Vite + MapLibre GL JS. Talks to the FastAPI backend described in [`../API.md`](../API.md).

## Run locally

1. Start the backend (from the repo root, in a Python env with the backend dependencies):

   ```bash
   cd backend
   uvicorn app.api.main:app --port 8000
   ```

   `POST /api/analyze` also needs Google Vertex AI credentials (`GOOGLE_CLOUD_PROJECT` set and
   `gcloud auth application-default login`). The map and asset panels work without them.

2. Start the frontend:

   ```bash
   npm install
   npm run dev
   ```

   Vite proxies `/api/*` to `http://localhost:8000` (see `vite.config.ts`).
   To point at a deployed backend instead, set `VITE_API_URL=https://your-host`.

## How it uses the API

| Screen | Endpoint | Code |
|---|---|---|
| Map polygons, coloured by `map_status` | `GET /api/map/geometry` | `src/App.tsx` |
| Asset list + asset panel (diagnosis, evidence) | `GET /api/assets/profiles` (loaded once, cached) | `src/components/DeadspaceList.tsx`, `AssetPanel.tsx` |
| Ask the AI about an asset (with optional .txt/.csv/.pdf files) | `POST /api/analyze` (multipart form) | `src/components/AssetPanel.tsx` |
| "Show plan on map" overlay | `GET /api/map/geometry?run_id=…` | `src/App.tsx` |
| Simulation results (before/after, counterfactual, timeline) | `POST /api/analyze` response | `src/components/ComparisonModal.tsx` |

All API calls live in `src/api.ts`; response types are in `src/types.ts`.
