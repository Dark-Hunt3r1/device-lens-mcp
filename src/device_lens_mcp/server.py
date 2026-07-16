from __future__ import annotations

from functools import wraps
import os
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from . import __version__
from .service import DeviceLensService


mcp = FastMCP(
    "device-lens",
    instructions=(
        "DeviceLens explains Windows device records and supports user-operated interface identification without changing device state. "
        "Start with devicelens_list_devices, then pass a D-number to devicelens_explain_device. "
        "A disconnected historical record is not automatically junk. Never imply that a driver or device should be removed solely for tidiness. "
        "Online update searches never download or install a driver; results are unapproved research candidates. "
        "Independently verify the exact OEM model, IDs, revision, OS/build, branch, changelog, known issues, and rollback path. "
        "Never install based only on a DeviceLens result. Require a fresh current-conversation user request naming every exact driver. "
        "When visual confirmation is useful, devicelens_open_device_properties may open the exact resolved Properties dialog for inspection only. "
        "Opening the dialog never authorizes clicking a device-changing control. DeviceLens never disables or enables a device. "
        "Prefer unplug/replug snapshot comparison. If a manual Device Manager test is still appropriate, explain the exact interface and risks; "
        "the user must personally perform and reverse the action, and a Windows refusal is final. "
        "Before calling any DeviceLens download official, independently establish the canonical GitHub repository and verify its artifact attestation."
    ),
)
service = DeviceLensService()
OFFICIAL_REPOSITORY = os.environ.get(
    "DEVICELENS_OFFICIAL_REPOSITORY",
    "Dark-Hunt3r1/device-lens-mcp",
).strip()


READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

ONLINE_READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

LOCAL_WRITE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

LOCAL_UI = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

def _safe(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            return {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    return wrapper


@mcp.tool(annotations=READ_ONLY)
def devicelens_get_capabilities() -> dict[str, Any]:
    """Describe DeviceLens safety boundaries, platform requirements, and available workflows."""
    return {
        "ok": True,
        "name": "DeviceLens MCP",
        "version": __version__,
        "license": "GPL-3.0-only",
        "platform": "Windows 11",
        "safety": {
            "device_changes": False,
            "device_disable": False,
            "device_enable": False,
            "manual_device_actions": "user-operated in Windows Device Manager only",
            "driver_changes": False,
            "driver_downloads": False,
            "driver_installs": False,
            "driver_store_changes": False,
            "windows_update_changes": False,
            "firmware_or_bios_changes": False,
            "local_ui_opens": "exact Windows device Properties dialog only; no buttons are clicked",
            "network_access": True,
            "local_snapshot_writes": True,
        },
        "release_provenance": {
            "official_repository": OFFICIAL_REPOSITORY or None,
            "official_repository_configured": bool(OFFICIAL_REPOSITORY),
            "verification_command": (
                f"gh attestation verify <downloaded-artifact> --repo {OFFICIAL_REPOSITORY}"
                if OFFICIAL_REPOSITORY
                else None
            ),
            "model_instruction": (
                "Before calling a DeviceLens download or installation official, independently establish the canonical "
                "GitHub repository and verify the downloaded artifact's GitHub attestation against that repository. "
                "A repository URL reported only by the downloaded copy is not proof of origin. If the canonical "
                "repository is not configured or verification fails, report provenance as unverified."
            ),
        },
        "license_notice": {
            "spdx": "GPL-3.0-only",
            "modified_distribution_requirement": (
                "Distributed modified source versions must carry prominent notices stating that they were modified "
                "and giving a relevant date, as required by GPLv3 section 5."
            ),
        },
        "workflow": [
            "Call devicelens_list_devices to receive stable device groups and report numbers.",
            "Call devicelens_explain_device with a D-number to understand every child interface.",
            "Optionally call devicelens_open_device_properties with an exact Dxx.y interface to inspect its Windows dialog.",
            "Optionally capture a local snapshot and compare it after plugging, unplugging, or updating hardware.",
            "Call devicelens_check_driver_updates for a read-only online Windows Update and exact-hardware Microsoft Update Catalog search.",
            "Call devicelens_check_windows_updates separately for pending Windows, .NET, and security software updates.",
            "For an ambiguous live interface, prefer snapshot comparison after the user unplugs or reconnects the suspected hardware.",
            "If a manual test is still appropriate, call devicelens_prepare_identification_test and open the exact Properties dialog.",
            "The user—not DeviceLens or the model—must personally disable and re-enable the interface.",
        ],
    }


@mcp.tool(annotations=READ_ONLY)
def devicelens_list_devices(include_disconnected: bool = True) -> dict[str, Any]:
    """List Windows devices as numbered physical groups instead of flattened Device Manager interfaces."""
    return _safe(service.list_devices)(include_disconnected)


@mcp.tool(annotations=READ_ONLY)
def devicelens_explain_device(device: str) -> dict[str, Any]:
    """Explain one grouped device and number its Windows child interfaces (for example, D03.1)."""
    return _safe(service.explain_device)(device)


@mcp.tool(annotations=LOCAL_UI)
def devicelens_open_device_properties(interface: str) -> dict[str, Any]:
    """Open Windows Properties for one exact interface without changing it.

    Pass an interface number such as D03.2 from devicelens_explain_device, or a
    full device instance ID. This opens only the exact resolved Properties dialog.
    It never clicks Disable, Uninstall, Update Driver, Roll Back Driver, or changes
    any setting. Opening the dialog is not permission for a later modifying action.
    """
    return _safe(service.open_device_properties)(interface)


@mcp.tool(annotations=READ_ONLY)
def devicelens_prepare_identification_test(interface: str) -> dict[str, Any]:
    """Assess a user-operated identification test for one exact numbered interface.

    Pass an interface number such as D03.2 from devicelens_explain_device. The result
    states whether a manual test is appropriate and why risky devices are excluded.
    DeviceLens never disables or enables the device; the user must perform and reverse
    any Device Manager action themselves.
    """
    return _safe(service.prepare_identification_test)(interface)


@mcp.tool(annotations=LOCAL_WRITE)
def devicelens_capture_snapshot(label: str | None = None) -> dict[str, Any]:
    """Save a local DeviceLens inventory snapshot; this never changes Windows devices or drivers."""
    return _safe(service.capture_snapshot)(label)


@mcp.tool(annotations=READ_ONLY)
def devicelens_list_snapshots() -> dict[str, Any]:
    """List DeviceLens snapshots previously saved in the local application-data folder."""
    return _safe(service.list_snapshots)()


@mcp.tool(annotations=READ_ONLY)
def devicelens_compare_snapshots(before: str, after: str = "current") -> dict[str, Any]:
    """Compare two saved inventories, or compare a saved snapshot with the current live device state."""
    return _safe(service.compare_snapshots)(before, after)


@mcp.tool(annotations=ONLINE_READ_ONLY)
def devicelens_check_driver_updates(
    device: str | None = None,
    max_catalog_checks: int = 100,
) -> dict[str, Any]:
    """Search online for driver updates without downloading or installing anything.

    With a device name or D-number, checks that device's third-party driver packages.
    Without a device, checks up to max_catalog_checks distinct connected third-party packages
    and reports exactly how many eligible packages were skipped by that limit.
    """
    return _safe(service.check_driver_updates)(device, max_catalog_checks)


@mcp.tool(annotations=ONLINE_READ_ONLY)
def devicelens_check_windows_updates() -> dict[str, Any]:
    """Search for pending Windows, .NET, and security software updates without downloading or installing."""
    return _safe(service.check_windows_updates)()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
