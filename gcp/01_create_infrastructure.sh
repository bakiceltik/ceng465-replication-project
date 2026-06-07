#!/usr/bin/env bash
# GCP infrastructure creation for CENG465 single-leader replication project.
# Run this once from your local machine with gcloud CLI authenticated.
set -euo pipefail

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
PROJECT_ID="c465-repl-baki-new"
REGION="us-central1"
ZONE="us-central1-a"

MACHINE_TYPE="e2-micro"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"
DISK_SIZE="10GB"
DISK_TYPE="pd-standard"

LEADER_NAME="ceng465-leader"
FOLLOWER_NAME="ceng465-follower"
NETWORK_TAG="postgres"

# Change this if your home IP changes.
MY_PUBLIC_IP="31.223.96.173/32"
INTERNAL_RANGE="10.128.0.0/9"
# ──────────────────────────────────────────────────────────────────────────────

echo "==> Setting active project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"
gcloud config set compute/zone "$ZONE"

echo "==> Creating leader VM: $LEADER_NAME"
gcloud compute instances create "$LEADER_NAME" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="$DISK_SIZE" \
    --boot-disk-type="$DISK_TYPE" \
    --tags="$NETWORK_TAG" \
    --metadata="role=leader"

echo "==> Creating follower VM: $FOLLOWER_NAME"
gcloud compute instances create "$FOLLOWER_NAME" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="$DISK_SIZE" \
    --boot-disk-type="$DISK_TYPE" \
    --tags="$NETWORK_TAG" \
    --metadata="role=follower"

echo "==> Creating firewall rule: internal PostgreSQL traffic"
gcloud compute firewall-rules create allow-postgres-internal \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:5432 \
    --target-tags="$NETWORK_TAG" \
    --source-ranges="$INTERNAL_RANGE" \
    --description="Allow PostgreSQL traffic between GCP VMs" \
    || echo "Firewall rule allow-postgres-internal already exists, skipping."

echo "==> Creating firewall rule: PostgreSQL from local machine"
gcloud compute firewall-rules create allow-postgres-from-my-ip \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:5432 \
    --target-tags="$NETWORK_TAG" \
    --source-ranges="$MY_PUBLIC_IP" \
    --description="Allow PostgreSQL access from local experiment runner" \
    || echo "Firewall rule allow-postgres-from-my-ip already exists, skipping."

echo ""
echo "==> VMs created. Fetching IPs..."

LEADER_EXTERNAL_IP=$(gcloud compute instances describe "$LEADER_NAME" --zone="$ZONE" \
    --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
FOLLOWER_EXTERNAL_IP=$(gcloud compute instances describe "$FOLLOWER_NAME" --zone="$ZONE" \
    --format="get(networkInterfaces[0].accessConfigs[0].natIP)")

LEADER_INTERNAL_IP=$(gcloud compute instances describe "$LEADER_NAME" --zone="$ZONE" \
    --format="get(networkInterfaces[0].networkIP)")
FOLLOWER_INTERNAL_IP=$(gcloud compute instances describe "$FOLLOWER_NAME" --zone="$ZONE" \
    --format="get(networkInterfaces[0].networkIP)")
