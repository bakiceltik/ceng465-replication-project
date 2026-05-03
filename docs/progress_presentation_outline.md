# Progress Presentation Outline

1. Project Objective
   - Demonstrate data replication in a single-leader PostgreSQL environment.

2. Distributed Environment
   - Mac 1 runs PostgreSQL Leader/Primary.
   - Mac 2 runs PostgreSQL Follower/Standby.
   - Both machines are on the same local network.

3. Database Choice: PostgreSQL
   - PostgreSQL supports primary/standby replication.
   - It is suitable for demonstrating leader writes and follower visibility.

4. Single-Leader Replication Architecture
   - All writes go to the leader.
   - Follower is used for read-only visibility checks.
   - Replication sends leader changes to the follower.

5. Order Tracking Schema
   - Main table: `orders`.
   - Fields store customer, product, quantity, status, and soft-delete state.

6. Update Tracking Fields
   - `version` tracks operation order.
   - `operation_id` uniquely identifies each write.
   - `last_updated` records the latest leader-side modification time.
   - `deleted` marks soft-deleted orders.

7. Replication Logging Mechanism
   - `operation_log` records every insert, update, and soft delete.
   - Logs include leader write time, follower visible time, delay, and snapshots.

8. Sample Insert/Update/Delete Demo
   - Create a sample order.
   - Update status from `pending` to `paid`.
   - Update status from `paid` to `shipped`.
   - Soft-delete the order as `cancelled`.

9. Observed Replication Behavior
   - Show terminal output with follower snapshots.
   - Show measured replication delay for each operation.
   - Show `operation_log` rows as evidence.

10. Next Steps
    - Eventual consistency experiment.
    - Monotonic reads experiment.
    - Read-after-write consistency experiment.
    - Concurrent writes and ordering observations.
