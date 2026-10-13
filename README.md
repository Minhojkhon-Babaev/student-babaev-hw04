# ДЗ 4 — аналитическая витрина погоды в ClickHouse

## Первый запуск

Распакуйте проект в любую папку и перейдите в неё. Ни один исполняемый файл не
использует путь автора. В macOS/Linux это `cd /ваш/путь/student-babaev-hw04`,
в Windows PowerShell — `Set-Location 'C:\ваш\путь\student-babaev-hw04'`.
Все следующие команды одинаковы для этих систем:

```sh
docker compose build runner
docker compose up -d --wait postgres clickhouse
docker compose --profile tools run --rm runner python scripts/run.py --evidence-dir evidence/my-run
docker compose --profile tools run --rm runner python scripts/verify.py --evidence-dir evidence/my-run
docker compose ps
```

`run.py` проверяет отсутствие таблиц до загрузки. Он не очищает существующие
базы. Повторный запуск загрузчика в том же проекте завершится объяснимой ошибкой.
`verify.py` повторяет контроль уже загруженных баз без изменения данных.
`evidence/my-run` сохраняет новый результат отдельно от сданного основного опыта.

Алгоритм `run.py`: создать схему → сгенерировать CSV → проверить уникальность
всего источника → загрузить историю в обе СУБД и обе MergeTree → создать MV →
однократно backfill `batch_id=0` → контроль → вставить пачку 1 → контроль →
вставить пачку 2 → контроль → `VACUUM (ANALYZE)` → прогрев и 5 повторов каждого
запроса → изолированный опыт дублей → возобновить merges.

Во время вставок новых пачек и замеров merges трёх исследуемых таблиц временно
остановлены. Чтение витрины всегда группирует её ключ и объединяет состояния.
В `finally` merges возобновляются; данные не удаляются.

## Параметры источника и локальные пути

По умолчанию: `--seed 20261013 --days 278 --cities 30 --repeats 5`.
Начало ряда фиксировано: `2024-01-01 00:00:00 UTC`. Для другого размера
передайте эти параметры `scripts/run.py` в новом Docker-проекте. Ограничения
`days>=185`, `3<=cities<=100` сохраняют смысл фиксированных SQL-профилей;
сданные численные результаты относятся только к параметрам по умолчанию.

- `.:/workspace` — относительный bind mount всего проекта для загрузчика.
- `./docker/clickhouse.xml:...:ro` — относительный конфиг ClickHouse.
- `pg_data`, `ch_data` — named volumes Docker, без host-specific путей.
- `/workspace/data/generated` — воспроизводимые временные CSV; не входят в сдачу.
- `data/examples/batch_1.csv` и `batch_2.csv` — маленькие реальные новые пачки
  основного опыта, входят в сдачу (18 и 66 строк).
- На Docker Desktop разрешите доступ к папке распакованного проекта; на Windows
  предпочтителен локальный каталог с разрешённым File Sharing или каталог WSL2.
- Межконтейнерные имена — `postgres`, `clickhouse`. Порты на хост не опубликованы,
  поэтому проект не конфликтует с установленными СУБД.
- `local_homework_only` — заведомо учебный пароль этой изолированной сети, не
  пароль какой-либо реальной системы.

## SQL и новая вставка

Готовые запросы лежат в `sql/queries/`, полный дневной контроль — в `sql/check/`.
DDL: `sql/postgres.sql`, `sql/clickhouse.sql`, `sql/mv.sql`, `sql/backfill.sql`.
Основной загрузчик выполняет `COPY` в PG и `INSERT ... FORMAT TSVWithNames` в
каждую MergeTree; MV срабатывает на вставку в `weather_city` автоматически.
Пачки уже вставлены основным прогоном — не вставляйте их вручную второй раз.

Открыть SQL и проверить витрину через CLI:

```sh
docker compose exec -T postgres psql -U student -d weather -c "SELECT count(*) FROM weather_hourly;"
docker compose exec -T clickhouse clickhouse-client --user student --password local_homework_only --query "SELECT count() FROM weather.weather_city;"
docker compose exec -T clickhouse clickhouse-client --user student --password local_homework_only --query "SELECT city_id, observed_date, sum(observations), sum(temp_sum_centi), sum(temp_count) FROM weather.weather_daily WHERE city_id='moscow' AND observed_date='2024-10-05' GROUP BY city_id, observed_date;"
```

## Остановка без удаления данных

```sh
docker compose stop
# либо для другого имени:
docker compose -p hw04-fresh-your-id stop
```

Вернуть работающие базы: `docker compose up -d --wait postgres clickhouse`.
После возвращения запускать `verify.py`, а не повторную загрузку. Named volumes
сохраняются. В работе и в инструкции не используется `down -v`.
