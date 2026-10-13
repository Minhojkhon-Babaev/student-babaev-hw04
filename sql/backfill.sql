-- Явная граница: история batch_id=0, новые пачки имеют batch_id>=1.
-- Выполнять ровно один раз, в эксклюзивном окне без конкурентных вставок.
INSERT INTO weather.weather_daily
SELECT city_id,
       toDate(observed_at, 'UTC') AS observed_date,
       count() AS observations,
       sum(toUInt64(is_valid)) AS valid_observations,
       sum(toUInt64(is_valid = 1 AND isNotNull(temp_centi))) AS temp_count,
       sum(if(is_valid = 1, ifNull(toInt64(temp_centi), 0), toInt64(0))) AS temp_sum_centi,
       sum(toUInt64(is_valid = 1 AND isNotNull(precip_centi))) AS precip_count,
       sum(if(is_valid = 1, ifNull(toUInt64(precip_centi), 0), toUInt64(0))) AS precip_sum_centi,
       min(if(is_valid = 1, temp_centi, NULL)) AS min_temp_centi,
       max(if(is_valid = 1, temp_centi, NULL)) AS max_temp_centi
FROM weather.weather_city
WHERE batch_id = 0
GROUP BY city_id, observed_date;
