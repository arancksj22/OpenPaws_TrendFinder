"""FastAPI application entrypoint."""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router


def _load_cors_origins() -> list[str]:
	raw = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://localhost:5173")
	return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="OpenPaws TrendFinder", version="0.1.0")
app.add_middleware(
	CORSMiddleware,
	allow_origins=_load_cors_origins(),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
	return {"status": "ok"}
