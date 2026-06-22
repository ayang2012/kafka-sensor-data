# kafka-sensor-data

A production-style IoT data pipeline that ingests real-time air quality sensor readings from [Sensor.Community](https://sensor.community/) and streams them through MQTT → Kafka → S3 → Snowflake, following a medallion (bronze/silver/gold) architecture with a device registry, data quality enforcement, and orchestrated incremental refresh.

## Architecture
<img width="936" height="512" alt="image" src="https://github.com/user-attachments/assets/33f30981-684a-4f59-bbb4-008a087205e7" />

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
     │  looks up sensor_id in the Postgres device registry
     │  logs an alert if the sensor is unregistered
     ▼  Kafka produce  sensor-readings topic
[Kafka]
     ▼  Kafka consume
[consumer.py]
     │  buffers messages, flushes every 60s or 500 messages
     │  no dedup here — bronze stays the immutable raw log, including
     │  any Kafka redeliveries; dbt's silver model dedupes on reading_id
     │  writes an S3 _SUCCESS marker when an hour partition closes
     ▼  Parquet (Snappy) → S3
[S3 Bronze Layer]
     sensor-readings/year=YYYY/month=MM/day=DD/hour=HH/<uuid>.parquet
     sensor-readings/year=YYYY/month=MM/day=DD/hour=HH/_SUCCESS
     ▼  Snowflake external table
[Airflow]
     │  S3KeySensor waits for the hour's _SUCCESS marker
     ▼
[dbt: silver]
     │  TRY_PARSE_JSON + TRY_TO_TIMESTAMP_TZ, deduped on reading_id
     │  rows with null reading_id / unparseable timestamp / junk sensor_type
     │  are excluded and logged to silver.rejected_readings instead of dropped
     ▼
[dbt: gold]      (incremental, enriched via dim_sensors + dim_customers)
     │  pm25_by_country_hour
     │  temperature_by_region_day
     │  sensor_activity_by_customer
     ▼
[dbt test]  →  16 data quality tests (not_null, unique, accepted_values)
```

**Device registry (Postgres):** `customers`, `dim_sensors`, and `alert_log` live in Postgres as the operational source of truth — devices are registered there, not auto-created from streaming events. A scheduled/manual sync (`sql/sync_dims.py`) replicates `customers`/`dim_sensors` into Snowflake as `silver.dim_customers`/`silver.dim_sensors` for analytical joins.

## Quickstart

### 1. Set up the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — defaults point to LocalStack for S3. Remove the
# S3_ENDPOINT_URL/AWS_*_KEY lines to write to real AWS S3 instead.
```

### 3. Start infrastructure

```bash
docker-compose up -d zookeeper kafka mosquitto localstack postgres
docker-compose ps   # wait for kafka and postgres to show Up (healthy)
```

### 4. Initialize the device registry

```bash
docker exec -i kafka-sensor-data_postgres_1 psql -U sensor -d sensordb < sql/init.sql
```

This creates `customers`/`dim_sensors`/`alert_log` and seeds 6 pseudo customers across 3 regions.

### 5. Create the S3 bucket (LocalStack)

```bash
aws --endpoint-url=http://localhost:4566 s3 mb s3://sensor-readings-bronze \
  --region us-east-1 --no-cli-pager
```

### 6. Seed sensor profiles (run once)

```bash
python -m sensor_pipeline bootstrap
```

This fetches a snapshot from Sensor.Community and pickles 1,000 sensor profiles to `sensor_profiles.pkl`.

### 7. Register those sensors in the device registry

```bash
POSTGRES_DSN=postgresql://sensor:sensor@localhost:5432/sensordb python sql/seed.py
```

Assigns each sensor a region (from lat/lon/country) and a customer, deterministically distributed across the customer pool for that region.

### 8. Start the pipeline

```bash
python -m sensor_pipeline simulate &   # emit sensor readings via MQTT
python -m sensor_pipeline produce &    # forward MQTT → Kafka, check registry
python -m sensor_pipeline consume &    # write Kafka → S3 Parquet
```

### 9. Watch it live (optional)

```bash
python trace.py
```

Three-column live tracer showing MQTT → Kafka → S3 events as they happen.

### 10. Verify data is landing in S3

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://sensor-readings-bronze/sensor-readings/ \
  --recursive --no-cli-pager
```

If you removed the LocalStack env vars to use real AWS, drop `--endpoint-url` and use `aws s3 ls s3://sensor-readings-bronze/sensor-readings/ --recursive` instead.

## Orchestration: refreshing silver and gold in Snowflake

Bronze landing in S3 doesn't automatically become silver/gold in Snowflake — that refresh is orchestrated by Airflow.

### Airflow + dbt

```bash
docker-compose -f airflow/docker-compose.yml up -d
```

Open `http://localhost:8080` (`admin`/`admin`). The `sensor_pipeline_refresh` DAG runs hourly:

1. `S3KeySensor` waits for the current hour's `_SUCCESS` marker in bronze
2. `dbt run` — incremental `silver.sensor_readings` + `silver.rejected_readings`
3. `dbt run` — all 3 gold models, in parallel
4. `dbt test` — 16 data quality checks

On startup, `consumer.py` also backfills any missing `_SUCCESS` markers from the last 48 hours — protects against a consumer restart landing inside a new hour and permanently skipping the previous hour's completion signal (hit this for real; see the architecture doc's Lessons Learned).

Requires `airflow/.env` with `SNOWFLAKE_*` and `AWS_*` credentials (see `airflow/docker-compose.yml` for the full list). Not committed to git.

### GitHub Actions (manual fallback only — not scheduled)

- `.github/workflows/refresh_pipeline.yml` — `workflow_dispatch` only. Originally scheduled hourly as an interim path before Airflow existed; running both on the same cron caused them to race against each other refreshing the same Snowflake tables. Kept as a manual emergency fallback if the Airflow stack is down, not a parallel scheduler.
- `.github/workflows/sync_dims.yml` — manual trigger, syncs Postgres `customers`/`dim_sensors` into Snowflake. GitHub Actions can't reach a local-only Postgres instance, so this stays manual until Postgres is hosted somewhere network-accessible.

## Running tests

### Unit tests (no Docker required)

```bash
pytest tests/unit/ -v
```

### Integration tests (requires infrastructure running)

```bash
docker-compose up -d zookeeper kafka mosquitto localstack postgres
docker exec -i kafka-sensor-data_postgres_1 psql -U sensor -d sensordb < sql/init.sql
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
│   ├── producer.py      # MQTT → Kafka, device registry lookup + alerting
│   ├── consumer.py      # Kafka → S3 Parquet writer, _SUCCESS marker on hour rollover
│   ├── registry.py      # Postgres device registry lookups
│   └── fetch.py         # Sensor.Community API client
├── sql/
│   ├── init.sql          # Postgres schema: customers, dim_sensors, alert_log
│   ├── seed.py            # assign region/customer to bootstrapped sensors
│   ├── sync_dims.py       # Postgres → Snowflake dim table sync
│   ├── refresh_silver.py  # standalone silver refresh (GitHub Actions path)
│   ├── build_gold.py      # standalone gold refresh (GitHub Actions path)
│   └── gold/*.sql         # gold table definitions (GitHub Actions path)
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── sources.yml
│       ├── silver/        # sensor_readings (incremental), rejected_readings (audit log)
│       └── gold/          # pm25_by_country_hour, temperature_by_region_day, sensor_activity_by_customer
├── airflow/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── dags/sensor_refresh.py   # hourly DAG: S3 sensor → dbt run → dbt test
├── tests/
│   ├── unit/            # fully mocked, no external services
│   ├── integration/     # real Kafka + MQTT + LocalStack + Postgres (--integration flag)
│   └── quality/         # pandera schema checks on bronze Parquet files
├── mosquitto/
│   └── mosquitto.conf   # MQTT broker config
├── docs/
│   └── generate_doc.js  # generates the architecture decision log (.docx)
├── docker-compose.yml   # Zookeeper, Kafka, Mosquitto, LocalStack, Postgres
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## Data model

### Bronze (S3 Parquet, external table in Snowflake)

| Field | Type | Description |
|---|---|---|
| `reading_id` | string (UUID) | Unique per emission — used for dedup |
| `sensor_id` | int | Sensor.Community sensor ID |
| `sensor_type` | string | e.g. `SDS011`, `DHT22`, `BME280`, `SPS30`, etc. |
| `ingested_at` | string (ISO 8601) | Timestamp of emission |
| `latitude` / `longitude` | float | Sensor location |
| `country` | string | ISO country code |
| `values` | string (JSON) | e.g. `{"P1": 12.5, "P2": 8.3}` |

S3 files are Hive-partitioned by `year/month/day/hour`. A `_SUCCESS` marker is written to each hour's prefix when the consumer rolls over, signaling Airflow that the partition is complete.

### Silver (native Snowflake table, deduped + typed)

`pm25`, `pm10`, `temperature`, `humidity`, `pressure`, `pressure_at_sealevel` parsed out of the raw `values` JSON. Deduplicated on `reading_id`. Rows with a null `reading_id`, an unparseable `ingested_at`, or a junk `sensor_type` (`''`/`test`) are excluded and logged to `silver.rejected_readings` instead of silently dropped.

### Gold (native Snowflake tables, pre-aggregated)

- `pm25_by_country_hour` — hourly PM2.5/PM10 stats by country and customer
- `temperature_by_region_day` — daily temperature/humidity/pressure stats by region and customer
- `sensor_activity_by_customer` — daily active sensor counts and reading volumes by customer

All three enrich via `dim_sensors`/`dim_customers`, falling back to `'Unknown'` for sensors not in the device registry.

### Device registry (Postgres — operational source of truth)

| Table | Purpose |
|---|---|
| `customers` | 6 pseudo customers across 3 regions |
| `dim_sensors` | sensor_id → region/customer mapping, registered at "purchase time" via `sql/seed.py` |
| `alert_log` | `unregistered_device` alerts logged by `producer.py` and `sql/build_gold.py` |

## CI

GitHub Actions runs unit tests on every push, and integration tests (with Kafka, Mosquitto, LocalStack, and Postgres services) on PRs. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
