"""Backward-compatible env loader facade.

Delegates to `app.utils.env_loader` so legacy imports keep working.
"""

from app.utils.env_loader import AppSettings, fetch_secrets_from_vault, load_dotenv_like, settings

__all__ = [
    "AppSettings",
    "fetch_secrets_from_vault",
    "load_dotenv_like",
    "settings",
]
