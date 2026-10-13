-- Самодостаточный пример для отдельного чистого проекта после основного опыта.
-- Ключ свободен при параметрах генератора по умолчанию. Выполнять один раз.
INSERT INTO weather.weather_city VALUES
    ('moscow', '2025-01-01 00:00:00', 1000, 25, 1, 3),
    ('moscow', '2025-01-01 01:00:00', 3000, 75, 1, 3);

SELECT city_id, observed_date, sum(observations) AS observations,
       sum(temp_sum_centi) AS temp_sum_centi, sum(temp_count) AS temp_count,
       sum(precip_sum_centi) AS precip_sum_centi
FROM weather.weather_daily
WHERE city_id = 'moscow' AND observed_date = '2025-01-01'
GROUP BY city_id, observed_date;
-- Ожидается: moscow / 2025-01-01 / 2 / 4000 / 2 / 100.
-- В основном опыте реальные новые пачки из data/examples загружаются в обе СУБД.
