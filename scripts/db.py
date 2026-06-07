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
REQUIRED_DB_FIELDS = ("HOST", "PORT", "NAME", "USER")

register_uuid()


def load_env() -> None:
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
        raise RuntimeError(
            f"Missing env var(s): {', '.join(missing)}. Check .env file."
        )
    config: dict[str, Any] = {
        "host": os.environ[f"{prefix}_DB_HOST"],
        "port": int(os.environ[f"{prefix}_DB_PORT"]),
        "dbname": os.environ[f"{prefix}_DB_NAME"],
        "user": os.environ[f"{prefix}_DB_USER"],
        "cursor_factory": RealDictCursor,
    }
    password = os.getenv(f"{prefix}_DB_PASSWORD")
    if password:
        config["password"] = password
    return config


def get_leader_connection():
    return psycopg2.connect(**_db_config("LEADER"))


def get_follower_connection():
    return psycopg2.connect(**_db_config("FOLLOWER"))


# ── Generic helpers ────────────────────────────────────────────────────────────

def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
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


def rows_to_list(rows: Any) -> list[dict[str, Any]]:
    return [_json_safe(dict(r)) for r in rows]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Table fetches (leader or follower conn) ────────────────────────────────────

def fetch_customer_by_id(conn, customer_id: str | uuid.UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM customers WHERE id = %s",
            (str(customer_id),),
        )
        return cur.fetchone()


def fetch_customer_by_email(conn, email: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM customers WHERE email = %s AND deleted = FALSE",
            (email,),
        )
        return cur.fetchone()


def fetch_category_by_name(conn, name: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM categories WHERE name = %s AND deleted = FALSE",
            (name,),
        )
        return cur.fetchone()


def fetch_product_by_id(conn, product_id: str | uuid.UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM products WHERE id = %s",
            (str(product_id),),
        )
        return cur.fetchone()


def fetch_order_by_id(conn, order_id: str | uuid.UUID) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM orders WHERE id = %s",
            (str(order_id),),
        )
        return cur.fetchone()


def fetch_order_items_by_order_id(conn, order_id: str | uuid.UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT oi.*, p.name AS product_name
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = %s AND oi.deleted = FALSE
            ORDER BY oi.last_updated
            """,
            (str(order_id),),
        )
        return cur.fetchall()


def fetch_order_full(conn, order_id: str | uuid.UUID) -> dict[str, Any] | None:
    """Order with customer info and items list."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                o.*,
                c.name  AS customer_name,
                c.email AS customer_email
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.id = %s
            """,
            (str(order_id),),
        )
        order = cur.fetchone()
    if order is None:
        return None
    result = row_to_dict(order)
    result["items"] = rows_to_list(fetch_order_items_by_order_id(conn, order_id))
    return result


# ── Write helpers (leader conn) ────────────────────────────────────────────────

def get_or_create_category(conn, name: str, description: str = "") -> dict[str, Any]:
    row = fetch_category_by_name(conn, name)
    if row:
        return row_to_dict(row)
    op_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO categories (name, description, operation_id)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (name, description, op_id),
        )
        return row_to_dict(cur.fetchone())


def get_or_create_customer(
    conn, name: str, email: str, phone: str = "", address: str = ""
) -> dict[str, Any]:
    row = fetch_customer_by_email(conn, email)
    if row:
        return row_to_dict(row)
    op_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO customers (name, email, phone, address, operation_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (name, email, phone or None, address or None, op_id),
        )
        return row_to_dict(cur.fetchone())


def get_or_create_product(
    conn,
    name: str,
    category_id: str,
    price: float,
    description: str = "",
    stock: int = 100,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM products WHERE name = %s AND deleted = FALSE LIMIT 1",
            (name,),
        )
        row = cur.fetchone()
    if row:
        return row_to_dict(row)
    op_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO products (category_id, name, description, price, stock, operation_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (category_id, name, description or None, price, stock, op_id),
        )
        return row_to_dict(cur.fetchone())
