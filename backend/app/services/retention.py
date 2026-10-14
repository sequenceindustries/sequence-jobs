"""Data retention: uploaded-CV text expires; read notifications and stale rate-limit rows are cleaned."""
from ..db import connect


def purge_expired(db_url: str) -> dict:
    with connect(db_url) as conn:
        cvs = conn.execute("DELETE FROM cvs WHERE expires_at < now()").rowcount
        notes = conn.execute("DELETE FROM notifications WHERE read_at IS NOT NULL AND read_at < now() - interval '90 days'").rowcount
        rl = conn.execute("DELETE FROM rate_limits WHERE window_start < now() - interval '1 day'").rowcount
        conn.commit()
    return {"cvs_deleted": cvs, "notifications_deleted": notes, "rate_limit_rows_deleted": rl}
