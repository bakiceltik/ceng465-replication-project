from __future__ import annotations

from typing import Any

from scripts.create_order import create_order
from scripts.soft_delete_order import soft_delete_order
from scripts.update_order_status import update_order_status


def _format_time(value) -> str:
    return value.isoformat(timespec="milliseconds")


def _print_step(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _print_summary(results: list[dict[str, Any]]) -> None:
    headers = [
        "operation_type",
        "order_id",
        "version",
        "leader_write_time",
        "follower_visible_time",
        "replication_delay_ms",
    ]
    rows = [
        [
            result["operation_type"],
            result["order_id"],
            str(result["version"]),
            _format_time(result["leader_write_time"]),
            _format_time(result["follower_visible_time"]),
            str(result["replication_delay_ms"]),
        ]
        for result in results
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]

    print("\nReplication Summary")
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def main() -> None:
    print("CENG465 PostgreSQL Single-Leader Replication Progress Demo")
    print("Writes go to the leader. The follower is polled until each change is visible.")

    results: list[dict[str, Any]] = []

    _print_step("1. Create sample order on leader")
    created = create_order(
        customer_name="Ada Lovelace",
        product_name="Mechanical Keyboard",
        quantity=1,
    )
    results.append(created)
    print(
        f"Follower saw INSERT for order {created['order_id']} "
        f"in {created['replication_delay_ms']} ms."
    )

    order_id = created["order_id"]

    _print_step("2. Update order status: pending -> paid")
    paid = update_order_status(order_id, "paid")
    results.append(paid)
    print(
        f"Follower saw UPDATE version {paid['version']} "
        f"in {paid['replication_delay_ms']} ms."
    )

    _print_step("3. Update order status: paid -> shipped")
    shipped = update_order_status(order_id, "shipped")
    results.append(shipped)
    print(
        f"Follower saw UPDATE version {shipped['version']} "
        f"in {shipped['replication_delay_ms']} ms."
    )

    _print_step("4. Soft-delete order: shipped -> cancelled, deleted=true")
    deleted = soft_delete_order(order_id)
    results.append(deleted)
    print(
        f"Follower saw DELETE version {deleted['version']} "
        f"in {deleted['replication_delay_ms']} ms."
    )

    _print_summary(results)


if __name__ == "__main__":
    main()
