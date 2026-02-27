"""Safe terminal connection tester service.

Performs a single credential check against Hikvision ISAPI using DigestAuth.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class AutoDiscoveryService:
    """Connection tester for terminal provisioning flows."""

    @staticmethod
    async def _try_hikvision(ip: str, user: str, pwd: str) -> bool:
        """Try a single authenticated request to Hikvision ISAPI."""
        url = f"http://{ip}/ISAPI/System/deviceInfo"
        try:
            async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
                response = await client.get(url, auth=httpx.DigestAuth(user, pwd))
                return response.status_code == 200
        except httpx.RequestError:
            return False

    @staticmethod
    async def probe_terminal(
        ip: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate user-provided credentials with one probe attempt."""
        ip = (ip or "").strip()
        user = (username or "").strip()
        pwd = password if password is not None else ""

        if not ip or not user:
            return {
                "status": "error",
                "message": "ip and username are required",
            }

        ok = await AutoDiscoveryService._try_hikvision(ip, user, pwd)
        if ok:
            return {
                "status": "success",
                "type": "HIKVISION_ISAPI",
                "message": "Connection successful",
            }

        return {
            "status": "error",
            "message": "Connection failed. Check IP/login/password.",
        }
