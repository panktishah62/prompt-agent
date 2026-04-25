from __future__ import annotations

import logging
import re

from openai import AsyncOpenAI

from app.config import settings
from app.models.schemas import ProductPrecisionAssessment, StructuredQuery, UrgencyOption

logger = logging.getLogger(__name__)

SUPPORTED_CATEGORIES = ("electronics", "medicine")
SUPPORTED_CATEGORY_MESSAGE = (
    "Right now we only serve electronics and medicines. "
    "Please search for an electronics or medicine product."
)

SYSTEM_PROMPT = """
You are a query structuring assistant. Convert the user's natural language shopping query into a structured JSON object.

Return ONLY valid JSON with these exact fields:
- "product": the specific item they want (string)
- "category": broad category like "groceries", "electronics", "clothing", "medicine", "hardware", or "services" (string)
- "location": the city or area mentioned, or "unknown" if not specified (string)
- "intent": one of "cheapest", "fastest", "best_value", "nearest" — infer from context (string)
- "urgency": one of "immediate", "1-2 days", "10 days", "no rush" — infer from context and default to "immediate" if missing
- "raw_query": the original query repeated verbatim (string)

Examples:
User: "I need cheap tomatoes in Rajkot"
Output: {"product": "tomatoes", "category": "groceries", "location": "Rajkot", "intent": "cheapest", "urgency": "immediate", "raw_query": "I need cheap tomatoes in Rajkot"}

User: "fastest delivery for iPhone 15 pro max"
Output: {"product": "iPhone 15 Pro Max", "category": "electronics", "location": "unknown", "intent": "fastest", "urgency": "immediate", "raw_query": "fastest delivery for iPhone 15 pro max"}

Return ONLY the JSON object, no markdown, no explanation.
""".strip()

PRECISION_SYSTEM_PROMPT = """
You are a shopping intake assistant. Decide whether the user's current request is precise enough to safely start product search.

Return ONLY valid JSON with these exact fields:
- "refined_product": a cleaned canonical product name based on the user's latest context
- "precise_enough": boolean
- "missing_attributes": a short list of the important missing attributes still needed before search
- "follow_up_questions": 1 to 4 concise questions that would make the request search-ready

Rules:
- Be strict. If the request could match multiple materially different products, set "precise_enough" to false.
- For electronics, common attributes may include product type, brand, model, storage/capacity, color, wattage/power, size, or budget.
- For medicines, common attributes may include medicine/brand name, strength, dosage form, quantity, and whether substitutes are okay.
- Tailor the questions to the product. Do not ask irrelevant things like color for paracetamol.
- If enough detail is already present to identify a real listing confidently, set "precise_enough" to true and return no follow-up questions.
""".strip()

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "groceries": (
        "tomato",
        "potato",
        "onion",
        "vegetable",
        "fruit",
        "milk",
        "rice",
        "atta",
        "paneer",
        "bread",
        "dal",
        "oil",
        "grocery",
    ),
    "electronics": (
        "iphone",
        "phone",
        "laptop",
        "tv",
        "tablet",
        "earbuds",
        "earphone",
        "headphone",
        "speaker",
        "camera",
        "charger",
        "monitor",
        "boat",
        "noise",
        "jbl",
    ),
    "clothing": (
        "shirt",
        "jeans",
        "dress",
        "shoe",
        "jacket",
        "kurta",
        "tshirt",
        "t-shirt",
        "saree",
        "hoodie",
        "trouser",
        "blazer",
    ),
    "medicine": (
        "medicine",
        "tablet",
        "capsule",
        "syrup",
        "pharmacy",
        "paracetamol",
        "chemist",
        "dolo",
        "crocin",
        "ointment",
        "inhaler",
    ),
    "hardware": (
        "drill",
        "paint",
        "pipe",
        "screw",
        "hammer",
        "tool",
        "plywood",
        "cement",
        "wire",
        "switch",
        "nail",
        "tap",
    ),
    "services": (
        "repair",
        "service",
        "cleaning",
        "plumber",
        "electrician",
        "salon",
        "spa",
        "doctor",
        "dentist",
        "carpenter",
        "installation",
        "massage",
    ),
}

VAGUE_PRODUCT_TERMS = {
    "iron",
    "phone",
    "mobile",
    "iphone",
    "laptop",
    "tv",
    "television",
    "tablet",
    "earphones",
    "earbuds",
    "headphones",
    "speaker",
    "charger",
    "monitor",
    "camera",
    "printer",
    "watch",
    "fridge",
    "refrigerator",
    "ac",
    "air conditioner",
    "washing machine",
    "medicine",
    "tablet",
    "capsule",
    "syrup",
    "paracetamol",
}


def is_supported_category(category: str | None) -> bool:
    return (category or "").strip().lower() in SUPPORTED_CATEGORIES


def unsupported_category_message() -> str:
    return SUPPORTED_CATEGORY_MESSAGE


def infer_category(raw_query: str) -> str:
    lowered = raw_query.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "groceries" if any(token in lowered for token in ("kg", "fresh", "near me")) else "electronics"


def infer_intent(raw_query: str) -> str:
    lowered = raw_query.lower()
    if any(word in lowered for word in ("cheap", "cheapest", "lowest", "budget")):
        return "cheapest"
    if any(word in lowered for word in ("fast", "fastest", "urgent", "quick")):
        return "fastest"
    if any(word in lowered for word in ("near", "nearby", "closest", "nearest")):
        return "nearest"
    return "best_value"


def infer_location(raw_query: str) -> str:
    if "near me" in raw_query.lower():
        return "near me"
    for trigger in ("in", "near", "at"):
        if f" {trigger} " in raw_query.lower():
            return raw_query.lower().split(f" {trigger} ", 1)[1].strip().title() or "unknown"
    return "unknown"


def infer_product(raw_query: str) -> str:
    location_stripped = re.split(r"\b(?:near me|near|in|at)\b", raw_query, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.sub(
        (
            r"\b("
            r"cheapest|cheap|fastest|best|best value|near|near me|in|find|get|need|buy|delivery|for|"
            r"want|looking|searching|purchase|order"
            r")\b"
        ),
        "",
        location_stripped,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(i|me|myself|to|a|an)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned or raw_query.strip()


def infer_urgency(raw_query: str) -> UrgencyOption:
    lowered = raw_query.lower()
    if any(token in lowered for token in ("immediate", "right now", "asap", "today", "urgent")):
        return "immediate"
    if any(token in lowered for token in ("1-2 days", "1 / 2 days", "1 or 2 days", "tomorrow", "day after")):
        return "1-2 days"
    if any(token in lowered for token in ("10 days", "ten days", "next week", "week or so")):
        return "10 days"
    if any(token in lowered for token in ("no rush", "flexible", "anytime", "whenever")):
        return "no rush"
    return "immediate"


def _normalize_product_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,")


def _fallback_follow_up_questions(product: str, category: str | None) -> list[str]:
    normalized = product.lower()

    if "iron" in normalized:
        return [
            "Do you need a dry iron, steam iron, garment steamer, or ironing press?",
            "Any preferred brand, like Philips, Bajaj, Havells, or Usha?",
            "What budget range should I stay within?",
            "Any must-have spec like wattage, soleplate type, or travel use?",
        ]

    if category == "medicine" or any(term in normalized for term in ("paracetamol", "tablet", "capsule", "syrup")):
        return [
            "Which medicine or brand do you need exactly?",
            "What strength or dosage should I look for, like 500 mg or 650 mg?",
            "How much quantity do you need?",
            "Are substitutes okay, or do you need one exact brand?",
        ]

    if any(term in normalized for term in ("iphone", "phone", "mobile", "smartphone")):
        return [
            "Which exact brand and model do you want?",
            "What storage or RAM variant should I search for?",
            "Any preferred color?",
            "What budget range should I stay within?",
        ]

    return [
        "Which exact brand or model should I search for?",
        "What key specification or variant matters most for this item?",
        "What budget range should I stay within?",
    ]


def _fallback_precision_assessment(
    raw_query: str,
    category: str | None = None,
    current_product: str | None = None,
) -> ProductPrecisionAssessment:
    product = _normalize_product_text(current_product or infer_product(raw_query))
    normalized = product.lower()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    has_numbers = bool(re.search(r"\d", normalized))
    has_variant = bool(
        re.search(
            r"\b(pro|max|plus|mini|ultra|air|steam|dry|press|automatic|semi|500mg|650mg|128gb|256gb|512gb|1tb)\b",
            normalized,
        )
    )
    has_brand = bool(
        re.search(
            r"\b(apple|iphone|samsung|oneplus|redmi|xiaomi|vivo|oppo|realme|boat|jbl|sony|philips|bajaj|havells|usha|dolo|crocin|calpol)\b",
            normalized,
        )
    )

    precise_enough = True
    missing_attributes: list[str] = []

    if not normalized or normalized in VAGUE_PRODUCT_TERMS or len(tokens) <= 1:
        precise_enough = False

    if category == "electronics":
        if "iron" in normalized and not any(term in normalized for term in ("steam", "dry", "press", "steamer")):
            precise_enough = False
            missing_attributes.append("product type")
        if not (has_brand or has_numbers or has_variant) and len(tokens) <= 2:
            precise_enough = False
        if not has_brand:
            missing_attributes.append("brand")
        if not (has_numbers or has_variant):
            missing_attributes.append("specification or variant")
    elif category == "medicine":
        if not has_numbers:
            precise_enough = False
            missing_attributes.append("strength")
        if len(tokens) <= 2:
            precise_enough = False
        missing_attributes.append("quantity")
    else:
        if len(tokens) <= 1:
            precise_enough = False
            missing_attributes.append("exact product name")

    missing_attributes = list(dict.fromkeys(attr for attr in missing_attributes if attr))
    follow_up_questions = [] if precise_enough else _fallback_follow_up_questions(product or raw_query, category)

    return ProductPrecisionAssessment(
        refined_product=product or raw_query.strip(),
        precise_enough=precise_enough,
        missing_attributes=missing_attributes,
        follow_up_questions=follow_up_questions,
    )


async def analyze_product_precision(
    raw_query: str,
    category: str | None = None,
    current_product: str | None = None,
) -> ProductPrecisionAssessment:
    if not settings.openai_api_key:
        return _fallback_precision_assessment(raw_query, category, current_product)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    context = (
        f"Raw user context: {raw_query}\n"
        f"Current category: {category or 'unknown'}\n"
        f"Current product candidate: {current_product or 'unknown'}"
    )

    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": PRECISION_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            text_format=ProductPrecisionAssessment,
            temperature=0,
        )
        assessment = response.output_parsed
        if assessment is None:
            raise ValueError("OpenAI returned no parsed ProductPrecisionAssessment.")
        assessment.refined_product = _normalize_product_text(assessment.refined_product or current_product or "")
        if not assessment.refined_product:
            assessment.refined_product = _normalize_product_text(current_product or infer_product(raw_query))
        return assessment
    except Exception as exc:  # pragma: no cover - external API
        logger.warning("Product precision analysis failed, using fallback: %s", exc)
        return _fallback_precision_assessment(raw_query, category, current_product)


def _best_effort_structure(raw_query: str) -> StructuredQuery:
    return StructuredQuery(
        product=infer_product(raw_query),
        category=infer_category(raw_query),
        location=infer_location(raw_query),
        intent=infer_intent(raw_query),
        urgency=infer_urgency(raw_query),
        raw_query=raw_query,
    )


async def structure_query(raw_query: str) -> StructuredQuery:
    logger.info("Structuring query: %s", raw_query)
    if not settings.openai_api_key:
        logger.info("OpenAI API key missing; using heuristic query structurer.")
        return _best_effort_structure(raw_query)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            response = await client.responses.parse(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_query},
                ],
                text_format=StructuredQuery,
                temperature=0,
            )
            structured = response.output_parsed
            if structured is None:
                raise ValueError("OpenAI returned no parsed StructuredQuery.")
            structured.raw_query = raw_query
            logger.info("Structured query generated successfully on attempt %s", attempt + 1)
            return structured
        except Exception as exc:  # pragma: no cover - depends on external API
            last_error = exc
            logger.warning("Query structurer failed on attempt %s: %s", attempt + 1, exc)

    logger.warning("Falling back to heuristic query structurer after error: %s", last_error)
    return _best_effort_structure(raw_query)
