"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import pipeline, trends

api_router = APIRouter()
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(trends.router, prefix="/trends", tags=["trends"])
