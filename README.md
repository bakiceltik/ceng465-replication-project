# CENG465 Replicated Order Tracking System

## Objective

This repository demonstrates the **Data Schema and Replication Logging** part of
the CENG465 project, "Data Replication in a Single-Leader Environment".

The demo uses PostgreSQL with one physical Mac acting as the leader/primary and
another physical Mac acting as the follower/standby. Python scripts perform
order writes on the leader, poll the follower for visibility, and log measured
replication delay for each write operation.

## Architecture

```text
                      same local network

  Mac 1: PostgreSQL Leader/Primary           Mac 2: PostgreSQL Follower/Standby
  ┌────────────────────────────────┐         ┌────────────────────────────────┐
  │ replication_project database   │ WAL --> │ replication_project database   │
  │                                │         │                                │
  │ writes: INSERT/UPDATE/DELETE   │         │ reads: visibility checks only  │
  │ tables: orders, operation_log  │         │ replicated orders/log records  │
  └───────────────▲────────────────┘         └───────────────▲────────────────┘
                  │                                          │
                  └──────── Python client/demo scripts ──────┘
```

All write operations go to the leader. The follower is used as a read-only node
to observe when the leader's changes become visible after replication.

## Requirements

- Two physical Mac computers on the same local network
- PostgreSQL installed on both Macs
- PostgreSQL primary/standby replication configured separately
- Python 3.10 or newer
- Network access to PostgreSQL port `5432`

This repository does **not** configure PostgreSQL physical replication
automatically. It provides the schema, operation scripts, logging, and demo code
used after the leader/follower PostgreSQL environment is ready.

## Setup

Create and activate a Python virtual environment:

```bash
cd ceng465-replication-project
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Edit `.env` with the actual local IP addresses, database names, users, and
passwords for the leader and follower Macs:

```text
LEADER_DB_HOST=192.168.x.x
FOLLOWER_DB_HOST=192.168.x.x
```

The database `replication_project` should already exist on the leader. In a
physical standby setup, the follower receives database contents through
replication.

## Initialize Schema

Run schema initialization against the leader only:

```bash
python -m scripts.init_schema
```

Do not apply the schema directly to a PostgreSQL physical standby. Schema
changes should be written on the leader and then replicated to the follower.

## Run the Progress Demo

After replication is configured and the schema exists:

```bash
python -m scripts.demo_progress
```

The demo performs:

1. Insert a sample order on the leader.
2. Poll the follower until that order is visible.
3. Update status from `pending` to `paid`.
4. Poll the follower for the updated version.
5. Update status from `paid` to `shipped`.
6. Poll the follower again.
7. Soft-delete the order by setting `deleted=true` and `status='cancelled'`.
8. Print a compact summary table with replication delay for every operation.

You can also run individual operations:

```bash
python -m scripts.create_order --customer-name "Grace Hopper" --product-name "Laptop Stand" --quantity 2
python -m scripts.update_order_status --order-id <order-id> --status paid
python -m scripts.soft_delete_order --order-id <order-id>
```

## How Replication Logging Works

The main table is `orders`. It includes update-tracking fields:

- `version`: increments on each update or soft delete
- `operation_id`: a UUID generated for each write operation
- `last_updated`: timestamp of the latest leader-side change
- `deleted`: soft-delete marker

The `operation_log` table is written on the leader for each operation:

- `operation_type`: `INSERT`, `UPDATE`, or `DELETE`
- `leader_write_time`: client-side UTC time for the leader write
- `follower_visible_time`: client-side UTC time when polling observes the row
- `replication_delay_ms`: measured delay between those two moments
- `leader_snapshot` and `follower_snapshot`: JSONB evidence for comparison

Because `operation_log` is also written on the leader, its rows are replicated to
the follower too.

## Progress Presentation Fit

This codebase satisfies the progress presentation requirements by showing:

- Schema design through `orders` and `operation_log`
- Update tracking fields: `version`, `operation_id`, `last_updated`, `deleted`
- A logging mechanism for every write operation
- Sample insert, update, and soft-delete operations
- Evidence of replication behavior through follower polling, snapshots, and
  measured delay values

Future project work can build on this foundation to test eventual consistency,
monotonic reads, read-after-write behavior, and concurrent writes.
