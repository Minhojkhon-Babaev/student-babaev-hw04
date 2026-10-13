# ДЗ 4 — аналитическая витрина погоды в ClickHouse

Самодостаточный эксперимент на синтетических почасовых наблюдениях: PostgreSQL,
две сортировки MergeTree, инкрементальная витрина `город × сутки UTC`.
Продолжает погодную предметную область ДЗ 1–3. Внешние погодные API не нужны.

Результат и ограничения: [report.md](report.md). Полный основной прогон и
повтор в новом Compose-проекте сохранены в `evidence/main/` и `evidence/clean/`.

## Требования и версии

- Docker Desktop на macOS / Windows, режим **Linux containers**, либо Docker
  Engine + Compose на Linux. Фактическая проверка: macOS 26.4, Apple ARM64,
  Colima, Docker Engine 29.5.2, Compose 5.5.1, VM 6 CPU / 12 ГиБ.
- Для двух СУБД и загрузчика выделить Docker не менее 6 CPU / 8 ГиБ RAM;
  рекомендуется 12 ГиБ. Если ресурсы меньше, изменённые лимиты записать в отчёт.
- PostgreSQL **16.4**, ClickHouse **24.8.14.39**, Python **3.12.14**,
  `psycopg2-binary==2.9.10`. Образы закреплены digest в Compose / Dockerfile;
  проверено наличие Linux ARM64 и AMD64 в manifest index.
- Интернет нужен для первого получения образов и Python wheel. Docker build
  cache допускается: чистый опыт означает новые базы и volumes, а не пересборку
  всех базовых образов без кэша.
- Python на хосте не требуется: код выполняется сервисом `runner`.

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

## Ещё один чистый Docker-проект

Выберите ранее не использовавшееся имя проекта. Оно определяет отдельные сеть,
контейнеры и named volumes, поэтому старые данные сохраняются:

```sh
docker compose -p hw04-fresh-your-id build runner
docker compose -p hw04-fresh-your-id up -d --wait postgres clickhouse
docker compose -p hw04-fresh-your-id --profile tools run --rm runner python scripts/run.py --evidence-dir evidence/my-clean-run
docker compose -p hw04-fresh-your-id --profile tools run --rm runner python scripts/verify.py --evidence-dir evidence/my-clean-run
```

Не запускайте опыты параллельно: они разделяют ресурсы Docker, а генератор
пишет один каталог `data/generated`. Сданный повтор использовал имя
`hw04-clean-20261013`; подтверждения создания новых volumes, полный вывод и
проверки находятся в `evidence/clean/`.

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

Последний ответ: `moscow / 2024-10-05 / 24 / 60000 / 24`, то есть средняя **25 °C**.
Доказательства перехода 6 → 24 наблюдения сохранены в
`evidence/main/checks/incremental.json`; первые 12 часов Москвы 4 октября
доставляются поздно и обновляют существующий день.

`sql/new_batch_example.sql` — дополнительная иллюстрация вставки двух новых
часов **только в ClickHouse** с ожидаемым результатом MV. Это отдельный ручной
пример после опыта; он меняет сравниваемый набор и не входит в основной прогон.
Для контрольного эксперимента используются именно обе CSV-пачки через `run.py`.

## Остановка без удаления данных

```sh
docker compose stop
# либо для другого имени:
docker compose -p hw04-fresh-your-id stop
```

Вернуть работающие базы: `docker compose up -d --wait postgres clickhouse`.
После возвращения запускать `verify.py`, а не повторную загрузку. Named volumes
сохраняются. В работе и в инструкции не используется `down -v`.

## Состав сдачи

`report.md`, Compose / Dockerfile / конфиг, `scripts/`, `sql/`, маленькие
`data/examples/`, исходные замеры и проверки в `evidence/`, браузерные скриншоты
их фактического вывода в `evidence/screenshots/`. Представление снимков можно
пересоздать скриптом `scripts/render_evidence.py`; HTML исходники остаются рядом.
Снимки дополняют JSON/CSV/SQL и не заменяют их.

Большие CSV истории генерируются заново; Docker volumes, `.git`, локальные env
и Python cache не включаются в архив. После частичной ошибки между PG и CH
нет распределённой транзакции: не повторяйте загрузку вслепую; используйте новое
имя Compose-проекта и отдельный каталог evidence, сохранив предыдущий опыт.
