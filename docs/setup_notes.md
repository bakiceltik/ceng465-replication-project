# Two-Mac PostgreSQL Setup Notes

These notes describe the intended environment for the CENG465 progress demo.
They do not automatically configure PostgreSQL replication.

## Machine Roles

- Mac 1: PostgreSQL Leader/Primary
- Mac 2: PostgreSQL Follower/Standby

Both machines must be on the same local network. Single-machine Docker-only or
single-machine VM-only setups do not satisfy the project requirement.

## Find Local IP Addresses on macOS

On each Mac, run:

```bash
ipconfig getifaddr en0
```

Use the returned local IP addresses in `.env`:

```text
LEADER_DB_HOST=192.168.x.x
FOLLOWER_DB_HOST=192.168.x.x
```

If `en0` does not return an address, check the active network interface in
System Settings or with `ifconfig`.

## PostgreSQL Port

The default PostgreSQL port is:

```text
5432
```

The leader must accept PostgreSQL connections from:

- the follower, for replication
- the client machine running the Python scripts, for leader writes

The follower must accept PostgreSQL connections from the client machine for
read-only visibility checks.

## Leader/Primary Notes

The leader should contain the writable `replication_project` database. Apply the
schema only on the leader:

```bash
python -m scripts.init_schema
```

The leader must allow the follower to connect for replication. In a real
PostgreSQL physical replication setup, this usually involves configuration such
as `postgresql.conf`, `pg_hba.conf`, replication user credentials, WAL settings,
and a standby configuration on the follower.

## Follower/Standby Notes

The follower should connect to the leader for replication and should be treated
as read-only for this project. Do not run `init_schema.py` directly against the
follower in a physical standby setup.

The Python scripts poll the follower after each leader write to observe when the
expected `orders` row version and `operation_id` become visible.

## Network and Firewall Checks

If connections fail:

- Confirm both Macs are on the same Wi-Fi or LAN.
- Confirm each Mac can reach the other by IP address.
- Confirm PostgreSQL is listening on port `5432`.
- Confirm macOS firewall settings allow PostgreSQL connections.
- Confirm PostgreSQL host-based access rules allow the expected client and
  follower IP addresses.

## Important Boundary

This repository provides application-level demo code, schema, operation logging,
and measurement scripts. PostgreSQL primary/standby replication must be
configured separately on the two physical machines.
