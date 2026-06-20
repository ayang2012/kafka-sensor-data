import io
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from confluent_kafka import Consumer, KafkaException

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
KAFKA_GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP", "sensor-consumer-group")
S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_PREFIX = os.getenv("S3_PREFIX", "sensor-readings")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL")  # set for LocalStack
FLUSH_INTERVAL_S = int(os.getenv("FLUSH_INTERVAL_SECONDS", "60"))
FLUSH_BATCH_SIZE = int(os.getenv("FLUSH_BATCH_SIZE", "500"))

SCHEMA = pa.schema([
    pa.field("reading_id", pa.string()),
    pa.field("sensor_id", pa.int64()),
    pa.field("sensor_type", pa.string()),
    pa.field("ingested_at", pa.string()),
    pa.field("latitude", pa.float64()),
    pa.field("longitude", pa.float64()),
    pa.field("country", pa.string()),
    pa.field("values", pa.string()),  # JSON string; cast in silver dbt model
])


def _s3_client():
    kwargs = {}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    return boto3.client("s3", **kwargs)


def _flush(buffer: list[dict], s3) -> int:
    if not buffer:
        return 0

    rows = []
    seen_ids = set()
    for record in buffer:
        rid = record.get("reading_id")
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        rows.append({
            "reading_id": rid,
            "sensor_id": int(record.get("sensor_id", 0)),
            "sensor_type": str(record.get("sensor_type", "")),
            "ingested_at": str(record.get("ingested_at", "")),
            "latitude": float(record.get("latitude", 0.0)),
            "longitude": float(record.get("longitude", 0.0)),
            "country": str(record.get("country", "")),
            "values": json.dumps(record.get("values", {})),
        })

    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)

    now = datetime.now(timezone.utc)
    key = (
        f"{S3_PREFIX}/"
        f"year={now.year}/month={now.month:02d}/"
        f"day={now.day:02d}/hour={now.hour:02d}/"
        f"{uuid.uuid4()}.parquet"
    )
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=buf.getvalue())
    logger.info("Flushed %d rows → s3://%s/%s", len(rows), S3_BUCKET, key)
    return len(rows)


def run():
    s3 = _s3_client()
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": KAFKA_GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    })
    consumer.subscribe([KAFKA_TOPIC])
    logger.info("Consumer subscribed to %s", KAFKA_TOPIC)

    buffer: list[dict] = []
    last_flush = time.time()

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is not None:
                if msg.error():
                    raise KafkaException(msg.error())
                record = json.loads(msg.value().decode())
                buffer.append(record)

            should_flush = (
                len(buffer) >= FLUSH_BATCH_SIZE
                or (buffer and time.time() - last_flush >= FLUSH_INTERVAL_S)
            )
            if should_flush:
                _flush(buffer, s3)
                buffer = []
                last_flush = time.time()
    finally:
        if buffer:
            _flush(buffer, s3)
        consumer.close()
