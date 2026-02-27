#!/usr/bin/env python3
"""
ai_mutator.py – Интеллектуальное мутационное тестирование.
Использует LLM для внесения реалистичных логических уязвимостей в код,
после чего запускает тесты и оценивает, были ли они обнаружены.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("AI_Mutator")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
LLM_API_URL = os.getenv("LLM_API_URL", "http://localhost:11434/api/generate")


class AIMutationEngine:
    def __init__(self, target_path: str, test_command: str, mutation_description: str | None = None):
        self.target_path = Path(target_path)
        self.test_command = test_command
        self.mutation_description = (
            mutation_description
            or "внеси логическую ошибку, которая может остаться незамеченной, но нарушит безопасность"
        )

    async def _call_llm(self, code_snippet: str) -> str:
        prompt = f"""Ты — эксперт по безопасности кода. Задача: внести в приведённый ниже код одну логическую уязвимость, которая:
- может остаться незамеченной при обычном ревью,
- нарушает безопасность (например, обходит аутентификацию, допускает SQL-инъекцию, неправильно проверяет права),
- не изменяет синтаксис (код должен оставаться валидным),
- не слишком очевидна.

Требуется: {self.mutation_description}

Верни только изменённый код, без пояснений. Оригинальный код:
```python
{code_snippet}
```"""

        # Local LLM (e.g., Ollama)
        if LLM_API_URL.startswith("http://localhost") or LLM_API_URL.startswith("http://127.0.0.1"):
            import aiohttp

            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": os.getenv("OLLAMA_MODEL", "codellama:13b"),
                    "prompt": prompt,
                    "stream": False,
                }
                async with session.post(LLM_API_URL, json=payload, timeout=90) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
                    text = (result.get("response") or "").strip()
                    if text:
                        return text

        # OpenAI fallback
        if OPENAI_API_KEY:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = (response.choices[0].message.content or "").strip()
            if content:
                return content

        # Deterministic fallback to keep script usable in offline CI environments
        logger.warning("LLM недоступна, применяем детерминированную мутацию fallback")
        fallback = code_snippet.replace("if not token_is_valid:", "if False:  # AI MUTATION", 1)
        return fallback if fallback != code_snippet else code_snippet + "\n# AI MUTATION NO-OP\n"

    async def _send_alert(self, message: str) -> None:
        try:
            from app.bot.notifications import send_to_admin

            await send_to_admin(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Модуль уведомлений не сработал: %s", exc)

    async def run_mutation_cycle(self) -> bool:
        logger.warning("Запуск ИИ-мутации для %s...", self.target_path)
        if not self.target_path.exists():
            logger.error("Файл не найден: %s", self.target_path)
            return False

        original_code = self.target_path.read_text(encoding="utf-8")

        try:
            mutated_code = await self._call_llm(original_code)
            self.target_path.write_text(mutated_code, encoding="utf-8")

            logger.info("Запуск тестов: %s", self.test_command)
            process = await asyncio.create_subprocess_exec(
                *shlex.split(self.test_command),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.critical("❌ КРИТИЧЕСКАЯ УЯЗВИМОСТЬ ТЕСТОВ: ИИ-мутация прошла незамеченной!")
                await self._send_alert(
                    f"Мутация в {self.target_path} не поймана тестами!\nКоманда: {self.test_command}"
                )
                logger.info(stdout.decode("utf-8", errors="ignore"))
                return False

            logger.info("✅ УСПЕХ: Мутация обнаружена тестами.")
            logger.info(stdout.decode("utf-8", errors="ignore"))
            logger.info(stderr.decode("utf-8", errors="ignore"))
            return True

        except Exception as e:  # noqa: BLE001
            logger.error("Ошибка при выполнении мутации: %s", e)
            return False
        finally:
            self.target_path.write_text(original_code, encoding="utf-8")
            logger.info("Исходный код восстановлен.")


async def main() -> int:
    parser = argparse.ArgumentParser(description="AI Mutation Testing")
    parser.add_argument("--target", required=True, help="Путь к файлу для мутации")
    parser.add_argument("--test-cmd", required=True, help="Команда запуска тестов")
    parser.add_argument("--desc", default="внеси логическую уязвимость", help="Описание мутации")
    args = parser.parse_args()

    engine = AIMutationEngine(args.target, args.test_cmd, args.desc)
    success = await engine.run_mutation_cycle()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
