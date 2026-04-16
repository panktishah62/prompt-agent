from __future__ import annotations

import logging
import re

from app.models.schemas import (
    ChatField,
    ChatMessageResponse,
    ConversationState,
    SearchStrategy,
    StructuredQuery,
)
from app.services import orchestrator, query_structurer

logger = logging.getLogger(__name__)

_SESSIONS: dict[str, ConversationState] = {}

GENERIC_PRODUCT_TERMS = {
    "iphone",
    "phone",
    "mobile",
    "laptop",
    "tv",
    "television",
    "tablet",
    "headphones",
    "earbuds",
    "medicine",
    "shirt",
    "shoes",
    "grocery",
    "vegetables",
    "service",
    "repair",
}

URGENCY_OPTIONS = ["Immediate", "1-2 days", "10 days", "No rush"]


def _get_session(session_id: str | None) -> ConversationState:
    if session_id and session_id in _SESSIONS:
        return _SESSIONS[session_id]

    state = ConversationState()
    _SESSIONS[state.session_id] = state
    return state


def _save_session(state: ConversationState) -> None:
    _SESSIONS[state.session_id] = state


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_specific_product(product: str | None, category: str | None) -> bool:
    if not product:
        return False

    normalized = _normalize_whitespace(product).lower()
    if not normalized:
        return False

    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        return False

    if normalized in GENERIC_PRODUCT_TERMS:
        return False

    if category == "electronics":
        has_capacity = bool(re.search(r"\b\d+\s?(gb|tb)\b", normalized))
        has_model_number = bool(re.search(r"\b\d{1,2}\b", normalized))
        has_variant = any(token in normalized for token in ("pro", "plus", "max", "mini", "ultra", "air"))
        brand_only = len(tokens) <= 2 and not (has_capacity or has_model_number or has_variant)
        if any(token in normalized for token in ("iphone", "samsung", "oneplus", "pixel", "redmi", "vivo", "oppo")):
            return not brand_only

    if category == "services":
        return len(tokens) >= 2

    return True


def _parse_urgency(message: str) -> str | None:
    lowered = message.lower()
    if any(token in lowered for token in ("immediate", "right now", "asap", "today", "urgent", "now")):
        return "immediate"
    if any(token in lowered for token in ("1-2 days", "1 / 2 days", "1 or 2 days", "tomorrow", "day after")):
        return "1-2 days"
    if any(token in lowered for token in ("10 days", "ten days", "next week", "a week or so")):
        return "10 days"
    if any(token in lowered for token in ("no rush", "flexible", "anytime", "whenever")):
        return "no rush"
    return None


def _parse_intent(message: str) -> str | None:
    lowered = message.lower()
    if any(token in lowered for token in ("cheap", "cheapest", "lowest", "budget")):
        return "cheapest"
    if "best value" in lowered or any(token in lowered for token in ("value", "balanced", "worth it")):
        return "best_value"
    if any(token in lowered for token in ("fast", "fastest", "quick", "quickest", "urgent")):
        return "fastest"
    return None


def _next_missing_field(state: ConversationState) -> ChatField | None:
    order: list[ChatField] = ["product", "urgency", "intent", "category"]
    for field in order:
        if field in state.missing_fields:
            return field
    return None


def _update_missing_fields(state: ConversationState) -> None:
    missing: list[ChatField] = []
    if not _is_specific_product(state.product, state.category):
        missing.append("product")
    if not state.urgency:
        missing.append("urgency")
    if not state.intent:
        missing.append("intent")
    if not state.category:
        missing.append("category")
    state.missing_fields = missing
    state.awaiting_field = _next_missing_field(state)


def _suggested_replies(field: ChatField | None) -> list[str]:
    if field == "urgency":
        return URGENCY_OPTIONS
    if field == "intent":
        return ["Cheapest", "Best value", "Fastest"]
    if field == "product":
        return ["iPhone 16 128GB", "Daikin AC repair", "Tomatoes 1kg"]
    return []


def _parse_category(message: str) -> str | None:
    lowered = message.lower().strip()
    allowed = ("groceries", "electronics", "clothing", "medicine", "hardware", "services")
    for category in allowed:
        if lowered == category or f" {category}" in lowered or f"{category} " in lowered:
            return category
    return None


def _question_for_state(state: ConversationState) -> str:
    if state.awaiting_field == "product":
        existing = state.product or "that"
        return (
            f"I need the exact product or service before I search. \"{existing}\" is still too broad. "
            "Please reply with the precise item, like \"iPhone 16 128GB\" or \"Daikin AC repair\"."
        )
    if state.awaiting_field == "urgency":
        return (
            "How soon do you need it? Choose one: Immediate, 1-2 days, 10 days, or No rush. "
            "If you do not specify, I will default to Immediate."
        )
    if state.awaiting_field == "intent":
        return "What should I prioritize for this search: Cheapest, Best value, or Fastest?"
    if state.awaiting_field == "category":
        return (
            "Which category fits best: groceries, electronics, clothing, medicine, hardware, or services?"
        )
    return "Tell me what you want to find, and I will narrow it down before searching."


def _decide_search_strategy(state: ConversationState) -> SearchStrategy:
    return "both"


async def _merge_message_into_state(state: ConversationState, message: str) -> None:
    state.raw_query = _normalize_whitespace(f"{state.raw_query} {message}")
    parsed_location = query_structurer.infer_location(message)
    if parsed_location != "unknown":
        state.location = parsed_location

    parsed_intent = _parse_intent(message)
    if parsed_intent:
        state.intent = parsed_intent

    parsed_urgency = _parse_urgency(message)
    if parsed_urgency:
        state.urgency = parsed_urgency

    parsed_category = _parse_category(message)
    if parsed_category:
        state.category = parsed_category

    if state.awaiting_field == "urgency":
        urgency = _parse_urgency(message)
        if urgency:
            state.urgency = urgency
        else:
            state.urgency_prompt_count += 1
            if state.urgency_prompt_count >= 1:
                state.urgency = "immediate"
        return

    if state.awaiting_field == "intent":
        return

    if state.awaiting_field == "category":
        parsed = _parse_category(message) or query_structurer.infer_category(message)
        if parsed:
            state.category = parsed
        return

    if state.awaiting_field == "product":
        structured = await query_structurer.structure_query(message)
        state.product = structured.product or _normalize_whitespace(message)
        if not state.category:
            state.category = structured.category
        if structured.location != "unknown":
            state.location = structured.location
        return

    structured = await query_structurer.structure_query(message)
    if structured.product:
        state.product = structured.product
    if structured.category:
        state.category = structured.category
    if structured.location and structured.location != "unknown":
        state.location = structured.location

    if not state.intent and structured.intent in {"cheapest", "fastest", "best_value"}:
        state.intent = structured.intent

    if not state.urgency:
        state.urgency = None


def _build_structured_query(state: ConversationState) -> StructuredQuery:
    return StructuredQuery(
        product=state.product or "",
        category=state.category or "services",
        location=state.location or "unknown",
        intent=state.intent or "cheapest",
        urgency=state.urgency or "immediate",
        raw_query=state.raw_query.strip() or (state.product or ""),
    )


async def process_message(message: str, session_id: str | None = None) -> ChatMessageResponse:
    state = _get_session(session_id)
    user_message = _normalize_whitespace(message)
    logger.info("Processing chat message for session=%s", state.session_id)

    await _merge_message_into_state(state, user_message)
    _update_missing_fields(state)

    if state.awaiting_field is not None:
        assistant_message = _question_for_state(state)
        _save_session(state)
        return ChatMessageResponse(
            session_id=state.session_id,
            assistant_message=assistant_message,
            state=state,
            ready_to_search=False,
            suggested_replies=_suggested_replies(state.awaiting_field),
        )

    state.search_strategy = _decide_search_strategy(state)
    structured_query = _build_structured_query(state)
    results = await orchestrator.run_search_structured(
        structured_query,
        search_strategy=state.search_strategy,
    )

    scope_phrase = {
        "online": "online sources",
        "offline": "nearby offline vendors",
        "both": "both online and offline sources",
    }[state.search_strategy]
    assistant_message = (
        f"Searching {scope_phrase} for {structured_query.product}. "
        f"I am optimizing for {structured_query.intent.replace('_', ' ')} with {structured_query.urgency} urgency."
    )

    _save_session(state)
    return ChatMessageResponse(
        session_id=state.session_id,
        assistant_message=assistant_message,
        state=state,
        ready_to_search=True,
        suggested_replies=[],
        results=results,
    )
