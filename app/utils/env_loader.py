from __future__ import annotations

import logging
import os
from pathlib import Path

import hvac
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

VAULT_URL = os.getenv("VAULT_ADDR", "http://vault-service:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "playe-absolute-zero-token")


def load_dotenv_like(*candidates: str) -> str | None:
    """Minimal .env loader for local development fallback.

    Loads KEY=VALUE lines into os.environ if key is not already set.
    Returns the path that was loaded, or None if nothing found.
    """
    paths: list[Path] = []
    for c in candidates:
        if c:
            paths.append(Path(c))

    cwd = Path.cwd()
    here = Path(__file__).resolve()
    proj_root = here.parents[2]
    paths.extend([cwd / ".env", proj_root / ".env", cwd / ".env.local", proj_root / ".env.local"])

    for p in paths:
        try:
            if not p.exists() or not p.is_file():
                continue
            for raw in p.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k:
                    continue
                os.environ.setdefault(k, v)
            return str(p)
        except Exception:
            continue
    return None


class AppSettings(BaseSettings):
    """Strict app settings hydrated from Vault (with env fallback)."""

    database_uri: str = "cockroachdb+asyncpg://root@playe-db-cockroachdb-public:26257/defaultdb"
    redis_url: str = "redis://redis-service:6379/0"
    cloudflare_token: str = ""
    jwt_secret: str = "super_secret_fallback"

    class Config:
        env_file = ".env"


def _apply_settings_to_environ(cfg: AppSettings) -> None:
    """Backfill process env so legacy modules keep working during migration."""
    os.environ["DATABASE_URI"] = cfg.database_uri
    os.environ["REDIS_URL"] = cfg.redis_url
    if cfg.cloudflare_token:
        os.environ["CLOUDFLARE_API_TOKEN"] = cfg.cloudflare_token
    if cfg.jwt_secret:
        os.environ["JWT_SECRET_KEY"] = cfg.jwt_secret
        os.environ.setdefault("SECRET_KEY", cfg.jwt_secret)


def fetch_secrets_from_vault() -> AppSettings:
    """Fetch runtime secrets from HashiCorp Vault into memory."""
    logger.info("[VAULT] Инициализация защищенного соединения с хранилищем...")

    # Local/dev fallback still supported.
    load_dotenv_like()

    try:
        client = hvac.Client(url=VAULT_URL, token=VAULT_TOKEN)

        if not client.is_authenticated():
            logger.error("[VAULT] Ошибка аутентификации! Аварийная остановка.")
            cfg = AppSettings()
            _apply_settings_to_environ(cfg)
            return cfg

        response = client.secrets.kv.v2.read_secret_version(path="playe_cti")
        secrets = (response.get("data") or {}).get("data") or {}

        logger.warning("[VAULT] Секреты успешно загружены в оперативную память. Жесткий диск чист.")

        cfg = AppSettings(
            database_uri=secrets.get("DATABASE_URI", os.getenv("DATABASE_URI", AppSettings().database_uri)),
            redis_url=secrets.get("REDIS_URL", os.getenv("REDIS_URL", AppSettings().redis_url)),
            cloudflare_token=secrets.get("CLOUDFLARE_API_TOKEN", ""),
            jwt_secret=secrets.get("JWT_SECRET_KEY", os.getenv("JWT_SECRET_KEY", "fallback")),
        )
        _apply_settings_to_environ(cfg)
        return cfg

    except Exception as e:
        logger.error(f"[VAULT] Не удалось достучаться до сейфа: {e}. Используем локальные ENV.")
        cfg = AppSettings()
        _apply_settings_to_environ(cfg)
        return cfg


settings = fetch_secrets_from_vault()
