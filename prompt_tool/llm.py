from __future__ import annotations

import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError


class LLMClient:
    def __init__(self, model: str | None = None) -> None:
        load_dotenv(override=False)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("PROMPT_TOOL_MODEL", "gpt-4.1")
        self._client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY is not set")

        self.last_error = None
        delays = [1.0, 2.0, 4.0]
        for attempt, delay in enumerate([0.0] + delays, start=1):
            if delay:
                time.sleep(delay)
            try:
                response = self._client.responses.create(
                    model=self.model,
                    temperature=temperature,
                    input=[
                        {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                        {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
                    ],
                )
                return getattr(response, "output_text", "").strip()
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                if attempt == len(delays) + 1:
                    raise
                continue

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        raw = self.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
