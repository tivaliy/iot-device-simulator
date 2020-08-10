#!/bin/bash

set -e

print_usage() {
  echo "No DEVICE_ID argument specified and environment variable GCP_DEVICE_ID is not set" >&2
  echo "" >&2
  echo "Usage: run-iot-device.sh [-d GCP_DEVICE_ID] [-b]" >&2
  echo "    -d GCP_DEVICE_ID    - run GCP_DEVICE_ID device" >&2
  echo "    -b                  - run in background" >&2
  exit 1
}

# Initialize environment variables that are defined in .env file
echo "[*] Initializing environment variables from '.env'..."
export $(grep -v '^#' .env | xargs)

b_flag=''
GCP_DEVICE_ID=$GCP_DEVICE_ID

while getopts 'bd:' flag; do
  case "${flag}" in
    b)  b_flag='true' ;;
    d)  GCP_DEVICE_ID="${OPTARG}" ;;
    *)  print_usage
        exit 1 ;;
  esac
done

# No $GCP_DEVICE_ID specified + forbid positional arguments (only flags)
if [ -z "$GCP_DEVICE_ID" ] || [ "${@:$OPTIND:1}" ]; then
  print_usage
  exit 1
fi

# Check that IoT device exists
echo "[*] Fetching '$GCP_DEVICE_ID' information..."
gcloud beta iot devices describe "$GCP_DEVICE_ID" \
  --region="$GCP_REGION" \
  --registry="$GCP_IOT_REGISTRY_NAME"

# Run IoT device simulator
echo "[*] Running '$GCP_DEVICE_ID'..."
if [ "$b_flag" = true ] ; then
  gcloud compute ssh "$GCP_VM_SIMULATOR_NAME" --zone="$GCP_ZONE" \
    --command="nohup \
     python3.7 cloud_iot_mqtt.py \
       --project_id=$GCP_PROJECT \
       --registry_id=$GCP_IOT_REGISTRY_NAME \
       --device_id=$GCP_DEVICE_ID \
       --private_key_file='/home/user/.ssh/rsa_private.pem' \
       --algorithm=RS256 \
       --ca_certs='/home/user/.ssh/roots.pem' \
       --num_messages 100 \
     > /dev/null 2>&1 &"
else
  gcloud compute ssh "$GCP_VM_SIMULATOR_NAME" --zone="$GCP_ZONE" -- \
   "python3.7 cloud_iot_mqtt.py \
     --project_id=$GCP_PROJECT \
     --registry_id=$GCP_IOT_REGISTRY_NAME \
     --device_id=$GCP_DEVICE_ID \
     --private_key_file='/home/user/.ssh/rsa_private.pem' \
     --algorithm=RS256 \
     --ca_certs='/home/user/.ssh/roots.pem' \
     --num_messages 10 \
     --verbose"
fi
