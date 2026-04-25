from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import ChatMessageRequest, ChatMessageResponse, SearchProgressSnapshot
from app.services import chat_session, request_context, search_progress

router = APIRouter()


@router.post("/api/chat/message", response_model=ChatMessageResponse)
async def chat_message(request: Request, payload: ChatMessageRequest) -> ChatMessageResponse:
    metadata = request_context.extract_request_metadata(request)
    return await chat_session.process_message(
        payload.message,
        payload.session_id,
        payload.location,
        request_metadata=metadata,
    )


@router.get("/api/chat/search/{search_id}", response_model=SearchProgressSnapshot)
async def chat_search_status(search_id: str) -> SearchProgressSnapshot:
    snapshot = search_progress.get_snapshot(search_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Search session not found.")
    return snapshot
