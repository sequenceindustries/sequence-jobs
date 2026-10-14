"""User accounts, rate limiting and audit logging. No secrets are ever logged."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg.types.json import Jsonb
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import connect

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")
MIN_PASSWORD_LEN = 10
# A fixed hash so login takes similar time whether or not the email exists.
_DUMMY_HASH = generate_password_hash("not-a-real-password-for-timing")


class AccountError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def validate_credentials(email: str, password: str) -> str:
    email = (email or "").strip()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AccountError("invalid_email", "Enter a valid email address.")
    if len(password or "") < MIN_PASSWORD_LEN or len(password) > 200:
        raise AccountError("weak_password", f"Password must be {MIN_PASSWORD_LEN}-200 characters.")
    if password.lower() in {"password123", "1234567890", "qwertyuiop", "password1234"} or \
            password.lower().startswith(email.split("@")[0].lower()) and len(email.split("@")[0]) >= 4:
        raise AccountError("weak_password", "Choose a password that is harder to guess.")
    return email


def create_user(db_url: str, email: str, password: str, role: str = "user") -> int:
    email = validate_credentials(email, password)
    with connect(db_url) as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,)).fetchone():
            raise AccountError("email_taken", "That email is already registered.")
        row = conn.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (%s,%s,%s) RETURNING id",
            (email, generate_password_hash(password), role)).fetchone()
        conn.commit()
        return row["id"]


def authenticate(db_url: str, email: str, password: str) -> Optional[dict]:
    with connect(db_url) as conn:
        row = conn.execute("SELECT id, email, role, password_hash FROM users WHERE lower(email) = lower(%s)",
                           ((email or "").strip(),)).fetchone()
        ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password or "")
        if not row or not ok:
            return None
        conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row["id"],))
        conn.commit()
        return {"id": row["id"], "email": row["email"], "role": row["role"]}


def get_user(db_url: str, user_id: int) -> Optional[dict]:
    with connect(db_url) as conn:
        return conn.execute("SELECT id, email, role, created_at FROM users WHERE id = %s", (user_id,)).fetchone()


def delete_user(db_url: str, user_id: int) -> None:
    """Deletes the account and (by FK cascade) profile, CVs, tracker, alerts, notifications, outbox."""
    with connect(db_url) as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


# ---- rate limiting (fixed window, stored in Postgres so it works across processes) -----------------------------------
def rate_limit_hit(db_url: str, key: str, limit: int, window_secs: int) -> bool:
    """Record a hit. Returns True if the caller is within the limit, False if it should be blocked."""
    now = datetime.now(timezone.utc)
    start = int(now.timestamp()) // window_secs * window_secs      # stable integer-epoch window
    window = datetime.fromtimestamp(start, tz=timezone.utc)
    with connect(db_url) as conn:
        row = conn.execute(
            "INSERT INTO rate_limits (key, window_start, hits) VALUES (%s,%s,1) "
            "ON CONFLICT (key, window_start) DO UPDATE SET hits = rate_limits.hits + 1 RETURNING hits",
            (key, window)).fetchone()
        conn.execute("DELETE FROM rate_limits WHERE window_start < %s", (now - timedelta(days=1),))
        conn.commit()
        return row["hits"] <= limit


def audit(db_url: str, actor_id: Optional[int], action: str, target: Optional[str] = None,
          detail: Optional[dict] = None) -> None:
    safe = {k: v for k, v in (detail or {}).items() if k not in ("password", "token", "secret", "api_key")}
    with connect(db_url) as conn:
        conn.execute("INSERT INTO audit_log (actor_id, action, target, detail) VALUES (%s,%s,%s,%s)",
                     (actor_id, action, target, Jsonb(safe)))
        conn.commit()
