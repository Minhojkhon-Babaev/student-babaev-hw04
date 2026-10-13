#!/usr/bin/env python3
"""Клиенты PostgreSQL и HTTP ClickHouse; только локальная сеть Compose."""
from __future__ import annotations
import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
CH_SETTINGS = {
    "max_threads": 2,
    "max_memory_usage": 1000000000,
    "use_query_cache": 0,
    "log_queries": 1,
    "output_format_json_quote_64bit_integers": 0,
    "session_timezone": "UTC",
    "join_use_nulls": 1,
}


def connect_pg():
    connection = psycopg2.connect("")
    connection.autocommit = True
    return connection


def pg_rows(connection, query: str) -> list[list]:
    with connection.cursor() as cursor:
        cursor.execute(query)
        return (
            [list(row) for row in cursor.fetchall()]
            if cursor.description
            else []
        )


def ch_request(
    query: str,
    query_id: str | None = None,
    data: bytes | None = None,
    formatted: bool = True,
) -> tuple[dict | str, float]:
    parameters = {"database": "weather", **CH_SETTINGS}
    if query_id:
        parameters["query_id"] = query_id
    sql = query.strip().rstrip(";")
    if formatted:
        sql += "\nFORMAT JSONCompact"
    body = sql.encode() if data is None else sql.encode() + b"\n" + data
    url = os.environ["CH_URL"] + "/?" + urllib.parse.urlencode(parameters)
    credentials = (
        os.environ["CH_USER"] + ":" + os.environ["CH_PASSWORD"]
    ).encode()
    headers = {
        "Authorization": "Basic " + base64.b64encode(credentials).decode()
    }
    started = time.perf_counter_ns()
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = response.read().decode()
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode()) from error
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return (json.loads(result) if formatted else result), elapsed_ms


def ch_rows(query: str) -> list[list]:
    return ch_request(query)[0]["data"]


def ch_execute(query: str) -> None:
    ch_request(query, formatted=False)


def execute_file(connection, path: str, engine: str) -> None:
    sql = (ROOT / path).read_text(encoding="utf-8")
    if engine == "pg":
        pg_rows(connection, sql)
    else:
        for statement in sql.split(";"):
            if statement.strip():
                ch_execute(statement)


def save_json(directory: Path, name: str, value) -> None:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
