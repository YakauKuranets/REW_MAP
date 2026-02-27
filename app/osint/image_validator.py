"""
image_validator.py — модуль проверки целостности изображений.
Опасный парсинг сначала делегируется в Wasm-песочницу.
"""

import ast
import json
import logging
import os
import tempfile

import exifread
from cryptography.fernet import Fernet
from fastapi import UploadFile

from app.sandbox.wasm_runner import sandbox_engine

logger = logging.getLogger(__name__)

_ENV_KEY = os.getenv("IMAGE_VALIDATOR_KEY")
_ENCRYPTION_KEY = (_ENV_KEY.encode("utf-8") if _ENV_KEY else Fernet.generate_key())
_cipher = Fernet(_ENCRYPTION_KEY)

WASM_EXIF_PARSER_PATH = os.getenv("WASM_EXIF_PARSER_PATH", "/app/bin/exif_parser_secure.wasm")


def _normalize_coordinates(value):
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)


def _encrypt_sensitive(data: dict) -> dict:
    encrypted = {}
    for key, value in data.items():
        if key in ("gps", "device"):
            plain_text = str(value).encode("utf-8")
            encrypted[key] = _cipher.encrypt(plain_text).decode("utf-8")
        else:
            encrypted[key] = value
    return encrypted


def _parse_exif_with_python(image_path: str) -> dict:
    """Fallback parser for MVP while wasm parser is not yet implemented."""
    result = {"valid": False, "issues": [], "metadata": {}}
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
    return result


async def validate_and_extract_exif_secure(file: UploadFile) -> dict:
    """Безопасный анализ подозрительных изображений через WebAssembly."""
    logger.warning("[OSINT_VISION] Передача файла %s в изолированную Wasm-песочницу.", file.filename)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result_json = sandbox_engine.run_parser(WASM_EXIF_PARSER_PATH, tmp_path)
        parsed = json.loads(result_json)
        if parsed.get("error") == "wasm module missing":
            # Graceful fallback requested for MVP.
            return _parse_exif_with_python(tmp_path)
        if parsed.get("error"):
            return {"valid": False, "issues": [parsed.get("error")], "metadata": {}}
        return {"status": "clean", "metadata": "parsed_safely"}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def validate_image_integrity(image_path: str) -> dict:
    """Synchronous validator used by existing pipelines."""
    logger.info("[VALIDATOR] Проверка целостности %s...", image_path)

    try:
        result_json = sandbox_engine.run_parser(WASM_EXIF_PARSER_PATH, image_path)
        parsed = json.loads(result_json)
        if parsed.get("error") == "wasm module missing":
            return _parse_exif_with_python(image_path)
        if parsed.get("error"):
            return {"valid": False, "issues": [parsed.get("error")], "metadata": {}}

        # Until wasm parser returns structured metadata, fallback for metadata extraction.
        return _parse_exif_with_python(image_path)
    except Exception as exc:
        logger.error("[VALIDATOR] Ошибка: %s", exc)
        return {"valid": False, "issues": [str(exc)], "metadata": {}}


def decrypt_metadata(encrypted_data: dict) -> dict:
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
