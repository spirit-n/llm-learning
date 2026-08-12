# Tenant and sensitive-column reference

Load this reference only for access-control findings.

| Tenant | Allowed tables |
|---|---|
| `tenant-a` | `analytics.daily_metrics`, `analytics.orders`, `analytics.public_metrics` |
| `tenant-b` | `analytics.public_metrics` |

The practice validator also applies a table-column allowlist:

- `analytics.daily_metrics`: `day`, `revenue`, `success_count`, `request_count`, `success_rate`
- `analytics.orders`: `day`, `order_id`, `user_id`, `revenue`, `status`
- `analytics.public_metrics`: `day`, `success_rate`, `success_count`, `request_count`

Never select these raw columns:

- `customer_email`
- `phone`
- `api_secret`
- `password_hash`

Reject `SELECT *` because it makes field-level authorization and schema changes unsafe. Prefer explicit, minimum projections and approved aggregates. Do not reveal the contents of denied tables or columns in an error.
