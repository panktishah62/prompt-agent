from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import ChatMessageRequest, ChatMessageResponse
from app.services import chat_session

router = APIRouter()


@router.post("/api/chat/message", response_model=ChatMessageResponse)
async def chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    return await chat_session.process_message(request.message, request.session_id)
