CREATE OR REPLACE TABLE SENSOR_DATA.GOLD.PM25_BY_COUNTRY_HOUR AS
SELECT
    DATE_TRUNC('hour', f.ingested_at)      AS hour,
    COALESCE(ds.country, f.country)        AS country,
    COALESCE(dc.region, 'Unknown')         AS region,
    COALESCE(dc.customer_name, 'Unknown')  AS customer_name,
    COUNT(*)                               AS reading_count,
    ROUND(AVG(f.pm25), 3)                  AS avg_pm25,
    ROUND(MAX(f.pm25), 3)                  AS max_pm25,
    ROUND(MIN(f.pm25), 3)                  AS min_pm25,
    ROUND(AVG(f.pm10), 3)                  AS avg_pm10,
    ROUND(MAX(f.pm10), 3)                  AS max_pm10
FROM SENSOR_DATA.SILVER.SENSOR_READINGS f
LEFT JOIN SENSOR_DATA.SILVER.DIM_SENSORS ds
    ON f.sensor_id = ds.sensor_id
LEFT JOIN SENSOR_DATA.SILVER.DIM_CUSTOMERS dc
    ON ds.customer_id = dc.customer_id
WHERE f.pm25 IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY hour DESC, avg_pm25 DESC;
