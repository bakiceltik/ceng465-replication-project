from __future__ import annotations

import argparse
import json
import uuid
from decimal import Decimal
from typing import Any

from psycopg2.extras import Json

from scripts.db import (
    get_leader_connection,
    get_or_create_category,
    get_or_create_customer,
    get_or_create_product,
    now_utc,
    row_to_dict,
    rows_to_list,
)
from scripts.measure_replication import (
    calculate_replication_delay_ms,
    wait_for_follower_order,
)


def _log_operation(cur, table_name: str, record_id: str, op_type: str,
                   version: int, write_time, snapshot: dict) -> str:
    log_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO operation_log
            (id, table_name, record_id, operation_type, version,
             leader_write_time, leader_snapshot, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            log_id, table_name, record_id, op_type, version,
            write_time, Json(snapshot),
            f"{op_type} on {table_name} id={record_id}",
        ),
    )
    return log_id


def _update_log_follower(conn, log_id: str, visible_time, delay_ms: int,
                         follower_snapshot: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE operation_log
            SET follower_visible_time = %s,
                replication_delay_ms  = %s,
                follower_snapshot     = %s
            WHERE id = %s
            """,
            (visible_time, delay_ms, Json(follower_snapshot), log_id),
        )


def create_order(
    customer_name: str,
    customer_email: str,
    items: list[tuple[str, int, float]],   # (product_name, qty, unit_price)
    category_name: str = "General",
    timeout_seconds: float = 60,
    interval_seconds: float = 0.5,
) -> dict[str, Any]:
    """
    Full order creation flow on the leader:
      1. get_or_create category
      2. get_or_create customer
      3. get_or_create products
      4. INSERT order
      5. INSERT order_items
      6. Poll follower for replication
      7. Return full result with delay

    items: list of (product_name, quantity, unit_price)
    """
    if not items:
        raise ValueError("At least one item required.")

    order_id = str(uuid.uuid4())
    order_op_id = str(uuid.uuid4())
    total_amount = sum(Decimal(str(p)) * q for _, q, p in items)

    conn = get_leader_connection()
    log_id: str = ""
    try:
        with conn:
            with conn.cursor() as cur:
                # ── category ──────────────────────────────────────────────────
                category = get_or_create_category(conn, category_name)

                # ── customer ──────────────────────────────────────────────────
                customer = get_or_create_customer(conn, customer_name, customer_email)

                # ── products ──────────────────────────────────────────────────
                product_rows: list[dict] = []
                for p_name, _, p_price in items:
                    p = get_or_create_product(
                        conn, p_name, category["id"], p_price
                    )
                    product_rows.append(p)

                # ── order ─────────────────────────────────────────────────────
                write_time = now_utc()
                cur.execute(
                    """
                    INSERT INTO orders
                        (id, customer_id, status, total_amount, version, operation_id)
                    VALUES (%s, %s, 'pending', %s, 1, %s)
                    RETURNING *
                    """,
                    (order_id, customer["id"], str(total_amount), order_op_id),
                )
                order_snapshot = row_to_dict(cur.fetchone())

                # ── order_items ───────────────────────────────────────────────
                item_snapshots: list[dict] = []
                for (p_name, qty, unit_price), product in zip(items, product_rows):
                    item_op_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO order_items
                            (order_id, product_id, quantity, unit_price, operation_id)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (order_id, product["id"], qty, str(unit_price), item_op_id),
                    )
                    item_snapshots.append(row_to_dict(cur.fetchone()))

                # ── operation_log ─────────────────────────────────────────────
                log_id = _log_operation(
                    cur, "orders", order_id, "INSERT", 1,
                    write_time,
                    {
                        "order": order_snapshot,
                        "customer": customer,
                        "items": item_snapshots,
                    },
                )
    finally:
        conn.close()

    # ── Poll follower ──────────────────────────────────────────────────────────
    follower_snapshot, follower_visible_time = wait_for_follower_order(
        order_id,
        expected_version=1,
        expected_operation_id=order_op_id,
        expected_deleted=False,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    delay_ms = calculate_replication_delay_ms(write_time, follower_visible_time)

    # ── Update log with follower info ──────────────────────────────────────────
    conn2 = get_leader_connection()
    try:
        with conn2:
            _update_log_follower(conn2, log_id, follower_visible_time, delay_ms,
                                 follower_snapshot)
    finally:
        conn2.close()

    return {
        "operation_log_id": log_id,
        "operation_type": "INSERT",
        "order_id": order_id,
        "customer": customer,
        "version": 1,
        "total_amount": float(total_amount),
        "items": item_snapshots,
        "leader_write_time": write_time,
        "follower_visible_time": follower_visible_time,
        "replication_delay_ms": delay_ms,
        "leader_snapshot": order_snapshot,
        "follower_snapshot": follower_snapshot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an order on the leader.")
    parser.add_argument("--customer-name", required=True)
    parser.add_argument("--customer-email", required=True)
    parser.add_argument(
        "--item", dest="items", action="append", required=True,
        metavar="NAME:QTY:PRICE",
        help="e.g. --item 'Keyboard:2:49.99'  (repeatable)",
    )
    parser.add_argument("--category", default="General")
    args = parser.parse_args()

    parsed_items: list[tuple[str, int, float]] = []
    for raw in args.items:
        parts = raw.split(":")
        if len(parts) != 3:
            parser.error(f"Bad --item format '{raw}'. Expected NAME:QTY:PRICE")
        name, qty, price = parts
        parsed_items.append((name.strip(), int(qty), float(price)))

    result = create_order(
        customer_name=args.customer_name,
        customer_email=args.customer_email,
        items=parsed_items,
        category_name=args.category,
    )

    print("\nINSERT completed and replicated.")
    print(f"  Order ID     : {result['order_id']}")
    print(f"  Customer     : {result['customer']['name']} <{result['customer']['email']}>")
    print(f"  Total        : {result['total_amount']:.2f}")
    print(f"  Items        : {len(result['items'])}")
    print(f"  Delay        : {result['replication_delay_ms']} ms")
    print("\nLeader snapshot:")
    print(json.dumps(result["leader_snapshot"], indent=2))
    print("\nFollower snapshot:")
    print(json.dumps(result["follower_snapshot"], indent=2))


if __name__ == "__main__":
    main()
