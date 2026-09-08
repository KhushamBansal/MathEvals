"""Thin OpenAI chat wrapper. temperature is hard-forced to 0.

Every call is recorded (full messages + response + usage) onto whatever
`recorder` list is passed in, so the sample log captures every LLM exchange.
"""
from __future__ import annotations

import os
import time

from openai import OpenAI

_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set (source ./.env)")
        _CLIENT = OpenAI(api_key=key)
    return _CLIENT


class Chat:
    """One configured model, callable by name, temperature 0."""

    def __init__(self, model: str, max_tokens: int = 1536):
        self.model = model
        self.max_tokens = max_tokens

    def __call__(self, messages, *, stop=None, tag: str = "", recorder=None,
                 max_tokens=None) -> str:
        mt = max_tokens or self.max_tokens
        last_err = None
        for attempt in range(6):
            try:
                t0 = time.time()
                resp = _client().chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    max_tokens=mt,
                    stop=stop,
                )
                text = resp.choices[0].message.content or ""
                if recorder is not None:
                    recorder.append({
                        "tag": tag,
                        "model": self.model,
                        "messages": messages,
                        "stop": stop,
                        "response": text,
                        "finish_reason": resp.choices[0].finish_reason,
                        "usage": resp.usage.model_dump() if resp.usage else None,
                        "seconds": round(time.time() - t0, 3),
                    })
                return text
            except Exception as e:  # noqa: BLE001 - narrow retry on transient API errors
                last_err = e
                name = type(e).__name__
                if name in ("RateLimitError", "APIConnectionError", "APITimeoutError",
                            "InternalServerError", "APIError"):
                    time.sleep(min(2 ** attempt, 30))
                    continue
                raise
        raise RuntimeError(f"LLM call failed after retries: {last_err}")
