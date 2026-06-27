from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


EDGE_HAS_COMMUNICATED_WITH = "HAS_COMMUNICATED_WITH"
EDGE_IS_REACHABLE_BY = "IS_REACHABLE_BY"

EDGE_LABELS = {
    EDGE_HAS_COMMUNICATED_WITH: "has communicated with",
    EDGE_IS_REACHABLE_BY: "is reachable by",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def normalize_edge_type(value: str | None) -> str:
    normalized = (value or EDGE_HAS_COMMUNICATED_WITH).strip().upper()
    normalized = normalized.replace(" ", "_").replace("-", "_")
    if normalized in {"COMMUNICATED_WITH", "HAS_COMMUNICATED"}:
        return EDGE_HAS_COMMUNICATED_WITH
    if normalized in {"REACHABLE_BY", "IS_REACHABLE"}:
        return EDGE_IS_REACHABLE_BY
    if normalized not in EDGE_LABELS:
        return EDGE_HAS_COMMUNICATED_WITH
    return normalized


OS_CODE_ALIASES = {
    "aix": "AIX",
    "android": "AND",
    "arch": "ARL",
    "archlinux": "ARL",
    "centos": "CES",
    "chromeos": "COS",
    "darwin": "MAC",
    "debian": "DEB",
    "fedora": "FED",
    "freebsd": "BSD",
    "gentoo": "GNT",
    "ios": "IOS",
    "ipad": "IPA",
    "ipados": "IPA",
    "linux": "LIN",
    "mac": "MAC",
    "macos": "MAC",
    "mint": "MIN",
    "openbsd": "OBS",
    "openwrt": "OWR",
    "raspberry": "RAS",
    "raspbian": "RAS",
    "redhat": "RHT",
    "rhel": "RHT",
    "solaris": "SOS",
    "suse": "SSE",
    "ubuntu": "UBT",
    "windows": "WIN",
    "win": "WIN",
    "xubuntu": "XBT",
}


def os_code_for(os_name: str | None, os_code: str | None = None) -> str:
    if os_code:
        return os_code.strip().upper()[:3]
    key = "".join(ch for ch in (os_name or "").lower() if ch.isalnum())
    return OS_CODE_ALIASES.get(key, "LIN")


class NetworkEdge(BaseModel):
    source: str | None = None
    target: str
    type: str = EDGE_HAS_COMMUNICATED_WITH
    protocol: str | None = None
    port: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CheckInPayload(BaseModel):
    instance_id: str | None = None
    hostname: str
    os: str = "linux"
    os_code: str | None = None
    arch: str = "unknown"
    target_triple: str | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    reachable_by: list[str] = Field(default_factory=list)
    communicated_with: list[str] = Field(default_factory=list)
    edges: list[NetworkEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] | None = None
    checked_at: str | None = None

    @property
    def node_id(self) -> str:
        return self.instance_id or self.hostname


class BytecodeJobRequest(BaseModel):
    target_instance_id: str | None = None
    target_triple: str = "arm64-apple-macos"
    mode: str = "macos_say"
    message: str = "smoke test of pwnage"
    prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BytecodeJob(BaseModel):
    id: str
    target_instance_id: str
    target_triple: str
    mode: str
    message: str
    status: str
    created_at: str
    dispatched_at: str | None = None
    completed_at: str | None = None
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    provider: str
    message: str
    model: str | None = None
