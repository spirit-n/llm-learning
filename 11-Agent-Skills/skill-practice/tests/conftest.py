import importlib.util
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parents[2] / "clickhouse-sql-review"


@pytest.fixture(scope="session")
def validator_module():
    path = SKILL_DIR / "scripts" / "validate_sql.py"
    spec = importlib.util.spec_from_file_location("clickhouse_validator_tests", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def validator(validator_module):
    return validator_module.validate_sql


@pytest.fixture(scope="session")
def skill_dir():
    return SKILL_DIR
