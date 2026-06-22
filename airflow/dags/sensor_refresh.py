"""
Hourly sensor pipeline refresh DAG.

Flow:
  S3KeySensor (wait for previous hour _SUCCESS marker)
      -> dbt run: silver.sensor_readings  (incremental)
      -> dbt run: gold.*                  (incremental, fanned out in parallel)
      -> dbt test                         (data quality)

The _SUCCESS marker is written by consumer.py when it rolls over to a new
hour partition, signalling that the previous hour's data is complete.

NOTE: At larger production scale the S3KeySensor would be replaced by a
more sophisticated partition sensor (e.g. Dataswarm-style dependency checks)
and dbt would be invoked via dbt Cloud or Astronomer Cosmos for richer
lineage, observability, and parallelism. GitHub Actions was used as an
interim orchestrator; Airflow is the production upgrade path.
"""
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

S3_BUCKET = os.getenv("S3_BUCKET", "sensor-readings-bronze")
S3_PREFIX = os.getenv("S3_PREFIX", "sensor-readings")
DBT_DIR   = "/opt/airflow/dbt"
DBT_PROFILES_DIR = "/opt/airflow/dbt"

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="sensor_pipeline_refresh",
    description="Hourly incremental refresh: silver + gold via dbt, triggered by S3 _SUCCESS marker",
    schedule_interval="@hourly",
    start_date=datetime(2026, 6, 21),
    catchup=False,
    default_args=default_args,
    tags=["sensor", "dbt", "incremental"],
) as dag:

    # Wait for _SUCCESS marker written by consumer.py when previous hour closes.
    # {{ execution_date }} is the start of the current schedule interval,
    # so we wait on the partition for that hour.
    wait_for_partition = S3KeySensor(
        task_id="wait_for_bronze_partition",
        bucket_name=S3_BUCKET,
        bucket_key=(
            f"{S3_PREFIX}/"
            "year={{ execution_date.strftime('%Y') }}/"
            "month={{ execution_date.strftime('%m') }}/"
            "day={{ execution_date.strftime('%d') }}/"
            "hour={{ execution_date.strftime('%H') }}/"
            "_SUCCESS"
        ),
        aws_conn_id="aws_default",
        poke_interval=30,
        timeout=60 * 60,  # give up after 1 hour
        mode="reschedule",  # release worker slot while waiting
    )

    dbt_silver = BashOperator(
        task_id="dbt_run_silver",
        bash_command=(
            f"cd {DBT_DIR} && "
            f"dbt run --profiles-dir {DBT_PROFILES_DIR} --models silver.sensor_readings"
        ),
        env={
            "SNOWFLAKE_ACCOUNT":   "{{ var.value.SNOWFLAKE_ACCOUNT }}",
            "SNOWFLAKE_USER":      "{{ var.value.SNOWFLAKE_USER }}",
            "SNOWFLAKE_PASSWORD":  "{{ var.value.SNOWFLAKE_PASSWORD }}",
            "SNOWFLAKE_WAREHOUSE": "{{ var.value.SNOWFLAKE_WAREHOUSE }}",
            "SNOWFLAKE_DATABASE":  "{{ var.value.get('SNOWFLAKE_DATABASE', 'SENSOR_DATA') }}",
            **os.environ,
        },
    )

    dbt_gold_pm25 = BashOperator(
        task_id="dbt_run_gold_pm25",
        bash_command=(
            f"cd {DBT_DIR} && "
            f"dbt run --profiles-dir {DBT_PROFILES_DIR} --models gold.pm25_by_country_hour"
        ),
        env={**os.environ},
    )

    dbt_gold_temp = BashOperator(
        task_id="dbt_run_gold_temperature",
        bash_command=(
            f"cd {DBT_DIR} && "
            f"dbt run --profiles-dir {DBT_PROFILES_DIR} --models gold.temperature_by_region_day"
        ),
        env={**os.environ},
    )

    dbt_gold_activity = BashOperator(
        task_id="dbt_run_gold_activity",
        bash_command=(
            f"cd {DBT_DIR} && "
            f"dbt run --profiles-dir {DBT_PROFILES_DIR} --models gold.sensor_activity_by_customer"
        ),
        env={**os.environ},
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {DBT_DIR} && "
            f"dbt test --profiles-dir {DBT_PROFILES_DIR}"
        ),
        env={**os.environ},
    )

    # DAG dependency chain:
    # wait → silver → [pm25, temp, activity in parallel] → test
    wait_for_partition >> dbt_silver >> [dbt_gold_pm25, dbt_gold_temp, dbt_gold_activity] >> dbt_test
