#!/usr/bin/env bash
# Run from your local Mac AFTER 02_configure_leader.sh succeeds.
# Sets up PostgreSQL streaming standby on follower via pg_basebackup.
set -euo pipefail

PROJECT="c465-repl-baki-new"
ZONE="us-central1-a"
FOLLOWER="ceng465-follower"
LEADER_INTERNAL_IP="10.128.0.2"

REPL_USER="replicator"
REPL_PASSWORD="replpass123"

# Local Mac IP — update if your public IP changes
MY_PUBLIC_IP="31.223.96.173"

# ── Write remote setup script locally ─────────────────────────────────────────
cat > /tmp/_follower_setup.sh << REMOTE
#!/usr/bin/env bash
set -euo pipefail

echo "--- apt update & install PostgreSQL ---"
sudo apt-get update -qq
sudo apt-get install -y -qq postgresql postgresql-contrib

PG_VER=\$(ls /etc/postgresql/)
PG_DATA="/var/lib/postgresql/\${PG_VER}/main"

echo "--- Detected PostgreSQL \${PG_VER} ---"

echo "--- Stopping PostgreSQL ---"
sudo systemctl stop postgresql

echo "--- Wiping data dir for base backup ---"
sudo rm -rf "\${PG_DATA}"
sudo mkdir -p "\${PG_DATA}"
sudo chown postgres:postgres "\${PG_DATA}"
sudo chmod 700 "\${PG_DATA}"

echo "--- pg_basebackup from leader ---"
sudo -u postgres bash -c "PGPASSWORD='${REPL_PASSWORD}' pg_basebackup \
    -h ${LEADER_INTERNAL_IP} -p 5432 \
    -U ${REPL_USER} \
    -D \${PG_DATA} \
    --wal-method=stream \
    --checkpoint=fast \
    -P -v"

echo "--- Creating standby.signal ---"
sudo -u postgres touch "\${PG_DATA}/standby.signal"

echo "--- Writing primary_conninfo ---"
sudo -u postgres bash -c "cat >> \${PG_DATA}/postgresql.auto.conf << EOF

primary_conninfo = 'host=${LEADER_INTERNAL_IP} port=5432 user=${REPL_USER} password=${REPL_PASSWORD} application_name=ceng465_follower'
hot_standby = on
EOF"

echo "--- Configuring follower to accept external connections ---"
PG_CONF="/etc/postgresql/\${PG_VER}/main/postgresql.conf"
PG_HBA="/etc/postgresql/\${PG_VER}/main/pg_hba.conf"
sudo sed -i "s|#listen_addresses = 'localhost'|listen_addresses = '*'|" "\$PG_CONF"
sudo sed -i "s|listen_addresses = 'localhost'|listen_addresses = '*'|"  "\$PG_CONF"
sudo bash -c "echo '' >> \$PG_HBA"
sudo bash -c "echo 'host all all ${MY_PUBLIC_IP}/32 scram-sha-256' >> \$PG_HBA"
sudo bash -c "echo 'host all all 10.128.0.0/9 scram-sha-256' >> \$PG_HBA"

echo "--- Starting PostgreSQL follower ---"
sudo systemctl start postgresql
sleep 4

echo "--- Verifying standby mode (expect t) ---"
sudo -u postgres psql -c "SELECT pg_is_in_recovery();"

echo "--- Done ---"
REMOTE

# ── Copy and run ───────────────────────────────────────────────────────────────
echo "==> Copying setup script..."
gcloud compute scp \
    --project="$PROJECT" --zone="$ZONE" \
    /tmp/_follower_setup.sh "${FOLLOWER}:/tmp/_follower_setup.sh"

echo "==> Running setup on $FOLLOWER ..."
gcloud compute ssh "$FOLLOWER" \
    --project="$PROJECT" --zone="$ZONE" \
    --command="bash /tmp/_follower_setup.sh"

echo ""
echo "============================================================"
echo "  Follower configured. pg_is_in_recovery() must show 't'."
echo "  Next: run 04_verify_replication.sh"
echo "============================================================"
