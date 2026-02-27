"""Auto-discovery helpers for VMS/NVR terminals.

Chain-of-responsibility service composed from protocol-specific probers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import socket
from typing import Any, Dict, Iterable, List, Optional
import xml.etree.ElementTree as ET

import httpx


SOAP_ENVELOPE = "http://www.w3.org/2003/05/soap-envelope"
ONVIF_DEVICE_WSDL = "http://www.onvif.org/ver10/device/wsdl"
ONVIF_MEDIA_WSDL = "http://www.onvif.org/ver10/media/wsdl"


@dataclass
class DiscoveredChannel:
    """Single discovered video channel."""

    channel_number: int
    name: str
    stream_url: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    """Probe response returned by a prober in the chain."""

    prober: str
    terminal_type: str
    channels: List[DiscoveredChannel]
    details: Dict[str, Any] = field(default_factory=dict)


class BaseProber:
    """Abstract prober for the discovery chain."""

    name: str = "base"

    async def probe(
        self,
        ip: str,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[DiscoveryResult]:
        raise NotImplementedError


class OnvifUniversalProber(BaseProber):
    """Universal ONVIF prober.

    1) Sends GetServices/GetDeviceInformation SOAP request to
       ``http://{ip}/onvif/device_service``.
    2) Resolves Media service endpoint.
    3) Executes GetProfiles and GetStreamUri for each profile.
    """

    name = "onvif_universal"

    async def probe(
        self,
        ip: str,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[DiscoveryResult]:
        device_url = f"http://{ip}/onvif/device_service"

        auth: Optional[httpx.Auth] = None
        if login and password:
            auth = httpx.DigestAuth(login, password)

        async with httpx.AsyncClient(timeout=timeout, auth=auth) as client:
            services_xml = await self._soap_call(
                client,
                device_url,
                self._get_services_body(),
                soap_action=f"{ONVIF_DEVICE_WSDL}/GetServices",
            )

            if services_xml is None:
                # fallback probe for devices that reject GetServices
                services_xml = await self._soap_call(
                    client,
                    device_url,
                    self._get_device_information_body(),
                    soap_action=f"{ONVIF_DEVICE_WSDL}/GetDeviceInformation",
                )
                if services_xml is None:
                    return None

            media_xaddr = self._extract_media_xaddr(services_xml) or device_url

            profiles_xml = await self._soap_call(
                client,
                media_xaddr,
                self._get_profiles_body(),
                soap_action=f"{ONVIF_MEDIA_WSDL}/GetProfiles",
            )
            if profiles_xml is None:
                return None

            profiles = self._extract_profiles(profiles_xml)
            if not profiles:
                return None

            channels: List[DiscoveredChannel] = []
            for index, profile in enumerate(profiles, start=1):
                token = profile["token"]
                stream_xml = await self._soap_call(
                    client,
                    media_xaddr,
                    self._get_stream_uri_body(token),
                    soap_action=f"{ONVIF_MEDIA_WSDL}/GetStreamUri",
                )
                stream_url = self._extract_stream_uri(stream_xml) if stream_xml else None
                if not stream_url:
                    continue
                channels.append(
                    DiscoveredChannel(
                        channel_number=index,
                        name=profile.get("name") or f"ONVIF CH {index}",
                        stream_url=stream_url,
                        metadata={"profile_token": token},
                    )
                )

        if not channels:
            return None

        return DiscoveryResult(
            prober=self.name,
            terminal_type="ONVIF",
            channels=channels,
            details={"device_service": device_url},
        )

    async def _soap_call(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        body: str,
        *,
        soap_action: str,
    ) -> Optional[str]:
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": soap_action,
        }
        try:
            response = await client.post(endpoint, content=body.encode("utf-8"), headers=headers)
            response.raise_for_status()
            return response.text
        except Exception:
            return None

    def _extract_media_xaddr(self, xml_text: str) -> Optional[str]:
        root = ET.fromstring(xml_text)
        for service in root.findall('.//{*}Service'):
            namespace = (service.findtext('{*}Namespace') or '').lower()
            if 'media' in namespace:
                xaddr = service.findtext('{*}XAddr')
                if xaddr:
                    return xaddr.strip()
        return None

    def _extract_profiles(self, xml_text: str) -> List[Dict[str, str]]:
        root = ET.fromstring(xml_text)
        profiles: List[Dict[str, str]] = []
        for profile in root.findall('.//{*}Profiles'):
            token = profile.attrib.get('token', '').strip()
            name = (profile.findtext('{*}Name') or '').strip()
            if token:
                profiles.append({'token': token, 'name': name})
        return profiles

    def _extract_stream_uri(self, xml_text: str) -> Optional[str]:
        root = ET.fromstring(xml_text)
        uri = root.findtext('.//{*}Uri')
        if uri:
            return uri.strip()
        return None

    @staticmethod
    def _envelope(body: str) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<s:Envelope xmlns:s="{SOAP_ENVELOPE}">'
            f'<s:Body>{body}</s:Body>'
            f'</s:Envelope>'
        )

    def _get_services_body(self) -> str:
        return self._envelope(
            '<tds:GetServices xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
            '<tds:IncludeCapability>false</tds:IncludeCapability>'
            '</tds:GetServices>'
        )

    def _get_device_information_body(self) -> str:
        return self._envelope(
            '<tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>'
        )

    def _get_profiles_body(self) -> str:
        return self._envelope(
            '<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>'
        )

    def _get_stream_uri_body(self, token: str) -> str:
        return self._envelope(
            '<trt:GetStreamUri xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema">'
            '<trt:StreamSetup>'
            '<tt:Stream>RTP-Unicast</tt:Stream>'
            '<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>'
            '</trt:StreamSetup>'
            f'<trt:ProfileToken>{token}</trt:ProfileToken>'
            '</trt:GetStreamUri>'
        )


class DahuaTvtCgiProber(BaseProber):
    """Dahua/TVT CGI prober for channel discovery."""

    name = "dahua_tvt_cgi"

    async def probe(
        self,
        ip: str,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[DiscoveryResult]:
        if not login or not password:
            return None

        url = f"http://{ip}/cgi-bin/configManager.cgi?action=getConfig&name=VideoInChannels"
        auth_variants: List[httpx.Auth] = [httpx.DigestAuth(login, password), httpx.BasicAuth(login, password)]

        payload: Optional[str] = None
        status_code: Optional[int] = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for auth in auth_variants:
                try:
                    resp = await client.get(url, auth=auth)
                    status_code = resp.status_code
                    if resp.status_code == 200 and resp.text:
                        payload = resp.text
                        break
                except Exception:
                    continue

        if not payload:
            return None

        channels = self._parse_channels(payload, ip=ip, login=login, password=password)
        if not channels:
            return None

        return DiscoveryResult(
            prober=self.name,
            terminal_type="DAHUA_TVT",
            channels=channels,
            details={"endpoint": url, "status_code": status_code},
        )

    def _parse_channels(self, text: str, *, ip: str, login: str, password: str) -> List[DiscoveredChannel]:
        found: Dict[int, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if ".Name=" in line:
                left, right = line.split("=", 1)
                try:
                    idx = int(left.split("[")[-1].split("]")[0])
                except Exception:
                    continue
                found[idx + 1] = right.strip()

        if not found:
            # fallback if names are missing: infer channels from indexes
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("table.VideoInChannels["):
                    continue
                try:
                    idx = int(line.split("[")[-1].split("]")[0])
                except Exception:
                    continue
                found.setdefault(idx + 1, f"CH {idx + 1}")

        channels: List[DiscoveredChannel] = []
        for channel in sorted(found):
            channels.append(
                DiscoveredChannel(
                    channel_number=channel,
                    name=found[channel] or f"CH {channel}",
                    stream_url=(
                        f"rtsp://{login}:{password}@{ip}:554/"
                        f"cam/realmonitor?channel={channel}&subtype=0"
                    ),
                    metadata={"source": "cgi"},
                )
            )
        return channels


class RawRtspScannerProber(BaseProber):
    """Fallback RTSP scanner.

    1) Verifies TCP/554 is reachable.
    2) Iterates channels 1..16 and sends RTSP OPTIONS.
    3) Adds channel if RTSP endpoint responds with ``200 OK``.
    """

    name = "raw_rtsp_scanner"

    async def probe(
        self,
        ip: str,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[DiscoveryResult]:
        if not await asyncio.to_thread(self._is_port_open, ip, 554, timeout):
            return None

        channels: List[DiscoveredChannel] = []
        username = login or "admin"
        secret = password or "admin"

        for channel in range(1, 17):
            rtsp_url = (
                f"rtsp://{username}:{secret}@{ip}:554/"
                f"cam/realmonitor?channel={channel}&subtype=0"
            )
            ok = await asyncio.to_thread(self._rtsp_options_ok, ip, 554, rtsp_url, timeout)
            if ok:
                channels.append(
                    DiscoveredChannel(
                        channel_number=channel,
                        name=f"RTSP CH {channel}",
                        stream_url=rtsp_url,
                        metadata={"source": "rtsp_options"},
                    )
                )

        if not channels:
            return None

        return DiscoveryResult(
            prober=self.name,
            terminal_type="RTSP_GENERIC",
            channels=channels,
            details={"port": 554},
        )

    def _is_port_open(self, host: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _rtsp_options_ok(self, host: str, port: int, rtsp_url: str, timeout: float) -> bool:
        request = (
            f"OPTIONS {rtsp_url} RTSP/1.0\r\n"
            f"CSeq: 1\r\n"
            f"User-Agent: CommandCenter-Discovery\r\n"
            f"\r\n"
        ).encode("utf-8")

        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                sock.sendall(request)
                response = sock.recv(2048).decode("utf-8", errors="ignore")
                return "RTSP/1.0 200" in response
        except OSError:
            return False


class AutoDiscoveryService:
    """Device auto-discovery orchestrator (chain-of-responsibility)."""

    def __init__(self, probers: Optional[Iterable[BaseProber]] = None) -> None:
        self._probers: List[BaseProber] = list(probers) if probers is not None else [
            OnvifUniversalProber(),
            DahuaTvtCgiProber(),
            RawRtspScannerProber(),
        ]

    async def discover(
        self,
        ip: str,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[DiscoveryResult]:
        ip = (ip or '').strip()
        if not ip:
            return None

        for prober in self._probers:
            result = await prober.probe(ip, login=login, password=password, timeout=timeout)
            if result and result.channels:
                return result
        return None

    async def probe_terminal(
        self,
        ip: str,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """Compatibility wrapper requested by API layer/UI.

        Returns normalized payload with ``status``, ``type`` and ``channels``.
        """
        result = await self.discover(ip, login=login, password=password, timeout=timeout)
        if not result:
            return {"status": "error", "message": "terminal_not_detected", "type": None, "channels": []}

        return {
            "status": "success",
            "type": result.terminal_type,
            "channels": [
                {
                    "channel_number": channel.channel_number,
                    "name": channel.name,
                    "stream_url": channel.stream_url,
                    "metadata": channel.metadata,
                }
                for channel in result.channels
            ],
            "prober": result.prober,
            "details": result.details,
        }
