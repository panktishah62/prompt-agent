from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException

from app.models.schemas import SearchRequest, SearchResponse
from app.services import orchestrator

router = APIRouter()


@router.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    try:
        return await orchestrator.run_search(request.query, request.location)
    except orchestrator.UnsupportedCategoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
