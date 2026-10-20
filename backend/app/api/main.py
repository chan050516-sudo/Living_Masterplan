import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

# Ensure backend.app can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_paths
from app.llm.orchestrator import orchestrate_and_simulate_batch
from app.llm.vertex_client import VertexGeminiClient
from app.llm.file_parser import parse_uploaded_file
from app.llm.tool_service import TownshipDataSource

log = logging.getLogger(__name__)
app = FastAPI(title="Living Masterplan API")

# Enable CORS and Gzip compression for large JSON payloads
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

from app.config import load_paths

REPO_ROOT = Path(__file__).resolve().parents[3]  # -> Living_Masterplan/
_PATHS = load_paths()
BASE_DIR = REPO_ROOT / _PATHS["base"]  # -> Living_Masterplan/bukit_jelutong/processed

MAX_QUERY_LENGTH = 5000
MAX_FILE_SIZE_MB = 10
MAX_FILES = 3


# class AnalyzeRequest(BaseModel):
#     user_query: str = Field(..., max_length=MAX_QUERY_LENGTH, description="User's question")
#     selected_assets: str = Field(..., description="Comma-separated asset IDs")

#     @field_validator('selected_assets')
#     @classmethod
#     def validate_assets(cls, v):
#         if not v.strip():
#             raise ValueError("selected_assets cannot be empty")
#         return v


# =====================================================================
# API 1: Run LLM Analysis Pipeline
# =====================================================================
@app.post("/api/analyze")
async def analyze_township(
    user_query: str = Form(..., max_length=MAX_QUERY_LENGTH, description="User's question"),
    selected_assets: str = Form(..., description="Comma-separated asset IDs"),
    files: Optional[List[UploadFile]] = File(None)
):
    try:
        # 1. Parse and validate asset IDs
        asset_ids = [aid.strip() for aid in selected_assets.split(",") if aid.strip()]
        if not asset_ids:
            raise HTTPException(status_code=400, detail="selected_assets cannot be empty")
        
        ds = TownshipDataSource(REPO_ROOT, year=2026)
        valid_assets = set(ds.assets["asset_id"].astype(str))
        invalid_ids = [aid for aid in asset_ids if aid not in valid_assets]
        if invalid_ids:
            raise HTTPException(status_code=400, detail=f"Invalid asset IDs: {invalid_ids}")

        # 2. Validate uploaded files (size and count limits)
        if files:
            if len(files) > MAX_FILES:
                raise HTTPException(status_code=400, detail=f"Too many files. Max {MAX_FILES}.")
            
            for file in files:
                file.file.seek(0, 2) # Seek to end to get size
                size_mb = file.file.tell() / (1024 * 1024)
                file.file.seek(0) # Reset pointer
                if size_mb > MAX_FILE_SIZE_MB:
                    raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds {MAX_FILE_SIZE_MB}MB limit.")

        # 3. Parse uploaded files (Handle PDFs and Text)
        augmented_query = user_query
        attachments = []
        
        if files:
            augmented_query += "\n\n--- ATTACHED DOCUMENTS ---\n"
            for file in files:
                content = await file.read()
                if file.content_type == "application/pdf":
                    # Pass PDF directly to the LLM as multimodal input
                    attachments.append((content, "application/pdf"))
                    augmented_query += f"\n[Attached PDF Document: {file.filename}]\n"
                else:
                    # Parse text/csv locally and append to prompt
                    parsed_text = parse_uploaded_file(content, file.filename)
                    augmented_query += parsed_text

        log.info(f"Processing API request for {len(asset_ids)} assets. Query len: {len(augmented_query)}")

        # 4. Run Orchestrator
        client = VertexGeminiClient(thinking_level="MEDIUM", temperature=0.2)

        result = orchestrate_and_simulate_batch(
            user_query=augmented_query,
            selected_asset_ids=asset_ids,
            llm_client=client,
            repo_root=REPO_ROOT,
            base_year=2026,
            attachments=attachments
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return result

    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        log.exception("Analysis pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# API 2: Get Full Asset Profiles (For Dashboard/Modals)
# =====================================================================
@app.get("/api/assets/profiles")
async def get_asset_profiles():
    """
    Returns the cleaned dictionary of all asset profiles.
    Frontend should fetch this once and cache it in memory (O(1) lookup).
    """
    profile_path = BASE_DIR / "business" / "asset_profiles_2026.json"
    if not profile_path.exists():
        raise HTTPException(
            status_code=500, 
            detail="Profiles not found. Run build_profiles.py first."
        )
    
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


# =====================================================================
# API 3: Get Map Geometry (For MapLibre GL JS)
# =====================================================================
@app.get("/api/map/geometry")
async def get_map_geometry(
    run_id: Optional[str] = Query(None, description="Optional LLM run ID"),
    year: int = Query(2026, description="Target simulation year"),
):
    """
    Returns a lightweight GeoJSON FeatureCollection.
    Supports dynamic map_status and diagnosis-based metadata for different simulation years.
    """
    paths = load_paths()
    
    # 1. Load status dictionary based on the requested year
    ds_dict = {}
    flags_dict = {}
    urgency_dict = {}
    
    if year == 2026:
        # For 2026, use the authoritative B6 deadspace output
        ds_path = BASE_DIR / "business" / "deadspace_2026.json"
        if ds_path.exists():
            with open(ds_path, "r", encoding="utf-8") as f:
                ds_list = json.load(f)
                ds_dict = {d["asset_id"]: d["status"] for d in ds_list}
                flags_dict = {d["asset_id"]: d.get("flags", []) for d in ds_list}
                urgency_dict = {d["asset_id"]: d.get("urgency_index", 0) for d in ds_list}
    else:
        # For 2027+, read the B4 SC-CURRENT baseline simulation
        sc_path = BASE_DIR / "business" / "scenarios" / "SC-CURRENT.json"
        if sc_path.exists():
            with open(sc_path, "r", encoding="utf-8") as f:
                sc_data = json.load(f)
                year_assets = sc_data.get("years", {}).get(str(year), {}).get("assets", {})
                for aid, state in year_assets.items():
                    if aid.startswith("PRJ::"):
                        continue
                    
                    occ = state.get("occupancy_rate")
                    util = state.get("utilisation_rate")
                    
                    # Dynamic status inference for future years
                    status = "healthy"
                    flags = []
                    urgency = 0.0
                    
                    if occ is not None and occ < 0.50:
                        status = "deadspace_candidate"
                        flags.append("low_occupancy")
                        urgency = 2.0
                    elif util is not None and util < 0.40:
                        status = "underperforming_facility"
                        flags.append("low_utilisation")
                        urgency = 2.0
                        
                    ds_dict[aid] = status
                    flags_dict[aid] = flags
                    urgency_dict[aid] = urgency

    # Overlay LLM intervention status if run_id is provided
    if run_id:
        run_path = BASE_DIR / "business" / "llm_runs" / f"{run_id}.json"
        if run_path.exists():
            with open(run_path, "r", encoding="utf-8") as f:
                run_data = json.load(f)
            for asset in run_data.get("frontend", {}).get("assets_analysis", []):
                ds_dict[asset["asset_id"]] = "intervened"

    # 2. Load the geometry layers
    gdf_buildings = gpd.read_file(BASE_DIR / paths["geometry"]["buildings"])
    asset_ids = set(pd.read_csv(BASE_DIR / paths["business"]["assets"])["asset_id"].astype(str))
    gdf_buildings["building_id"] = gdf_buildings["building_id"].astype(str).str.replace("unlinked-", "")
    # Calculate extrusion height based on floors (3.5m per floor)
    gdf_buildings["height"] = gdf_buildings["floors"].fillna(1).clip(lower=1) * 3.5
    gdf_buildings = gdf_buildings[gdf_buildings["building_id"].isin(asset_ids)].copy()
    gdf_buildings["asset_id"] = gdf_buildings["building_id"]
    
    gdf_parcels = gpd.read_file(BASE_DIR / paths["geometry"]["parcels"])
    gdf_green = gpd.read_file(BASE_DIR / paths["geometry"]["green_blue"])
    
    gdf_parcels = gdf_parcels[gdf_parcels["land_use"] == "undeveloped"].copy()
    
    # 3. Assign dynamic statuses
    gdf_buildings["map_status"] = gdf_buildings["asset_id"].map(lambda x: ds_dict.get(x, "healthy"))
    gdf_parcels["map_status"] = "vacant"
    
    green_id_col = "asset_id" if "asset_id" in gdf_green.columns else "green_id"
    gdf_green["asset_id"] = gdf_green[green_id_col]
    gdf_green = gdf_green[gdf_green["asset_id"].isin(asset_ids)].copy()
    gdf_green["map_status"] = gdf_green["asset_id"].map(lambda x: ds_dict.get(x, "healthy"))

    # 4. Attach diagnostic metadata directly to geometry properties
    def _attach_metadata(df):
        df["flags"] = df["asset_id"].map(lambda x: flags_dict.get(x, []))
        df["urgency_index"] = df["asset_id"].map(lambda x: urgency_dict.get(x, 0.0))
        return df

    gdf_buildings = _attach_metadata(gdf_buildings)
    gdf_green = _attach_metadata(gdf_green)
    gdf_parcels = _attach_metadata(gdf_parcels)

    # 5. Keep only necessary columns to reduce payload size
    cols = ["asset_id", "map_status", "flags", "urgency_index", "height", "geometry"]
    for df in [gdf_buildings, gdf_parcels, gdf_green]:
        for c in cols:
            if c not in df.columns:
                df[c] = None

    # 6. Combine and convert to EPSG:4326
    combined_gdf = pd.concat([
        gdf_buildings[cols],
        gdf_parcels[cols],
        gdf_green[cols]
    ], ignore_index=True)
    
    combined_gdf = combined_gdf.to_crs("EPSG:4326")
    
    return Response(content=combined_gdf.to_json(), media_type="application/json")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)