"""Celery tasks for scheduled AI mutation checks."""

from __future__ import annotations

import os
import subprocess
from celery import shared_task


@shared_task(name="app.tasks.ai_mutation_tasks.run_weekend_ai_mutation")
def run_weekend_ai_mutation() -> dict[str, str | int]:
    """Run ai mutator script and return execution summary."""
    target = os.environ.get("AI_MUTATOR_TARGET", "app/auth/routes.py")
    cmd = os.environ.get("AI_MUTATOR_TEST_CMD", "pytest tests/test_auth_rbac_csrf.py")

    proc = subprocess.run(
        [
            "python",
            "tools/ai_mutator.py",
            "--target",
            target,
            "--test-cmd",
            cmd,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
