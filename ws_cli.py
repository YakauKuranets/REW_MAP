"""
Простейший консольный клиент для подключения к WebSocket‑серверу проекта
Map v12. Он позволяет подписаться на события сервера (новые заявки,
изменение статуса, сообщения чата) и отправлять сообщения в чат от
администратора. Для работы требуется установка библиотеки websockets.

Запуск:
    python ws_cli.py

После запуска будет установлено соединение с сервером. На экране
появится меню с вариантами действий:

1. Прослушивать события. Клиент будет печатать каждое сообщение,
   приходящее с сервера, пока вы не нажмёте Enter.
2. Отправить сообщение. Необходимо ввести идентификатор пользователя
   (тот, кто общается с админом через Telegram) и текст сообщения.
   Сообщение будет отправлено через HTTP‑API, поэтому для работы
   требуется, чтобы приложение было запущено и вы вошли как админ.
0. Выход. Завершает работу клиента.

Обратите внимание, что WebSocket‑соединение используется только для
получения событий. Отправка сообщений осуществляется через REST API
(`POST /api/chat/<user_id>`), так как протокол Telegram для бота
остается прежним. Также можно расширить этот скрипт, добавив
поддержку отправки через WS, если это потребуется.
"""

import asyncio
import json
import os
import sys

try:
    import websockets
    import aiohttp
except ImportError:
    print("Не установлены зависимости. Пожалуйста, выполните `pip install websockets aiohttp`.")
    sys.exit(1)


# WS URL по умолчанию. Сервер требует token (см. GET /api/realtime/token).
# Можно переопределить:
#   WS_URL=ws://127.0.0.1:8765/ws?token=... python ws_cli.py
# или:
#   WS_TOKEN=... python ws_cli.py
_tok = os.environ.get("WS_TOKEN", "").strip()
WS_URL = os.environ.get("WS_URL") or ("ws://localhost:8765/ws" + (f"?token={_tok}" if _tok else ""))

API_BASE = os.environ.get("API_BASE") or "http://localhost:5000/api"


async def listen_to_ws(ws):
    """Слушаем WebSocket и выводим все входящие события."""
    try:
        async for message in ws:
            try:
                data = json.loads(message)
                print(f"\n[WS] Событие: {data.get('event')}, данные: {data.get('data')}")
            except json.JSONDecodeError:
                print(f"\n[WS] Получено текстовое сообщение: {message}")
    except websockets.exceptions.ConnectionClosedOK:
        print("\nWebSocket‑соединение закрыто.")
    except Exception as exc:
        print(f"\nОшибка WS: {exc}")


async def send_chat_message(user_id: str, text: str, session: aiohttp.ClientSession):
    """Отправляет сообщение от администратора в чат конкретному пользователю."""
    url = f"{API_BASE}/chat/{user_id}"
    try:
        async with session.post(url, json={"text": text}, headers={"X-Admin": "1"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"Отправлено: {data}")
            else:
                print(f"Ошибка отправки: HTTP {resp.status}")
    except Exception as exc:
        print(f"Ошибка при отправке: {exc}")


async def main():
    # Подключаемся к WebSocket
    print(f"Подключение к {WS_URL}…")
    async with websockets.connect(WS_URL) as ws:
        print("Соединение установлено.")
        # Создаём HTTP‑сессию для REST запросов
        async with aiohttp.ClientSession() as session:
            while True:
                print("\nМеню:\n 1 – слушать события\n 2 – отправить сообщение\n 0 – выход")
                choice = input("Ваш выбор: ").strip()
                if choice == '1':
                    print("Нажмите Enter, чтобы прекратить прослушивание.")
                    listener_task = asyncio.create_task(listen_to_ws(ws))
                    # Ожидаем, пока пользователь нажмёт Enter в другом потоке
                    await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                    listener_task.cancel()
                    try:
                        await listener_task
                    except asyncio.CancelledError:
                        pass
                elif choice == '2':
                    user_id = input("Введите ID пользователя: ").strip()
                    text = input("Введите сообщение: ").strip()
                    if user_id and text:
                        await send_chat_message(user_id, text, session)
                elif choice == '0':
                    print("Выход…")
                    break
                else:
                    print("Неизвестная команда.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nЗавершение работы.")