"""
Integration test: publish a message to Mosquitto and assert it arrives.
Requires MQTT_HOST and MQTT_PORT env vars (set by docker-compose or testcontainers).
Skip if broker not available.
"""
import json
import os
import threading
import time
import pytest
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TIMEOUT = 5  # seconds


def _broker_available() -> bool:
    import socket
    try:
        with socket.create_connection((MQTT_HOST, MQTT_PORT), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def mqtt_client():
    if not _broker_available():
        pytest.skip("MQTT broker not available")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test-client")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
    client.loop_start()
    yield client
    client.loop_stop()
    client.disconnect()


class TestMQTTBroker:
    def test_message_arrives_within_timeout(self, mqtt_client):
        received = threading.Event()
        payloads = []

        def on_message(client, userdata, msg):
            payloads.append(json.loads(msg.payload.decode()))
            received.set()

        mqtt_client.subscribe("test/integration/+", qos=1)
        mqtt_client.on_message = on_message

        payload = {"reading_id": "test-123", "sensor_id": 1}
        mqtt_client.publish("test/integration/1", json.dumps(payload), qos=1)

        assert received.wait(timeout=TIMEOUT), "Message not received within timeout"
        assert payloads[0]["reading_id"] == "test-123"

    def test_wildcard_subscription_receives_multiple_sensors(self, mqtt_client):
        received = []
        done = threading.Event()

        def on_message(client, userdata, msg):
            received.append(json.loads(msg.payload.decode()))
            if len(received) >= 3:
                done.set()

        mqtt_client.subscribe("test/multi/+", qos=1)
        mqtt_client.on_message = on_message

        for i in range(3):
            mqtt_client.publish(f"test/multi/{i}", json.dumps({"sensor_id": i}), qos=1)

        assert done.wait(timeout=TIMEOUT), "Did not receive all 3 messages"
        assert len(received) == 3
