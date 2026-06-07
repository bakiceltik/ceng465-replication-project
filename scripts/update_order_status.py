from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

from psycopg2.extras import Json

from scripts.db import (
    fetch_order_by_id,
    get_leader_connection,
    now_utc,
    row_to_dict,
)
from scripts.measure_replication import (
    calculate_replication_delay_ms,
    wait_for_follower_order,
)

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled"}


def update_order_status(
    order_id: str,
    status: str,
    timeout_seconds: float = 60,
    interval_seconds: float = 0.5,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed: {', '.join(sorted(VALID_STATUSES))}"
        )

    operation_id = str(uuid.uuid4())
    log_id = str(uuid.uuid4())

    conn = get_leader_connection()
    try:
        with conn:
            current = fetch_order_by_id(conn, order_id)
            if current is None:
                raise ValueError(f"Order not found on leader: {order_id}")

            new_version = int(current["version"]) + 1
            write_time = now_utc()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE orders
                    SET status       = %s,
                        version      = %s,
                        operation_id = %s,
                        last_updated = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (status, new_version, operation_id, order_id),
                )
                leader_snapshot = row_to_dict(cur.fetchone())

                cur.execute(
                    """
                    INSERT INTO operation_log
                        (id, table_name, record_id, operation_type, version,
                         leader_write_time, leader_snapshot, notes)
                    VALUES (%s, 'orders', %s, 'UPDATE', %s, %s, %s, %s)
                    """,
                    (
                        log_id, order_id, new_version, write_time,
                        Json(leader_snapshot),
                        f"Order status updated to '{status}'.",
                    ),
                )
    finally:
        conn.close()

    follower_snapshot, follower_visible_time = wait_for_follower_order(
        order_id,
        expected_version=new_version,
        expected_operation_id=operation_id,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    delay_ms = calculate_replication_delay_ms(write_time, follower_visible_time)

    conn2 = get_leader_connection()
    try:
        with conn2:
            with conn2.cursor() as cur:
                cur.execute(
                    """
                    UPDATE operation_log
                    SET follower_visible_time = %s,
                        replication_delay_ms  = %s,
                        follower_snapshot     = %s
                    WHERE id = %s
                    """,
                    (follower_visible_time, delay_ms, Json(follower_snapshot), log_id),
                )
    finally:
        conn2.close()

    return {
        "operation_log_id": log_id,
        "operation_type": "UPDATE",
        "order_id": order_id,
        "version": new_version,
        "status": status,
        "leader_write_time": write_time,
        "follower_visible_time": follower_visible_time,
        "replication_delay_ms": delay_ms,
        "leader_snapshot": leader_snapshot,
        "follower_snapshot": follower_snapshot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Update order status on the leader.")
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    args = parser.parse_args()

    result = update_order_status(args.order_id, args.status)
    print(f"\nUPDATE completed. version={result['version']} delay={result['replication_delay_ms']} ms")
    print("\nLeader snapshot:")
    print(json.dumps(result["leader_snapshot"], indent=2))


if __name__ == "__main__":
    main()
