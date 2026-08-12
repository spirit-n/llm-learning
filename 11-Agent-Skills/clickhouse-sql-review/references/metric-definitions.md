# Metric-definition reference

Load this reference only when the request names a target metric.

| Metric | Required fields | Definition |
|---|---|---|
| `success_rate` | approved `success_rate`, or `success_count` + `request_count` | approved materialized field, or `success_count / request_count` with zero-denominator handling |
| `revenue` | `revenue` | approved net, tax-exclusive revenue field |
| `active_users` | `user_id` | `count(DISTINCT user_id)` for authorized users in the requested period |

The validator verifies registered fields and the key expression shape for `success_rate`/`active_users`. It cannot prove business facts such as filters, time zone, refund status, denominator version, or upstream field lineage; confirm those with the owning metric catalog before production execution.
