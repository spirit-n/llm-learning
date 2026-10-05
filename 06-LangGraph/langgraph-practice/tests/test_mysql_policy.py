from lg_lab.sql_policy import inspect_sql


def test_sql_for_execution_contains_only_validated_ast():
    policy = inspect_sql(
        "SELECT revenue FROM daily_metrics LIMIT 1 /*!50000 INTO OUTFILE '/tmp/unsafe' */",
        allowed_tables={"daily_metrics"},
    )
    assert policy.allowed
    assert policy.normalized_sql == "SELECT revenue FROM daily_metrics LIMIT 1"


def test_untrusted_optimizer_hint_is_rejected():
    policy = inspect_sql("SELECT /*+ MAX_EXECUTION_TIME(0) */ revenue FROM daily_metrics LIMIT 1",
                         allowed_tables={"daily_metrics"})
    assert not policy.allowed
