# CENG465 — Quick Reference

## VM Connections

```bash
# SSH into leader
gcloud compute ssh ceng465-leader --zone=us-central1-a

# SSH into follower
gcloud compute ssh ceng465-follower --zone=us-central1-a
```

## VM Start / Stop

```bash
# Stop (billing pauses for compute, disk still billed)
gcloud compute instances stop ceng465-leader   --zone=us-central1-a
gcloud compute instances stop ceng465-follower --zone=us-central1-a

# Start again
gcloud compute instances start ceng465-leader   --zone=us-central1-a
gcloud compute instances start ceng465-follower --zone=us-central1-a

# Check status
gcloud compute instances list
```

> **Note:** External IPs change on every start unless reserved. Update `.env` after restarting.

## psql Connections (from local Mac)

```bash
# Leader (writes)
psql "host=35.184.141.149 port=5432 dbname=replication_project user=ceng465 password=ceng465pass"

# Follower (reads / standby)
psql "host=34.63.239.194 port=5432 dbname=replication_project user=ceng465 password=ceng465pass"
```

## Check Replication Status

```sql
-- Run on leader — is follower connected?
SELECT client_addr, state, write_lag, flush_lag, replay_lag
FROM pg_stat_replication;

-- Run on follower — is it in standby mode?
SELECT pg_is_in_recovery();
```

## Example SQL Operations

### INSERT (write on leader, read on follower)

```sql
-- LEADER
INSERT INTO customers (name, email)
VALUES ('eray', 'eray@example.com')
RETURNING id, name, version, last_updated;

-- FOLLOWER (visible within a few ms)
SELECT id, name, version, last_updated
FROM customers
WHERE email = 'eray@example.com';
```

### UPDATE (version increments)

```sql
-- LEADER
UPDATE customers
SET name         = 'Ada Lovelace (Updated)',
    version      = version + 1,
    operation_id = gen_random_uuid(),
    last_updated = NOW()
WHERE email = 'ada@example.com'
RETURNING id, name, version, last_updated;

-- FOLLOWER
SELECT id, name, version, last_updated
FROM customers
WHERE email = 'ada@example.com';
```

### SOFT DELETE

```sql
-- LEADER
UPDATE customers
SET deleted      = TRUE,
    version      = version + 1,
    operation_id = gen_random_uuid(),
    last_updated = NOW()
WHERE email = 'ada@example.com'
RETURNING id, name, deleted, version;

-- FOLLOWER
SELECT id, name, deleted, version FROM customers WHERE email = 'ada@example.com';
```

### Full Order Creation

```sql
-- LEADER — run in order
INSERT INTO categories (name) VALUES ('Electronics') ON CONFLICT DO NOTHING;

INSERT INTO products (category_id, name, price, stock)
SELECT id, 'Laptop', 999.99, 10 FROM categories WHERE name = 'Electronics'
RETURNING id, name, price;

INSERT INTO customers (name, email) VALUES ('Test User', 'test@test.com')
ON CONFLICT DO NOTHING;

INSERT INTO orders (customer_id, status, total_amount)
SELECT id, 'pending', 999.99 FROM customers WHERE email = 'test@test.com'
RETURNING id, status, total_amount, version;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT
    (SELECT id FROM orders WHERE customer_id = (SELECT id FROM customers WHERE email='test@test.com') LIMIT 1),
    (SELECT id FROM products WHERE name = 'Laptop'),
    1, 999.99
RETURNING id, quantity, unit_price;

-- FOLLOWER — read everything
SELECT o.id, c.name AS customer, o.status, o.total_amount, o.version
FROM orders o JOIN customers c ON c.id = o.customer_id
ORDER BY o.last_updated DESC LIMIT 5;
```

## Python Scripts

```bash
cd ceng465-replication-project
source .venv/bin/activate

# Full demo: INSERT → UPDATE → DELETE + replication delay measurement
python -m scripts.demo_progress

# Create a single order
python -m scripts.create_order \
  --customer-name "John Doe" \
  --customer-email "john@test.com" \
  --item "Keyboard:1:89.99"

# Experiment 1: Eventual Consistency
python -m scripts.experiment_eventual_consistency

# Experiment 2: Monotonic Reads
python -m scripts.experiment_monotonic_reads

# Experiment 3: Read-After-Write Consistency
python -m scripts.experiment_read_after_write

# Scenario: Concurrent Writes
python -m scripts.experiment_concurrent_writes
```

## Presentation Demo

```bash
bash gcp/demo_presentation.sh
```

Press Enter between each step — writes on leader, reads on follower.

## Tables

| Table | Description |
|-------|-------------|
| `customers` | Customer records |
| `categories` | Product categories |
| `products` | Products (price, stock) |
| `orders` | Orders (customer_id, status, total) |
| `order_items` | Order line items (product, qty, price) |
| `operation_log` | Replication log for every write operation |

Every table includes: `version`, `operation_id`, `last_updated`, `deleted` — for replication tracking.
