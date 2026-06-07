from __future__ import annotations

from typing import Any

from scripts.create_order import create_order
from scripts.soft_delete_order import soft_delete_order
from scripts.update_order_status import update_order_status


def _fmt(value) -> str:
    return value.isoformat(timespec="milliseconds")


def _section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _summary(results: list[dict[str, Any]]) -> None:
    headers = ["op", "order_id", "ver", "leader_write", "follower_visible", "delay_ms"]
    rows = [
        [
            r["operation_type"],
            r["order_id"][:8] + "...",
            str(r["version"]),
            _fmt(r["leader_write_time"]),
            _fmt(r["follower_visible_time"]),
            str(r["replication_delay_ms"]) + " ms",
        ]
        for r in results
    ]
    widths = [
        max(len(h), *(len(row[i]) for row in rows))
        for i, h in enumerate(headers)
    ]
    print("\nReplication Summary")
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(v.ljust(widths[i]) for i, v in enumerate(row)))


def main() -> None:
    print("CENG465 — PostgreSQL Single-Leader Replication Demo")
    print("Writes go to leader. Follower is polled until each change is visible.")

    results: list[dict[str, Any]] = []

    # ── 1. Create order ────────────────────────────────────────────────────────
    _section("1. Create order — Ada Lovelace, 2 items")
    created = create_order(
        customer_name="Ada Lovelace",
        customer_email="ada@example.com",
        items=[
            ("Mechanical Keyboard", 1, 89.99),
            ("USB-C Hub", 2, 34.99),
        ],
        category_name="Electronics",
    )
    results.append(created)
    print(f"  order_id    : {created['order_id']}")
    print(f"  customer    : {created['customer']['name']} <{created['customer']['email']}>")
    print(f"  total       : ${created['total_amount']:.2f}")
    print(f"  items       : {len(created['items'])}")
    print(f"  delay       : {created['replication_delay_ms']} ms")

    order_id = created["order_id"]

    # ── 2. Update: pending → paid ──────────────────────────────────────────────
    _section("2. Update status: pending → paid")
    paid = update_order_status(order_id, "paid")
    results.append(paid)
    print(f"  version {paid['version']} visible on follower in {paid['replication_delay_ms']} ms")

    # ── 3. Update: paid → shipped ──────────────────────────────────────────────
    _section("3. Update status: paid → shipped")
    shipped = update_order_status(order_id, "shipped")
    results.append(shipped)
    print(f"  version {shipped['version']} visible on follower in {shipped['replication_delay_ms']} ms")

    # ── 4. Soft-delete ─────────────────────────────────────────────────────────
    _section("4. Soft-delete order (deleted=TRUE, status=cancelled)")
    deleted = soft_delete_order(order_id)
    results.append(deleted)
    print(f"  version {deleted['version']} visible on follower in {deleted['replication_delay_ms']} ms")

    _summary(results)


if __name__ == "__main__":
    main()
