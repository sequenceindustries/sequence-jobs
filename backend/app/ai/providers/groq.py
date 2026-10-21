"""Groq LLM provider integration.

Supports Mixtral and Llama models via Groq's fast inference API.
Requires GROQ_API_KEY env var.
"""
import os
from typing import Optional

import requests

from ..provider import AIProvider, AIUnavailable, Completion


class GroqProvider(AIProvider):
    name = "groq"
    # Groq pricing (USD per 1M tokens, input/output): Mixtral 8x7B
    # https://console.groq.com/docs/pricing
    price_per_mtok = (0.27 / 1000, 0.27 / 1000)  # $0.27 per 1M for both input and output

    def __init__(self, api_key: Optional[str] = None, model: str = "mixtral-8x7b-32768"):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"

        if not self.api_key:
            raise AIUnavailable("GROQ_API_KEY not set")

    def complete(self, system: str, user: str, max_output_tokens: int, json_mode: bool = True) -> Completion:
        """Send a request to Groq API and return the completion."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0.7,
        }

        # JSON mode: request structured output (Groq supports JSON schema)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise AIUnavailable(f"Groq API error: {e}") from e

        data = resp.json()

        # Extract token counts and completion text
        input_tokens = data.get("usage", {}).get("prompt_tokens")
        output_tokens = data.get("usage", {}).get("completion_tokens")
        text = data["choices"][0]["message"]["content"]

        return Completion(
            text=text,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
