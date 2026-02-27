from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from celery import shared_task

from app.diagnostics.models import DiagnosticTarget


def _ensure_parent(path: str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _feedback_to_example(target: DiagnosticTarget) -> dict[str, str] | None:
    feedback = target.feedback or {}
    if not isinstance(feedback, dict):
        return None

    # Defensive-only dataset schema: context -> improvement recommendation
    recommendation = (feedback.get("improvement") or feedback.get("recommendation") or "").strip()
    if not recommendation:
        return None

    context: dict[str, Any] = target.context if isinstance(target.context, dict) else {}
    prompt = (
        "Context: "
        f"{json.dumps(context, ensure_ascii=False)}\n"
        "Task result summary: "
        f"{json.dumps(target.result or {}, ensure_ascii=False)}\n"
        "Recommended diagnostic improvement:"
    )
    completion = f" {recommendation}"
    return {"prompt": prompt, "completion": completion}


@shared_task(name="app.ai.finetune.prepare_finetune_dataset")
def prepare_finetune_dataset(output_path: str | None = None) -> dict[str, Any]:
    """
    Система автоматического улучшения качества диагностики на основе обратной связи.
    Собирает успешные defensive-примеры в JSONL-датасет для последующей оптимизации модели.
    """
    output_path = output_path or os.environ.get("AI_FEEDBACK_DATASET_PATH", "/data/ai/diagnostics_feedback.jsonl")
    out = _ensure_parent(output_path)

    rows = DiagnosticTarget.query.filter(DiagnosticTarget.feedback.isnot(None)).all()
    written = 0

    with out.open("w", encoding="utf-8") as stream:
        for row in rows:
            example = _feedback_to_example(row)
            if not example:
                continue
            stream.write(json.dumps(example, ensure_ascii=False) + "\n")
            written += 1

    return {"status": "ok", "dataset": str(out), "total_rows": len(rows), "written_examples": written}


@shared_task(name="app.ai.finetune.run_finetuning")
def run_finetuning() -> dict[str, Any]:
    """
    Запускает внешний процесс статистического улучшения/оптимизации модели по подготовленному датасету.
    Скрипт опционален; при отсутствии возвращается диагностический ответ.
    """
    dataset_path = os.environ.get("AI_FEEDBACK_DATASET_PATH", "/data/ai/diagnostics_feedback.jsonl")
    script_path = os.environ.get("AI_FINETUNE_SCRIPT", "/opt/ai/finetune_llm.py")

    if not os.path.exists(dataset_path):
        return {"status": "skipped", "reason": "dataset_not_found", "dataset": dataset_path}
    if not os.path.exists(script_path):
        return {"status": "skipped", "reason": "script_not_found", "script": script_path}

    cmd = ["python3", script_path, "--dataset", dataset_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
    }
