CREATE OR REPLACE TABLE SENSOR_DATA.GOLD.TEMPERATURE_BY_REGION_DAY AS
SELECT
    DATE_TRUNC('day', f.ingested_at)       AS day,
    COALESCE(dc.region, 'Unknown')         AS region,
    COALESCE(dc.customer_name, 'Unknown')  AS customer_name,
    f.sensor_type,
    COUNT(*)                               AS reading_count,
    ROUND(AVG(f.temperature), 3)           AS avg_temperature,
    ROUND(MAX(f.temperature), 3)           AS max_temperature,
    ROUND(MIN(f.temperature), 3)           AS min_temperature,
    ROUND(AVG(f.humidity), 3)              AS avg_humidity,
    ROUND(AVG(f.pressure), 3)             AS avg_pressure
FROM SENSOR_DATA.SILVER.SENSOR_READINGS f
LEFT JOIN SENSOR_DATA.SILVER.DIM_SENSORS ds
    ON f.sensor_id = ds.sensor_id
LEFT JOIN SENSOR_DATA.SILVER.DIM_CUSTOMERS dc
    ON ds.customer_id = dc.customer_id
WHERE f.temperature IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY day DESC, region, sensor_type;
