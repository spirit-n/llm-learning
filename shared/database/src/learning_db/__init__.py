"""Shared persistent database configuration. SQLite is explicit and test-only."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool, StaticPool

DatabaseError = SQLAlchemyError


def database_url(value: str | Path | None = None) -> str:
    if value is not None:
        value = str(value)
        if "://" in value:
            return value
        if value == ":memory:":
            return "sqlite:///:memory:"
        path = Path(value).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + path.as_posix()
    # Environment wins; search upwards from the caller's working directory.
    for directory in [Path.cwd(), *Path.cwd().parents]:
        config = directory / ".env"
        if config.exists():
            load_dotenv(config, override=False)
            break
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 未配置；参见 shared/database/README.md")
    if make_url(url).get_backend_name() != "mysql":
        raise ValueError("DATABASE_URL 必须使用 mysql+pymysql；离线测试请显式传入 SQLite 路径")
    return url


class Database:
    def __init__(self, url: str | Path | None = None):
        self.url = database_url(url)
        options = {"pool_pre_ping": True, "pool_recycle": 1800}
        if self.url.startswith("mysql"):
            options["connect_args"] = {"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10}
        else:
            options["poolclass"] = StaticPool if self.url.endswith(":memory:") else NullPool
            if self.url.endswith(":memory:"):
                options["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(self.url, **options)
        self.mysql = self.engine.dialect.name == "mysql"

    @contextmanager
    def transaction(self):
        with self.engine.connect() as connection:
            # Serialize SQLite test writers; MySQL uses row locks in each store.
            if not self.mysql:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @contextmanager
    def connection(self):
        with self.engine.connect() as connection:
            yield connection

    def create_tables(self, statements: list[str]):
        with self.transaction() as connection:
            for statement in statements:
                suffix = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin" if self.mysql else ""
                connection.execute(text(statement + suffix))

    def insert_once(self, connection, table: str, columns: str, values: str, params: dict):
        # Identifiers come only from application constants, never from user SQL.
        key = columns.split(",")[0].strip()
        clause = f"ON DUPLICATE KEY UPDATE {key}={key}" if self.mysql else "ON CONFLICT DO NOTHING"
        connection.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({values}) {clause}"), params)

    @property
    def for_update(self):
        return " FOR UPDATE" if self.mysql else ""

    def close(self):
        self.engine.dispose()
