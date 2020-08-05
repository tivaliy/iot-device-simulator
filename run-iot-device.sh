#!/bin/sh

set -e

# Initialize environment variables that are defined in .env file
echo "[*] Initializing environment variables from '.env'..."
export $(grep -v '^#' .env | xargs)

# Option to override GCP_DEVICE_ID from the first argument
GCP_DEVICE_ID="${1:-$GCP_DEVICE_ID}"

if [ -z "${GCP_DEVICE_ID}" ]; then
  echo "No DEVICE_ID argument and environment variable GCP_DEVICE_ID is not set" >&2
  echo "Usage: run-iot-device.sh [GCP_DEVICE_ID]" >&2
  exit 1
fi

# Check that IoT device exists
echo "[*] Fetching '$GCP_DEVICE_ID' information..."
gcloud beta iot devices describe "$GCP_DEVICE_ID" \
  --region="$GCP_REGION" \
  --registry="$GCP_IOT_REGISTRY_NAME"

# Run simulator
echo "[*] Running '$GCP_DEVICE_ID'..."
gcloud compute ssh "$GCP_VM_SIMULATOR_NAME" --zone="$GCP_ZONE" -- \
   "python3.7 cloud_iot_mqtt.py \
     --project_id=$GCP_PROJECT \
     --registry_id=$GCP_IOT_REGISTRY_NAME \
     --device_id=$GCP_DEVICE_ID \
     --private_key_file='/home/user/.ssh/rsa_private.pem' \
     --algorithm=RS256 \
     --ca_certs='/home/user/.ssh/roots.pem' \
     --num_messages 10"