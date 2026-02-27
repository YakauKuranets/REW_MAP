"""Создание "чистого" релизного архива (без секретов и локальных данных).

Использование:
  python tools/make_release_zip.py

Создаст файл вида:
  release_mapv12_YYYYmmdd_HHMMSS.zip

Что исключается:
  - .env* (секреты)
  - app.db / zones.db (локальные БД)
  - __pycache__ / *.pyc
  - uploads/ (если хочешь включать — убери из ignore)
"""

from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

IGNORE_NAMES = {
    '.env', '.env.prod', '.env.local',
    'app.db', 'zones.db',
}

IGNORE_DIRS = {
    '__pycache__', '.pytest_cache', '.mypy_cache',
    'backups',
}

IGNORE_SUFFIXES = {'.pyc', '.pyo', '.pyd'}


def should_skip(path: Path) -> bool:
    name = path.name
    if name in IGNORE_NAMES:
        return True
    if name.startswith('.env'):
        return True
    if path.suffix in IGNORE_SUFFIXES:
        return True
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True
    # uploads по умолчанию исключаем (можно включать при необходимости)
    if 'uploads' in path.parts:
        return True
    return False


def main() -> None:
    ts = time.strftime('%Y%m%d_%H%M%S')
    out_name = f'release_mapv12_{ts}.zip'
    out_path = PROJECT_ROOT / out_name

    with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in PROJECT_ROOT.rglob('*'):
            if p.is_dir():
                continue
            rel = p.relative_to(PROJECT_ROOT)
            if should_skip(rel):
                continue
            zf.write(p, rel.as_posix())

    print(f'OK: {out_path}')


if __name__ == '__main__':
    main()
