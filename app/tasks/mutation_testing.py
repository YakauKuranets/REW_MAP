"""Periodic AI mutation testing tasks."""

from __future__ import annotations

import asyncio
from celery import shared_task

from tools.ai_mutator import AIMutationEngine


@shared_task(name="app.tasks.mutation_testing.run_ai_mutation_on_critical_modules")
def run_ai_mutation_on_critical_modules() -> dict[str, bool]:
    """Run AI mutations on critical modules and report per-target result."""
    targets = [
        ("app/auth/routes.py", "pytest tests/test_auth.py"),
        ("app/osint/image_validator.py", "pytest tests/test_image_validator.py"),
        ("app/threat_intel/attribution_engine.py", "pytest tests/test_attribution.py"),
    ]

    results: dict[str, bool] = {}
    for file_path, test_cmd in targets:
        engine = AIMutationEngine(file_path, test_cmd)
        results[file_path] = asyncio.run(engine.run_mutation_cycle())

    return results
