"""
Утилита для простого бэкапа локальных SQLite-баз проекта (app.db, zones.db).

Запуск:
    python tools/backup_sqlite_dbs.py

Что делает:
    - создаёт папку backups/YYYYmmdd_HHMMSS рядом с проектом;
    - копирует туда app.db и zones.db (если они существуют);
    - выводит пути к созданным файлам.

Скрипт не трогает сам проект и не изменяет базу.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    backups_root = base_dir / "backups"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = backups_root / timestamp

    dest_dir.mkdir(parents=True, exist_ok=True)

    db_names = ["app.db", "zones.db"]
    copied = []

    for name in db_names:
        src = base_dir / name
        if src.exists():
            dst = dest_dir / name
            shutil.copy2(src, dst)
            copied.append(dst)

    if not copied:
        print("SQLite-базы не найдены (app.db, zones.db).")
        print("Убедись, что запускаешь скрипт из рабочей копии проекта.")
        return

    print("Создан бэкап SQLite-баз:")
    for path in copied:
        print("  -", path)


if __name__ == "__main__":
    main()
