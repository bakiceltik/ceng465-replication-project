#!/usr/bin/env bash
# Run from local Mac after both 02 and 03 finish.
# Verifies streaming replication is working.
set -euo pipefail

PROJECT="c465-repl-baki-new"
ZONE="us-central1-a"
LEADER="ceng465-leader"
FOLLOWER="ceng465-follower"

LEADER_EXT_IP="35.192.167.186"
FOLLOWER_EXT_IP="34.59.242.132"
DB_NAME="replication_project"
DB_USER="ceng465"
DB_PASSWORD="ceng465pass"

echo "=== 1. Leader: pg_stat_replication ==="
gcloud compute ssh "$LEADER" \
    --project="$PROJECT" --zone="$ZONE" \
    --command="sudo -u postgres psql -c 'SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn, sync_state, application_name FROM pg_stat_replication;'"

echo ""
echo "=== 2. Follower: confirm recovery mode ==="
gcloud compute ssh "$FOLLOWER" \
    --project="$PROJECT" --zone="$ZONE" \
    --command="sudo -u postgres psql -c 'SELECT pg_is_in_recovery(), now();'"

echo ""
echo "=== 3. Write test row on leader, read on follower ==="
TEST_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
echo "  Test UUID: $TEST_UUID"

PGPASSWORD="$DB_PASSWORD" psql \
    -h "$LEADER_EXT_IP" -p 5432 -U "$DB_USER" -d "$DB_NAME" \
    -c "INSERT INTO customers (id, name, email, operation_id)
        VALUES ('$TEST_UUID', 'Replication Test', 'reptest@test.com', gen_random_uuid());"

echo "  Waiting 2s for replication..."
sleep 2

echo "  Reading from follower..."
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$FOLLOWER_EXT_IP" -p 5432 -U "$DB_USER" -d "$DB_NAME" \
    -c "SELECT id, name, email, version, last_updated FROM customers WHERE id = '$TEST_UUID';"

echo ""
echo "=== 4. Replication lag ==="
gcloud compute ssh "$LEADER" \
    --project="$PROJECT" --zone="$ZONE" \
    --command="sudo -u postgres psql -c 'SELECT application_name, state, write_lag, flush_lag, replay_lag FROM pg_stat_replication;'"

echo ""
echo "============================================================"
echo "  If test row appeared on follower → replication is working."
echo "  Run Python scripts:"
echo "    python -m scripts.demo_progress"
echo "============================================================"
