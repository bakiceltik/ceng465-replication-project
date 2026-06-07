"""
Experiment 3: Read-After-Write Consistency
--------------------------------------
Write to the leader, then immediately read from the leader and from the follower.

Expected result:
  - Leader read: always sees the write immediately (RAW consistent).
  - Follower read: may not yet see the write (replication lag).
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

FOLLOWER_POLL_INTERVAL = 0.5
FOLLOWER_POLL_TIMEOUT = 60.0


def _setup_fixtures() -> tuple[str, str]:
    conn = get_leader_connection()
    try:
        with conn:
            cat = get_or_create_category(conn, "Electronics", "Electronic products")
            cust = get_or_create_customer(conn, "Carol Raw", "carol@experiment.com")
            prod = get_or_create_product(conn, "RAW Test Gadget", cat["id"], 15.00)
            return cust["id"], prod["id"]
    finally:
        conn.close()


def run() -> None:
    print("=" * 70)
    print("EXPERIMENT 3 — Read-After-Write Consistency")
    print("=" * 70)

    customer_id, product_id = _setup_fixtures()
    order_id = str(uuid.uuid4())
    op_id = str(uuid.uuid4())

    # ── Write to leader ────────────────────────────────────────────────────────
    conn = get_leader_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                write_time = now_utc()
                cur.execute(
                    """
                    INSERT INTO orders
                        (id, customer_id, status, total_amount, version, operation_id)
                    VALUES (%s, %s, 'pending', 15.00, 1, %s)
                    """,
                    (order_id, customer_id, op_id),
                )
                cur.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price, operation_id)
                    VALUES (%s, %s, 1, 15.00, %s)
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
                    (str(uuid.uuid4()), order_id, write_time,
                     "Experiment 3: read-after-write insert."),
                )
        print(f"\n[WRITE ] leader_write_time = {write_time.isoformat(timespec='milliseconds')}")
        print(f"[WRITE ] order_id          = {order_id}")

        # ── Immediate read from leader ─────────────────────────────────────────
        leader_read_time = now_utc()
        leader_row = fetch_order_by_id(conn, order_id)
        leader_delay_ms = int((leader_read_time - write_time).total_seconds() * 1000)

        print(f"\n[LEADER] immediate read (t+{leader_delay_ms} ms)")
        if leader_row:
            print(f"         version={leader_row['version']} — write IS visible  (RAW satisfied)")
        else:
            print("         record NOT found on leader  (unexpected!)")
    finally:
        conn.close()

    # ── Immediate read from follower ───────────────────────────────────────────
    follower_conn = get_follower_connection()
    follower_conn.autocommit = True
    try:
        first_read_time = now_utc()
        first_row = fetch_order_by_id(follower_conn, order_id)
        first_delay_ms = int((first_read_time - write_time).total_seconds() * 1000)

        print(f"\n[FOLLWR] immediate read (t+{first_delay_ms} ms)")
        if first_row:
            print("         record already visible on follower (very low lag)")
        else:
            print("         record NOT yet visible — replication lag in progress")

        # ── Poll follower until convergence ────────────────────────────────────
        print(f"\n[FOLLWR] Polling for convergence (every {FOLLOWER_POLL_INTERVAL}s) ...")
        deadline = time.monotonic() + FOLLOWER_POLL_TIMEOUT
        poll = 0
        convergence_time: datetime | None = None

        while time.monotonic() <= deadline:
            poll += 1
            poll_time = now_utc()
            row = fetch_order_by_id(follower_conn, order_id)
            elapsed_ms = int((poll_time - write_time).total_seconds() * 1000)

            if row and str(row["operation_id"]) == op_id:
                convergence_time = poll_time
                print(
                    f"  poll {poll:02d} | t+{elapsed_ms} ms | "
                    f"CONVERGED version={row['version']}"
                )
                break
            else:
                print(f"  poll {poll:02d} | t+{elapsed_ms} ms | not yet visible")
            time.sleep(FOLLOWER_POLL_INTERVAL)
    finally:
        follower_conn.close()

    print()
    print("=" * 70)
    print("RESULT SUMMARY")
    print(f"  Leader write time    : {write_time.isoformat(timespec='milliseconds')}")
    print(f"  Leader read (ms)     : {leader_delay_ms} ms — {'VISIBLE' if leader_row else 'NOT FOUND'}")
    print(f"  Follower 1st read    : {'visible' if first_row else 'not yet visible'} at t+{first_delay_ms} ms")
    if convergence_time:
        total_ms = int((convergence_time - write_time).total_seconds() * 1000)
        print(f"  Follower convergence : {total_ms} ms after write")
    else:
        print(f"  Follower convergence : did not converge within {FOLLOWER_POLL_TIMEOUT}s")
    print("=" * 70)


if __name__ == "__main__":
    run()
