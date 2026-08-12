# Validator failure cases

Load this reference only after the deterministic validator returns `reject`, or when adding a regression case.

| Reason code | Typical cause | Minimal repair |
|---|---|---|
| `EMPTY_SQL` / `SQL_PARSE_ERROR` | Empty or ambiguous syntax | Submit one parseable statement |
| `MULTI_STATEMENT` | More than one parsed statement | Submit each query separately |
| `READ_ONLY_SELECT_REQUIRED` | DML/DDL, `UNION`, `EXPLAIN`, or unsupported root | Rewrite as one supported SELECT; extend code + tests before allowing a new shape |
| `TABLE_FORBIDDEN` / `COLUMN_FORBIDDEN` | Outside tenant/table-column allowlist | Use an authorized table and minimum projection |
| `SENSITIVE_COLUMN` / `STAR_FORBIDDEN` | Raw secret field or implicit schema expansion | Remove the field and explicitly list approved columns |
| `DANGEROUS_FUNCTION` | External I/O/database or delay function | Remove the function; provide data through an authorized tool |
| `LIMIT_REQUIRED` / `LIMIT_TOO_LARGE` / `DYNAMIC_LIMIT` | Unbounded or caller-controlled result size | Add an environment-bounded positive literal LIMIT |
| `OFFSET_TOO_LARGE` / `DYNAMIC_OFFSET` | Expensive or caller-controlled deep page | Use bounded literal OFFSET or keyset pagination |
| `QUERY_SETTINGS_FORBIDDEN` | SQL tries to change runtime resource settings | Remove SETTINGS; enforce them in the execution service |
| `UNKNOWN_METRIC` / `METRIC_MISMATCH` | Missing catalog definition or fields | Select a registered metric and required approved fields |
| `METRIC_EXPRESSION_MISMATCH` | Fields exist but formula is wrong | Use the exact approved division/distinct-count shape |

A repaired query must go through the validator again. Do not edit the JSON decision by hand. If the parser or policy does not cover the requested SQL shape, keep it rejected and add a focused implementation plus positive/negative tests first.
