import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

from .bootstrap import load_profiles

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")
PROFILES_PATH = Path(os.getenv("PROFILES_PATH", "sensor_profiles.pkl"))
MIN_INTERVAL_MS = float(os.getenv("MIN_INTERVAL_MS", "30"))
MAX_INTERVAL_MS = float(os.getenv("MAX_INTERVAL_MS", "300"))


def _generate_reading(profile: dict) -> dict:
    values = {}
    for value_type, params in profile["value_ranges"].items():
        val = random.gauss(params["mean"], params["std"])
        values[value_type] = round(max(0.0, val), 2)

    return {
        "reading_id": str(uuid.uuid4()),
        "sensor_id": profile["id"],
        "sensor_type": profile["sensor_type"],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "latitude": profile["latitude"],
        "longitude": profile["longitude"],
        "country": profile["country"],
        "values": values,
    }


async def _sensor_task(profile: dict, client: mqtt.Client):
    topic = f"{MQTT_TOPIC_PREFIX}/{profile['id']}/data"
    while True:
        interval_s = random.uniform(MIN_INTERVAL_MS, MAX_INTERVAL_MS) / 1000.0
        await asyncio.sleep(interval_s)
        reading = _generate_reading(profile)
        client.publish(topic, json.dumps(reading), qos=1)


def run():
    profiles = load_profiles(PROFILES_PATH)
    logger.info("Loaded %d sensor profiles", len(profiles))

    client = mqtt.Client(client_id="sensor-simulator")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    async def _main():
        tasks = [_sensor_task(p, client) for p in profiles]
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_main())
    finally:
        client.loop_stop()
        client.disconnect()
