from .models import PlanDecision, TaskSpec, UserContext
from .planner import ScriptedPlanner
from .runtime import AgentHarness
from .tools import build_demo_registry
from .verifiers import verify_metric_answer


def main() -> None:
    planner = ScriptedPlanner(
        [
            PlanDecision(kind="tool", tool_name="query_metric", arguments={"metric_name": "success_rate", "tenant": "tenant-a"}),
            PlanDecision(kind="final", answer="tenant-a 昨日成功率为 98%。"),
        ]
    )
    task = TaskSpec(
        task_id="demo-001",
        objective="查询昨日成功率",
        expected_metric="success_rate",
        allowed_tools=frozenset({"query_metric"}),
    )
    user = UserContext(
        user_id="learner",
        tenant="tenant-a",
        permissions=frozenset({"metrics:query"}),
    )
    result = AgentHarness(build_demo_registry(), verify_metric_answer).run(planner, task, user)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
