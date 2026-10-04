"""Run pause/resume as two separate processes; no model or external DB call."""

import argparse
import json

from langgraph.types import Command

from .persistence import SqliteWarehouse, persistent_graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pause", "approve", "reject"])
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--thread", required=True)
    args = parser.parse_args()
    config = {"configurable": {"thread_id": args.thread}}
    try:
        with persistent_graph(args.checkpoint, args.ledger) as graph:
            snapshot = graph.get_state(config)
            if args.action == "pause":
                if snapshot.values:
                    parser.error("thread already exists; use approve/reject or a new thread ID")
                result = graph.invoke({"question": "查询昨天收入"}, config)
            else:
                if not snapshot.interrupts:
                    parser.error("thread has no pending approval; no action was executed")
                result = graph.invoke(Command(resume=args.action == "approve"), config)
        print(json.dumps({"paused": "__interrupt__" in result,
                          "status": result.get("status", "running"),
                          "execution_count": SqliteWarehouse(args.ledger).execution_count}, ensure_ascii=False))
    except RuntimeError as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
