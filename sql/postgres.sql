-- Почасовая погода: первичный ключ одновременно защищает от повторов.
CREATE TABLE dim_city (
    city_id text PRIMARY KEY,
    city_name text NOT NULL,
    federal_district text NOT NULL
);

CREATE TABLE weather_hourly (
    city_id text NOT NULL REFERENCES dim_city (city_id),
    observed_at timestamptz NOT NULL,
    temp_centi smallint,
    precip_centi integer,
    is_valid boolean NOT NULL,
    batch_id smallint NOT NULL,
    PRIMARY KEY (city_id, observed_at),
    CHECK (temp_centi BETWEEN -9000 AND 6000),
    CHECK (precip_centi BETWEEN 0 AND 30000),
    CHECK (date_trunc('hour', observed_at AT TIME ZONE 'UTC') = observed_at AT TIME ZONE 'UTC')
);

-- Покрывающий индекс под фильтр города и диапазона времени.
CREATE INDEX weather_city_time_cover ON weather_hourly (city_id, observed_at)
    INCLUDE (temp_centi, precip_centi, is_valid);
-- Альтернативный доступ по датам без заданного города.
CREATE INDEX weather_time_city ON weather_hourly (observed_at, city_id);
