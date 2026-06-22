import io
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

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
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL")
FLUSH_INTERVAL_S = int(os.getenv("FLUSH_INTERVAL_SECONDS", "60"))
FLUSH_BATCH_SIZE = int(os.getenv("FLUSH_BATCH_SIZE", "500"))
SUCCESS_BACKFILL_LOOKBACK_HOURS = int(os.getenv("SUCCESS_BACKFILL_LOOKBACK_HOURS", "48"))

SCHEMA = pa.schema([
    pa.field("reading_id", pa.string()),
    pa.field("sensor_id", pa.int64()),
    pa.field("sensor_type", pa.string()),
    pa.field("ingested_at", pa.string()),
    pa.field("latitude", pa.float64()),
    pa.field("longitude", pa.float64()),
    pa.field("country", pa.string()),
    pa.field("values", pa.string()),
])


def _s3_client():
    kwargs = {}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
    return boto3.client("s3", **kwargs)


def _partition_prefix(dt: datetime) -> str:
    return (
        f"{S3_PREFIX}/"
        f"year={dt.year}/month={dt.month:02d}/"
        f"day={dt.day:02d}/hour={dt.hour:02d}"
    )


def _write_success_marker(dt: datetime, s3) -> None:
    """Write _SUCCESS sentinel to signal that the hour partition is complete."""
    key = f"{_partition_prefix(dt)}/_SUCCESS"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=dt.isoformat().encode())
    logger.info("Wrote _SUCCESS marker → s3://%s/%s", S3_BUCKET, key)


def backfill_missing_success_markers(s3, lookback_hours: int = SUCCESS_BACKFILL_LOOKBACK_HOURS) -> None:
    """
    The consumer's hour-rollover detection only fires while a process is
    alive to observe the transition. A restart that crosses an hour
    boundary (e.g. a crash + relaunch mid-hour-change) permanently skips
    that boundary's _SUCCESS marker unless something backfills it.

    On startup, scan the last `lookback_hours` of past (fully-closed) hour
    partitions for ones that have data but no marker, and write it. The
    current wall-clock hour is never touched here — it's still open and
    will get its own marker naturally on the next rollover.
    """
    now = datetime.now(timezone.utc)
    for i in range(1, lookback_hours + 1):
        hour_dt = now - timedelta(hours=i)
        prefix = _partition_prefix(hour_dt)

        success_check = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{prefix}/_SUCCESS", MaxKeys=1)
        if success_check.get("KeyCount", 0) > 0:
            continue  # marker already exists

        data_check = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{prefix}/", MaxKeys=1)
        if data_check.get("KeyCount", 0) == 0:
            continue  # no data landed for this hour at all — nothing to mark

        logger.warning(
            "Backfilling missing _SUCCESS marker for closed partition %s "
            "(found data but no completion marker, likely from a restart "
            "that crossed an hour boundary)", prefix,
        )
        _write_success_marker(hour_dt, s3)


def _flush(buffer: list[dict], s3, flush_hour: datetime | None = None) -> int:
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

    now = flush_hour or datetime.now(timezone.utc)
    key = f"{_partition_prefix(now)}/{uuid.uuid4()}.parquet"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=buf.getvalue())
    logger.info("Flushed %d rows → s3://%s/%s", len(rows), S3_BUCKET, key)
    return len(rows)


def run():
    s3 = _s3_client()
    backfill_missing_success_markers(s3)

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
    current_hour = datetime.now(timezone.utc).hour

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is not None:
                if msg.error():
                    raise KafkaException(msg.error())
                record = json.loads(msg.value().decode())
                buffer.append(record)

            now = datetime.now(timezone.utc)
            hour_rolled = now.hour != current_hour

            should_flush = (
                len(buffer) >= FLUSH_BATCH_SIZE
                or (buffer and time.time() - last_flush >= FLUSH_INTERVAL_S)
                or (buffer and hour_rolled)
            )

            if should_flush:
                # flush buffer into the hour it was collected in
                flush_dt = now.replace(hour=current_hour) if hour_rolled else now
                _flush(buffer, s3, flush_hour=flush_dt)
                buffer = []
                last_flush = time.time()

                if hour_rolled:
                    # previous hour is complete — write sentinel for Airflow sensor
                    closing_hour = now.replace(hour=current_hour)
                    _write_success_marker(closing_hour, s3)
                    current_hour = now.hour

    finally:
        if buffer:
            _flush(buffer, s3)
        consumer.close()
