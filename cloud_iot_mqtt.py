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
import logging
import os
import random
import ssl
import time

from dataclasses import dataclass
from contextlib import contextmanager
from random import randint

import jwt
import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


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
    logger.debug(f"Creating JWT using '{algorithm}' "
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

    # The maximum backoff time before giving up, in seconds.
    MAX_BACKOFF_TIME = 32

    def __init__(self, project_id, cloud_region, registry_id, device_id):
        # params that form client_id
        self._project_id = project_id
        self._cloud_region = cloud_region
        self._registry_id = registry_id
        self._device_id = device_id

        self._client = mqtt.Client(client_id=self.client_id)

        self._client.on_connect = self.on_connect
        self._client.on_publish = self.on_publish
        self._client.on_disconnect = self.on_disconnect
        self._client.on_subscribe = self.on_subscribe
        self._client.on_message = self.on_message
        # Whether to wait with exponential backoff before publishing.
        self._should_backoff = True
        # The initial backoff time after a disconnection occurs, in seconds.
        self._min_backoff_time = 1

    @classmethod
    def create_from_client_id(cls, client_id):
        """
        Creates a Device from client_id string.

        :param client_id: client_id as a string.
        """
        return cls(*client_id.split("/")[1::2])

    @property
    def client_id(self):
        return (
            f"projects/{self._project_id}/"
            f"locations/{self._cloud_region}/"
            f"registries/{self._registry_id}/"
            f"devices/{self._device_id}"
        )

    @property
    def project_id(self):
        return self._project_id

    @property
    def cloud_region(self):
        return self._cloud_region

    @property
    def registry_id(self):
        return self._registry_id

    @property
    def device_id(self):
        return self._device_id

    def authenticate(self, token):
        self._client.username_pw_set(username="unused", password=token)

    def tls_set(self, ca_certs, tls_version, **kwargs):
        self._client.tls_set(
            ca_certs=ca_certs,
            tls_version=tls_version,
            **kwargs
        )

    def connect(self, mqtt_bridge_hostname, mqtt_bridge_port):
        logger.info(f"Connecting... {mqtt_bridge_hostname}:{mqtt_bridge_port}")
        if self._should_backoff:
            # If backoff time is too large, give up.
            if self._min_backoff_time > self.MAX_BACKOFF_TIME:
                logger.error(
                    f"Exceeded maximum backoff time for the device with "
                    f"ID '{self.device_id}'. Giving up."
                )
                return
            delay = self._min_backoff_time + random.randint(0, 1000) / 1000.0
            time.sleep(delay)
            self._min_backoff_time *= 2
            self._client.connect(
                host=mqtt_bridge_hostname,
                port=mqtt_bridge_port
            )

    def disconnect(self):
        self._client.disconnect()

    def publish(self, topic, payload=None, qos=0, retain=False, properties=None): # noqa
        self._client.publish(
            topic,
            payload=payload,
            qos=qos,
            retain=retain,
            properties=properties
        )

    def subscribe(self, topic, qos=0, options=None, properties=None):
        self._client.subscribe(
            topic,
            qos=qos,
            options=options,
            properties=properties
        )

    def loop_start(self):
        self._client.loop_start()

    def loop_stop(self):
        self._client.loop_stop()

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        """
        Callback for when a device connects.
        """
        logger.info(f"on_connect {mqtt.connack_string(rc)}")

        # After a successful connect, reset backoff time and stop backing off.
        self._should_backoff = False
        self._min_backoff_time = 1

    def on_disconnect(self, unused_client, unused_userdata, rc):
        """
        Callback for when a device disconnects.
        """
        logger.info(f"Disconnected: {error_str(rc)}")

        # Since a disconnect occurred, the next loop iteration will wait with
        # exponential backoff.
        self._should_backoff = True

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        """
        Callback when the device receives a PUBACK from the MQTT bridge.
        """
        logger.info('Published message acked.')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid, granted_qos):  # noqa
        """
        Callback when the device receives a SUBACK from the MQTT bridge.
        """
        logger.info(f"Subscribed: {granted_qos}")
        if granted_qos[0] == 128:
            logger.info("Subscription failed.")

    def on_message(self, unused_client, unused_userdata, message):
        """
        Callback when the device receives a message on a subscription.
        """
        payload = message.payload.decode("utf-8")
        logger.info(
            f"Received message '{payload}' on topic '{message.topic}' "
            f"with Qos {str(message.qos)}."
        )

        # The device will receive its latest config when it subscribes to the
        # config topic. If there is no configuration for the device, the device
        # will receive a config with an empty payload.
        if not payload:
            logger.info("No payload provided.")
            return

        # The config is passed in the payload of the message.
        data = json.loads(payload)
        logger.info(f"Received new config: {data}")


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
        "-v", "--verbose",
        action="store_true",
        help="increase output verbosity"
    )
    return parser.parse_args()


@dataclass
class MqttConnectionConfig:
    ca_certs: str
    tls_version: int = ssl.PROTOCOL_TLSv1_2
    mqtt_bridge_hostname: str = "mqtt.googleapis.com"
    mqtt_bridge_port: int = 8883


@contextmanager
def managed_device(
        client_id: str,
        conn_cfg: MqttConnectionConfig,
        token: str = None
):
    device = Device.create_from_client_id(client_id)
    if token:
        device.authenticate(token)
    if conn_cfg.ca_certs:
        device.tls_set(
            ca_certs=conn_cfg.ca_certs,
            tls_version=conn_cfg.tls_version
        )
    device.connect(
        conn_cfg.mqtt_bridge_hostname,
        conn_cfg.mqtt_bridge_port
    )
    device.loop_start()
    yield device
    device.disconnect()
    device.loop_stop()


def main():
    args = parse_command_line_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    client_id = (f"projects/{args.project_id}/"
                 f"locations/{args.cloud_region}/"
                 f"registries/{args.registry_id}/"
                 f"devices/{args.device_id}")
    conn_cfg = MqttConnectionConfig(
        ca_certs=args.ca_certs,
        tls_version=ssl.PROTOCOL_TLSv1_2,
        mqtt_bridge_hostname=args.mqtt_bridge_hostname,
        mqtt_bridge_port=args.mqtt_bridge_port
    )
    token = create_jwt(args.project_id, args.private_key_file, args.algorithm)

    # This is the topic that the device will publish telemetry events
    # (e.g. temperature data, power consumption etc.) to.
    mqtt_telemetry_topic = f"/devices/{args.device_id}/events"

    # This is the topic that the device will receive configuration updates on.
    mqtt_config_topic = f"/devices/{args.device_id}/config"

    # This is the topic that the device will receive commands from IoT Core.
    mqtt_commands_topic = f"/devices/{args.device_id}/commands/#"

    with managed_device(client_id, conn_cfg, token) as device:
        # Subscribe to the config topic.
        device.subscribe(mqtt_config_topic, qos=1)

        # Subscribe to the commands topic
        device.subscribe(mqtt_commands_topic, qos=1)

        # Update and publish telemetry readings.
        for i in range(1, args.num_messages + 1):
            payload = f"{device.registry_id}/{device.device_id}-payload-{i}"
            logger.info(
                f"Publishing message '{i}' '{args.num_messages}': '{payload}'"
            )
            device.publish(mqtt_telemetry_topic, payload, qos=1)
            # Send events every second.
            time.sleep(randint(1, 4))

        # This is the topic that the device will send state updates on.
        mqtt_state_topic = f"/devices/{device.device_id}/state"
        payload = "Fake state"
        logger.info(
            f"Publishing {device.device_id} state: '{payload}'"
        )
        device.publish(mqtt_state_topic, payload)

    logger.info("Finished loop successfully. Goodbye!")


if __name__ == "__main__":
    main()
