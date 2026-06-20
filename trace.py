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
from confluent_kafka import Consumer
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.console import Console
from rich.text import Text

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
KAFKA_GROUP = "tracer-" + str(int(time.time()))
S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL")
MAX_ROWS = 30

console = Console()

mqtt_rows: list[str] = []
kafka_rows: list[str] = []
s3_rows: list[str] = []
counts = {"mqtt": 0, "kafka": 0, "s3_files": 0}
lock = threading.Lock()
known_s3_keys: set[str] = set()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _append(rows: list, line: str):
    rows.append(line)
    if len(rows) > MAX_ROWS:
        rows.pop(0)


def _short(rid: str) -> str:
    return rid[:8] if rid else "?"


def on_mqtt_message(client, userdata, msg):
    try:
        p = json.loads(msg.payload.decode())
    except Exception:
        return
    rid = _short(p.get("reading_id", ""))
    sid = p.get("sensor_id", "?")
    vals = p.get("values", {})
    val_str = "  ".join(f"{k}={v}" for k, v in list(vals.items())[:2])
    line = f"[dim]{_ts()}[/]  [bold green]{rid}[/]\nsensor={sid}  {val_str}"
    with lock:
        _append(mqtt_rows, line)
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
            _append(mqtt_rows, f"[red]error: {e}[/]")


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
            if msg is None or msg.error():
                continue
            try:
                p = json.loads(msg.value().decode())
            except Exception:
                continue
            rid = _short(p.get("reading_id", ""))
            sid = p.get("sensor_id", "?")
            line = f"[dim]{_ts()}[/]  [bold blue]{rid}[/]\nkey={sid}  offset={msg.offset()}"
            with lock:
                _append(kafka_rows, line)
                counts["kafka"] += 1
    except Exception as e:
        with lock:
            _append(kafka_rows, f"[red]error: {e}[/]")
    finally:
        consumer.close()


def run_s3_watcher():
    kwargs = {"region_name": "us-east-1"}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    s3 = boto3.client("s3", **kwargs)

    # auto-create bucket if missing
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
    except Exception:
        try:
            s3.create_bucket(Bucket=S3_BUCKET)
        except Exception:
            pass

    while True:
        try:
            resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix="sensor-readings/")
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".parquet") or key in known_s3_keys:
                    continue
                known_s3_keys.add(key)
                size_kb = round(obj["Size"] / 1024, 1)
                short_key = "/".join(key.split("/")[-4:])
                line = f"[dim]{_ts()}[/]  [bold yellow]new file[/]\n{short_key}\n{size_kb} KB"
                with lock:
                    _append(s3_rows, line)
                    counts["s3_files"] += 1
        except Exception as e:
            with lock:
                _append(s3_rows, f"[red]error: {e}[/]")
        time.sleep(5)


def make_panel(rows: list[str], title: str, subtitle: str, border: str) -> Panel:
    body = Text.from_markup("\n\n".join(rows)) if rows else Text("waiting...", style="dim")
    return Panel(body, title=title, subtitle=subtitle, border_style=border)


def build_layout() -> Layout:
    with lock:
        mqtt_p = make_panel(
            mqtt_rows,
            f"[bold green]MQTT[/]  [dim]{counts['mqtt']} msgs[/]",
            "[dim]sensors/+/data[/]",
            "green",
        )
        kafka_p = make_panel(
            kafka_rows,
            f"[bold blue]Kafka[/]  [dim]{counts['kafka']} msgs[/]",
            "[dim]sensor-readings[/]",
            "blue",
        )
        s3_p = make_panel(
            s3_rows,
            f"[bold yellow]S3[/]  [dim]{counts['s3_files']} files[/]",
            "[dim]bronze / parquet[/]",
            "yellow",
        )

    layout = Layout()
    layout.split_row(
        Layout(mqtt_p, name="mqtt"),
        Layout(kafka_p, name="kafka"),
        Layout(s3_p, name="s3"),
    )
    return layout


def main():
    for target in (run_mqtt_watcher, run_kafka_watcher, run_s3_watcher):
        threading.Thread(target=target, daemon=True).start()

    console.print("[bold]Pipeline event tracer[/]  [dim]ctrl+c to stop[/]\n")

    with Live(build_layout(), console=console, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                time.sleep(0.25)
                live.update(build_layout())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
