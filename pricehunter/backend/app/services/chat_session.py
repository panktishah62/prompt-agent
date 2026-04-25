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
from app.services import orchestrator, query_structurer, search_progress

logger = logging.getLogger(__name__)

_SESSIONS: dict[str, ConversationState] = {}

GENERIC_PRODUCT_TERMS = {
    "iron",
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

SUPPORTED_CHAT_CATEGORIES = ("electronics", "medicine")

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


async def _refresh_product_precision(state: ConversationState) -> None:
    candidate_product = state.product or query_structurer.infer_product(state.raw_query)
    assessment = await query_structurer.analyze_product_precision(
        raw_query=state.raw_query,
        category=state.category,
        current_product=candidate_product,
    )
    state.product = assessment.refined_product or candidate_product
    state.product_precise = assessment.precise_enough and _is_specific_product(state.product, state.category)
    state.product_missing_attributes = assessment.missing_attributes
    state.product_follow_up_questions = assessment.follow_up_questions


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
    if not state.product_precise or not _is_specific_product(state.product, state.category):
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
        return ["iPhone 16 128GB", "boat Airdopes 141", "paracetamol tablets"]
    return []


def _product_suggested_replies(state: ConversationState) -> list[str]:
    normalized = (state.product or "").lower()
    if "iron" in normalized:
        return [
            "Philips steam iron under 3000",
            "Bajaj dry iron 1000W",
            "Usha garment steamer",
        ]
    if state.category == "medicine" or any(
        term in normalized for term in ("paracetamol", "tablet", "capsule", "syrup")
    ):
        return [
            "Dolo 650 tablets, 1 strip",
            "Paracetamol 500 mg, 10 tablets",
            "Calpol 650, any brand substitute okay",
        ]
    return ["iPhone 16 128GB Black", "boat Airdopes 141", "paracetamol 650 mg tablets"]


def _parse_category(message: str) -> str | None:
    lowered = message.lower().strip()
    allowed = ("groceries", "electronics", "clothing", "medicine", "hardware", "services")
    for category in allowed:
        if lowered == category or f" {category}" in lowered or f"{category} " in lowered:
            return category
    if lowered == "medicines":
        return "medicine"
    return None


def _unsupported_category_response(state: ConversationState) -> ChatMessageResponse:
    assistant_message = query_structurer.unsupported_category_message()
    state.category = None
    state.product = None
    state.product_precise = False
    state.product_missing_attributes = []
    state.product_follow_up_questions = []
    state.search_strategy = None
    state.awaiting_field = "product"
    state.missing_fields = ["product", "urgency", "intent", "category"]
    _save_session(state)
    return ChatMessageResponse(
        session_id=state.session_id,
        assistant_message=assistant_message,
        state=state,
        ready_to_search=False,
        suggested_replies=["iPhone 16 128GB", "boat earphones", "paracetamol tablets"],
    )


def _question_for_state(state: ConversationState) -> str:
    if state.awaiting_field == "product":
        existing = state.product or "that"
        if state.product_follow_up_questions:
            lines = [
                f'I want to avoid a vague search. "{existing}" still needs a bit more detail before I start looking.',
                "Please reply with these details:",
            ]
            for index, question in enumerate(state.product_follow_up_questions, start=1):
                lines.append(f"{index}. {question}")
            return "\n".join(lines)
        return (
            f"I need the exact product or service before I search. \"{existing}\" is still too broad. "
            "Please reply with the precise item, like \"iPhone 16 128GB\" or \"paracetamol tablets\"."
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
        await _refresh_product_precision(state)
        return

    if state.awaiting_field == "intent":
        await _refresh_product_precision(state)
        return

    if state.awaiting_field == "category":
        parsed = _parse_category(message) or query_structurer.infer_category(message)
        if parsed:
            state.category = parsed
        await _refresh_product_precision(state)
        return

    if state.awaiting_field == "product":
        structured = await query_structurer.structure_query(state.raw_query)
        state.product = structured.product or _normalize_whitespace(message)
        if structured.category:
            state.category = structured.category
        if structured.location != "unknown":
            state.location = structured.location
        await _refresh_product_precision(state)
        return

    structured = await query_structurer.structure_query(state.raw_query)
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

    await _refresh_product_precision(state)


def _build_structured_query(state: ConversationState) -> StructuredQuery:
    return StructuredQuery(
        product=state.product or "",
        category=state.category or "services",
        location=state.location or "unknown",
        intent=state.intent or "cheapest",
        urgency=state.urgency or "immediate",
        raw_query=state.raw_query.strip() or (state.product or ""),
    )


async def process_message(
    message: str,
    session_id: str | None = None,
    location: str | None = None,
) -> ChatMessageResponse:
    state = _get_session(session_id)
    user_message = _normalize_whitespace(message)
    logger.info("Processing chat message for session=%s", state.session_id)

    if location:
        state.location = _normalize_whitespace(location)

    await _merge_message_into_state(state, user_message)
    if state.category and not query_structurer.is_supported_category(state.category):
        return _unsupported_category_response(state)
    _update_missing_fields(state)

    if state.awaiting_field is not None:
        assistant_message = _question_for_state(state)
        _save_session(state)
        return ChatMessageResponse(
            session_id=state.session_id,
            assistant_message=assistant_message,
            state=state,
            ready_to_search=False,
            suggested_replies=(
                _product_suggested_replies(state)
                if state.awaiting_field == "product"
                else _suggested_replies(state.awaiting_field)
            ),
        )

    state.search_strategy = _decide_search_strategy(state)
    structured_query = _build_structured_query(state)
    try:
        progress = await search_progress.start_search(
            structured_query,
            search_strategy=state.search_strategy,
        )
    except orchestrator.UnsupportedCategoryError:
        return _unsupported_category_response(state)

    vendor_count = len(progress.discovered_vendors)
    platform_count = len(progress.online_platforms)
    assistant_message = (
        f"I found {vendor_count} nearby vendors and queued {platform_count} online sources for "
        f"{structured_query.product} in {structured_query.location}. I’m showing the vendor list now and "
        "will keep updating prices as calls and online fetches complete."
    )

    _save_session(state)
    return ChatMessageResponse(
        session_id=state.session_id,
        assistant_message=assistant_message,
        state=state,
        ready_to_search=True,
        suggested_replies=[],
        search_progress=progress,
    )
