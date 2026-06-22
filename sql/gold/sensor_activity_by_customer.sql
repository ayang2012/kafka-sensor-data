CREATE OR REPLACE TABLE SENSOR_DATA.GOLD.SENSOR_ACTIVITY_BY_CUSTOMER AS
SELECT
    DATE_TRUNC('day', f.ingested_at)       AS day,
    COALESCE(dc.customer_name, 'Unknown')  AS customer_name,
    COALESCE(dc.region, 'Unknown')         AS region,
    f.sensor_type,
    COUNT(DISTINCT f.sensor_id)            AS active_sensors,
    COUNT(*)                               AS total_readings,
    ROUND(COUNT(*) / COUNT(DISTINCT f.sensor_id), 1) AS avg_readings_per_sensor
FROM SENSOR_DATA.SILVER.SENSOR_READINGS f
LEFT JOIN SENSOR_DATA.SILVER.DIM_SENSORS ds
    ON f.sensor_id = ds.sensor_id
LEFT JOIN SENSOR_DATA.SILVER.DIM_CUSTOMERS dc
    ON ds.customer_id = dc.customer_id
GROUP BY 1, 2, 3, 4
ORDER BY day DESC, total_readings DESC;
