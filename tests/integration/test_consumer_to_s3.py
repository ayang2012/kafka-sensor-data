"""
Integration test: _flush() writes Parquet to S3 (LocalStack).
Tests the flush function directly rather than requiring a running consumer process.
Requires LocalStack on port 4566.
"""
import io
import json
import os
import socket
import uuid

import boto3
import pyarrow.parquet as pq
import pytest

from sensor_pipeline.consumer import _flush

S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_PREFIX = os.getenv("S3_PREFIX", "sensor-readings")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:4566")


def _localstack_available() -> bool:
    try:
        with socket.create_connection(("localhost", 4566), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def s3():
    if not _localstack_available():
        pytest.skip("LocalStack not available")
    client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    try:
        client.create_bucket(Bucket=S3_BUCKET)
    except Exception:
        pass  # bucket may already exist
    return client


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
    def test_flush_writes_parquet_to_s3(self, s3):
        readings = [_make_reading(i) for i in range(10)]
        count = _flush(readings, s3)

        assert count == 10
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
        assert keys, "No Parquet files found in S3"

    def test_parquet_schema_is_correct(self, s3):
        readings = [_make_reading(i) for i in range(5)]
        _flush(readings, s3)

        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        keys = sorted([o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")])
        obj = s3.get_object(Bucket=S3_BUCKET, Key=keys[-1])
        table = pq.read_table(io.BytesIO(obj["Body"].read()))

        required = {"reading_id", "sensor_id", "ingested_at", "latitude", "longitude", "country", "values"}
        assert required.issubset(set(table.schema.names))

    def test_reading_ids_unique_within_file(self, s3):
        readings = [_make_reading(i) for i in range(10)]
        _flush(readings, s3)

        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        keys = sorted([o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")])
        obj = s3.get_object(Bucket=S3_BUCKET, Key=keys[-1])
        table = pq.read_table(io.BytesIO(obj["Body"].read()))

        ids = table.column("reading_id").to_pylist()
        assert len(ids) == len(set(ids)), "Duplicate reading_ids in Parquet file"

    def test_deduplicates_within_batch(self, s3):
        rid = str(uuid.uuid4())
        readings = [
            {**_make_reading(1), "reading_id": rid},
            {**_make_reading(2), "reading_id": rid},  # duplicate
        ]
        count = _flush(readings, s3)
        assert count == 1, "Duplicate reading_id should be dropped"

    def test_s3_key_has_hive_partitioning(self, s3):
        _flush([_make_reading(1)], s3)
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
        for key in keys:
            assert "year=" in key
            assert "month=" in key
            assert "day=" in key
            assert "hour=" in key

    def test_empty_buffer_writes_nothing(self, s3):
        resp_before = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        count_before = len(resp_before.get("Contents", []))

        count = _flush([], s3)

        resp_after = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        assert count == 0
        assert len(resp_after.get("Contents", [])) == count_before
