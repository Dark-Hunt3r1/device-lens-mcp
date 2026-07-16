from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = {1, SCHEMA_VERSION}


def default_data_dir() -> Path:
    configured = os.environ.get("DEVICELENS_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "DeviceLensMCP"
    return Path.home() / ".device-lens-mcp"


def _slug(value: str | None) -> str:
    if not value:
        return "snapshot"
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned[:48] or "snapshot"


class SnapshotStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.snapshot_dir = self.data_dir / "snapshots"

    def save(
        self,
        devices: list[dict[str, Any]],
        label: str | None = None,
        drivers: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        captured_at = datetime.now(timezone.utc)
        base = f"{captured_at.strftime('%Y%m%dT%H%M%SZ')}-{_slug(label)}"
        path = self.snapshot_dir / f"{base}.json"
        counter = 2
        while path.exists():
            path = self.snapshot_dir / f"{base}-{counter}.json"
            counter += 1
        payload = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": path.stem,
            "label": label,
            "captured_at": captured_at.isoformat(),
            "device_count": len(devices),
            "devices": devices,
            "driver_count": len(drivers or []),
            "drivers": drivers or [],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload | {"path": str(path)}

    def list(self) -> list[dict[str, Any]]:
        if not self.snapshot_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in sorted(self.snapshot_dir.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            results.append(
                {
                    "snapshot_id": payload.get("snapshot_id", path.stem),
                    "label": payload.get("label"),
                    "captured_at": payload.get("captured_at"),
                    "device_count": payload.get("device_count", len(payload.get("devices", []))),
                    "driver_count": payload.get("driver_count", len(payload.get("drivers", []))),
                    "schema_version": payload.get("schema_version"),
                    "path": str(path),
                }
            )
        return results

    def load(self, snapshot_id: str) -> dict[str, Any]:
        if not snapshot_id or Path(snapshot_id).name != snapshot_id:
            raise ValueError("snapshot_id must be a snapshot name, not a path")
        candidate = self.snapshot_dir / (snapshot_id if snapshot_id.endswith(".json") else f"{snapshot_id}.json")
        if not candidate.is_file():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if payload.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported snapshot schema: {payload.get('schema_version')}")
        return payload
