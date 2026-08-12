"""MCP 之外的领域数据，方便独立单测和复用。"""

METRICS = {
    "success_rate": {
        "name": "success_rate",
        "definition": "成功请求数 / 总请求数",
        "version": "v2",
    },
    "revenue": {
        "name": "revenue",
        "definition": "不含税支付金额 - 已完成退款",
        "version": "v3",
    },
}

SCHEMAS = {
    ("analytics", "daily_metrics"): {
        "columns": ["day", "tenant_id", "revenue", "success_count", "request_count", "customer_email"],
        "sensitive_columns": ["customer_email"],
    },
    ("analytics", "public_metrics"): {
        "columns": ["day", "success_rate"],
        "sensitive_columns": [],
    },
}

TENANT_TABLES = {
    "tenant-a": {"analytics.daily_metrics", "analytics.public_metrics"},
    "tenant-b": {"analytics.public_metrics"},
}

FIXTURE_ROWS = [
    {"day": "2026-07-31", "revenue": 128000.0, "success_count": 980, "request_count": 1000},
    {"day": "2026-07-30", "revenue": 121500.0, "success_count": 960, "request_count": 1000},
]


def metric_definition(metric_name: str) -> dict:
    metric = METRICS.get(metric_name)
    if metric is None:
        return {"ok": False, "error": {"code": "METRIC_NOT_FOUND", "message": "未知指标"}}
    return {"ok": True, "metric": metric}


def table_schema(database: str, table: str) -> dict:
    schema = SCHEMAS.get((database, table))
    if schema is None:
        return {"ok": False, "error": {"code": "TABLE_NOT_FOUND", "message": "表不存在或不可见"}}
    return {"ok": True, "database": database, "table": table, **schema}

