from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

from psycopg2.extras import Json

from scripts.db import fetch_order_by_id, get_leader_connection, now_utc, row_to_dict
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


def soft_delete_order(
    order_id: str,
    timeout_seconds: float = 60,
    interval_seconds: float = 0.5,
) -> dict[str, Any]:
    operation_id = uuid.uuid4()
    log_id = uuid.uuid4()

    conn = get_leader_connection()
    try:
        with conn:
            current = fetch_order_by_id(conn, order_id)
            if current is None:
                raise ValueError(f"Order does not exist on leader: {order_id}")

            expected_version = int(current["version"]) + 1
            leader_write_time = now_utc()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE orders
                    SET
                        deleted = TRUE,
                        status = 'cancelled',
                        version = %s,
                        operation_id = %s,
                        last_updated = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (expected_version, str(operation_id), order_id),
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
                    VALUES (%s, %s, 'DELETE', %s, %s, %s, %s)
                    """,
                    (
                        str(log_id),
                        order_id,
                        expected_version,
                        leader_write_time,
                        Json(leader_snapshot),
                        "Order soft-deleted on leader.",
                    ),
                )
    finally:
        conn.close()

    follower_snapshot, follower_visible_time = wait_for_follower_order(
        order_id,
        expected_version=expected_version,
        expected_operation_id=str(operation_id),
        expected_deleted=True,
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
        "operation_type": "DELETE",
        "order_id": order_id,
        "version": expected_version,
        "leader_write_time": leader_write_time,
        "follower_visible_time": follower_visible_time,
        "replication_delay_ms": replication_delay_ms,
        "leader_snapshot": leader_snapshot,
        "follower_snapshot": follower_snapshot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Soft-delete an order on the leader.")
    parser.add_argument("--order-id", required=True)
    args = parser.parse_args()

    try:
        result = soft_delete_order(args.order_id)
        print("\nDELETE completed and replicated to follower.")
        _print_json("Leader snapshot:", result["leader_snapshot"])
        _print_json("Follower snapshot:", result["follower_snapshot"])
        print(f"\nReplication delay: {result['replication_delay_ms']} ms")
    except Exception as exc:
        print("Soft-delete order failed.")
        print(f"Error: {exc}")
        raise


if __name__ == "__main__":
    main()
