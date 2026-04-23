from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatMessageRequest, ChatMessageResponse, SearchProgressSnapshot
from app.services import chat_session, search_progress

router = APIRouter()


@router.post("/api/chat/message", response_model=ChatMessageResponse)
async def chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    return await chat_session.process_message(request.message, request.session_id, request.location)


@router.get("/api/chat/search/{search_id}", response_model=SearchProgressSnapshot)
async def chat_search_status(search_id: str) -> SearchProgressSnapshot:
    snapshot = search_progress.get_snapshot(search_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Search session not found.")
    return snapshot
