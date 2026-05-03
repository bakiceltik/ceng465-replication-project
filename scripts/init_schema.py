from __future__ import annotations

from scripts.db import PROJECT_ROOT, get_leader_connection


def main() -> None:
    schema_path = PROJECT_ROOT / "sql" / "01_schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    try:
        conn = get_leader_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
        finally:
            conn.close()
        print("Schema initialized successfully on the PostgreSQL leader.")
        print("Do not run this directly on a physical standby follower.")
        print(f"Applied schema file: {schema_path}")
    except Exception as exc:
        print("Failed to initialize schema on the leader.")
        print(f"Error: {exc}")
        raise


if __name__ == "__main__":
    main()
