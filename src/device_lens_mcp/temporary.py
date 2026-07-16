from __future__ import annotations

from typing import Any

from .models import DeviceDetail


BLOCKED_CLASSES = {
    "battery",
    "computer",
    "diskdrive",
    "display",
    "firmware",
    "hdc",
    "keyboard",
    "mouse",
    "monitor",
    "net",
    "processor",
    "scsiadapter",
    "securitydevices",
    "system",
    "storagevolume",
    "volume",
}

BLOCKED_DESCRIPTION_TERMS = {
    "bluetooth adapter",
    "composite device",
    "disk drive",
    "game controller",
    "host controller",
    "keyboard",
    "mouse",
    "pointing device",
    "root hub",
    "storage controller",
    "touch screen",
    "touchpad",
    "trackball",
    "trackpad",
    "wireless controller",
}


def assess_manual_identification(detail: DeviceDetail) -> dict[str, Any]:
    """Assess whether a user-operated identification test is appropriate."""
    instance_id = detail.instance_id.strip()
    upper_id = instance_id.upper()
    class_name = (detail.class_name or "").strip().casefold()
    description = (detail.description or "").strip().casefold()
    status = (detail.status or "").strip().casefold()
    reasons: list[str] = []

    is_narrow_interface = (
        upper_id.startswith("HID\\")
        or upper_id.startswith("BTHENUM\\")
        or upper_id.startswith("BTHLEDEVICE\\")
        or (upper_id.startswith("USB\\VID_") and "&MI_" in upper_id)
    )
    if not is_narrow_interface:
        reasons.append(
            "Only HID, Bluetooth-peripheral, or USB function-interface instances are eligible; parent devices and internal buses are excluded."
        )
    if class_name in BLOCKED_CLASSES:
        reasons.append(f"The Windows device class '{detail.class_name}' is excluded from manual tests.")
    if any(term in description for term in BLOCKED_DESCRIPTION_TERMS):
        reasons.append(
            "This description identifies primary input, a parent device, controller, adapter, hub, or storage-level device."
        )
    if status in {"disconnected", "disabled", "unknown", "stopped"}:
        reasons.append("The interface is not currently active, so disabling it would not identify a live function.")

    return {
        "eligible": not reasons,
        "blocked_reasons": reasons,
        "safety_controls": [
            "DeviceLens resolves and opens one exact device instance only",
            "DeviceLens never disables or enables a device",
            "The user must perform and reverse any Device Manager action manually",
            "A working alternate input method and manual recovery command must be ready before testing",
            "No /force, /reboot, /deviceid, class, bus, or wildcard selector",
            "A Windows refusal is final; use read-only identification instead",
        ],
    }
