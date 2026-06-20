"""
Integration test: Kafka messages → consumer → assert Parquet lands in S3 (LocalStack).
Requires Kafka and LocalStack running.
"""
import io
import json
import os
import socket
import time
import uuid
import threading
import pytest
import boto3
import pyarrow.parquet as pq
from confluent_kafka import Producer

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:4566")
S3_PREFIX = os.getenv("S3_PREFIX", "sensor-readings")
TIMEOUT = 90  # consumer flushes every 60s


def _available(host, port) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def s3():
    if not _available("localhost", 4566):
        pytest.skip("LocalStack not available")
    client = boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name="us-east-1",
                          aws_access_key_id="test", aws_secret_access_key="test")
    try:
        client.create_bucket(Bucket=S3_BUCKET)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    return client


@pytest.fixture(scope="module")
def kafka_producer():
    if not _available("localhost", 9092):
        pytest.skip("Kafka not available")
    p = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    yield p
    p.flush()


def _make_reading(sensor_id: int = 1) -> dict:
    return {
        "reading_id": str(uuid.uuid4()),
        "sensor_id": sensor_id,
        "sensor_type": "SDS011",
        "ingested_at": "2026-06-20T10:00:00+00:00",
        "latitude": 48.137,
        "longitude": 11.575,
        "country": "DE",
        "values": {"P1": 12.5, "P2": 8.3},
    }


class TestConsumerToS3:
    def test_parquet_file_lands_in_s3(self, s3, kafka_producer):
        batch_id = str(uuid.uuid4())[:8]
        readings = [_make_reading(i) for i in range(10)]
        for r in readings:
            kafka_producer.produce(KAFKA_TOPIC, key=str(r["sensor_id"]).encode(),
                                   value=json.dumps(r).encode())
        kafka_producer.flush()

        # wait for consumer to flush
        deadline = time.time() + TIMEOUT
        found_keys = []
        while time.time() < deadline:
            resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
            found_keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
            if found_keys:
                break
            time.sleep(5)

        assert found_keys, "No Parquet files found in S3 within timeout"

    def test_parquet_schema_is_correct(self, s3, kafka_producer):
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
        if not keys:
            pytest.skip("No Parquet files in S3 yet")

        obj = s3.get_object(Bucket=S3_BUCKET, Key=keys[0])
        table = pq.read_table(io.BytesIO(obj["Body"].read()))
        columns = set(table.schema.names)

        required = {"reading_id", "sensor_id", "ingested_at", "latitude", "longitude", "country", "values"}
        assert required.issubset(columns)

    def test_reading_ids_are_unique_within_file(self, s3, kafka_producer):
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
        if not keys:
            pytest.skip("No Parquet files in S3 yet")

        obj = s3.get_object(Bucket=S3_BUCKET, Key=keys[0])
        table = pq.read_table(io.BytesIO(obj["Body"].read()))
        ids = table.column("reading_id").to_pylist()
        assert len(ids) == len(set(ids)), "Duplicate reading_ids found in Parquet file"
