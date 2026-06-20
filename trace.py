"""
Live three-column pipeline tracer.

Usage:
    python trace.py

Requires services running (docker-compose up -d zookeeper kafka mosquitto localstack)
and the producer running (python -m sensor_pipeline produce &).
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

import boto3
import paho.mqtt.client as mqtt
from confluent_kafka import Consumer, KafkaException
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
KAFKA_GROUP = "tracer-" + str(int(time.time()))
S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL")
REFRESH_HZ = 4
MAX_ROWS = 28


console = Console()

mqtt_rows: list[Text] = []
kafka_rows: list[Text] = []
s3_rows: list[Text] = []
counts = {"mqtt": 0, "kafka": 0, "s3_files": 0, "s3_rows": 0}
lock = threading.Lock()
known_s3_keys: set[str] = set()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _append(rows: list, text: Text):
    rows.append(text)
    if len(rows) > MAX_ROWS:
        rows.pop(0)


def _short_id(rid: str) -> str:
    return rid[:8] if rid else "?"


def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return
    rid = _short_id(payload.get("reading_id", ""))
    sid = payload.get("sensor_id", "?")
    vals = payload.get("values", {})
    val_str = "  ".join(f"{k}={v}" for k, v in list(vals.items())[:2])

    t = Text()
    t.append(f"{_ts()} ", style="dim")
    t.append(f"id={rid}  ", style="bold green")
    t.append(f"sensor={sid}\n", style="green")
    t.append(f"  {val_str}", style="dim green")

    with lock:
        _append(mqtt_rows, t)
        counts["mqtt"] += 1


def run_mqtt_watcher():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tracer-mqtt")
    client.on_message = on_mqtt_message
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/data", qos=0)
        client.loop_forever()
    except Exception as e:
        with lock:
            t = Text(f"MQTT error: {e}", style="red")
            _append(mqtt_rows, t)


def run_kafka_watcher():
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": KAFKA_GROUP,
        "auto.offset.reset": "latest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([KAFKA_TOPIC])
    try:
        while True:
            msg = consumer.poll(timeout=0.5)
            if msg is None:
                continue
            if msg.error():
                continue
            try:
                payload = json.loads(msg.value().decode())
            except Exception:
                continue
            rid = _short_id(payload.get("reading_id", ""))
            sid = payload.get("sensor_id", "?")
            offset = msg.offset()

            t = Text()
            t.append(f"{_ts()} ", style="dim")
            t.append(f"id={rid}  ", style="bold blue")
            t.append(f"key={sid}\n", style="blue")
            t.append(f"  offset={offset}", style="dim blue")

            with lock:
                _append(kafka_rows, t)
                counts["kafka"] += 1
    except Exception as e:
        with lock:
            t = Text(f"Kafka error: {e}", style="red")
            _append(kafka_rows, t)
    finally:
        consumer.close()


def run_s3_watcher():
    kwargs = {}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    s3 = boto3.client("s3", region_name="us-east-1", **kwargs)

    while True:
        try:
            resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="sensor-readings/")
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".parquet") or key in known_s3_keys:
                    continue
                known_s3_keys.add(key)
                size_kb = round(obj["Size"] / 1024, 1)
                short_key = "/".join(key.split("/")[-5:])

                t = Text()
                t.append(f"{_ts()} ", style="dim")
                t.append(f"new file\n", style="bold yellow")
                t.append(f"  {short_key}\n", style="yellow")
                t.append(f"  {size_kb} KB", style="dim yellow")

                with lock:
                    _append(s3_rows, t)
                    counts["s3_files"] += 1
        except Exception as e:
            with lock:
                t = Text(f"S3 error: {e}", style="red")
                _append(s3_rows, t)
        time.sleep(5)


def build_layout() -> Columns:
    with lock:
        mqtt_text = Text("\n").join(mqtt_rows) if mqtt_rows else Text("waiting...", style="dim")
        kafka_text = Text("\n").join(kafka_rows) if kafka_rows else Text("waiting...", style="dim")
        s3_text = Text("\n").join(s3_rows) if s3_rows else Text("waiting for flush...", style="dim")
        c = counts.copy()

    mqtt_panel = Panel(
        mqtt_text,
        title=f"[bold green]MQTT[/]  [dim]{c['mqtt']} msgs[/]",
        subtitle="[dim]sensors/+/data[/]",
        border_style="green",
    )
    kafka_panel = Panel(
        kafka_text,
        title=f"[bold blue]Kafka[/]  [dim]{c['kafka']} msgs[/]",
        subtitle="[dim]sensor-readings[/]",
        border_style="blue",
    )
    s3_panel = Panel(
        s3_text,
        title=f"[bold yellow]S3[/]  [dim]{c['s3_files']} files[/]",
        subtitle="[dim]bronze / parquet[/]",
        border_style="yellow",
    )
    return Columns([mqtt_panel, kafka_panel, s3_panel], equal=True, expand=True)


def main():
    for target in (run_mqtt_watcher, run_kafka_watcher, run_s3_watcher):
        t = threading.Thread(target=target, daemon=True)
        t.start()

    console.print("[bold]Pipeline event tracer[/]  [dim]ctrl+c to stop[/]\n")

    with Live(build_layout(), console=console, refresh_per_second=REFRESH_HZ) as live:
        try:
            while True:
                time.sleep(1 / REFRESH_HZ)
                live.update(build_layout())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
