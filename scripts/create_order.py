from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

from psycopg2.extras import Json

from scripts.db import get_leader_connection, now_utc, row_to_dict
from scripts.measure_replication import (
    calculate_replication_delay_ms,
    wait_for_follower_order,
)


def _print_json(title: str, snapshot: dict[str, Any]) -> None:
    print(f"\n{title}")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


def _update_operation_log(
    log_id: uuid.UUID,
    follower_visible_time,
    replication_delay_ms: int,
    follower_snapshot: dict[str, Any],
) -> None:
    conn = get_leader_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operation_log
                    SET
                        follower_visible_time = %s,
                        replication_delay_ms = %s,
                        follower_snapshot = %s,
                        notes = %s
                    WHERE id = %s
                    """,
                    (
                        follower_visible_time,
                        replication_delay_ms,
                        Json(follower_snapshot),
                        "Follower visibility confirmed by polling.",
                        str(log_id),
                    ),
                )
    finally:
        conn.close()


def create_order(
    customer_name: str,
    product_name: str,
    quantity: int,
    timeout_seconds: float = 60,
    interval_seconds: float = 0.5,
) -> dict[str, Any]:
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    order_id = uuid.uuid4()
    operation_id = uuid.uuid4()
    log_id = uuid.uuid4()

    conn = get_leader_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                leader_write_time = now_utc()
                cur.execute(
                    """
                    INSERT INTO orders (
                        id,
                        customer_name,
                        product_name,
                        quantity,
                        status,
                        version,
                        operation_id,
                        last_updated,
                        deleted
                    )
                    VALUES (%s, %s, %s, %s, 'pending', 1, %s, NOW(), FALSE)
                    RETURNING *
                    """,
                    (
                        str(order_id),
                        customer_name,
                        product_name,
                        quantity,
                        str(operation_id),
                    ),
                )
                leader_snapshot = row_to_dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO operation_log (
                        id,
                        order_id,
                        operation_type,
                        version,
                        leader_write_time,
                        leader_snapshot,
                        notes
                    )
                    VALUES (%s, %s, 'INSERT', 1, %s, %s, %s)
                    """,
                    (
                        str(log_id),
                        str(order_id),
                        leader_write_time,
                        Json(leader_snapshot),
                        "Order inserted on leader.",
                    ),
                )
    finally:
        conn.close()

    follower_snapshot, follower_visible_time = wait_for_follower_order(
        str(order_id),
        expected_version=1,
        expected_operation_id=str(operation_id),
        expected_deleted=False,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    replication_delay_ms = calculate_replication_delay_ms(
        leader_write_time, follower_visible_time
    )
    _update_operation_log(
        log_id, follower_visible_time, replication_delay_ms, follower_snapshot
    )

    return {
        "operation_log_id": str(log_id),
        "operation_type": "INSERT",
        "order_id": str(order_id),
        "version": 1,
        "leader_write_time": leader_write_time,
        "follower_visible_time": follower_visible_time,
        "replication_delay_ms": replication_delay_ms,
        "leader_snapshot": leader_snapshot,
        "follower_snapshot": follower_snapshot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new order on the leader.")
    parser.add_argument("--customer-name", required=True)
    parser.add_argument("--product-name", required=True)
    parser.add_argument("--quantity", required=True, type=int)
    args = parser.parse_args()

    try:
        result = create_order(args.customer_name, args.product_name, args.quantity)
        print("\nINSERT completed and replicated to follower.")
        _print_json("Leader snapshot:", result["leader_snapshot"])
        _print_json("Follower snapshot:", result["follower_snapshot"])
        print(f"\nReplication delay: {result['replication_delay_ms']} ms")
        print(f"Order ID: {result['order_id']}")
    except Exception as exc:
        print("Create order failed.")
        print(f"Error: {exc}")
        raise


if __name__ == "__main__":
    main()
