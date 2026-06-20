"""
Bronze layer data quality checks.
Run against real S3 (or LocalStack) Parquet files after pipeline has produced data.

Usage:
    S3_ENDPOINT_URL=http://localhost:4566 pytest tests/quality/ -v
"""
import io
import json
import os
from datetime import datetime, timezone

import boto3
import pandas as pd
import pandera as pa
import pandera.extensions as extensions
import pyarrow.parquet as pq
import pytest

S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_PREFIX = os.getenv("S3_PREFIX", "sensor-readings")
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL")

BRONZE_SCHEMA = pa.DataFrameSchema(
    columns={
        "reading_id": pa.Column(str, nullable=False, unique=True),
        "sensor_id": pa.Column(int, nullable=False, checks=pa.Check.greater_than(0)),
        "sensor_type": pa.Column(str, nullable=False),
        "ingested_at": pa.Column(str, nullable=False),
        "latitude": pa.Column(
            float,
            nullable=False,
            checks=pa.Check.in_range(-90.0, 90.0),
        ),
        "longitude": pa.Column(
            float,
            nullable=False,
            checks=pa.Check.in_range(-180.0, 180.0),
        ),
        "country": pa.Column(str, nullable=False),
        "values": pa.Column(str, nullable=False),
    },
    strict=False,  # allow extra columns
)


def _s3_client():
    kwargs = {"region_name": "us-east-1"}
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"
    return boto3.client("s3", **kwargs)


@pytest.fixture(scope="module")
def bronze_df():
    s3 = _s3_client()
    try:
        resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    except Exception:
        pytest.skip("S3 bucket not accessible")

    keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
    if not keys:
        pytest.skip("No Parquet files found in bronze layer")

    frames = []
    for key in keys[:10]:  # sample up to 10 files
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        table = pq.read_table(io.BytesIO(obj["Body"].read()))
        frames.append(table.to_pandas())

    return pd.concat(frames, ignore_index=True)


class TestBronzeSchema:
    def test_schema_validates(self, bronze_df):
        BRONZE_SCHEMA.validate(bronze_df)

    def test_reading_id_globally_unique(self, bronze_df):
        dupes = bronze_df["reading_id"].duplicated().sum()
        assert dupes == 0, f"{dupes} duplicate reading_ids found across sampled files"

    def test_no_null_reading_ids(self, bronze_df):
        assert bronze_df["reading_id"].isna().sum() == 0

    def test_no_null_sensor_ids(self, bronze_df):
        assert bronze_df["sensor_id"].isna().sum() == 0

    def test_no_null_ingested_at(self, bronze_df):
        assert bronze_df["ingested_at"].isna().sum() == 0

    def test_ingested_at_no_future_timestamps(self, bronze_df):
        now = datetime.now(timezone.utc).isoformat()
        future = bronze_df[bronze_df["ingested_at"] > now]
        assert len(future) == 0, f"{len(future)} rows have future ingested_at timestamps"

    def test_lat_in_bounds(self, bronze_df):
        out = bronze_df[(bronze_df["latitude"] < -90) | (bronze_df["latitude"] > 90)]
        assert len(out) == 0, f"{len(out)} rows have out-of-bounds latitude"

    def test_lon_in_bounds(self, bronze_df):
        out = bronze_df[(bronze_df["longitude"] < -180) | (bronze_df["longitude"] > 180)]
        assert len(out) == 0, f"{len(out)} rows have out-of-bounds longitude"

    def test_values_is_valid_json(self, bronze_df):
        invalid = []
        for i, v in enumerate(bronze_df["values"]):
            try:
                json.loads(v)
            except (json.JSONDecodeError, TypeError):
                invalid.append(i)
        assert not invalid, f"{len(invalid)} rows have invalid JSON in 'values' column"

    def test_values_not_empty(self, bronze_df):
        empty = bronze_df["values"].apply(lambda v: json.loads(v) == {})
        assert empty.sum() == 0, f"{empty.sum()} rows have empty values dict"

    def test_s3_partitioning_by_date(self):
        """Assert files are partitioned by year/month/day/hour in S3 key path."""
        s3 = _s3_client()
        try:
            resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        except Exception:
            pytest.skip("S3 not accessible")

        keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".parquet")]
        if not keys:
            pytest.skip("No Parquet files found")

        for key in keys:
            assert "year=" in key, f"Key missing year partition: {key}"
            assert "month=" in key, f"Key missing month partition: {key}"
            assert "day=" in key, f"Key missing day partition: {key}"
            assert "hour=" in key, f"Key missing hour partition: {key}"
