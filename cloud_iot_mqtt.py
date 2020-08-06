"""
To connect the device you must have downloaded Google's CA root certificates,
and a copy of your private key file. Run this script with the corresponding
algorithm flag.

  $ python cloud_iot_mqtt.py \
      --project_id=my-project-id \
      --registry_id=example-my-registry-id \
      --device_id=my-device-id \
      --private_key_file=rsa_private.pem \
      --algorithm=RS256

With a single server, you can run multiple instances of the device with
different device ids, and the server will distinguish them. Try creating a few
devices and running them all at the same time.
"""

import argparse
import datetime
import json
import os
import ssl
import threading
import time

import jwt
import paho.mqtt.client as mqtt


def create_jwt(project_id, private_key_file, algorithm):
    """
    Creates a JWT to establish an MQTT connection.
    """

    token = {
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
        "aud": project_id
    }
    with open(private_key_file, "r") as f:
        private_key = f.read()
    print(f"Creating JWT using '{algorithm}' "
          f"from private key file '{private_key_file}'")
    return jwt.encode(token, private_key, algorithm=algorithm)


def error_str(rc):
    """
    Converts a Paho error to a human readable string.
    """
    return f"{rc}: {mqtt.error_string(rc)}"


class Device:
    """
    Represents the state of a single device.
    """

    def __init__(self):
        self.connected_event = threading.Event()

    def wait_for_connection(self, timeout):
        """
        Wait for the device to become connected.
        """
        while not self.connected_event.wait(timeout):
            raise RuntimeError("Could not connect to MQTT bridge.")

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        """
        Callback for when a device connects.
        """
        if rc != 0:
            print("Error connecting:", error_str(rc))
        else:
            print("Connected successfully.")
        self.connected_event.set()

    def on_disconnect(self, unused_client, unused_userdata, rc):
        """
        Callback for when a device disconnects.
        """
        print("Disconnected:", error_str(rc))
        self.connected_event.clear()

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        """
        Callback when the device receives a PUBACK from the MQTT bridge.
        """
        print('Published message acked.')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid, granted_qos):  # noqa
        """
        Callback when the device receives a SUBACK from the MQTT bridge.
        """
        print("Subscribed: ", granted_qos)
        if granted_qos[0] == 128:
            print("Subscription failed.")

    def on_message(self, unused_client, unused_userdata, message):
        """
        Callback when the device receives a message on a subscription.
        """
        payload = message.payload.decode("utf-8")
        print(
            f"Received message '{payload}' on topic '{message.topic}' "
            f"with Qos {str(message.qos)}."
        )

        # The device will receive its latest config when it subscribes to the
        # config topic. If there is no configuration for the device, the device
        # will receive a config with an empty payload.
        if not payload:
            print("No payload provided.")
            return

        # The config is passed in the payload of the message.
        data = json.loads(payload)
        print(f"Received new config. {data}")


def parse_command_line_args():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Fake Google Cloud IoT MQTT device."
    )
    parser.add_argument(
        "--project_id",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        required=True,
        help="GCP cloud project name."
    )
    parser.add_argument(
        "--registry_id",
        required=True,
        help="Cloud IoT registry ID."
    )
    parser.add_argument(
        "--device_id",
        required=True,
        help="Cloud IoT device id"
    )
    parser.add_argument(
        "--private_key_file",
        required=True,
        help="Path to private key file."
    )
    parser.add_argument(
        "--algorithm",
        choices=("RS256", "ES256"),
        default="RS256",
        help="Encryption algorithm to generate the JWT. Defaults to RS256."
    )
    parser.add_argument(
        "--cloud_region",
        default="us-central1",
        help="GCP Cloud Region"
    )
    parser.add_argument(
        "--ca_certs",
        default="roots.pem",
        help="CA root certificate. Get from https://pki.google.com/roots.pem"
    )
    parser.add_argument(
        "--num_messages",
        type=int,
        default=20,
        help="Number of messages to publish.")
    parser.add_argument(
        "--mqtt_bridge_hostname",
        default="mqtt.googleapis.com",
        help="MQTT bridge hostname."
    )
    parser.add_argument(
        "--mqtt_bridge_port",
        type=int,
        default=8883,
        help="MQTT bridge port."
    )
    parser.add_argument(
        "--message_type", choices=("event", "state"),
        default="event",
        help=("Indicates whether the message to be published is a "
              "telemetry event or a device state message.")
    )

    return parser.parse_args()


def main():
    args = parse_command_line_args()

    # Create the MQTT client and connect to Cloud IoT.
    client_id = (f"projects/{args.project_id}/"
                 f"locations/{args.cloud_region}/"
                 f"registries/{args.registry_id}/"
                 f"devices/{args.device_id}")
    client = mqtt.Client(client_id=client_id)
    pwd = create_jwt(args.project_id, args.private_key_file, args.algorithm)
    client.username_pw_set(username="unused", password=pwd)
    client.tls_set(ca_certs=args.ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)

    device = Device()

    client.on_connect = device.on_connect
    client.on_publish = device.on_publish
    client.on_disconnect = device.on_disconnect
    client.on_subscribe = device.on_subscribe
    client.on_message = device.on_message

    client.connect(args.mqtt_bridge_hostname, args.mqtt_bridge_port)

    client.loop_start()

    # This is the topic that the device will publish telemetry events
    # (temperature data) to.
    mqtt_telemetry_topic = f"/devices/{args.device_id}/events"

    # This is the topic that the device will receive configuration updates on.
    mqtt_config_topic = f"/devices/{args.device_id}/config"

    # Wait up to 5 seconds for the device to connect.
    device.wait_for_connection(5)

    # Subscribe to the config topic.
    client.subscribe(mqtt_config_topic, qos=1)

    # Update and publish telemetry readings at a rate of one per second.
    for i in range(1, args.num_messages + 1):
        payload = f"{args.registry_id}/{args.device_id}-payload-{i}"
        print(f"Publishing message '{i}' '{args.num_messages}': '{payload}'")
        client.publish(mqtt_telemetry_topic, payload, qos=1)
        # Send events every second.
        time.sleep(1)

    client.disconnect()
    client.loop_stop()
    print("Finished loop successfully. Goodbye!")


if __name__ == "__main__":
    main()
