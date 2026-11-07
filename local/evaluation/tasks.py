from __future__ import annotations

from huey.contrib.djhuey import HUEY, db_task

from evaluation.models import EvalRun


@db_task(retries=720, retry_delay=5)
def run_eval_task(eval_id: int) -> None:
    from evaluation.services import run_eval

    with HUEY.lock_task("yoriqnoma-explore"):  # shares the GPU with runs
        run_eval(EvalRun.objects.get(pk=eval_id))
