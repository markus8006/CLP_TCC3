#!/usr/bin/env python
"""Wait for the PostgreSQL service to become available."""

from __future__ import annotations

import os
import sys
import time
from typing import Tuple

import psycopg2
from psycopg2 import OperationalError
from sqlalchemy.engine.url import make_url

DEFAULT_TIMEOUT = int(os.environ.get("DB_STARTUP_TIMEOUT", "60"))
SLEEP_INTERVAL = float(os.environ.get("DB_RETRY_INTERVAL", "1"))


def _settings_from_url(url: str) -> Tuple[str, str, str, int, str]:
    parsed = make_url(url)
    username = parsed.username or os.environ.get("POSTGRES_USER", "postgres")
    password = parsed.password or os.environ.get("POSTGRES_PASSWORD", "postgres")
    host = parsed.host or os.environ.get("POSTGRES_HOST", "db")
    port = parsed.port or int(os.environ.get("POSTGRES_PORT", "5432"))
    database = parsed.database or os.environ.get("POSTGRES_DB", "postgres")
    return username, password, host, port, database


def get_connection_settings() -> Tuple[str, str, str, int, str]:
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            return _settings_from_url(url)
        except Exception:
            pass

    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    host = os.environ.get("POSTGRES_HOST", "db")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    database = os.environ.get("POSTGRES_DB") or os.environ.get("POSTGRES_DATABASE", "postgres")
    return user, password, host, port, database


def wait_for_database(timeout: int = DEFAULT_TIMEOUT) -> None:
    user, password, host, port, database = get_connection_settings()

    start_time = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            conn = psycopg2.connect(
                dbname=database,
                user=user,
                password=password,
                host=host,
                port=port,
            )
            conn.close()
            print(f"PostgreSQL disponível após {attempt} tentativas.")
            return
        except OperationalError as exc:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                print(f"Falha ao conectar ao PostgreSQL em {host}:{port} após {elapsed:.1f}s: {exc}", file=sys.stderr)
                raise SystemExit(1)
            print(
                f"Aguardando PostgreSQL em {host}:{port} (tentativa {attempt})...", file=sys.stderr
            )
            time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    wait_for_database()
