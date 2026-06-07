from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from scripts.db import fetch_order_by_id, get_follower_connection, now_utc, row_to_dict


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def calculate_replication_delay_ms(
    leader_write_time: datetime, follower_visible_time: datetime
) -> int:
    return max(
        0,
        int(
            (_as_utc(follower_visible_time) - _as_utc(leader_write_time)).total_seconds()
            * 1000
        ),
    )


def _matches_expected_state(
    row: dict[str, Any] | None,
    expected_version: int | None,
    expected_operation_id: str | None,
    expected_deleted: bool | None,
) -> bool:
    if row is None:
        return False
    if expected_version is not None and row["version"] != expected_version:
        return False
    if expected_operation_id is not None:
        if str(row["operation_id"]) != str(expected_operation_id):
            return False
    if expected_deleted is not None and row["deleted"] != expected_deleted:
        return False
    return True


def wait_for_follower_order(
    order_id: str,
    expected_version: int | None = None,
    expected_operation_id: str | None = None,
    expected_deleted: bool | None = None,
    timeout_seconds: float = 60,
    interval_seconds: float = 0.5,
) -> tuple[dict[str, Any], datetime]:
    """
    Poll follower until the expected order state becomes visible.
    Returns (snapshot_dict, follower_visible_time).
    """
    deadline = time.monotonic() + timeout_seconds
    last_snapshot = None

    conn = get_follower_connection()
    try:
        conn.autocommit = True
        while time.monotonic() <= deadline:
            row = fetch_order_by_id(conn, order_id)
            if _matches_expected_state(
                row, expected_version, expected_operation_id, expected_deleted
            ):
                return row_to_dict(row), now_utc()
            last_snapshot = row_to_dict(row)
            time.sleep(interval_seconds)
    finally:
        conn.close()

    raise TimeoutError(
        f"Follower did not converge. order_id={order_id} "
        f"expected_version={expected_version} "
        f"expected_operation_id={expected_operation_id} "
        f"expected_deleted={expected_deleted} "
        f"last_snapshot={last_snapshot}"
    )
