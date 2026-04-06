from __future__ import annotations

import asyncio
from executor import get_executor, Task, TaskType, TaskStatus
from memory import get_memory


async def _run_reliability() -> dict:
    exe = get_executor()
    mem = get_memory()
    tid = "eval_reliability_checkpoint"
    task = Task(id=tid, typ=TaskType.CHAT, prompt="checkpoint test", beschreibung="checkpoint test")
    task.status = TaskStatus.RUNNING
    task.iteration = 2
    exe._tasks[tid] = task
    exe._checkpoint(task, "tool_running", tool_snapshot={"tool": "search_web"}, result_snapshot={"partial": True}, side_effect_refs=["search:checkpoint test"])
    cp = mem.get_latest_checkpoint(tid)
    task.status = TaskStatus.RESUMABLE
    ok_resume = exe.resume_task(tid)
    task2 = exe.get_task(tid)
    cases = [
        {"name": "checkpoint_written", "ok": bool(cp and cp.get("state_name") == "tool_running"), "detail": cp or {}},
        {"name": "task_resumable", "ok": bool(ok_resume and task2 and task2.status == TaskStatus.QUEUED), "detail": task2.to_dict() if task2 else {}},
    ]
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "reliability", "passed": passed, "total": len(cases), "cases": cases}


def run() -> dict:
    return asyncio.run(_run_reliability())


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
