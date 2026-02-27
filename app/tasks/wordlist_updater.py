import hashlib
import logging
import os
import tempfile

import requests
from celery import shared_task

from app.extensions import db
from app.wordlists.models import Wordlist

logger = logging.getLogger(__name__)

# Источники словарей (можно добавить больше)
WORDLIST_SOURCES = [
    {
        "name": "rockyou_optimized",
        "url": "https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt",
        "fallback_urls": [
            "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Leaked-Databases/rockyou.txt.tar.gz",
        ],
    },
    {
        "name": "wifi_specific",
        "url": "https://raw.githubusercontent.com/kennyn510/wpa2-wordlists/master/wpa2-wordlist.txt",
        "fallback_urls": [],
    },
]


def compute_file_hash(file_path: str) -> str:
    """Вычисляет SHA-256 хеш файла."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def count_lines(file_path: str) -> int:
    """Подсчитывает количество строк в файле (для отображения размера)."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def _download_to_temp(source: dict) -> tuple[str, str]:
    urls = [source["url"], *source.get("fallback_urls", [])]
    last_error = None
    for url in urls:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
                response = requests.get(url, stream=True, timeout=60)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                return tmp_file.name, url
        except Exception as exc:
            last_error = exc
            logger.warning("Failed to download %s from %s: %s", source["name"], url, exc)
    raise RuntimeError(f"All sources failed for {source['name']}: {last_error}")


@shared_task(name="app.tasks.wordlist_updater.update_wordlists")
def update_wordlists() -> None:
    """Периодическая задача для обновления словарей паролей."""
    logger.info("Starting wordlist update task")

    for source in WORDLIST_SOURCES:
        tmp_path = None
        try:
            tmp_path, used_url = _download_to_temp(source)
            new_hash = compute_file_hash(tmp_path)

            existing = (
                Wordlist.query.filter_by(name=source["name"])
                .order_by(Wordlist.version.desc())
                .first()
            )

            if existing and existing.hash == new_hash:
                logger.info("Wordlist %s is already up to date", source["name"])
                os.unlink(tmp_path)
                continue

            new_version = (existing.version + 1) if existing else 1

            target_dir = "/data/wordlists"
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, f"{source['name']}_v{new_version}.txt")

            if os.path.exists(target_path):
                os.unlink(target_path)

            os.replace(tmp_path, target_path)
            tmp_path = None

            line_count = count_lines(target_path)

            new_wordlist = Wordlist(
                name=source["name"],
                version=new_version,
                size=line_count,
                file_path=target_path,
                source_url=used_url,
                hash=new_hash,
                is_active=True,
            )

            if existing:
                existing.is_active = False

            db.session.add(new_wordlist)
            db.session.commit()

            logger.info("Updated %s to version %s (%s entries)", source["name"], new_version, line_count)
        except Exception as exc:
            logger.error("Failed to update %s: %s", source["name"], exc)
            db.session.rollback()
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    logger.info("Wordlist update task completed")
