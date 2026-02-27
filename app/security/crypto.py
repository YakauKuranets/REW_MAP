import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_master_key = os.getenv("FERNET_MASTER_KEY")
if not _master_key:
    _master_key = Fernet.generate_key().decode()
    logger.warning(
        "FERNET_MASTER_KEY не найден в ENV. Сгенерирован временный ключ. "
        "Запишите его в .env: %s",
        _master_key,
    )

_cipher_suite = Fernet(_master_key.encode())


def encrypt_secret(secret: str) -> str:
    """Шифрует чувствительные данные перед записью в БД."""
    if not secret:
        return secret
    return _cipher_suite.encrypt(secret.encode()).decode()


def decrypt_secret(encrypted_secret: str) -> str:
    """Расшифровывает данные для отображения в безопасном UI."""
    if not encrypted_secret:
        return encrypted_secret
    try:
        return _cipher_suite.decrypt(encrypted_secret.encode()).decode()
    except Exception as exc:
        logger.error("Ошибка расшифровки: %s", exc)
        return "[DECRYPTION_ERROR]"
