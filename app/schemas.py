"""Pydantic v2 contracts for strict API input/output validation."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    """Base strict schema: forbids unknown fields and strips strings."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class TelemetryCreateSchema(StrictSchema):
    """Contract for telemetry point creation requests."""

    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    alt: float | None = Field(default=None, ge=-1000, le=100000)
    battery: int | None = Field(default=None, ge=0, le=100)
    status: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)


class IncidentCreateSchema(StrictSchema):
    """Contract for incident creation requests."""

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    level: int = Field(ge=1, le=5)
    location: str = Field(min_length=1, max_length=255)


class AiVoiceResultSchema(StrictSchema):
    """Contract for AI voice processing results (OpenAI response payload)."""

    transcript: str = Field(min_length=1, max_length=12000)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    confidence: float | None = Field(default=None, ge=0, le=1)
    intent: str | None = Field(default=None, min_length=1, max_length=128)
    entities: dict[str, Any] = Field(default_factory=dict)
    model: str | None = Field(default=None, min_length=1, max_length=128)


class IncidentChatSendSchema(StrictSchema):
    """Contract for posting incident chat messages."""

    text: str = Field(min_length=1, max_length=4000)
    author_id: str = Field(min_length=1, max_length=128)


class TerminalAuthCredentialsSchema(StrictSchema):
    """Write-only terminal credentials payload used only on create/update."""

    login: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    hash: str | None = Field(default=None, min_length=1, max_length=256)
    ftp_user: str | None = Field(default=None, min_length=1, max_length=128)
    ftp_password: str | None = Field(default=None, min_length=1, max_length=256)


class TerminalUpsertSchema(StrictSchema):
    """Terminal create/update contract.

    `auth_credentials` is accepted from clients but must never be exposed in
    response models.
    """

    name: str = Field(min_length=1, max_length=255)
    ip: str | None = Field(default=None, min_length=1, max_length=128)
    terminal_type: str | None = Field(default=None, min_length=1, max_length=64)
    archive_root_path: str | None = Field(default=None, min_length=1, max_length=512)
    auth_credentials: TerminalAuthCredentialsSchema | None = Field(default=None)


class TerminalReadSchema(StrictSchema):
    """Terminal response contract with credentials redacted (write-only)."""

    id: int
    name: str
    ip: str | None = None
    terminal_type: str | None = None
    archive_root_path: str | None = None
    has_auth_credentials: bool = False


# --- FastAPI migration contracts (Phase 1) ---
class AgentLocationUpdate(BaseModel):
    agent_id: str = Field(..., description="Уникальный ID агента")
    lat: float = Field(..., ge=-90, le=90, description="Широта")
    lon: float = Field(..., ge=-180, le=180, description="Долгота")
    status: Optional[str] = Field("active", description="Текущий статус агента")
    battery_level: Optional[int] = Field(None, ge=0, le=100)


class TrackerResponse(BaseModel):
    status: str
    message: str
    processed_id: Optional[str] = None


class ScanRequest(BaseModel):
    target_ip: str = Field(..., description="IP адрес или домен цели")
    scan_type: str = Field(..., description="Тип сканирования (modbus, 5g, can, osint)")
    options: dict = Field(default_factory=dict)


class ThreatIntelPayload(BaseModel):
    alias: Optional[str] = None
    email: Optional[str] = None
    context: str = Field(default="darknet_forum", description="Источник данных")


class ScanResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    message: str
