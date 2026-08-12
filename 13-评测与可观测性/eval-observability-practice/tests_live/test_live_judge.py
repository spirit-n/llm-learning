import sys
from pathlib import Path

import pytest

from eval_lab.app import DemoMetricAgent
from eval_lab.dataset import load_dataset
from eval_lab.judge import judge_contract_instruction, parse_judge_decision
from eval_lab.models import EvalInput


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import LiveLLMSettings, OpenAICompatibleChatClient, parse_json_content  # noqa: E402


pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    ("reverse_critical_fact", "expected_pass"),
    [(False, True), (True, False)],
    ids=["correct-definition", "reversed-numerator-denominator"],
)
def test_live_judge_obeys_strict_contract_and_rejects_critical_fact_error(
    reverse_critical_fact: bool,
    expected_pass: bool,
):
    case = load_dataset(PROJECT_ROOT / "evals" / "datasets" / "metric_agent_v1.jsonl")[0]
    trace = DemoMetricAgent("candidate").run(EvalInput(case_id=case.id, user_input=case.input))
    if reverse_critical_fact:
        # 两个关键词都还在，只把分子分母颠倒；这能抓出“关键词命中但事实相反”的 Judge 漏洞。
        trace = trace.model_copy(update={"output": "成功率 = 总请求数 / 成功请求数。"})

    message = OpenAICompatibleChatClient(LiveLLMSettings.from_env()).chat(
        [
            {
                "role": "system",
                "content": (
                    "你是独立评测器。只根据 rubric 和给定 trace 评分，不补充外部事实。"
                    "关键事实错误必须 passed=false，并写入 critical_fact_errors。"
                    + judge_contract_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    "rubric：成功率定义必须明确说明分子是成功请求数、分母是总请求数；"
                    "两者颠倒属于关键事实错误。不得声称调用未记录的工具。\n"
                    f"用户问题={case.input}\ntrace={trace.model_dump_json()}"
                ),
            },
        ],
        temperature=0,
    )
    # parse_json_content 只负责 JSON 语法；Pydantic 再负责字段、类型、范围及额外字段校验。
    decision = parse_judge_decision(parse_json_content(message))
    assert decision.passed is expected_pass, decision
    assert decision.reasons
    if reverse_critical_fact:
        assert decision.critical_fact_errors, decision
    else:
        assert decision.critical_fact_errors == [], decision
