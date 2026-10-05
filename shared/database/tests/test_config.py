import pytest

from learning_db import Database, database_url
from sqlalchemy import text


def test_unconfigured_default_never_silently_uses_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("learning_db.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()


def test_environment_rejects_sqlite_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(ValueError, match="mysql"):
        database_url()


def test_explicit_offline_database_rolls_back(tmp_path):
    db = Database(tmp_path / "test.sqlite")
    db.create_tables(["CREATE TABLE sample (id INTEGER PRIMARY KEY)"])
    with pytest.raises(RuntimeError):
        with db.transaction() as c:
            c.execute(text("INSERT INTO sample VALUES (1)"))
            raise RuntimeError("rollback")
    with db.connection() as c:
        assert c.execute(text("SELECT COUNT(*) FROM sample")).scalar_one() == 0
