# ClickHouse review rules

Load this reference for ClickHouse-specific syntax or external data access.

- Allow one parsed query whose root is `SELECT` only. Comments and casing must not change the result. Reject unsupported roots such as `UNION`/`EXPLAIN` until a complete policy is implemented.
- Reject table functions and functions that can reach files, URLs, remote servers, external databases, object storage, HDFS, or deliberate delays: `file`, `url`, `remote`, `remoteSecure`, `s3`, `hdfs`, `azureBlobStorage`, `mysql`, `postgresql`, `jdbc`, `odbc`, `sleep`.
- Require a positive literal `LIMIT`: dev ≤ 1000, staging ≤ 500, prod ≤ 200. Reject dynamic limits.
- Reject offsets over 10,000 and dynamic offsets. Prefer keyset pagination for deep pages.
- Reject query-level `SETTINGS`; the execution service owns timeout, memory, thread, scan, and result limits.
- Treat `FINAL`, dictionary access, joins, nested subqueries, large `GROUP BY`, and unbounded windows as scan-cost warnings requiring execution-side budgets.
- Reject on parse ambiguity. Do not fall back to `startswith("select")`.
- Re-run the same checks in the execution service using a read-only database account.
