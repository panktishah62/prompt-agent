from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

UrgencyOption = Literal["immediate", "1-2 days", "10 days", "no rush"]
SearchStrategy = Literal["online", "offline", "both"]
ChatIntent = Literal["cheapest", "fastest", "best_value"]
ChatField = Literal["product", "urgency", "intent", "category", "location"]
ProgressStatus = Literal["pending", "running", "completed", "failed"]


class StructuredQuery(BaseModel):
    """Output of LLM #1 — the structured version of user's raw query."""

    product: str
    category: str
    location: str
    intent: Literal["cheapest", "fastest", "best_value", "nearest"]
    urgency: UrgencyOption = "immediate"
    raw_query: str


class ProductPrecisionAssessment(BaseModel):
    """Whether a product request is precise enough to search."""

    refined_product: str
    precise_enough: bool
    missing_attributes: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class UnifiedResult(BaseModel):
    """THE core schema. Both pipelines MUST return a list of these."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: Literal["online", "offline"]
    name: str
    price: Optional[float] = None
    currency: str = "INR"
    delivery_time: Optional[str] = None
    availability: bool = True
    negotiated: bool = False
    confidence: float = 0.5
    url: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_mock: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VendorInfo(BaseModel):
    """A discovered local vendor."""

    name: str
    phone: str
    address: str
    location: Optional[dict] = None
    place_id: Optional[str] = None
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    is_mock: bool = False


class VoiceCallResult(BaseModel):
    """Raw result from a voice call before extraction."""

    vendor: VendorInfo
    call_id: str
    status: Literal["completed", "failed", "no_answer", "busy"]
    transcript: Optional[str] = None
    duration_seconds: Optional[int] = None
    extracted_data: Optional[dict] = None
    is_mock: bool = False


class SearchRequest(BaseModel):
    """API request body."""

    query: str
    location: Optional[str] = None


class SearchResponse(BaseModel):
    """API response body."""

    query: StructuredQuery
    results: list[UnifiedResult]
    online_count: int
    offline_count: int
    total_time_seconds: float
    search_strategy: SearchStrategy = "both"


class SearchProgressStep(BaseModel):
    id: str
    label: str
    status: ProgressStatus = "pending"
    detail: Optional[str] = None


class SearchProgressSnapshot(BaseModel):
    search_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: StructuredQuery
    status: ProgressStatus = "pending"
    discovered_vendors: list[VendorInfo] = Field(default_factory=list)
    online_platforms: list[str] = Field(default_factory=list)
    steps: list[SearchProgressStep] = Field(default_factory=list)
    partial_results: list[UnifiedResult] = Field(default_factory=list)
    final_results: Optional[SearchResponse] = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationState(BaseModel):
    """Current chatbot slot-filling state for a search session."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product: Optional[str] = None
    category: Optional[str] = None
    location: str = "unknown"
    intent: Optional[ChatIntent] = None
    urgency: Optional[UrgencyOption] = None
    missing_fields: list[ChatField] = Field(default_factory=list)
    awaiting_field: Optional[ChatField] = None
    search_strategy: Optional[SearchStrategy] = None
    raw_query: str = ""
    urgency_prompt_count: int = 0
    product_precise: bool = False
    product_missing_attributes: list[str] = Field(default_factory=list)
    product_follow_up_questions: list[str] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    """User message for the chat workflow."""

    message: str
    session_id: Optional[str] = None
    location: Optional[str] = None


class ChatHistoryMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: Literal["assistant", "user"]
    content: str
    kind: Literal["text", "status", "results"] = "text"
    payload: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    last_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(BaseModel):
    session_id: str
    title: str
    state: Optional[ConversationState] = None
    messages: list[ChatHistoryMessage] = Field(default_factory=list)
    latest_search: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class ChatHistoryMessageCreate(BaseModel):
    message_id: Optional[str] = None
    role: Literal["assistant", "user"]
    content: str
    kind: Literal["text", "status", "results"] = "text"
    payload: Optional[dict] = None


class ChatMessageResponse(BaseModel):
    """Assistant reply plus optional search results."""

    session_id: str
    assistant_message: str
    state: ConversationState
    ready_to_search: bool = False
    suggested_replies: list[str] = Field(default_factory=list)
    results: Optional[SearchResponse] = None
    search_progress: Optional[SearchProgressSnapshot] = None


class ResolveLocationRequest(BaseModel):
    latitude: float
    longitude: float


class ResolveLocationResponse(BaseModel):
    location: str
    formatted_address: Optional[str] = None
