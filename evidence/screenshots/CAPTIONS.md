# Скриншоты ДЗ 4

Сняты headless Google Chrome через Playwright с HTML, созданных
`scripts/render_evidence.py` из фактических результатов выполненного опыта.
Это браузерный evidence-viewer, а не интерфейс СУБД. Запросы, планы и ответы
читаемы в полном размере PNG. Исходный HTML каждого снимка сохранён рядом;
JSON/CSV/TXT, по которым он построен, остаются в `evidence/main/` и `clean/`.

1. [01_environment.png](01_environment.png) — `docker compose ps`: обе СУБД
   healthy, версии, лимиты и выполненные SELECT, по 200232 строк и уникальных
   ключей в PostgreSQL/ClickHouse. [HTML](01_environment.html).
2. [02_plans_narrow.png](02_plans_narrow.png) — полный выборочный SQL, Index Only
   Scan / Heap Fetches=0 / BUFFERS в PG, PrimaryKey / Granules=1/26 и pipeline CH.
   [HTML](02_plans_narrow.html).
3. [02b_plans_wide.png](02b_plans_wide.png) — широкий SQL с JOIN, Seq Scan /
   Hash Join / HashAggregate в PG и планы широкого CH.
   [HTML](02b_plans_wide.html).
4. [03_equality.png](03_equality.png) — полный перенос всех полей, SHA256,
   совпадение всех ключей и 9 метрик четырёх вариантов с независимым CSV-расчётом,
   проверки после истории / обеих пачек / возобновления merges и исполненный
   полный дневной SQL. [HTML](03_equality.html).
5. [04_incremental.png](04_incremental.png) — новые вставки, 6→24 измерения
   Москвы, правильная средняя 10→25 °C, объединение нескольких частей до merges,
   короткий выполненный SELECT с фактическим ответом. [HTML](04_incremental.html).
6. [05_replay.png](05_replay.png) — отдельный опыт повторных шести часов:
   24→30, средняя 25→22 °C; PostgreSQL отклоняет PK-дубль, SQLSTATE 23505.
   [HTML](05_replay.html).
7. [06_measurements.png](06_measurements.png) — пять повторов каждого из 12
   вариантов, min/median/max, чтение, условия прогрева, полный PASS чистого
   Compose-проекта. [HTML](06_measurements.html).

Пересоздать HTML без доступа к СУБД:

```sh
docker compose --profile tools run --rm runner python scripts/render_evidence.py
```

Для пересъёмки PNG дополнительно нужны Node.js, Playwright и Google Chrome;
это необязательные зависимости оформления, сам эксперимент их не использует:

```sh
node scripts/capture_screenshots.cjs
```
