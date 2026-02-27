"""eBPF/Tetragon watcher that escalates kernel alerts to Aegis SOAR."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.security.aegis_soar import block_ip_on_edge

logger = logging.getLogger(__name__)

TETRAGON_CMD = [
    "kubectl",
    "logs",
    "-n",
    "kube-system",
    "-l",
    "app.kubernetes.io/name=tetragon",
    "-f",
]


def _pick_nested(data: dict[str, Any], path: list[str]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def extract_ip_from_k8s_context(event: dict[str, Any]) -> str | None:
    """Best-effort extraction of source IP from Tetragon payload."""
    candidates = [
        ["process_exec", "source", "ip"],
        ["process_exec", "source_ip"],
        ["process_exec", "process", "pod", "pod_ip"],
        ["process_exec", "process", "pod", "ip"],
        ["process_kprobe", "source", "ip"],
        ["process_kprobe", "source_ip"],
    ]
    for path in candidates:
        value = _pick_nested(event, path)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _is_policy_violation(event: dict[str, Any]) -> tuple[bool, str, str]:
    proc_exec = event.get("process_exec") if isinstance(event, dict) else None
    if not isinstance(proc_exec, dict):
        return False, "", ""

    policy = str(proc_exec.get("policy_name") or "").strip()
    binary = str(_pick_nested(proc_exec, ["process", "binary"]) or "unknown").strip()
    return bool(policy), policy, binary


async def _stream_tetragon_events() -> None:
    logger.critical(
        "[SOAR_eBPF] Подключение к потоку ядра (Ring 0) установлено. Ожидание аномалий..."
    )

    process = await asyncio.create_subprocess_exec(
        *TETRAGON_CMD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert process.stdout is not None

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        try:
            event = json.loads(line.decode("utf-8").strip())
            is_violation, policy, binary = _is_policy_violation(event)
            if not is_violation:
                continue

            logger.error(
                "[SOAR_eBPF] АЛЕРТ ЯДРА! Нарушение политики: %s. Заблокирован бинарник: %s",
                policy,
                binary,
            )

            attacker_ip = extract_ip_from_k8s_context(event)
            if attacker_ip:
                logger.warning(
                    "[SOAR_eBPF] Инициализация протокола ЭГИДА для IP %s",
                    attacker_ip,
                )
                await block_ip_on_edge(attacker_ip, reason=f"eBPF Violation: {policy}")
            else:
                logger.warning("[SOAR_eBPF] Источник IP не найден в событии Tetragon")

        except json.JSONDecodeError:
            continue
        except Exception as exc:  # noqa: BLE001
            logger.error("[SOAR_eBPF] Ошибка парсинга события: %s", exc)

    await process.wait()


async def monitor_tetragon_events() -> None:
    """Run watcher forever with automatic reconnects."""
    backoff = 1
    while True:
        try:
            await _stream_tetragon_events()
            logger.warning("[SOAR_eBPF] Поток Tetragon завершен. Переподключение...")
        except Exception as exc:  # noqa: BLE001
            logger.error("[SOAR_eBPF] Критическая ошибка watcher: %s", exc)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(monitor_tetragon_events())
