from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.models.schemas import (
    ChatHistoryMessageCreate,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionDetail,
    ChatSessionSummary,
    SearchProgressSnapshot,
)
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


@router.get("/api/chat/sessions", response_model=list[ChatSessionSummary])
async def list_chat_sessions(request: Request) -> list[ChatSessionSummary]:
    metadata = request_context.extract_request_metadata(request)
    return await chat_session.list_sessions(metadata.get("device_id"))


@router.get("/api/chat/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_chat_session(session_id: str) -> ChatSessionDetail:
    detail = await chat_session.get_session_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return detail


@router.post("/api/chat/sessions/{session_id}/messages", status_code=204)
async def persist_chat_history_message(session_id: str, payload: ChatHistoryMessageCreate) -> Response:
    await chat_session.persist_history_message(session_id, payload)
    return Response(status_code=204)
