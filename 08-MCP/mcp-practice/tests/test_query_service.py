from mcp_lab.models import Principal
from mcp_lab.service import QueryService, SchemaService


def principal(*scopes: str) -> Principal:
    return Principal(actor_id="learner", tenant="tenant-a", scopes=frozenset(scopes))


def test_service_projects_only_requested_columns_and_forces_limit():
    service = QueryService()
    result = service.execute(
        sql="SELECT day, revenue FROM analytics.daily_metrics",
        principal=principal("query:execute"),
        request_id="req-1",
        max_rows=1,
    )

    assert result.ok is True
    assert result.row_count == 1
    assert set(result.rows[0]) == {"day", "revenue"}
    assert "LIMIT 1" in result.normalized_sql


def test_idempotent_replay_returns_cache_but_conflicting_payload_is_rejected():
    service = QueryService()
    actor = principal("query:execute")
    kwargs = {
        "sql": "SELECT day FROM analytics.public_metrics",
        "principal": actor,
        "request_id": "same-key",
    }

    first = service.execute(**kwargs)
    replay = service.execute(**kwargs)
    conflict = service.execute(**{**kwargs, "sql": "SELECT success_rate FROM analytics.public_metrics"})

    assert first.cached is False
    assert replay.cached is True
    assert conflict.error.code == "IDEMPOTENCY_CONFLICT"
    assert [event["status"] for event in service.audit_log] == [
        "success",
        "idempotent_replay",
        "rejected",
    ]


def test_idempotency_key_is_scoped_to_actor_and_authorization_context():
    service = QueryService()
    common = {
        "sql": "SELECT day FROM analytics.public_metrics",
        "request_id": "same-key",
    }
    first = service.execute(**common, principal=principal("query:execute"))
    other_actor = service.execute(
        **common,
        principal=Principal(
            actor_id="other", tenant="tenant-a", scopes=frozenset({"query:execute"})
        ),
    )
    reduced_scope = service.execute(
        **common,
        principal=Principal(
            actor_id="learner",
            tenant="tenant-a",
            scopes=frozenset({"query:execute", "extra:scope"}),
        ),
    )
    assert not first.cached and not other_actor.cached and not reduced_scope.cached
    assert [event["status"] for event in service.audit_log] == ["success"] * 3


def test_missing_scope_is_rejected_and_raw_sql_is_not_audited():
    service = QueryService()
    sql = "SELECT day FROM analytics.public_metrics"

    result = service.execute(sql=sql, principal=principal(), request_id="req-2")

    assert result.error.code == "SCOPE_REQUIRED"
    assert sql not in str(service.audit_log)
    assert service.audit_log[0]["actor_id"] == "learner"


def test_schema_service_rechecks_scope_and_redacts_sensitive_column_name():
    service = SchemaService()
    denied = service.describe("analytics", "daily_metrics", principal())
    allowed = service.describe(
        "analytics", "daily_metrics", principal("schema:read")
    )
    assert denied.error.code == "SCOPE_REQUIRED"
    assert allowed.ok is True
    assert "customer_email" not in allowed.columns
    assert allowed.redacted_column_count == 1
