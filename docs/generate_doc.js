const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, Header, Footer, ExternalHyperlink,
} = require("docx");
const fs = require("fs");

const BLUE      = "2E75B6";
const DARK      = "1F2937";
const GRAY_BG   = "F3F4F6";
const BORDER_C  = "D1D5DB";
const WHITE     = "FFFFFF";
const ACCENT    = "0F4C81";

const border = { style: BorderStyle.SINGLE, size: 1, color: BORDER_C };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, bold: true, size: 36, color: ACCENT, font: "Arial" })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 80 },
    children: [new TextRun({ text, bold: true, size: 28, color: DARK, font: "Arial" })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 60 },
    children: [new TextRun({ text, bold: true, size: 24, color: DARK, font: "Arial" })],
  });
}

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    children: [new TextRun({ text, size: 22, font: "Arial", color: DARK, ...opts })],
  });
}

function bullet(text, bold_prefix = null) {
  const children = [];
  if (bold_prefix) {
    children.push(new TextRun({ text: bold_prefix + " ", bold: true, size: 22, font: "Arial", color: DARK }));
    children.push(new TextRun({ text, size: 22, font: "Arial", color: DARK }));
  } else {
    children.push(new TextRun({ text, size: 22, font: "Arial", color: DARK }));
  }
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children,
  });
}

function sub_bullet(text) {
  return new Paragraph({
    numbering: { reference: "sub-bullets", level: 0 },
    spacing: { before: 20, after: 20 },
    children: [new TextRun({ text, size: 20, font: "Arial", color: DARK })],
  });
}

function spacer(lines = 1) {
  return new Paragraph({
    spacing: { before: 0, after: 0 },
    children: [new TextRun({ text: "", size: lines * 24 })],
  });
}

function code_block(lines) {
  const children = [];
  lines.forEach((line, i) => {
    children.push(
      new Paragraph({
        spacing: { before: 0, after: 0 },
        children: [new TextRun({ text: line, font: "Courier New", size: 18, color: "1F2937" })],
      })
    );
  });
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: 9360, type: WidthType.DXA },
            shading: { fill: "F8F9FA", type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 180, right: 180 },
            children,
          }),
        ],
      }),
    ],
  });
}

function decision_box(decision, reasoning, tradeoffs) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: 9360, type: WidthType.DXA },
            shading: { fill: "EFF6FF", type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 180, right: 180 },
            children: [
              new Paragraph({
                spacing: { before: 0, after: 60 },
                children: [new TextRun({ text: "Decision: " + decision, bold: true, size: 22, font: "Arial", color: ACCENT })],
              }),
              new Paragraph({
                spacing: { before: 0, after: 60 },
                children: [new TextRun({ text: "Reasoning: " + reasoning, size: 22, font: "Arial", color: DARK })],
              }),
              new Paragraph({
                spacing: { before: 0, after: 0 },
                children: [new TextRun({ text: "Tradeoffs: " + tradeoffs, size: 22, font: "Arial", color: "6B7280", italics: true })],
              }),
            ],
          }),
        ],
      }),
    ],
  });
}

function two_col_table(headers, rows) {
  const headerRow = new TableRow({
    children: headers.map((h, i) => new TableCell({
      borders,
      width: { size: i === 0 ? 3000 : 6360, type: WidthType.DXA },
      shading: { fill: BLUE, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, size: 20, font: "Arial", color: WHITE })] })],
    })),
  });

  const dataRows = rows.map(([col1, col2]) => new TableRow({
    children: [
      new TableCell({
        borders,
        width: { size: 3000, type: WidthType.DXA },
        shading: { fill: GRAY_BG, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: col1, bold: true, size: 20, font: "Arial", color: DARK })] })],
      }),
      new TableCell({
        borders,
        width: { size: 6360, type: WidthType.DXA },
        shading: { fill: WHITE, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: col2, size: 20, font: "Arial", color: DARK })] })],
      }),
    ],
  }));

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3000, 6360],
    rows: [headerRow, ...dataRows],
  });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
      },
      {
        reference: "sub-bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1080, hanging: 360 } } } }],
      },
    ],
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22, color: DARK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: ACCENT },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 280, after: 80 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 200, after: 60 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 1 } },
            children: [
              new TextRun({ text: "IoT Sensor Data Pipeline", bold: true, font: "Arial", size: 20, color: BLUE }),
              new TextRun({ text: "  |  Architecture & Decision Log", font: "Arial", size: 20, color: "6B7280" }),
            ],
          }),
        ],
      }),
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 6, color: BORDER_C, space: 1 } },
            alignment: AlignmentType.RIGHT,
            children: [
              new TextRun({ text: "Page ", font: "Arial", size: 18, color: "6B7280" }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: "6B7280" }),
            ],
          }),
        ],
      }),
    },
    children: [

      // ─── TITLE ───────────────────────────────────────────────────────────────
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 480, after: 120 },
        children: [new TextRun({ text: "IoT Sensor Data Pipeline", bold: true, size: 56, font: "Arial", color: ACCENT })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "Architecture & Decision Log", size: 28, font: "Arial", color: "6B7280" })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 480 },
        children: [new TextRun({ text: "June 2026", size: 22, font: "Arial", color: "6B7280", italics: true })],
      }),

      // ─── 1. PROJECT OVERVIEW ─────────────────────────────────────────────────
      h1("1. Project Overview"),
      p("This project builds a real-time IoT data pipeline that ingests air quality sensor readings from the Sensor.Community global network and streams them through a modern data lakehouse stack. The pipeline is designed to demonstrate production patterns: streaming ingestion, bronze/silver/gold medallion architecture, device registry management, and real-time alerting."),
      spacer(),
      h2("Data Flow"),
      code_block([
        "Sensor.Community API",
        "       |  snapshot fetch (bootstrap, run once)",
        "       v",
        "sensor_profiles.pkl  (1,000 sensor profiles cached locally)",
        "       |",
        "       v",
        "simulator.py  (1,000 async tasks, 30-300ms per sensor)",
        "       |  MQTT publish  sensors/{sensor_id}/data",
        "       v",
        "Mosquitto MQTT Broker  (IoT gateway)",
        "       |  MQTT subscribe",
        "       v",
        "producer.py  (MQTT -> Kafka, idempotent, + registry lookup)",
        "       |  Kafka produce  sensor-readings topic",
        "       v",
        "Kafka",
        "       |  Kafka consume",
        "       v",
        "consumer.py  (buffer 500 msgs or 60s -> S3 Parquet, dedup on reading_id)",
        "       |",
        "       v",
        "S3 Bronze Layer  sensor-readings/year=YYYY/month=MM/day=DD/hour=HH/",
        "       |  Snowflake external table",
        "       v",
        "Snowflake Silver  (materialized table, typed columns, deduped)",
        "       |  enriched via dim joins",
        "       v",
        "Snowflake Gold  (pre-aggregated analytics tables)  [in progress]",
      ]),
      spacer(),

      // ─── 2. TECH STACK ───────────────────────────────────────────────────────
      h1("2. Technology Stack"),
      two_col_table(["Component", "Technology & Rationale"], [
        ["MQTT Broker", "Eclipse Mosquitto 2.0 — lightweight IoT gateway, simulates the edge layer between physical devices and the data pipeline"],
        ["Message Queue", "Apache Kafka — durable, replayable event log; decouples simulator from consumer; enables multiple independent consumers (S3 writer, alert engine)"],
        ["Object Storage", "AWS S3 — durable Parquet storage forming the bronze datalakehouse layer; Hive-partitioned by year/month/day/hour"],
        ["File Format", "Parquet + Snappy compression — columnar format optimized for analytical queries; ~60-70% size reduction vs JSON"],
        ["Data Warehouse", "Snowflake — external tables over S3 for bronze; native internal tables for silver/gold; QUALIFY ROW_NUMBER() for deduplication"],
        ["Operational DB", "PostgreSQL 16 — source of truth for device registry and customer data (OLTP workloads); feeds Snowflake dim tables via sync script"],
        ["Serialization", "JSON over MQTT/Kafka; PyArrow for Parquet serialization"],
        ["Testing", "pytest + moto[s3] (unit), LocalStack (integration), pandera (data quality)"],
        ["CI/CD", "GitHub Actions — unit tests on every push, integration tests on PR with service containers"],
        ["Local Infra", "Docker Compose — Zookeeper, Kafka, Mosquitto, LocalStack, Postgres"],
      ]),
      spacer(),

      // ─── 3. ARCHITECTURAL DECISIONS ──────────────────────────────────────────
      h1("3. Key Architectural Decisions"),

      h2("3.1  Streaming Simulation Strategy"),
      p("The Sensor.Community API is a REST snapshot endpoint (not a WebSocket), returning ~18,000 sensors at a point in time. To simulate continuous IoT streaming, we bootstrap once to cache 1,000 sensor profiles, then run 1,000 async tasks each emitting at random 30-300ms intervals with Gaussian noise on sensor values."),
      spacer(),
      decision_box(
        "Async per-sensor tasks at 30-300ms intervals",
        "Simulates realistic IoT device behavior where each physical sensor independently publishes at its own cadence. A polling loop would create artificial synchronization across all sensors.",
        "Readings from the same physical sensor will repeat with noise, not reflect true environmental change. Sensor profiles are frozen at bootstrap time."
      ),
      spacer(),

      h2("3.2  Deduplication Strategy"),
      p("Every simulated reading is stamped with a UUID4 reading_id at emission time. Deduplication happens at two layers:"),
      bullet("Bronze (within batch): consumer.py deduplicates on reading_id within each 60s/500-message flush window before writing to S3"),
      bullet("Silver (across batches): QUALIFY ROW_NUMBER() OVER (PARTITION BY reading_id ORDER BY ingested_at) = 1 removes any cross-batch duplicates"),
      spacer(),
      decision_box(
        "Bronze keeps all data; silver deduplicates",
        "Bronze is the source of truth and should be immutable. Dedup logic in silver means we can reprocess bronze if dedup requirements change without losing raw data.",
        "Silver is a point-in-time snapshot. As new data lands in bronze, silver must be refreshed (via dbt or scheduled ETL) to stay current."
      ),
      spacer(),

      h2("3.3  S3 as Bronze Layer (External Table)"),
      p("Data lands in S3 as Parquet files with Hive-style partitioning. Snowflake reads this via an external table using a storage integration (IAM role trust) rather than credentials."),
      bullet("Partition scheme: sensor-readings/year=YYYY/month=MM/day=DD/hour=HH/"),
      bullet("File naming: UUID4.parquet per flush (avoids collisions across concurrent consumers)"),
      bullet("Compression: Snappy (fast decompression, good ratio, Parquet-native)"),
      spacer(),
      decision_box(
        "External table for bronze, internal table for silver",
        "External tables scan S3 on every query — no caching, no micro-partition pruning. A SELECT * with QUALIFY ROW_NUMBER() on an external table required a full S3 scan (~6 minutes for our dataset). Materializing silver as a native Snowflake table makes queries instant.",
        "Silver is now a snapshot. It must be refreshed periodically to pick up new bronze data."
      ),
      spacer(),

      h2("3.4  IoT Gateway Pattern (MQTT -> Kafka)"),
      p("Rather than having the simulator write directly to Kafka, we use MQTT as an intermediate transport with Mosquitto acting as the broker. This reflects real IoT architecture where edge devices speak lightweight protocols (MQTT, CoAP) and a gateway bridges to enterprise messaging."),
      bullet("producer.py subscribes to sensors/+/data and forwards to Kafka with enable.idempotence=True"),
      bullet("Kafka key is sensor_id, enabling partition affinity for ordered processing per sensor"),
      bullet("Idempotent producer prevents duplicate Kafka messages from producer retries"),
      spacer(),
      decision_box(
        "MQTT -> Kafka bridge (producer.py) as separate process",
        "Decouples the IoT edge layer from the data pipeline. In production, MQTT clients are often constrained devices that cannot speak Kafka directly. The bridge pattern is standard.",
        "Adds a hop and a process to manage. The bridge is a single point of failure between MQTT and Kafka."
      ),
      spacer(),

      h2("3.5  Device Registry in PostgreSQL"),
      p("Customer and device registration data lives in PostgreSQL, not Snowflake or S3. This was a deliberate OLTP vs OLAP separation."),
      spacer(),
      two_col_table(["Store", "Purpose"], [
        ["PostgreSQL", "Source of truth for operational data: device registration, customer accounts, alert logs. Written to by application code. Low-latency reads for runtime lookups."],
        ["Snowflake", "Analytical copy of dim tables, synced from Postgres. Used for joins against fact_sensor_readings. Never written to directly."],
        ["S3 flat file", "Considered and rejected: no atomic updates, no concurrent write safety, manual process does not scale."],
        ["DynamoDB", "Good alternative if access patterns are key-value only and no relational joins needed. Postgres chosen here because customer data has relational structure."],
      ]),
      spacer(),
      decision_box(
        "Device registration happens at purchase time, not on first sensor event",
        "Auto-registering devices from streaming events conflates device provisioning (a business process) with data ingestion (a technical process). An unrecognized sensor_id arriving in Kafka is an anomaly to alert on, not an opportunity to auto-onboard.",
        "Requires an operational Postgres instance and a seeding process. Cold-start requires running seed.py before the pipeline."
      ),
      spacer(),

      h2("3.6  Unregistered Device Alerting at the Gateway"),
      p("The producer.py (IoT gateway) checks each incoming sensor_id against the Postgres registry. If the sensor is not found, it logs an alert to the alert_log table. A local seen_sensor_ids set avoids a Postgres round-trip on every message."),
      code_block([
        "seen_sensor_ids: set[int] = set()  # in-memory per producer process",
        "",
        "on each MQTT message:",
        "  if sensor_id not in seen_sensor_ids:",
        "    customer = get_customer(sensor_id, pg_conn)",
        "    if customer is None:",
        "      log_unregistered(sensor_id, payload, pg_conn)  # -> alert_log",
        "    seen_sensor_ids.add(sensor_id)  # cache, never look up again",
        "  # forward to Kafka regardless",
      ]),
      spacer(),
      decision_box(
        "Alert at gateway layer, not consumer or gold layer",
        "By the time data reaches gold, it may be hours old. An unregistered device alert needs to be actionable quickly. The gateway sees every message first and is the right place for real-time policy enforcement.",
        "seen_sensor_ids resets on producer restart, causing redundant Postgres lookups on startup. Handled gracefully via ON CONFLICT DO NOTHING in alert_log inserts."
      ),
      spacer(),

      h2("3.7  Dim Sync Strategy (Postgres -> Snowflake)"),
      p("Rather than CDC (Debezium, Fivetran) or DynamoDB Streams, we use a simple scheduled batch sync script (sync_dims.py) that runs daily or on-demand."),
      bullet("Loads all customers and dim_sensors from Postgres in one query"),
      bullet("Bulk-inserts into a Snowflake temp table via executemany"),
      bullet("Single MERGE statement from temp -> target (one round-trip per table)"),
      spacer(),
      decision_box(
        "Batch sync over CDC for slowly-changing dimensions",
        "Customers and device registrations change rarely (on purchase/onboarding events). The lag from daily sync is acceptable. CDC infrastructure (Debezium, Kafka Connect, Fivetran) is expensive to operate for data that changes a few times per day.",
        "Lag: new customers/devices won't appear in Snowflake analytics until next sync. If near-realtime dim freshness is required, CDC becomes necessary."
      ),
      spacer(),

      // ─── 4. MEDALLION ARCHITECTURE ───────────────────────────────────────────
      h1("4. Medallion Architecture"),
      two_col_table(["Layer", "Description"], [
        ["Bronze", "Raw Parquet files on S3. External table in Snowflake. Source of truth — never modified. All sensor types mixed. Full JSON row stored in VALUE column plus extracted columns."],
        ["Silver", "Native Snowflake table. Typed columns (pm25, pm10, temperature, humidity, pressure). Deduped on reading_id. JSON sensor_values unpacked via TRY_PARSE_JSON. TRY_TO_TIMESTAMP_TZ handles malformed ingested_at."],
        ["Silver Dims", "DIM_CUSTOMERS and DIM_SENSORS synced from Postgres. Enables enrichment joins on fact data."],
        ["Gold", "Pre-aggregated analytics tables, built via dbt incremental models. Designed for BI tools and dashboards. No heavy computation at query time: pm25_by_country_hour, temperature_by_region_day, sensor_activity_by_customer."],
      ]),
      spacer(),

      h2("4.1  Why Silver is a Materialized Table, Not a View"),
      p("Initial implementation used CREATE OR REPLACE VIEW for silver. A simple SELECT * LIMIT 10 took over 6 minutes because:"),
      bullet("External tables scan S3 on every query — no caching"),
      bullet("QUALIFY ROW_NUMBER() prevents early termination — full scan required before LIMIT applies"),
      p("Materializing silver as a native table reduces query time from minutes to milliseconds. The tradeoff is that silver must be refreshed as new bronze data arrives."),
      spacer(),

      // ─── 5. DATA MODEL ───────────────────────────────────────────────────────
      h1("5. Data Model"),

      h2("5.1  Bronze Schema (Parquet / S3)"),
      two_col_table(["Field", "Type & Description"], [
        ["reading_id", "STRING (UUID4) — unique per emission, primary dedup key"],
        ["sensor_id", "INT64 — Sensor.Community sensor ID"],
        ["sensor_type", "STRING — e.g. SDS011, DHT22, BME280, BMP280"],
        ["ingested_at", "STRING (ISO 8601) — timestamp of emission in simulator"],
        ["latitude", "FLOAT64 — sensor location"],
        ["longitude", "FLOAT64 — sensor location"],
        ["country", "STRING — ISO country code"],
        ["values", "STRING (JSON) — sensor measurements, schema varies by sensor_type"],
      ]),
      spacer(),

      h2("5.2  Silver Schema (Snowflake Internal Table)"),
      two_col_table(["Field", "Notes"], [
        ["reading_id", "Dedup key — one row per unique reading_id"],
        ["sensor_id, sensor_type, lat, lon, country", "Carried forward from bronze"],
        ["ingested_at", "Parsed to TIMESTAMPTZ via TRY_TO_TIMESTAMP_TZ"],
        ["pm25, pm10", "From SDS011 sensors (P1, P2 keys in JSON)"],
        ["temperature, humidity", "From DHT22 / BME280 sensors"],
        ["pressure, pressure_at_sealevel", "From BME280 / BMP280 sensors"],
      ]),
      spacer(),

      h2("5.3  Postgres Operational Schema"),
      two_col_table(["Table", "Purpose"], [
        ["customers", "customer_id, customer_name, region — 6 pseudo customers across 3 regions"],
        ["dim_sensors", "sensor_id, sensor_type, lat, lon, country, region, customer_id — pre-registered at bootstrap"],
        ["alert_log", "sensor_id, alert_type, payload (JSONB), created_at — unregistered device events"],
      ]),
      spacer(),

      // ─── 6. TESTING STRATEGY ─────────────────────────────────────────────────
      h1("6. Testing Strategy"),
      p("Tests are split into three tiers with different infrastructure requirements:"),
      spacer(),
      two_col_table(["Tier", "Description"], [
        ["Unit (tests/unit/)", "Fully mocked — no Docker, no network. Tests business logic in isolation: profile validation, reading generation, MQTT->Kafka forwarding, registry lookup/alert logic."],
        ["Integration (tests/integration/)", "Requires real Kafka + Mosquitto + LocalStack. Guarded by --integration flag. Tests end-to-end flows: MQTT pub/sub, Kafka produce/consume, S3 Parquet flush with real dedup."],
        ["Data Quality (tests/quality/)", "pandera schema validation on actual bronze Parquet files. Validates field types, non-null constraints, value ranges."],
      ]),
      spacer(),
      h3("Key Testing Decisions"),
      bullet("Consumer tests call _flush() directly rather than spawning a consumer process — avoids timing dependencies in CI"),
      bullet("--integration flag guard means unit tests run fast on every push; integration tests only run on PRs"),
      bullet("Mosquitto started as a manual docker run step in CI (after checkout) because service containers start before checkout, so the config file mount would fail"),
      bullet("Kafka service uses zookeeper:2181 (not localhost:2181) in CI because service containers communicate via network aliases"),
      bullet("Postgres added as a CI service after producer.py started requiring a registry connection at startup — the integration test job didn't have Postgres available, so the producer crashed before subscribing to MQTT, silently failing test_message_flows_mqtt_to_kafka with a 15s timeout rather than a clear connection error"),
      spacer(),

      // ─── 7. LESSONS LEARNED ──────────────────────────────────────────────────
      h1("7. Lessons Learned & Gotchas"),
      bullet("bool(0) bug", "sensor_id=0 evaluated as falsy with bool(p.get('id')). Fixed to p.get('id') is not None."),
      bullet("Stale background process", "A leftover python -m sensor_pipeline bridge & process stole the MQTT client_id, silently preventing the real producer from receiving messages."),
      bullet("Python alias override", "alias python=/usr/local/opt/python@3.9 in ~/.zshrc overrides venv activation. Requires unalias python each session."),
      bullet("S3_ENDPOINT_URL not loaded", "Python does not auto-load .env files. S3_ENDPOINT_URL was not set in the process environment, so boto3 hit real AWS S3 instead of LocalStack."),
      bullet("Snowflake reserved word", "Column named 'values' requires double-quoting in all SQL: TRY_PARSE_JSON(\"values\")"),
      bullet("External table SELECT speed", "Full S3 scan + QUALIFY window function = 6+ minutes for SELECT * LIMIT 10. Solution: materialize silver as a native table."),
      bullet("Sync script performance", "999 individual MERGE statements to Snowflake = ~10 minutes. Fixed to bulk insert into temp table + single MERGE = seconds."),
      bullet("TRY_TO_TIMESTAMP_TZ vs TO_TIMESTAMP_TZ", "One row had an empty string ingested_at, causing TO_TIMESTAMP_TZ to fail the entire CREATE TABLE. TRY_ variant returns NULL instead."),
      bullet("Incremental models don't retroactively fix old rows", "After adding row-filtering logic to the silver dbt model (excluding null reading_id, unparseable timestamps, junk sensor_type), dbt tests still failed. The filter only applies to newly-scanned bronze rows in an incremental run — bad rows already materialized from a prior full build stayed put until a dbt run --full-refresh was run explicitly."),
      bullet("uv installing into the wrong environment silently", "An attempt to isolate dbt in its own virtualenv (separate from Airflow's site-packages) failed silently: uv pip install run against the venv's own uv binary, without --python or an active VIRTUAL_ENV, fell back to installing into the system Python instead. The venv existed and looked correct, but was empty. Confirmed via pip list inside the venv showing only pip/setuptools/uv with no dbt-snowflake."),
      bullet("Airflow + dbt dependency conflicts", "dbt-snowflake's pinned snowflake-connector-python requires an older keyring than Airflow's official constraints file allows, making a single combined pip install unresolvable. Splitting into two separate pip install calls (one constrained to Airflow's official constraints file, one unconstrained for dbt-snowflake) sidesteps the conflict without needing true filesystem isolation."),
      bullet("uv vs pip install speed", "Installing dbt-snowflake + Airflow providers via plain pip inside the Airflow Docker image hung for 2000+ seconds on dependency backtracking. Switching to uv (10-100x faster resolver) cut this to under a minute."),
      bullet("Airflow catchup created phantom failed runs", "Even with catchup=False, Airflow auto-triggered a run for the most recent missed schedule interval before catching up to 'now', producing failed DAG runs for hours with no corresponding _SUCCESS marker. Expected behavior, but easy to mistake for a bug on first sight."),
      bullet("Empty-body S3 PutObject failing against LocalStack", "Writing a zero-byte _SUCCESS marker via boto3 against LocalStack raised botocore.exceptions.ClientError: 'NoneType' object has no attribute 'to_bytes' — a checksum-trailer incompatibility between newer botocore and LocalStack's S3 implementation. Fixed by writing a non-empty body (an ISO timestamp) instead of b''."),
      bullet("Multiple consumers in the same Kafka consumer group", "Restarting consume with corrected S3 env vars while the original (misconfigured) process was still running meant both shared the consumer group ID, causing Kafka to split partitions between them and scatter data across two destinations unpredictably. Always confirm the old process has actually exited before starting a replacement."),
      spacer(),

      // ─── 8. ORCHESTRATION: AIRFLOW + DBT ─────────────────────────────────────
      h1("8. Orchestration: Airflow + dbt"),
      p("Manually running CREATE TABLE statements and Python refresh scripts doesn't scale, and doesn't answer 'when does silver/gold actually update.' This section covers the move to scheduled, incremental, dependency-aware refresh."),
      spacer(),

      h2("8.1  Why Not Just Cron + Full Rebuilds"),
      p("The first refresh approach was a full CREATE OR REPLACE TABLE on every run, on a fixed schedule. Two problems surfaced:"),
      bullet("Full rebuilds re-scan the entire bronze external table every run, even though only the latest hour's data is new — wasteful and slow as bronze grows"),
      bullet("A fixed cron has no concept of whether the data it depends on is actually ready. Following Meta's Dataswarm pattern (don't run today's job until yesterday's partition is marked complete), the pipeline needed partition-level dependency awareness, not just a timer"),
      spacer(),

      h2("8.2  The _SUCCESS Marker Pattern"),
      p("consumer.py now detects when the wall-clock hour rolls over, flushes any remaining buffered messages into the closing hour's partition, and writes an empty (well — non-empty, see Lessons Learned) _SUCCESS file to that hour's S3 prefix. This is the same completion-signal pattern used in Hadoop/Hive: downstream consumers wait for _SUCCESS rather than guessing when an hour's files have all landed."),
      spacer(),
      decision_box(
        "Consumer-emitted _SUCCESS marker, not a fixed offset or file-count heuristic",
        "Waiting for 'at least one file' in an hour partition would trigger silver/gold refresh on a small fraction of that hour's data. Waiting for 'no new files in N minutes' adds latency and is still a heuristic. Only the consumer itself knows definitively when it has stopped writing to a given hour.",
        "Couples the orchestration layer's correctness to the consumer's hour-rollover logic being correct. If the consumer crashes mid-hour without flushing, no _SUCCESS marker is written and Airflow's sensor times out rather than silently proceeding on incomplete data — a deliberate fail-closed tradeoff."
      ),
      spacer(),

      h2("8.3  dbt Incremental Models"),
      p("Silver and all three gold models use materialized='incremental' with is_incremental() watermark filters, rather than full rebuilds:"),
      code_block([
        "{% if is_incremental() %}",
        "WHERE TRY_TO_TIMESTAMP_TZ(ingested_at) > (",
        "    SELECT MAX(ingested_at) FROM {{ this }}",
        ")",
        "{% endif %}",
      ]),
      p("Gold models incrementally MERGE on their own grain (hour+country for pm25, day+region+sensor_type for temperature, etc.), enriching via LEFT JOIN to dim_sensors/dim_customers so unregistered sensors fall back to 'Unknown' rather than being dropped."),
      spacer(),

      h2("8.4  Data Quality: Filtering and Auditing, Not Just Testing"),
      p("dbt tests caught real malformed bronze rows: a null reading_id, an unparseable ingested_at, and rows with sensor_type of '' or 'test'. Rather than only alerting on these via failing tests, silver.sensor_readings now filters them out at the source, and a new silver.rejected_readings table logs exactly what was excluded and why."),
      spacer(),
      decision_box(
        "Filter bad rows into an audit table, not just fail-and-block",
        "A failing dbt test blocks the whole pipeline run on every subsequent execution until someone manually intervenes. Filtering bad rows out of silver while logging them to rejected_readings keeps the pipeline flowing while still making every excluded row visible and explainable — nothing silently disappears between bronze and silver.",
        "Required discovering that, separately, 14 of the '16 unexpected sensor types' flagged by the original accepted_values test were legitimate real-world Sensor.Community sensors (SPS30, PMS5003, radiation/noise sensors, etc.) that simply hadn't been anticipated — only 3 rows were genuinely bad data. The accepted_values list was expanded accordingly rather than treating all 16 as errors."
      ),
      spacer(),

      h2("8.5  Airflow DAG Structure"),
      code_block([
        "wait_for_bronze_partition  (S3KeySensor, mode='reschedule')",
        "        |",
        "        v",
        "dbt_run_silver  (silver.sensor_readings + silver.rejected_readings)",
        "        |",
        "        +--> dbt_run_gold_pm25          (parallel)",
        "        +--> dbt_run_gold_temperature   (parallel)",
        "        +--> dbt_run_gold_activity      (parallel)",
        "        |",
        "        v",
        "dbt_test  (16 data quality checks)",
      ]),
      p("mode='reschedule' on the sensor releases the Airflow worker slot while waiting, rather than holding it for up to an hour. The DAG is scheduled hourly but is not the production end-state — see Next Steps."),
      spacer(),

      h2("8.6  GitHub Actions as an Interim Path"),
      p("Two GitHub Actions workflows (refresh_pipeline.yml, sync_dims.yml) provide a lighter-weight orchestration option that doesn't require a self-hosted Airflow stack, useful for environments without that infrastructure available yet."),
      spacer(),
      decision_box(
        "GitHub Actions now, Airflow as the real target, dbt either way",
        "GitHub Actions is a CI tool repurposed as a scheduler — it has no native concept of a data partition, a sensor, or a DAG with branching dependencies. It works for simple linear scheduled jobs but required workarounds (a fixed sleep, no partition awareness) for anything more sophisticated.",
        "GitHub Actions cannot reach a local-only Postgres instance, so sync_dims.yml is a manual-trigger-only workflow rather than scheduled, until Postgres is hosted somewhere network-accessible."
      ),
      spacer(),

      // ─── 9. NEXT STEPS ───────────────────────────────────────────────────────
      h1("9. Next Steps"),
      bullet("Alert consumer", "Separate Kafka consumer group reading sensor-readings topic in real-time; checks pressure > 130,000 Pa; writes to alert_log with customer context"),
      bullet("Live validation of the _SUCCESS marker", "So far only validated via manually-written _SUCCESS markers. Needs a full live run of the Kafka pipeline across a real hour boundary to confirm consumer.py's automatic rollover detection fires correctly without manual intervention"),
      bullet("Host Postgres somewhere network-accessible", "Unblocks scheduling sync_dims as an automated job (Railway, Supabase, RDS) rather than manual-trigger-only"),
      bullet("Production-grade Airflow deployment", "Current Airflow stack is self-hosted via docker-compose for demonstration. Production target is a managed service (Astronomer, MWAA, Cloud Composer) with proper secrets management, alerting, and high availability"),
      bullet("Partition-aware sensing beyond S3KeySensor", "Current sensor checks for a single file's existence. A more Dataswarm-like dependency model would track partition completeness across multiple upstream tables, not just one S3 key"),
      spacer(),
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/Users/ayang2012/Desktop/IoT_Pipeline_Architecture.docx", buffer);
  console.log("Done: IoT_Pipeline_Architecture.docx");
});
