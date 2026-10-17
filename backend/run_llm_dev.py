from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.llm.router import router

app = FastAPI(title="Living Masterplan LLM API (dev)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)