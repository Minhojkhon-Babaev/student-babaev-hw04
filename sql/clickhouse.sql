CREATE TABLE weather.dim_city (
    city_id String,
    city_name String,
    federal_district LowCardinality(String)
) ENGINE = MergeTree ORDER BY city_id;

-- ORDER BY не обеспечивает уникальность бизнес-ключа.
CREATE TABLE weather.weather_city (
    city_id LowCardinality(String),
    observed_at DateTime('UTC'),
    temp_centi Nullable(Int16),
    precip_centi Nullable(UInt16),
    is_valid UInt8,
    batch_id UInt16,
    CONSTRAINT temperature_range CHECK isNull(temp_centi) OR (temp_centi >= -9000 AND temp_centi <= 6000),
    CONSTRAINT precipitation_range CHECK isNull(precip_centi) OR precip_centi <= 30000,
    CONSTRAINT validity_range CHECK is_valid IN (0, 1),
    CONSTRAINT hour_alignment CHECK toStartOfHour(observed_at) = observed_at
) ENGINE = MergeTree
ORDER BY (city_id, observed_at)
SETTINGS index_granularity = 8192;

CREATE TABLE weather.weather_time AS weather.weather_city
ENGINE = MergeTree
ORDER BY (observed_at, city_id)
SETTINGS index_granularity = 8192;

-- Инкрементальная витрина: город × сутки UTC, только сливаемые агрегаты.
CREATE TABLE weather.weather_daily (
    city_id LowCardinality(String),
    observed_date Date,
    observations SimpleAggregateFunction(sum, UInt64),
    valid_observations SimpleAggregateFunction(sum, UInt64),
    temp_count SimpleAggregateFunction(sum, UInt64),
    temp_sum_centi SimpleAggregateFunction(sum, Int64),
    precip_count SimpleAggregateFunction(sum, UInt64),
    precip_sum_centi SimpleAggregateFunction(sum, UInt64),
    min_temp_centi SimpleAggregateFunction(min, Nullable(Int16)),
    max_temp_centi SimpleAggregateFunction(max, Nullable(Int16))
) ENGINE = AggregatingMergeTree
ORDER BY (city_id, observed_date)
SETTINGS index_granularity = 8192;
