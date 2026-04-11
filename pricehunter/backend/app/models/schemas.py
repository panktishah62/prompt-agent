from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class StructuredQuery(BaseModel):
    """Output of LLM #1 — the structured version of user's raw query."""

    product: str
    category: str
    location: str
    intent: Literal["cheapest", "fastest", "best_value", "nearest"]
    raw_query: str


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
    is_mock: bool = False


class VoiceCallResult(BaseModel):
    """Raw result from a voice call before extraction."""

    vendor: VendorInfo
    call_id: str
    status: Literal["completed", "failed", "no_answer", "busy"]
    transcript: Optional[str] = None
    duration_seconds: Optional[int] = None
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
