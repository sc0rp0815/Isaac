from __future__ import annotations

import asyncio
from executor import get_executor, Task, TaskType, TaskStatus
from memory import get_memory


async def _run_replay() -> dict:
    exe = get_executor()
    mem = get_memory()
    tid = 'eval_replay_ai'
    task = Task(id=tid, typ=TaskType.CHAT, prompt='resume me', beschreibung='resume me')
    task.status = TaskStatus.RESUMABLE
    exe._tasks[tid] = task
    mem.save_task_checkpoint(
        tid, 'evaluating',
        input_snapshot={'task_id': tid, 'typ': 'chat', 'prompt': 'resume me', 'iteration': 0, 'status': 'evaluating'},
        result_snapshot={'answer_preview': 'short answer', 'answer_full': 'short answer', 'provider': 'test-provider'},
    )
    ok = await exe._resume_from_checkpoint(task)
    cases = [
        {'name': 'resume_from_evaluating', 'ok': bool(ok), 'detail': task.to_dict()},
        {'name': 'resume_completed_state', 'ok': task.status in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.BLOCKED}, 'detail': task.status.value},
    ]
    passed = sum(1 for c in cases if c['ok'])
    return {'suite': 'replay', 'passed': passed, 'total': len(cases), 'cases': cases}


def run() -> dict:
    return asyncio.run(_run_replay())
