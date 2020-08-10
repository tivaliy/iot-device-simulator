#!/bin/bash

# This script initializes GCP project for iot-device-emulator infrastructure.
#
# It assumes an empty brand new project and may not work if there's already something.
# In case you have an existing project, you would probably want to just pick and run
# the relevant commands by hand.
#
# Be careful and good luck. (c)

set -e


if [ "$1" != "--confirm" ]; then
  echo "For your safety, this script requires confirmation."
  echo "You surely don't want to accidentally run it."
  echo ""
  echo "This script must be used carefully. Please make sure you understand what it does."
  echo "And make sure you've edited the environment variables inside, appropriately."
  echo "If you're sure and  want to proceed, use \"--confirm\" argument to proceed."
  echo ""
  exit 1
fi

# Initialize environment variables that are defined in .env file
echo "[*] Initializing environment variables from '.env'..."
export $(grep -v '^#' .env | xargs)

echo "[*] Enabling Google API Services..."
gcloud services enable --project "$GCP_PROJECT" \
  compute.googleapis.com \
  pubsub.googleapis.com \
  cloudiot.googleapis.com

# Create a PubSub topics
echo "[*] Creating PubSub topics..."
gcloud pubsub topics create \
  "$GCP_DEVICE_EVENT_TOPIC" \
  "$GCP_DEVICE_STATE_TOPIC"

# Create a Iot Device Registry
echo "[*] Creating IoT registry..."
gcloud beta iot registries create "$GCP_IOT_REGISTRY_NAME" \
  --project="$GCP_PROJECT" \
  --region="$GCP_REGION" \
  --no-enable-http-config \
  --enable-mqtt-config \
  --state-pubsub-topic="$GCP_DEVICE_STATE_TOPIC"\
  --event-notification-config=topic="$GCP_DEVICE_EVENT_TOPIC"

# Create VM instance that will simulate IoT device behavior
echo "[*] Creating VM instance '$GCP_VM_SIMULATOR_NAME'..."
gcloud beta compute --project="$GCP_PROJECT" instances create "$GCP_VM_SIMULATOR_NAME" \
  --zone="$GCP_ZONE" \
  --machine-type=f1-micro \
  --subnet=default \
  --network-tier=PREMIUM \
  --boot-disk-size=10GB \
  --boot-disk-type=pd-standard \
  --boot-disk-device-name="$GCP_GCP_VM_SIMULATOR_NAME"

IP=$(gcloud compute instances list | awk '/'$GCP_VM_SIMULATOR_NAME'/ {print $5}')
echo "[*] Waiting '$GCP_VM_SIMULATOR_NAME' to launch on port 22... May take a while"
while ! nc -zv "$IP" 22; do sleep 1; done

echo "[*] Preparing '$GCP_VM_SIMULATOR_NAME' instance..."
gcloud compute scp cloud_iot_mqtt.py iot-simulator-vm:~/
gcloud compute scp requirements.txt iot-simulator-vm:~/
gcloud compute ssh "$GCP_VM_SIMULATOR_NAME" --zone="$GCP_ZONE" \
  --command="sudo apt-get update \
   && sudo apt-get -y install python3-pip \
   && sudo pip3 install -r requirements.txt \
   && openssl req -x509 -newkey rsa:2048 -keyout ~/.ssh/rsa_private.pem -nodes -out ~/.ssh/rsa_cert.pem -subj '/CN=unused' \
   && curl https://pki.goog/roots.pem > ~/.ssh/roots.pem"

echo "...Completed..."