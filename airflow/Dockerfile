FROM apache/airflow:2.9.1-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

USER airflow

# Airflow's own dependencies (amazon provider, snowflake provider) — pinned
# against Airflow's official constraints file to avoid uv/pip silently
# upgrading core Airflow packages.
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.1/constraints-3.11.txt" \
    -r /requirements.txt

# dbt-snowflake is installed in a SEPARATE pip call, deliberately without the
# Airflow constraints file. dbt-snowflake's pinned snowflake-connector-python
# requires an older `keyring` than Airflow's constraints allow — running it
# in the same constrained call causes an unresolvable conflict. Splitting the
# install into two calls sidesteps that without needing true venv isolation.
RUN uv pip install --system --no-cache "dbt-snowflake>=1.8.0,<1.9.0"
