---
name: clickhouse-sql-review
description: Review model-generated or human-written ClickHouse analytics SQL for read-only safety, tenant table and column permissions, bounded LIMIT and OFFSET, dangerous functions, query settings, and metric-expression consistency. Use before executing ClickHouse SELECT queries or when asked to inspect, approve, reject, explain, or repair analytics SQL. Do not use for executing SQL, changing permissions, generating unrelated SQL, or reviewing non-SQL code.
---

# ClickHouse SQL Review

Review SQL without executing it. Treat the validator as a preflight policy check, not as the database's final security boundary.

## Require inputs

Collect:

- SQL text.
- Tenant or caller identity.
- Target metric when the query implements a business metric.
- Environment (`dev`, `staging`, or `prod`).

If SQL or tenant is missing, stop and request it. Do not infer permissions. If the user only asks to execute SQL and does not request review, do not activate this Skill.

## Run the deterministic review

Run from the skill directory:

```powershell
python scripts/validate_sql.py --sql "SELECT day, revenue FROM analytics.daily_metrics LIMIT 100" --tenant tenant-a --metric revenue --environment dev
```

The command prints JSON and exits with code `2` for `reject`. Use its result as the source of truth for parsing, statement shape, tenant table/column access, dangerous functions, environment-specific LIMIT, OFFSET, query settings, and registered metric expressions. Never turn `reject` into `pass` through natural-language reasoning.

The validator intentionally rejects unsupported roots such as `UNION` and `EXPLAIN` until their complete policy is implemented. “Read-only looking” is not the same as “covered by this validator.”

## Load references only as needed

- Read [references/clickhouse-rules.md](references/clickhouse-rules.md) when a query uses ClickHouse-specific functions, `FINAL`, joins, windows, dictionaries, table functions, query settings, or external data sources.
- Read [references/sensitive-columns.md](references/sensitive-columns.md) only when explaining table/column authorization or proposing a safe projection.
- Read [references/metric-definitions.md](references/metric-definitions.md) only when `--metric` is provided or the user asks about business semantics.
- Read [references/failure-cases.md](references/failure-cases.md) when explaining a stable reason code or constructing a minimal repair.

Do not scan every reference up front. Do not load unlinked or hidden files. Resolve every resource relative to this Skill directory and reject absolute paths, `..`, backslash traversal, and symbolic-link escape.

## Report

Return:

1. `decision`: `pass` or `reject` from the validator.
2. `reason_codes`: stable codes from the validator.
3. `evidence`: offending statement shape, table, column, function, limit, offset, setting, or metric requirement.
4. `suggested_fix`: the smallest repair that does not broaden access.
5. `warnings`: expensive but not automatically forbidden shapes that still need execution budgets.
6. `normalized_sql`: include only for passing queries.
7. `policy_version` and `environment`: preserve them for audit and replay.

State that a passing result means “eligible for the execution-side Guard,” not “already safe to execute.” Warnings never override a rejection and never replace execution-side limits.

## Preserve runtime boundaries

- Never execute SQL or connect to a database.
- Never grant access, reveal hidden schema, or weaken tenant rules.
- Never place credentials or raw sensitive values in the report.
- Never import or execute a script that is not explicitly named in this Skill.
- Require the execution service to repeat authorization, AST checks, LIMIT/timeout/scan limits, and audit logging with a read-only database account.
- Reject ambiguous parsing or unsupported query shapes instead of guessing.
