#!/bin/bash

set -e

# Initialize environment variables that are defined in .env file
echo "[*] Initializing environment variables from '.env'..."
export $(grep -v '^#' .env | xargs)

# Option to override GCP_DEVICE_ID from the first argument
GCP_DEVICE_ID="${1:-$GCP_DEVICE_ID}"

if [ -z "${GCP_DEVICE_ID}" ]; then
  echo "No DEVICE_ID argument and environment variable GCP_DEVICE_ID is not set" >&2
  echo "Usage: create-iot-device.sh [GCP_DEVICE_ID]" >&2
  exit 1
fi

echo "[*] Fetching public key..."
gcloud compute scp "$GCP_VM_SIMULATOR_NAME":~/.ssh/rsa_cert.pem /tmp/

# Create IoT device within provided IoT registry
echo "* Creating '$GCP_DEVICE_ID' device..."
gcloud beta iot devices create "$GCP_DEVICE_ID" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --registry="$GCP_IOT_REGISTRY_NAME" \
  --public-key path=/tmp/rsa_cert.pem,type=rsa-x509-pem
