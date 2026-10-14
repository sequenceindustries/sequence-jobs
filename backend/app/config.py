"""Environment-based configuration. No secrets are hard-coded; nothing external is assumed to exist."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    ENV = os.environ.get("APP_ENV", "development")          # development | test | production
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres@/sequence_jobs?host=/tmp&port=5433"
    )
    USER_AGENT = os.environ.get(
        "CRAWLER_USER_AGENT", "SequenceJobsBot/0.1 (+contact: set CRAWLER_CONTACT)"
    )
    HTTP_TIMEOUT_SECS = _int("HTTP_TIMEOUT_SECS", 20)
    HTTP_MAX_RETRIES = _int("HTTP_MAX_RETRIES", 3)
    MAX_CONCURRENT_SOURCES = _int("MAX_CONCURRENT_SOURCES", 3)

    # --- AI (provider-independent; disabled until credentials AND a budget are configured)
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "none")      # none | <future providers>
    AI_API_KEY = os.environ.get("AI_API_KEY")                # never logged
    AI_DAILY_BUDGET_USD = float(os.environ.get("AI_DAILY_BUDGET_USD", "0"))  # 0 = no paid calls allowed
    AI_MAX_INPUT_TOKENS = _int("AI_MAX_INPUT_TOKENS", 6000)
    AI_MAX_OUTPUT_TOKENS = _int("AI_MAX_OUTPUT_TOKENS", 1500)

    @classmethod
    def is_production(cls) -> bool:
        return cls.ENV == "production"
