from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor, register_uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DB_FIELDS = ("HOST", "PORT", "NAME", "USER", "PASSWORD")

register_uuid()


def load_env() -> None:
    """Load .env from the project directory if it exists."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _db_config(prefix: str) -> dict[str, Any]:
    load_env()
    missing = [
        f"{prefix}_DB_{field}"
        for field in REQUIRED_DB_FIELDS
        if not os.getenv(f"{prefix}_DB_{field}")
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing database environment variable(s): {joined}. "
            "Copy .env.example to .env and fill in the two Mac database settings."
        )

    return {
        "host": os.environ[f"{prefix}_DB_HOST"],
        "port": int(os.environ[f"{prefix}_DB_PORT"]),
        "dbname": os.environ[f"{prefix}_DB_NAME"],
        "user": os.environ[f"{prefix}_DB_USER"],
        "password": os.environ[f"{prefix}_DB_PASSWORD"],
        "cursor_factory": RealDictCursor,
    }


def get_leader_connection():
    """Return a PostgreSQL connection for writes to the leader/primary."""
    return psycopg2.connect(**_db_config("LEADER"))


def get_follower_connection():
    """Return a PostgreSQL connection for read checks on the follower/standby."""
    return psycopg2.connect(**_db_config("FOLLOWER"))


def fetch_order_by_id(conn, order_id: str | uuid.UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                customer_name,
                product_name,
                quantity,
                status,
                version,
                operation_id,
                last_updated,
                deleted
            FROM orders
            WHERE id = %s
            """,
            (str(order_id),),
        )
        return cur.fetchone()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return _json_safe(dict(row))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
