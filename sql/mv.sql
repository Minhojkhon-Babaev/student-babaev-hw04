-- Создаётся после загрузки истории, перед backfill, пока нет других писателей.
CREATE MATERIALIZED VIEW weather.weather_daily_mv TO weather.weather_daily AS
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
GROUP BY city_id, observed_date;
