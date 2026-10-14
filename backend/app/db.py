"""Thin psycopg3 helpers and a forward-only SQL migration runner."""
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row)


@contextmanager
def transaction(url: str):
    conn = connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(url: str) -> list[str]:
    """Apply any unapplied *.sql files in order. Returns the versions applied."""
    applied: list[str] = []
    with connect(url) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in done:
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
            applied.append(path.stem)
        conn.commit()
    return applied


def reset_schema(url: str) -> None:
    """TEST/DEV ONLY: drop everything in the public schema."""
    with connect(url) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
