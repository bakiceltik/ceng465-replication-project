#!/usr/bin/env bash
# Run from your local Mac.
# Installs PostgreSQL on leader VM, configures replication, creates DB + schema.
set -euo pipefail

PROJECT="c465-repl-baki-new"
ZONE="us-central1-a"
LEADER="ceng465-leader"
FOLLOWER_INTERNAL_IP="10.128.0.3"

DB_NAME="replication_project"
DB_USER="ceng465"
DB_PASSWORD="ceng465pass"
REPL_USER="replicator"
REPL_PASSWORD="replpass123"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── 1. Copy schema to leader ───────────────────────────────────────────────────
echo "==> Copying schema..."
gcloud compute scp \
    --project="$PROJECT" --zone="$ZONE" \
    "${SCRIPT_DIR}/../sql/01_schema.sql" \
    "${LEADER}:/tmp/01_schema.sql"

# ── 2. Write remote setup script locally (variables expanded here) ─────────────
cat > /tmp/_leader_setup.sh << REMOTE
#!/usr/bin/env bash
set -euo pipefail

echo "--- apt update & install PostgreSQL ---"
sudo apt-get update -qq
sudo apt-get install -y -qq postgresql postgresql-contrib

PG_VER=\$(ls /etc/postgresql/)
PG_CONF="/etc/postgresql/\${PG_VER}/main/postgresql.conf"
PG_HBA="/etc/postgresql/\${PG_VER}/main/pg_hba.conf"

echo "--- Detected PostgreSQL \${PG_VER} ---"

echo "--- postgresql.conf ---"
sudo sed -i "s|#listen_addresses = 'localhost'|listen_addresses = '*'|"    "\$PG_CONF"
sudo sed -i "s|#wal_level = replica|wal_level = replica|"                  "\$PG_CONF"
sudo sed -i "s|#max_wal_senders = 10|max_wal_senders = 5|"                "\$PG_CONF"
sudo sed -i "s|#wal_keep_size = 0|wal_keep_size = 128|"                   "\$PG_CONF"
sudo sed -i "s|#hot_standby = on|hot_standby = on|"                       "\$PG_CONF"
sudo sed -i "s|#wal_log_hints = off|wal_log_hints = on|"                  "\$PG_CONF"

echo "--- pg_hba.conf ---"
sudo bash -c "echo '' >> \$PG_HBA"
sudo bash -c "echo 'host replication ${REPL_USER} ${FOLLOWER_INTERNAL_IP}/32 scram-sha-256' >> \$PG_HBA"
sudo bash -c "echo 'host all all 0.0.0.0/0 scram-sha-256' >> \$PG_HBA"

echo "--- Restarting PostgreSQL ---"
sudo systemctl restart postgresql
sleep 2

echo "--- Creating users & database ---"
sudo -u postgres psql -c "CREATE USER ${REPL_USER} WITH REPLICATION ENCRYPTED PASSWORD '${REPL_PASSWORD}';" 2>/dev/null || echo "replicator already exists"
sudo -u postgres psql -c "CREATE USER ${DB_USER}   WITH ENCRYPTED PASSWORD '${DB_PASSWORD}';"                2>/dev/null || echo "ceng465 already exists"
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"                                      2>/dev/null || echo "db already exists"
sudo -u postgres psql -d ${DB_NAME} -c "GRANT ALL ON SCHEMA public TO ${DB_USER};"

echo "--- Applying schema ---"
sudo -u postgres psql -d ${DB_NAME} -f /tmp/01_schema.sql
sudo -u postgres psql -d ${DB_NAME} -c "GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO ${DB_USER};"
sudo -u postgres psql -d ${DB_NAME} -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${DB_USER};"

echo "--- Done. Tables: ---"
sudo -u postgres psql -d ${DB_NAME} -c "\dt"
REMOTE

# ── 3. Copy and run ────────────────────────────────────────────────────────────
echo "==> Copying setup script..."
gcloud compute scp \
    --project="$PROJECT" --zone="$ZONE" \
    /tmp/_leader_setup.sh "${LEADER}:/tmp/_leader_setup.sh"

echo "==> Running setup on $LEADER ..."
gcloud compute ssh "$LEADER" \
    --project="$PROJECT" --zone="$ZONE" \
    --command="bash /tmp/_leader_setup.sh"

echo ""
echo "============================================================"
echo "  Leader configured. DB=$DB_NAME user=$DB_USER"
echo "  Replication user: $REPL_USER / $REPL_PASSWORD"
echo "  Next: run 03_configure_follower.sh"
echo "============================================================"
