import logging
import sys
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# 确保能找到 backend.app
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.orchestrator import orchestrate_and_simulate_batch
from app.llm.vertex_client import VertexGeminiClient
from app.llm.file_parser import parse_uploaded_file
from app.llm.tool_service import TownshipDataSource

log = logging.getLogger(__name__)
app = FastAPI(title="Living Masterplan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_QUERY_LENGTH = 5000
MAX_FILE_SIZE_MB = 10
MAX_FILES = 3

class AnalyzeRequest(BaseModel):
    user_query: str = Field(..., max_length=MAX_QUERY_LENGTH, description="User's question")
    selected_assets: str = Field(..., description="Comma-separated asset IDs")

    @field_validator('selected_assets')
    @classmethod
    def validate_assets(cls, v):
        if not v.strip():
            raise ValueError("selected_assets cannot be empty")
        return v

@app.post("/api/analyze")
async def analyze_township(
    request: AnalyzeRequest,
    files: Optional[List[UploadFile]] = File(None)
):
    try:
        # 1. Parse and validate asset IDs exist in the data source
        asset_ids = [aid.strip() for aid in request.selected_assets.split(",") if aid.strip()]
        
        ds = TownshipDataSource(REPO_ROOT, year=2026)
        valid_assets = set(ds.assets["asset_id"].astype(str))
        invalid_ids = [aid for aid in asset_ids if aid not in valid_assets]
        if invalid_ids:
            raise HTTPException(status_code=400, detail=f"Invalid asset IDs: {invalid_ids}")

        # 2. Validate files
        if files:
            if len(files) > MAX_FILES:
                raise HTTPException(status_code=400, detail=f"Too many files. Max {MAX_FILES}.")
            
            for file in files:
                file.file.seek(0, 2) # Seek to end to get size
                size_mb = file.file.tell() / (1024 * 1024)
                file.file.seek(0) # Reset pointer
                if size_mb > MAX_FILE_SIZE_MB:
                    raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds {MAX_FILE_SIZE_MB}MB limit.")

        # 3. Parse uploaded files
        augmented_query = request.user_query
        if files:
            augmented_query += "\n\n--- ATTACHED DOCUMENTS ---\n"
            for file in files:
                content = await file.read()
                parsed_text = parse_uploaded_file(content, file.filename)
                augmented_query += parsed_text

        log.info(f"Processing API request for {len(asset_ids)} assets. Query len: {len(augmented_query)}")

        # 4. Run Orchestrator
        client = VertexGeminiClient(thinking_level="MEDIUM", temperature=0.2)

        attachments = []
        augmented_query = request.user_query
        
        if files:
            for file in files:
                content = await file.read()
                if file.content_type == "application/pdf":
                    # Pass directly to LLM
                    attachments.append((content, "application/pdf"))
                    augmented_query += f"\n[Attached PDF Document: {file.filename}]\n"
                else:
                    # Parse text locally
                    parsed_text = parse_uploaded_file(content, file.filename)
                    augmented_query += parsed_text

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