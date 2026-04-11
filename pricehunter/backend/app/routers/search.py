from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import SearchRequest, SearchResponse
from app.services import orchestrator

router = APIRouter()


@router.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    return await orchestrator.run_search(request.query, request.location)
