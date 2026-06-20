# kafka-sensor-data

A simulated IoT data pipeline that ingests air quality sensor readings from [Sensor.Community](https://sensor.community/) and streams them through MQTT → Kafka → S3 (Parquet), forming a bronze datalakehouse layer.

## Architecture

```
[bootstrap.py]
     │  fetches snapshot once from Sensor.Community API
     │  seeds 1,000 sensor profiles → sensor_profiles.pkl
     ▼
[simulator.py]
     │  1,000 async tasks, each emitting a reading every 30–300ms
     │  generates realistic values (PM2.5, PM10, temp, humidity ± noise)
     │  stamps every message with reading_id (UUID) + ingested_at
     ▼  MQTT publish  sensors/{sensor_id}/data
[Mosquitto MQTT Broker]        ← IoT Gateway
     ▼  MQTT subscribe
[producer.py]
     │  forwards every MQTT message to Kafka (idempotent producer)
     ▼  Kafka produce  sensor-readings topic
[Kafka]
     ▼  Kafka consume
[consumer.py]
     │  buffers messages, flushes every 60s or 500 messages
     │  deduplicates on reading_id within each batch
     ▼  Parquet (Snappy) → S3
[S3 Bronze Layer]
     sensor-readings/year=YYYY/month=MM/day=DD/hour=HH/<uuid>.parquet
```

## Quickstart

### 1. Set up the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if needed (defaults point to LocalStack for S3)
```

### 3. Start infrastructure

```bash
docker-compose up -d zookeeper kafka mosquitto localstack
docker-compose ps   # wait for kafka to show Up (healthy)
```

### 4. Create the S3 bucket (LocalStack)

```bash
aws --endpoint-url=http://localhost:4566 s3 mb s3://sensor-readings-bronze \
  --region us-east-1 --no-cli-pager
```

### 5. Seed sensor profiles (run once)

```bash
python -m sensor_pipeline bootstrap
```

This fetches a snapshot from Sensor.Community and pickles 1,000 sensor profiles to `sensor_profiles.pkl`.

### 6. Start the pipeline

```bash
python -m sensor_pipeline simulate &   # emit sensor readings via MQTT
python -m sensor_pipeline produce &    # forward MQTT → Kafka
python -m sensor_pipeline consume &    # write Kafka → S3 Parquet
```

### 7. Verify data is landing in S3

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://sensor-readings-bronze/sensor-readings/ \
  --recursive --no-cli-pager
```

## Running tests

### Unit tests (no Docker required)

```bash
pip install -r requirements-dev.txt
pytest tests/unit/ -v
```

### Integration tests (requires infrastructure running)

Start docker-compose and the bridge first (steps 3–5 above), then:

```bash
python -m sensor_pipeline produce &
pytest tests/integration/ --integration -v
```

### Data quality checks (requires Parquet files in S3)

```bash
pytest tests/quality/ -v
```

## Project structure

```
kafka-sensor-data/
├── sensor_pipeline/
│   ├── bootstrap.py     # fetch Sensor.Community snapshot, seed profiles
│   ├── simulator.py     # async IoT device simulator (MQTT publisher)
│   ├── producer.py      # MQTT → Kafka producer
│   ├── consumer.py      # Kafka → S3 Parquet writer
│   └── fetch.py         # Sensor.Community API client
├── tests/
│   ├── unit/            # fully mocked, no external services
│   ├── integration/     # real Kafka + MQTT + LocalStack (--integration flag)
│   └── quality/         # pandera schema checks on bronze Parquet files
├── mosquitto/
│   └── mosquitto.conf   # MQTT broker config
├── docker-compose.yml   # Zookeeper, Kafka, Mosquitto, LocalStack
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## Data model

Each Kafka message and Parquet row represents one sensor reading:

| Field | Type | Description |
|---|---|---|
| `reading_id` | string (UUID) | Unique per emission — used for dedup |
| `sensor_id` | int | Sensor.Community sensor ID |
| `sensor_type` | string | e.g. `SDS011`, `DHT22` |
| `ingested_at` | string (ISO 8601) | Timestamp of emission |
| `latitude` | float | Sensor location |
| `longitude` | float | Sensor location |
| `country` | string | ISO country code |
| `values` | string (JSON) | e.g. `{"P1": 12.5, "P2": 8.3}` |

S3 files are Hive-partitioned by `year/month/day/hour` for efficient querying with Athena or Snowflake external tables.

## CI

GitHub Actions runs unit tests on every push and integration tests on PRs. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
