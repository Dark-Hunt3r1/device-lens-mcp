from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import re
from typing import Any


ZERO_CONTAINER_IDS = {
    "{00000000-0000-0000-0000-000000000000}",
    "{00000000-0000-0000-ffff-ffffffffffff}",
}


def normalize_container_id(value: str | None) -> str:
    return (value or "").strip().lower()


def is_zero_container(value: str | None) -> bool:
    return normalize_container_id(value) in ZERO_CONTAINER_IDS


def _normalized_text(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def hardware_tokens(instance_ids: list[str]) -> list[str]:
    """Return stable-ish VID/PID or VEN/DEV identities from PnP instance IDs."""
    tokens: set[str] = set()
    patterns = (
        re.compile(r"(?:USB|HID)\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I),
        re.compile(r"PCI\\VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})", re.I),
    )
    for instance_id in instance_ids:
        for pattern in patterns:
            match = pattern.search(instance_id)
            if match:
                tokens.add(f"{match.group(1).upper()}:{match.group(2).upper()}")
    return sorted(tokens)


@dataclass(slots=True)
class DeviceNode:
    instance_id: str
    description: str
    status: str

    @property
    def active(self) -> bool:
        return self.status.casefold() not in {"disconnected", "unknown", "stopped", "disabled"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"active": self.active}


@dataclass(slots=True)
class DeviceContainer:
    container_id: str
    description: str
    status: str
    categories: list[str] = field(default_factory=list)
    manufacturer: str | None = None
    model_name: str | None = None
    model_number: str | None = None
    devices: list[DeviceNode] = field(default_factory=list)
    source: str = "unknown"

    @property
    def connected(self) -> bool:
        return self.status.casefold() == "connected" or any(node.active for node in self.devices)

    @property
    def stable_id(self) -> str:
        return f"container:{normalize_container_id(self.container_id)}"

    @property
    def identity_tokens(self) -> list[str]:
        return hardware_tokens([node.instance_id for node in self.devices])

    @property
    def fingerprint(self) -> str:
        parts = [
            _normalized_text(self.description),
            _normalized_text(self.model_name),
            ",".join(self.identity_tokens),
        ]
        return sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]

    @property
    def kind(self) -> str:
        prefixes = {node.instance_id.split("\\", 1)[0].upper() for node in self.devices}
        physical_prefixes = {"USB", "HID", "PCI", "BTHENUM", "BTHLEDEVICE", "DISPLAY", "SCSI", "STORAGE"}
        if prefixes & physical_prefixes:
            return "physical"
        if prefixes and prefixes <= {"ROOT", "SWD"}:
            return "virtual_or_software"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "container_id": normalize_container_id(self.container_id),
            "fingerprint": self.fingerprint,
            "description": self.description,
            "model_name": self.model_name,
            "model_number": self.model_number,
            "manufacturer": self.manufacturer,
            "status": "connected" if self.connected else "disconnected",
            "kind": self.kind,
            "categories": list(self.categories),
            "identity_tokens": self.identity_tokens,
            "interface_count": len(self.devices),
            "active_interface_count": sum(1 for node in self.devices if node.active),
            "interfaces": [node.to_dict() for node in self.devices],
        }


@dataclass(slots=True)
class DeviceDetail:
    instance_id: str
    description: str | None = None
    class_name: str | None = None
    manufacturer: str | None = None
    status: str | None = None
    hardware_ids: list[str] = field(default_factory=list)
    compatible_ids: list[str] = field(default_factory=list)
    parent: str | None = None
    service: str | None = None
    bus_description: str | None = None
    driver_provider: str | None = None
    driver_version: str | None = None
    driver_date: str | None = None
    driver_inf: str | None = None
    driver_signer: str | None = None
    problem_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
