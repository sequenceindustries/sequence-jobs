"""Provider-independent AI layer.

* `AIProvider` is the only thing a vendor integration has to implement.
* `AIGateway` is the only way application code calls AI. It enforces: credentials present, a
  non-zero configured budget, input/output token caps, usage logging, structured-output validation.
* There is NO fallback that fabricates output. When AI is unavailable the gateway raises
  `AIUnavailable` and callers degrade to non-AI behaviour (keyword search keeps working).
* Only the task-relevant text is ever passed in; callers must not include unnecessary personal data.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..db import connect

TASKS = (
    "cv_extraction", "job_extraction", "classification", "summarisation", "embedding",
    "job_matching", "cv_improvement", "cover_letter", "interview_prep", "career_chat",
    "search_filters",
)


class AIUnavailable(Exception):
    """AI cannot be used right now (no provider, no key, no budget, provider error)."""


class AIOutputInvalid(Exception):
    """Model returned something that failed structured validation. Never auto-repaired by guessing."""


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class AIProvider(ABC):
    name = "abstract"
    # USD per 1M tokens: (input, output). Set by the concrete provider from its published pricing.
    price_per_mtok: Optional[tuple[float, float]] = None

    @abstractmethod
    def complete(self, system: str, user: str, max_output_tokens: int, json_mode: bool = True) -> Completion: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(f"{self.name} does not support embeddings")


class NullProvider(AIProvider):
    """Used when no provider is configured. Always unavailable; never invents output."""
    name = "none"

    def complete(self, system, user, max_output_tokens, json_mode=True):
        raise AIUnavailable("No AI provider configured")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)        # coarse; real providers return exact counts


def estimate_cost(provider: AIProvider, in_tok: Optional[int], out_tok: Optional[int]) -> Optional[float]:
    if provider.price_per_mtok is None or in_tok is None or out_tok is None:
        return None                      # unknown price => unknown cost, not a made-up number
    pin, pout = provider.price_per_mtok
    return round((in_tok * pin + out_tok * pout) / 1_000_000, 6)


class AIGateway:
    def __init__(self, db_url: str, provider: Optional[AIProvider], daily_budget_usd: float,
                 max_input_tokens: int = 6000, max_output_tokens: int = 1500):
        self.db_url = db_url
        self.provider = provider or NullProvider()
        self.daily_budget_usd = daily_budget_usd
        self.max_in = max_input_tokens
        self.max_out = max_output_tokens

    def _log(self, task, status, started, comp=None, error=None, cost=None):
        with connect(self.db_url) as conn:
            conn.execute(
                "INSERT INTO ai_usage_log (task, provider, model, status, input_tokens, output_tokens, "
                "latency_ms, est_cost_usd, error) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (task, self.provider.name, comp.model if comp else None, status,
                 comp.input_tokens if comp else None, comp.output_tokens if comp else None,
                 int((time.monotonic() - started) * 1000), cost, (error or "")[:500] or None),
            )
            conn.commit()

    def spent_today_usd(self) -> float:
        with connect(self.db_url) as conn:
            row = conn.execute(
                "SELECT coalesce(sum(est_cost_usd),0) AS s FROM ai_usage_log "
                "WHERE at >= date_trunc('day', now()) AND status = 'ok'").fetchone()
        return float(row["s"])

    def run_json(self, task: str, system: str, user: str, required_keys: tuple[str, ...]) -> dict:
        if task not in TASKS:
            raise ValueError(f"unknown AI task {task}")
        t0 = time.monotonic()
        if isinstance(self.provider, NullProvider):
            self._log(task, "unavailable", t0, error="no provider")
            raise AIUnavailable("AI is not configured")
        if self.daily_budget_usd <= 0 or self.spent_today_usd() >= self.daily_budget_usd:
            self._log(task, "blocked_budget", t0)
            raise AIUnavailable("AI daily budget is zero or exhausted")
        if estimate_tokens(system + user) > self.max_in:
            self._log(task, "blocked_budget", t0, error="input over token cap")
            raise AIUnavailable("Input exceeds the configured token cap")
        try:
            comp = self.provider.complete(system, user, self.max_out, json_mode=True)
        except Exception as e:
            self._log(task, "error", t0, error=str(e))
            raise AIUnavailable(f"provider error: {e}") from e
        cost = estimate_cost(self.provider, comp.input_tokens, comp.output_tokens)
        try:
            data = json.loads(comp.text)
            if not isinstance(data, dict) or any(k not in data for k in required_keys):
                raise ValueError("missing required keys")
        except Exception as e:
            self._log(task, "error", t0, comp, error=f"invalid output: {e}", cost=cost)
            raise AIOutputInvalid(str(e)) from e
        self._log(task, "ok", t0, comp, cost=cost)
        return data
