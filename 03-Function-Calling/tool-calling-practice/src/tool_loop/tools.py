from __future__ import annotations

from pathlib import Path
from learning_db import Database
from sqlalchemy import text
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .guards import validate_and_rewrite_readonly_sql
from .registry import ToolRegistry, ToolSpec


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetricArgs(StrictArgs):
    metric_name: str = Field(min_length=1, max_length=100)


class DescribeTableArgs(StrictArgs):
    table: Literal["sales", "customers"]


class SqlArgs(StrictArgs):
    sql: str = Field(min_length=1, max_length=10_000)
    max_rows: int = Field(default=100, ge=1, le=1000)


METRIC_DEFINITIONS = {
    "营业收入": {
        "definition": "不含税支付金额，扣除已完成退款",
        "version": "2.0",
        "effective_date": "2025-03-01",
    },
    "转化率": {
        "definition": "支付用户数除以独立访客数",
        "version": "2.0",
        "effective_date": "2025-01-01",
    },
}

PUBLIC_TABLE_SCHEMAS = {
    "sales": {
        "columns": {
            "order_id": "TEXT",
            "channel": "TEXT",
            "amount": "REAL",
            "order_date": "TEXT",
        },
        "description": "脱敏后的支付订单事实表",
    },
    "customers": {
        "columns": {
            "customer_id": "TEXT",
            "segment": "TEXT",
            "created_at": "TEXT",
        },
        "description": "客户分群表；email 列不对模型开放",
    },
}


class AnalyticsStore:
    def __init__(self, url: str | Path | None = None) -> None:
        self.db = Database(url)
        self.db.create_tables([
            "CREATE TABLE IF NOT EXISTS sales (order_id VARCHAR(191) PRIMARY KEY, channel VARCHAR(64) NOT NULL, amount DOUBLE NOT NULL, order_date VARCHAR(10) NOT NULL)",
            "CREATE TABLE IF NOT EXISTS customers (customer_id VARCHAR(191) PRIMARY KEY, segment VARCHAR(64) NOT NULL, email VARCHAR(191) NOT NULL, created_at VARCHAR(10) NOT NULL)",
        ])
        self._seed()

    def _seed(self) -> None:
        with self.db.transaction() as db:
            for order, channel, amount, day in [('A100', 'wechat', 120.5, '2026-07-01'), ('A101', 'douyin', 80.0, '2026-07-02'), ('A102', 'website', 260.0, '2026-07-03')]:
                self.db.insert_once(db, 'sales', 'order_id,channel,amount,order_date', ':id,:channel,:amount,:day',
                                    {'id': order, 'channel': channel, 'amount': amount, 'day': day})
            for customer, segment, email, day in [('C01', 'new', 'alice@example.com', '2026-06-01'), ('C02', 'vip', 'bob@example.com', '2025-12-15')]:
                self.db.insert_once(db, 'customers', 'customer_id,segment,email,created_at', ':id,:segment,:email,:day',
                                    {'id': customer, 'segment': segment, 'email': email, 'day': day})

    def query(self, sql: str) -> list[dict[str, object]]:
        sql = validate_and_rewrite_readonly_sql(sql, 1000)
        with self.db.connection() as db:
            if self.db.mysql:
                db.execute(text('SET SESSION MAX_EXECUTION_TIME=2000'))
                db.commit()
                db.execute(text('START TRANSACTION READ ONLY'))
            else:
                db.execute(text('PRAGMA query_only=ON'))
            try:
                return [dict(row) for row in db.exec_driver_sql(sql, execution_options={"no_parameters": True}).mappings()]
            finally:
                db.rollback()
                if not self.db.mysql:
                    db.execute(text('PRAGMA query_only=OFF'))


def get_metric_definition(args: MetricArgs) -> dict[str, object]:
    definition = METRIC_DEFINITIONS.get(args.metric_name)
    if definition is None:
        return {"found": False, "metric_name": args.metric_name}
    return {
        "found": True,
        "metric_name": args.metric_name,
        **definition,
    }


def describe_table(args: DescribeTableArgs) -> dict[str, object]:
    return {
        "table": args.table,
        **PUBLIC_TABLE_SCHEMAS[args.table],
    }


def build_default_registry(store: AnalyticsStore | None = None) -> ToolRegistry:
    analytics_store = store or AnalyticsStore()
    registry = ToolRegistry()

    registry.register(
        ToolSpec(
            name="get_metric_definition",
            description="读取公司当前采用的指标口径",
            args_model=MetricArgs,
            handler=get_metric_definition,
            required_permission="metrics:read",
            timeout_seconds=1.0,
            output_limit_bytes=2_000,
        )
    )
    registry.register(
        ToolSpec(
            name="describe_table",
            description="返回允许模型查看的裁剪后数据表结构",
            args_model=DescribeTableArgs,
            handler=describe_table,
            required_permission="schema:read",
            timeout_seconds=1.0,
            output_limit_bytes=4_000,
        )
    )

    def run_readonly_sql(args: SqlArgs) -> dict[str, object]:
        normalized_sql = validate_and_rewrite_readonly_sql(
            args.sql,
            max_rows=args.max_rows,
            allowed_tables=set(PUBLIC_TABLE_SCHEMAS),
        )
        rows = analytics_store.query(normalized_sql)
        return {
            "sql": normalized_sql,
            "row_count": len(rows),
            "rows": rows,
        }

    registry.register(
        ToolSpec(
            name="run_readonly_sql",
            description="在学习用只读数据库中运行单条受控 SELECT",
            args_model=SqlArgs,
            handler=run_readonly_sql,
            required_permission="sql:read",
            timeout_seconds=2.0,
            output_limit_bytes=8_000,
        )
    )
    return registry

