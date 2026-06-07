"""
Scenario: Concurrent Writes
--------------------------------------
Perform N orders in rapid succession to the leader (no intentional delay).
Poll the follower for each and verify they appear in the same order
(by leader_write_time) as they were written.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from psycopg2.extras import Json

from scripts.db import (
    get_leader_connection,
    get_or_create_category,
    get_or_create_customer,
    get_or_create_product,
    now_utc,
)
from scripts.measure_replication import wait_for_follower_order

CONCURRENT_WRITE_COUNT = 5


def _setup_fixtures() -> tuple[str, str]:
    conn = get_leader_connection()
    try:
        with conn:
            cat = get_or_create_category(conn, "Electronics", "Electronic products")
            cust = get_or_create_customer(conn, "Concurrent Test", "concurrent@experiment.com")
            prod = get_or_create_product(conn, "Batch Item", cat["id"], 1.00)
            return cust["id"], prod["id"]
    finally:
        conn.close()


def _write_order(customer_id: str, product_id: str, seq: int) -> tuple[str, str, datetime]:
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
                    VALUES (%s, %s, 'pending', 1.00, 1, %s)
                    """,
                    (order_id, customer_id, op_id),
                )
                cur.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, quantity, unit_price, operation_id)
                    VALUES (%s, %s, 1, 1.00, %s)
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
                    (
                        str(uuid.uuid4()), order_id, write_time,
                        f"Experiment 4: concurrent write #{seq}.",
                    ),
                )
    finally:
        conn.close()
    return order_id, op_id, write_time


def run() -> None:
    print("=" * 70)
    print("SCENARIO — Concurrent Writes")
    print("=" * 70)
    print(f"\nWriting {CONCURRENT_WRITE_COUNT} orders to leader in rapid succession ...\n")

    customer_id, product_id = _setup_fixtures()
    writes: list[dict] = []

    for seq in range(1, CONCURRENT_WRITE_COUNT + 1):
        order_id, op_id, write_time = _write_order(customer_id, product_id, seq)
        writes.append({"seq": seq, "order_id": order_id, "op_id": op_id,
                        "write_time": write_time})
        print(
            f"  #{seq} written | ...{order_id[-8:]} | "
            f"{write_time.isoformat(timespec='milliseconds')}"
        )

    print(f"\n[FOLLOWER] Polling each order for visibility ...\n")

    results: list[dict] = []
    for w in writes:
        try:
            snapshot, visible_time = wait_for_follower_order(
                w["order_id"],
                expected_version=1,
                expected_operation_id=w["op_id"],
                timeout_seconds=60,
                interval_seconds=0.25,
            )
            delay_ms = int((visible_time - w["write_time"]).total_seconds() * 1000)
            results.append({**w, "visible_time": visible_time, "delay_ms": delay_ms})
            print(f"  #{w['seq']} visible | delay={delay_ms} ms | ...{w['order_id'][-8:]}")
        except TimeoutError:
            print(f"  #{w['seq']} TIMEOUT — follower did not receive ...{w['order_id'][-8:]}")
            results.append({**w, "visible_time": None, "delay_ms": None})

    visible = [r for r in results if r["visible_time"] is not None]
    order_preserved = all(
        visible[i]["visible_time"] <= visible[i + 1]["visible_time"]
        for i in range(len(visible) - 1)
    )

    print()
    print("=" * 70)
    print("RESULT SUMMARY")
    print(f"  {'#':<3} | {'order_id':>10} | {'leader_write':>28} | {'follower_visible':>28} | {'delay':>8}")
    print("  " + "-" * 85)
    for r in results:
        lw = r["write_time"].isoformat(timespec="milliseconds")
        fv = r["visible_time"].isoformat(timespec="milliseconds") if r["visible_time"] else "TIMEOUT"
        dl = f"{r['delay_ms']} ms" if r["delay_ms"] is not None else "-"
        print(f"  #{r['seq']:<2} | ...{r['order_id'][-8:]:>10} | {lw:>28} | {fv:>28} | {dl:>8}")
    print()
    if order_preserved:
        print("  Follower visibility order matches leader write sequence. (No ordering violation.)")
    else:
        print("  WARNING: Follower visibility order differs from leader write order.")
    print("=" * 70)


if __name__ == "__main__":
    run()
