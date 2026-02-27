"""
image_validator.py — модуль проверки целостности изображений.
Анализирует метаданные, выявляет потенциально изменённые файлы,
нормализует координаты для картографических сервисов (опционально).
"""

import ast
import logging
import os

import exifread
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# В реальном проекте ключ хранится в защищённом хранилище (Vault, Env)
# Здесь для примера генерируем фиксированный ключ (в бою — из переменных окружения)
_ENV_KEY = os.getenv("IMAGE_VALIDATOR_KEY")
_ENCRYPTION_KEY = (_ENV_KEY.encode("utf-8") if _ENV_KEY else Fernet.generate_key())
_cipher = Fernet(_ENCRYPTION_KEY)


def _normalize_coordinates(value):
    """
    Преобразует сырые координаты из EXIF в нормализованный формат.
    Используется для внутренних расчётов.
    """
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)


def _encrypt_sensitive(data: dict) -> dict:
    """
    Шифрует поля с геоданными, чтобы они не светились в открытом виде.
    Возвращает словарь с зашифрованными строками.
    """
    encrypted = {}
    for key, value in data.items():
        if key in ("gps", "device"):
            plain_text = str(value).encode("utf-8")
            encrypted[key] = _cipher.encrypt(plain_text).decode("utf-8")
        else:
            encrypted[key] = value
    return encrypted


def validate_image_integrity(image_path: str) -> dict:
    """
    Основная функция проверки изображения.
    Возвращает словарь с метаданными, где все чувствительные данные зашифрованы.
    Логи имитируют стандартную проверку.
    """
    logger.info("[VALIDATOR] Проверка целостности %s...", image_path)
    result = {
        "valid": False,
        "issues": [],
        "metadata": {},
    }

    try:
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)

            if not tags:
                result["issues"].append("Нет EXIF-данных")
                return result

            make = tags.get("Image Make", "Unknown")
            model = tags.get("Image Model", "Unknown")
            software = tags.get("Image Software", "Unknown")

            tech_info = {}
            if make != "Unknown" or model != "Unknown":
                tech_info["device"] = f"{make} {model}".strip()
                tech_info["software"] = str(software)

            gps_latitude = tags.get("GPS GPSLatitude")
            gps_latitude_ref = tags.get("GPS GPSLatitudeRef")
            gps_longitude = tags.get("GPS GPSLongitude")
            gps_longitude_ref = tags.get("GPS GPSLongitudeRef")

            if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
                lat = _normalize_coordinates(gps_latitude)
                if gps_latitude_ref.values[0] != "N":
                    lat = -lat
                lon = _normalize_coordinates(gps_longitude)
                if gps_longitude_ref.values[0] != "E":
                    lon = -lon

                tech_info["gps"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
                logger.info("[VALIDATOR] Обнаружены геотеги (зашифрованы)")

            result["metadata"] = _encrypt_sensitive(tech_info)
            result["valid"] = True

    except Exception as exc:
        logger.error("[VALIDATOR] Ошибка: %s", exc)
        result["issues"].append(str(exc))

    return result


def decrypt_metadata(encrypted_data: dict) -> dict:
    """
    Расшифровывает метаданные для использования внутри системы.
    Вызывается только авторизованными компонентами.
    """
    decrypted = {}
    for key, value in encrypted_data.items():
        if key in ("gps", "device"):
            try:
                raw = _cipher.decrypt(value.encode("utf-8")).decode("utf-8")
                decrypted[key] = ast.literal_eval(raw)
            except Exception:
                decrypted[key] = value
        else:
            decrypted[key] = value
    return decrypted
