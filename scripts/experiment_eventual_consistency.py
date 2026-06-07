"""
Experiment 1: Eventual Consistency
--------------------------------------
Write one order to the leader. Poll the follower every POLL_INTERVAL seconds
for POLL_DURATION seconds. Record when the follower converges to the same state.

Expected result: follower eventually shows the same data as the leader, but may lag.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime

from psycopg2.extras import Json

from scripts.db import (
    fetch_order_by_id,
    get_follower_connection,
    get_leader_connection,
    get_or_create_category,
    get_or_create_customer,
    get_or_create_product,
    now_utc,
    row_to_dict,
)

POLL_INTERVAL = 2.0   # seconds between follower reads
POLL_DURATION = 60.0  # total observation window in seconds


def _setup_fixtures() -> tuple[str, str]:
    """Returns (customer_id, product_id), creating them if needed."""
    conn = get_leader_connection()
    try:
        with conn:
            cat = get_or_create_category(conn, "Electronics", "Electronic products")
            cust = get_or_create_customer(
                conn, "Eve Experiment", "eve@experiment.com"
            )
            prod = get_or_create_product(
                conn, "Test Widget", cat["id"], 9.99
            )
            return cust["id"], prod["id"]
    finally:
        conn.close()


def _write_order(customer_id: str, product_id: str) -> tuple[str, str, datetime]:
    """Insert one order on the leader. Returns (order_id, operation_id, write_time)."""
    order_id = str(uuid.uuid4())
    op_id = str(uuid.uuid4())

    conn = get_leader_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                write_time = now_utc()
                cur.execute(
                    """
                    INSERT INTO orders
                        (id, customer_id, status, total_amount, version, operation_id)
                    VALUES (%s, %s, 'pending', 9.99, 1, %s)
                    """,
                    (order_id, customer_id, op_id),
                )
                cur.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price, operation_id)
                    VALUES (%s, %s, 1, 9.99, %s)
                    """,
                    (order_id, product_id, str(uuid.uuid4())),
                )
                cur.execute(
                    """
                    INSERT INTO operation_log
                        (id, table_name, record_id, operation_type, version,
                         leader_write_time, leader_snapshot, notes)
                    VALUES (%s, 'orders', %s, 'INSERT', 1, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), order_id, write_time,
                        Json({"order_id": order_id, "version": 1}),
                        "Experiment 1: eventual consistency write.",
                    ),
                )
    finally:
        conn.close()
    return order_id, op_id, write_time


def run() -> None:
    print("=" * 70)
    print("EXPERIMENT 1 — Eventual Consistency")
    print("=" * 70)

    customer_id, product_id = _setup_fixtures()
    order_id, op_id, write_time = _write_order(customer_id, product_id)

    print(f"[LEADER  WRITE] time={write_time.isoformat(timespec='milliseconds')}")
    print(f"[LEADER  WRITE] order_id={order_id}")
    print(f"\nPolling follower every {POLL_INTERVAL}s for {POLL_DURATION}s ...\n")

    deadline = time.monotonic() + POLL_DURATION
    poll_count = 0
    convergence_time: datetime | None = None

    conn = get_follower_connection()
    conn.autocommit = True
    try:
        while time.monotonic() <= deadline:
            poll_count += 1
            poll_time = now_utc()
            elapsed = (poll_time - write_time).total_seconds()
            row = fetch_order_by_id(conn, order_id)

            if row and str(row["operation_id"]) == op_id:
                snapshot = row_to_dict(row)
                delay_ms = int(elapsed * 1000)
                if convergence_time is None:
                    convergence_time = poll_time
                    print(
                        f"  poll {poll_count:02d} | t+{elapsed:5.1f}s | "
                        f"CONVERGED version={snapshot['version']} delay={delay_ms} ms  <--"
                    )
                else:
                    print(
                        f"  poll {poll_count:02d} | t+{elapsed:5.1f}s | "
                        f"stable   version={snapshot['version']}"
                    )
            else:
                print(
                    f"  poll {poll_count:02d} | t+{elapsed:5.1f}s | "
                    "not yet visible on follower"
                )

            time.sleep(POLL_INTERVAL)
    finally:
        conn.close()

    print()
    print("=" * 70)
    if convergence_time:
        total_ms = int((convergence_time - write_time).total_seconds() * 1000)
        print(f"RESULT: Follower converged after {total_ms} ms ({poll_count} polls total).")
    else:
        print(f"RESULT: Follower did NOT converge within {POLL_DURATION}s.")
    print("=" * 70)


if __name__ == "__main__":
    run()
