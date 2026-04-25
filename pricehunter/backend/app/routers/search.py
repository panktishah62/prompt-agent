from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi import HTTPException

from app.models.schemas import SearchRequest, SearchResponse
from app.services import orchestrator, request_context

router = APIRouter()


@router.post("/api/search", response_model=SearchResponse)
async def search(request: Request, payload: SearchRequest) -> SearchResponse:
    try:
        metadata = request_context.extract_request_metadata(request)
        return await orchestrator.run_search(payload.query, payload.location, request_metadata=metadata)
    except orchestrator.UnsupportedCategoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
