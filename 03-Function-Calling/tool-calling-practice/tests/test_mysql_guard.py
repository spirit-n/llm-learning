import pytest

from tool_loop.guards import GuardDenied, validate_and_rewrite_readonly_sql


def test_executable_comments_are_removed_before_execution():
    rewritten = validate_and_rewrite_readonly_sql(
        "SELECT amount FROM sales /*!50000 INTO OUTFILE '/tmp/unsafe' */", 10)
    assert rewritten == "SELECT amount FROM sales LIMIT 10"


def test_untrusted_optimizer_hint_cannot_override_timeout():
    with pytest.raises(GuardDenied):
        validate_and_rewrite_readonly_sql("SELECT /*+ MAX_EXECUTION_TIME(0) */ amount FROM sales", 10)
