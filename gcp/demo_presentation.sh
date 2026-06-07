#!/usr/bin/env bash
# CENG465 — Presentation Demo
# Runs step by step. Press Enter between steps.
# Shows leader writes replicated to follower in real time.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env not found at $ENV_FILE"
    exit 1
fi
set -a; source "$ENV_FILE"; set +a

LEADER="${LEADER_DB_HOST}"
FOLLOWER="${FOLLOWER_DB_HOST}"
PORT="${LEADER_DB_PORT:-5432}"
DB="${LEADER_DB_NAME}"
USER="${LEADER_DB_USER}"
export PGPASSWORD="${LEADER_DB_PASSWORD}"

L="psql -h $LEADER   -p $PORT -U $USER -d $DB"
F="psql -h $FOLLOWER -p $PORT -U $USER -d $DB"

# Unique suffix so the script can be run multiple times
RUN_ID=$(date +%H%M%S)
CUSTOMER_NAME="Grace Hopper $RUN_ID"
CUSTOMER_EMAIL="grace_${RUN_ID}@navy.mil"

pause() { echo ""; read -rp ">>> Press Enter to continue... "; echo ""; }

header() {
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════════════════════"
}

# ──────────────────────────────────────────────────────────────────────────────
header "SETUP — Schema tables on LEADER"
$L -c "\dt"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 1 — INSERT a customer on LEADER"
$L -c "
INSERT INTO customers (name, email)
VALUES ('$CUSTOMER_NAME', '$CUSTOMER_EMAIL')
RETURNING id, name, email, version, last_updated;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 2 — Read customers on FOLLOWER (should see Grace)"
$F -c "SELECT id, name, email, version, last_updated FROM customers ORDER BY last_updated DESC LIMIT 5;"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 3 — INSERT a category + product on LEADER"
$L -c "
INSERT INTO categories (name, description)
VALUES ('Electronics', 'Electronic devices')
ON CONFLICT (name) DO NOTHING;
SELECT id, name FROM categories WHERE name = 'Electronics';
"
$L -c "
INSERT INTO products (category_id, name, price, stock)
SELECT id, 'Mechanical Keyboard $RUN_ID', 89.99, 50
FROM categories WHERE name='Electronics'
RETURNING id, name, price, stock, version;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 4 — Check products on FOLLOWER"
$F -c "SELECT id, name, price, stock, version FROM products;"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 5 — INSERT an order on LEADER"
$L -c "
INSERT INTO orders (customer_id, status, total_amount)
SELECT c.id, 'pending', 89.99
FROM customers c WHERE c.email = '$CUSTOMER_EMAIL'
RETURNING id, customer_id, status, total_amount, version, operation_id;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 6 — Check orders on FOLLOWER"
$F -c "
SELECT o.id, c.name AS customer, o.status, o.total_amount, o.version
FROM orders o JOIN customers c ON c.id = o.customer_id
ORDER BY o.last_updated DESC LIMIT 5;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 7 — UPDATE order status on LEADER (pending → paid)"
$L -c "
UPDATE orders
SET status       = 'paid',
    version      = version + 1,
    operation_id = gen_random_uuid(),
    last_updated = NOW()
WHERE customer_id = (SELECT id FROM customers WHERE email = '$CUSTOMER_EMAIL')
RETURNING id, status, version, last_updated;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 8 — Check updated order on FOLLOWER"
$F -c "
SELECT o.id, c.name AS customer, o.status, o.version, o.last_updated
FROM orders o JOIN customers c ON c.id = o.customer_id
ORDER BY o.last_updated DESC LIMIT 5;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 9 — SOFT DELETE order on LEADER (deleted=TRUE)"
$L -c "
UPDATE orders
SET deleted      = TRUE,
    status       = 'cancelled',
    version      = version + 1,
    operation_id = gen_random_uuid(),
    last_updated = NOW()
WHERE customer_id = (SELECT id FROM customers WHERE email = '$CUSTOMER_EMAIL')
RETURNING id, status, deleted, version, last_updated;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 10 — Check soft-deleted order on FOLLOWER"
$F -c "
SELECT o.id, c.name AS customer, o.status, o.deleted, o.version
FROM orders o JOIN customers c ON c.id = o.customer_id
ORDER BY o.last_updated DESC LIMIT 5;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 10b — HARD DELETE order then customer on LEADER (real DELETE)"
$L -c "
DELETE FROM orders
WHERE customer_id = (SELECT id FROM customers WHERE email = '$CUSTOMER_EMAIL')
RETURNING id, status;
"
$L -c "
DELETE FROM customers
WHERE email = '$CUSTOMER_EMAIL'
RETURNING id, name, email;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 10c — Verify records gone on FOLLOWER"
$F -c "SELECT id, name, email FROM customers WHERE email = '$CUSTOMER_EMAIL';"
echo "(0 rows expected)"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 11 — Replication lag (from LEADER)"
$L -c "
SELECT
    application_name,
    state,
    client_addr,
    write_lag,
    flush_lag,
    replay_lag,
    sync_state
FROM pg_stat_replication;
"
pause

# ──────────────────────────────────────────────────────────────────────────────
header "STEP 12 — operation_log (replication tracking)"
$L -c "
SELECT
    table_name,
    operation_type,
    version,
    to_char(leader_write_time, 'HH24:MI:SS.MS') AS leader_write,
    replication_delay_ms,
    notes
FROM operation_log
ORDER BY leader_write_time DESC
LIMIT 10;
"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Demo complete."
echo "════════════════════════════════════════════════════════"
