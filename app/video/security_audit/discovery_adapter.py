# -*- coding: utf-8 -*-
"""Адаптер для обнаружения камер с использованием AutoDiscoveryService и fallback сканера."""

import asyncio
import logging
from typing import Optional

from app.video.discovery import AutoDiscoveryService, DiscoveryResult
from .discovery import (  # наш быстрый асинхронный сканер
    DetectedCamera,
    scan_port,
    fingerprint,
    CAMERA_PORTS
)

logger = logging.getLogger(__name__)

async def detect_camera_comprehensive(
    ip: str,
    login: Optional[str] = None,
    password: Optional[str] = None,
    timeout: float = 5.0
) -> Optional[DetectedCamera]:
    """
    Комплексное обнаружение камеры.
    1) Пытается использовать AutoDiscoveryService (ONVIF, Dahua CGI, RTSP scanner).
    2) Если не удалось, запускает быстрый порт-сканер и HTTP-фингерпринтинг.
    Возвращает DetectedCamera с ip, port, vendor, auth_type (если определены).
    """
    # Шаг 1: используем существующий AutoDiscoveryService
    discovery = AutoDiscoveryService()
    result = await discovery.discover(ip, login=login, password=password, timeout=timeout)

    if result and result.channels:
        # Есть каналы – устройство точно камера. Определим порт и вендора.
        port = 80  # большинство ONVIF/Dahua работают на 80
        # Попробуем уточнить порт из первого канала (например, RTSP URL)
        if result.channels and result.channels[0].stream_url:
            import re
            m = re.search(r':(\d+)', result.channels[0].stream_url)
            if m:
                port = int(m.group(1))
        vendor = result.terminal_type.lower() if result.terminal_type else None
        auth_type = None
        # В зависимости от пробера можно определить тип аутентификации
        if result.prober == 'onvif_universal':
            auth_type = 'digest'  # ONVIF обычно Digest
        elif result.prober == 'dahua_tvt_cgi':
            auth_type = 'digest'  # Dahua CGI тоже Digest
        elif result.prober == 'raw_rtsp_scanner':
            auth_type = 'basic'   # RTSP часто Basic, но может быть Digest
        # Дополнительно можно сохранить детали
        logger.info(f"AutoDiscoveryService нашёл камеру {ip}:{port} (vendor={vendor}, prober={result.prober})")
        return DetectedCamera(ip=ip, port=port, vendor=vendor, auth_type=auth_type)

    # Шаг 2: fallback – быстрый порт-сканер
    logger.info(f"AutoDiscoveryService не сработал для {ip}, запускаем порт-сканер")
    async with aiohttp.ClientSession() as session:
        # Сначала проверяем HTTP порты
        for port in [80, 443, 8080, 8443]:
            if await scan_port(ip, port, timeout):
                cam = await fingerprint(ip, port, session)
                if cam:
                    return cam
        # Если не нашли HTTP, просто возвращаем первый открытый порт
        for port in CAMERA_PORTS:
            if port not in [80, 443, 8080, 8443]:
                if await scan_port(ip, port, timeout):
                    logger.info(f"Найден открытый порт {port} на {ip}, но вендор не определён")
                    return DetectedCamera(ip=ip, port=port)

    return None
