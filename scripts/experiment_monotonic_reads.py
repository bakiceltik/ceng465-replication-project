"""
Experiment 2: Monotonic Reads
--------------------------------------
Perform 5 sequential version increments (1→5) on the leader with a short delay
between each. Then read the record from the follower 15 times sequentially.

Expected result: each follower read returns the same or a higher version —
reads must never go backward. Any violation is logged.
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

VERSION_STEPS = 5          # versions written to leader (1 → 5)
UPDATE_DELAY = 0.3         # seconds between version writes on leader
FOLLOWER_READS = 15        # total sequential reads from follower
FOLLOWER_READ_DELAY = 0.5  # seconds between follower reads


def _setup_fixtures() -> tuple[str, str]:
    conn = get_leader_connection()
    try:
        with conn:
            cat = get_or_create_category(conn, "Electronics", "Electronic products")
            cust = get_or_create_customer(conn, "Bob Monotonic", "bob@experiment.com")
            prod = get_or_create_product(conn, "Version Widget", cat["id"], 5.00)
            return cust["id"], prod["id"]
    finally:
        conn.close()


def _create_initial_order(customer_id: str, product_id: str) -> str:
    order_id = str(uuid.uuid4())
    op_id = str(uuid.uuid4())
    conn = get_leader_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders
                        (id, customer_id, status, total_amount, version, operation_id)
                    VALUES (%s, %s, 'pending', 5.00, 1, %s)
                    """,
                    (order_id, customer_id, op_id),
                )
                cur.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price, operation_id)
                    VALUES (%s, %s, 1, 5.00, %s)
                    """,
                    (order_id, product_id, str(uuid.uuid4())),
                )
                cur.execute(
                    """
                    INSERT INTO operation_log
                        (id, table_name, record_id, operation_type, version,
                         leader_write_time, notes)
                    VALUES (%s, 'orders', %s, 'INSERT', 1, %s, %s)
                    """,
                    (str(uuid.uuid4()), order_id, now_utc(),
                     "Experiment 2: initial insert."),
                )
    finally:
        conn.close()
    return order_id


def _increment_version(order_id: str, target_version: int) -> None:
    new_op_id = str(uuid.uuid4())
    conn = get_leader_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE orders
                    SET version = %s, operation_id = %s, last_updated = NOW()
                    WHERE id = %s
                    """,
                    (target_version, new_op_id, order_id),
                )
                cur.execute(
                    """
                    INSERT INTO operation_log
                        (id, table_name, record_id, operation_type, version,
                         leader_write_time, notes)
                    VALUES (%s, 'orders', %s, 'UPDATE', %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), order_id, target_version, now_utc(),
                        f"Experiment 2: version → {target_version}.",
                    ),
                )
    finally:
        conn.close()


def run() -> None:
    print("=" * 70)
    print("EXPERIMENT 2 — Monotonic Reads")
    print("=" * 70)

    customer_id, product_id = _setup_fixtures()
    order_id = _create_initial_order(customer_id, product_id)
    print(f"\norder_id = {order_id}")
    print(f"\n[LEADER] Writing versions 1 → {VERSION_STEPS} ...")
    print("  version 1 written (initial)")

    for v in range(2, VERSION_STEPS + 1):
        time.sleep(UPDATE_DELAY)
        _increment_version(order_id, v)
        print(f"  version {v} written")

    print(f"\n[FOLLOWER] Sequential reads ({FOLLOWER_READS}x, {FOLLOWER_READ_DELAY}s interval) ...\n")

    prev_version: int | None = None
    violations = 0

    conn = get_follower_connection()
    conn.autocommit = True
    try:
        for i in range(1, FOLLOWER_READS + 1):
            read_time = now_utc()
            row = fetch_order_by_id(conn, order_id)
            snapshot = row_to_dict(row) if row else None
            current_version = snapshot["version"] if snapshot else None

            flag = ""
            if current_version is None:
                flag = "  (not yet visible)"
            elif prev_version is not None and current_version < prev_version:
                violations += 1
                flag = f"  <-- MONOTONICITY VIOLATION (was {prev_version})"

            print(
                f"  read {i:02d} | {read_time.isoformat(timespec='milliseconds')} | "
                f"version={current_version}{flag}"
            )

            if current_version is not None:
                prev_version = current_version
            time.sleep(FOLLOWER_READ_DELAY)
    finally:
        conn.close()

    print()
    print("=" * 70)
    if violations == 0:
        print("RESULT: No monotonicity violations. All reads returned same or higher version.")
    else:
        print(f"RESULT: {violations} monotonicity violation(s) detected.")
    print("=" * 70)


if __name__ == "__main__":
    run()
