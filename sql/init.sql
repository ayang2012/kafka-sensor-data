CREATE TABLE IF NOT EXISTS customers (
    customer_id   SERIAL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    region        VARCHAR(50)  NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_sensors (
    sensor_id    BIGINT PRIMARY KEY,
    sensor_type  VARCHAR(50),
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    country      VARCHAR(10),
    region       VARCHAR(50),
    customer_id  INTEGER REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS alert_log (
    id          SERIAL PRIMARY KEY,
    sensor_id   BIGINT       NOT NULL,
    alert_type  VARCHAR(50)  NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (sensor_id, alert_type)
);

INSERT INTO customers (customer_name, region) VALUES
    ('AirWatch EU North',    'Europe'),
    ('AirWatch EU South',    'Europe'),
    ('ClimaCorp Americas',   'North America'),
    ('SkyNet Americas',      'North America'),
    ('AirWatch APAC',        'Asia-Pacific'),
    ('ClimaCorp Other',      'Other')
ON CONFLICT DO NOTHING;
