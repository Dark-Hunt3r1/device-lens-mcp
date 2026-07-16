from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .catalog import MicrosoftUpdateCatalog, compare_versions, normalize_hardware_id
from .explain import explain_interface
from .models import DeviceContainer, DeviceDetail
from .snapshots import SCHEMA_VERSION, SnapshotStore
from .temporary import assess_manual_identification
from .updates import WindowsUpdateProvider
from .windows import DeviceLensPlatformError, WindowsPnPProvider


DRIVER_REVIEW_REQUIREMENTS = [
    "Treat every result as an unapproved research candidate, not an instruction to install.",
    "Independently check the official computer, motherboard, or device-manufacturer support page for the exact model.",
    "Verify exact hardware IDs, subsystem/OEM ID, revision, architecture, Windows edition/build, and driver branch.",
    "Compare release date, version semantics, published fixes, known issues, signature, and rollback implications.",
    "Prefer a coordinated OEM bundle for integrated chipset, audio, Bluetooth, and other multi-component stacks.",
    "If authoritative evidence does not establish that the candidate is the newest optimal package, report that as unknown.",
    "Do not download or install merely because DeviceLens found a numerically newer version or exact-ID Catalog match.",
    "Only install after a fresh user request in the current conversation that explicitly names each driver to install.",
    "Before any external installation action, restate the exact device, installed version, proposed version, source, risks, restart needs, and rollback plan.",
]


class DeviceLensService:
    def __init__(
        self,
        provider: WindowsPnPProvider | None = None,
        data_dir: Path | None = None,
        update_provider: WindowsUpdateProvider | None = None,
        catalog: MicrosoftUpdateCatalog | None = None,
    ) -> None:
        self.provider = provider or WindowsPnPProvider()
        self.snapshots = SnapshotStore(data_dir)
        self.update_provider = update_provider or WindowsUpdateProvider()
        self.catalog = catalog or MicrosoftUpdateCatalog()
        self._last_number_map: dict[str, str] = {}
        self._last_number_devices: dict[str, DeviceContainer] = {}

    @staticmethod
    def _sort_key(container: DeviceContainer) -> tuple[int, int, str, str]:
        return (
            0 if container.connected else 1,
            0 if container.kind == "physical" else 1,
            container.description.casefold(),
            container.container_id,
        )

    def _inventory(self, include_disconnected: bool = True) -> list[DeviceContainer]:
        return sorted(
            self.provider.list_containers(include_disconnected=include_disconnected),
            key=self._sort_key,
        )

    def _number(self, containers: list[DeviceContainer]) -> list[tuple[str, DeviceContainer]]:
        numbered = [(f"D{index:02d}", container) for index, container in enumerate(containers, start=1)]
        self._last_number_map = {number: container.stable_id for number, container in numbered}
        self._last_number_devices = {number: deepcopy(container) for number, container in numbered}
        return numbered

    @staticmethod
    def _device_summary(number: str, container: DeviceContainer) -> dict[str, Any]:
        data = container.to_dict()
        data["report_number"] = number
        return data

    @staticmethod
    def _ordered_interfaces(container: DeviceContainer) -> list[Any]:
        return sorted(
            container.devices,
            key=lambda node: (0 if node.active else 1, node.description.casefold(), node.instance_id),
        )

    def list_devices(self, include_disconnected: bool = True) -> dict[str, Any]:
        containers = self._inventory(include_disconnected)
        numbered = self._number(containers)
        devices = [self._device_summary(number, container) for number, container in numbered]
        connected = sum(1 for _, container in numbered if container.connected)
        disconnected = len(numbered) - connected
        interface_count = sum(len(container.devices) for _, container in numbered)
        kinds = Counter(container.kind for _, container in numbered)

        lines = [
            "DEVICE LENS — PHYSICAL DEVICE VIEW",
            "",
            f"Device groups: {len(numbered)} ({connected} connected, {disconnected} disconnected)",
            f"Windows interface records grouped underneath them: {interface_count}",
            "",
        ]
        for number, container in numbered:
            state = "CONNECTED" if container.connected else "HISTORY"
            active = sum(1 for node in container.devices if node.active)
            categories = ", ".join(container.categories) or "Uncategorized"
            lines.extend(
                [
                    f"{number}  [{state}]  {container.description}",
                    f"     Kind: {container.kind} | Categories: {categories}",
                    f"     Interfaces: {len(container.devices)} ({active} active)",
                ]
            )
            if container.identity_tokens:
                lines.append(f"     Hardware: {', '.join(container.identity_tokens)}")

        return {
            "ok": True,
            "summary": {
                "device_groups": len(numbered),
                "connected": connected,
                "disconnected": disconnected,
                "interface_records": interface_count,
                "kinds": dict(kinds),
            },
            "devices": devices,
            "report": "\n".join(lines),
        }

    def _resolve(self, identifier: str, containers: list[DeviceContainer]) -> tuple[str, DeviceContainer]:
        normalized = identifier.strip().casefold()
        is_report_number = re.fullmatch(r"d\d+", normalized) is not None
        if is_report_number:
            if not self._last_number_map:
                self._number(containers)
            stable_id = self._last_number_map.get(normalized.upper())
            if stable_id is None:
                raise ValueError("That D-number was not present in the most recent device report. List devices again.")
            for container in containers:
                if container.stable_id == stable_id:
                    return normalized.upper(), container
            remembered = self._last_number_devices.get(normalized.upper())
            if remembered is not None:
                remembered = deepcopy(remembered)
                remembered.status = "Disconnected"
                remembered.source = "last_report_absent"
                for node in remembered.devices:
                    node.status = "Disconnected"
                return normalized.upper(), remembered
            raise ValueError("That D-number has no remembered device record. List devices again.")

        numbered = [(f"D{index:02d}", container) for index, container in enumerate(containers, start=1)]
        for number, container in numbered:
            if normalized in {container.stable_id.casefold(), container.container_id.casefold()}:
                return number, container

        exact_names = [
            (number, container)
            for number, container in numbered
            if normalized in {container.description.casefold(), (container.model_name or "").casefold()}
        ]
        if len(exact_names) == 1:
            return exact_names[0]

        partial = [
            (number, container)
            for number, container in numbered
            if normalized and normalized in container.description.casefold()
        ]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            matches = ", ".join(f"{number} {container.description}" for number, container in partial[:10])
            raise ValueError(f"Device name is ambiguous. Use a report number: {matches}")
        raise ValueError("Device not found. Call devicelens_list_devices and use a D-number from that report.")

    @staticmethod
    def _driver_block(detail: DeviceDetail | None) -> dict[str, Any] | None:
        if detail is None:
            return None
        return {
            "device_instance": detail.instance_id,
            "hardware_ids": detail.hardware_ids,
            "provider": detail.driver_provider,
            "version": detail.driver_version,
            "date": detail.driver_date,
            "inf": detail.driver_inf,
            "service": detail.service,
            "problem_code": detail.problem_code,
            "bus_description": detail.bus_description,
        }

    def explain_device(self, identifier: str) -> dict[str, Any]:
        containers = self._inventory(include_disconnected=True)
        number, container = self._resolve(identifier, containers)
        ordered_interfaces = self._ordered_interfaces(container)
        interfaces: list[dict[str, Any]] = []
        for index, node in enumerate(ordered_interfaces, start=1):
            explanation = explain_interface(node.description, node.instance_id)
            interfaces.append(
                {
                    "report_number": f"{number}.{index}",
                    **node.to_dict(),
                    "explanation": explanation.to_dict(),
                }
            )

        remembered_only = container.source == "last_report_absent"
        detail: DeviceDetail | None = None
        detail_error: str | None = None
        if remembered_only:
            detail_error = "The device is absent from current Windows inventory; showing its last reported metadata."
        else:
            try:
                detail = self.provider.get_container_detail(container)
            except (DeviceLensPlatformError, IndexError, ValueError) as exc:
                detail_error = str(exc)

        state = "ABSENT SINCE LAST REPORT" if remembered_only else (
            "CONNECTED" if container.connected else "DISCONNECTED HISTORY"
        )
        if remembered_only:
            assessment = (
                "This is the device that this D-number referred to in the last report. "
                "Windows no longer returns it in the current inventory."
            )
            recommendation = (
                "The D-number has been preserved and was not reassigned. List devices again when you want a new row order."
            )
        elif container.connected:
            assessment = "This device group is currently present. Its child entries are interfaces, not separate physical devices."
            recommendation = "Leave the device and its interfaces installed unless a specific problem is being diagnosed."
        else:
            assessment = "This is a remembered device instance. It is not currently generating input or acting as a connected peripheral."
            recommendation = "Leave it in history unless troubleshooting a specific stale-device problem or you no longer use the hardware."

        lines = [
            f"DEVICE {number} — {container.description}",
            "",
            "Current state:",
            f"  State: {state}",
            f"  Kind: {container.kind}",
            f"  Physical identity: {', '.join(container.identity_tokens) or 'No VID/PID or VEN/DEV token exposed'}",
            f"  Windows interfaces: {len(interfaces)}",
            "",
            "Assessment:",
            f"  {assessment}",
            "",
            "Recommendation:",
            f"  {recommendation}",
            "",
            "Interfaces:",
        ]
        for interface in interfaces:
            marker = "ACTIVE" if interface["active"] else "HISTORY"
            lines.extend(
                [
                    f"  {interface['report_number']}  [{marker}]  {interface['description']}",
                    f"        {interface['explanation']['meaning']}",
                ]
            )
        driver = self._driver_block(detail)
        if driver:
            lines.extend(
                [
                    "",
                    "Installed driver (representative parent interface):",
                    f"  Provider: {driver['provider'] or 'Unknown'}",
                    f"  Version: {driver['version'] or 'Unknown'}",
                    f"  INF: {driver['inf'] or 'Unknown'}",
                ]
            )

        return {
            "ok": True,
            "device": self._device_summary(number, container),
            "interfaces": interfaces,
            "driver": driver,
            "driver_detail_error": detail_error,
            "inventory_presence": "last_report_cache" if remembered_only else "live",
            "assessment": assessment,
            "recommendation": recommendation,
            "report": "\n".join(lines),
        }

    def _resolve_interface(self, identifier: str) -> tuple[str, DeviceContainer, Any, DeviceDetail]:
        containers = self._inventory(include_disconnected=True)
        normalized = identifier.strip().casefold()
        report_match = re.fullmatch(r"(d\d+)\.(\d+)", normalized)
        if report_match:
            number, container = self._resolve(report_match.group(1), containers)
            ordered = self._ordered_interfaces(container)
            index = int(report_match.group(2))
            if not 1 <= index <= len(ordered):
                raise ValueError(f"{number} has no interface number {index}. Explain the device again.")
            node = ordered[index - 1]
            interface_number = f"{number}.{index}"
        else:
            matches = [
                (container, node)
                for container in containers
                for node in container.devices
                if node.instance_id.casefold() == normalized
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Use an exact interface number such as D03.2 from devicelens_explain_device, "
                    "or a full device instance ID. Device names and whole-device D-numbers are not accepted."
                )
            container, node = matches[0]
            interface_number = "instance_id"
        detail = self.provider.get_detail(node.instance_id)
        if detail.instance_id.casefold() != node.instance_id.casefold():
            raise DeviceLensPlatformError("Windows returned a different device instance than the one requested.")
        return interface_number, container, node, detail

    def open_device_properties(self, interface: str) -> dict[str, Any]:
        """Open only the exact Windows Properties dialog resolved from an interface."""
        interface_number, container, node, detail = self._resolve_interface(interface)
        manual_assessment = assess_manual_identification(detail)
        process_id = self.provider.open_device_properties(detail.instance_id)
        return {
            "ok": True,
            "opened": True,
            "interface_number": interface_number,
            "physical_device": container.description,
            "interface": node.to_dict(),
            "exact_instance_id": detail.instance_id,
            "process_id": process_id,
            "device_changed": False,
            "driver_changed": False,
            "administrator_required": False,
            "manual_test_eligible": manual_assessment["eligible"],
            "manual_test_blocked_reasons": manual_assessment["blocked_reasons"],
            "model_instruction": (
                "The exact Windows device Properties dialog is open for inspection only. "
                + (
                    "A manual identification test is eligible only after the user has a working alternate input "
                    "method and the exact recovery command ready. The user must personally click Disable and Enable. "
                    if manual_assessment["eligible"]
                    else "This interface is blocked from manual identification testing. Do not instruct the user to click Disable. "
                )
                + "Do not click Disable, Uninstall, Update Driver, Roll Back Driver, or change any setting on the user's behalf."
            ),
        }

    def prepare_identification_test(
        self,
        interface: str,
    ) -> dict[str, Any]:
        interface_number, container, node, detail = self._resolve_interface(interface)
        assessment = assess_manual_identification(detail)
        manual_recovery_command = (
            f'pnputil /enable-device "{detail.instance_id}"' if assessment["eligible"] else None
        )
        return {
            "ok": True,
            "prepared_only": True,
            "interface_number": interface_number,
            "physical_device": container.description,
            "interface": node.to_dict(),
            "detail": detail.to_dict(),
            **assessment,
            "device_action_performed": False,
            "device_action_available": False,
            "suggested_observation_seconds": 60,
            "manual_recovery_command": manual_recovery_command,
            "recovery_requirements": [
                "Keep a working second mouse, touchpad, touchscreen, or keyboard available as appropriate.",
                "Copy the exact manual recovery command before disabling anything.",
                "Know how to open an Administrator terminal using the remaining input method.",
                "Do not assume a restart will re-enable a device disabled in Device Manager.",
                "Do not continue if the interface controls the only working keyboard, mouse, pointer, display, network, or storage path.",
            ],
            "model_instruction": (
                "Prefer read-only unplug/replug snapshot comparison. If the user still requests a manual test, "
                "show the exact physical device, interface, risks, and recovery steps. Open the exact Properties "
                "dialog, but require the user to click Disable and later Enable Device themselves. DeviceLens must "
                "never perform or bypass either action."
            ),
            "report": (
                f"Manual identification assessment for {interface_number}: {node.description}\n"
                f"Exact instance: {detail.instance_id}\n"
                f"Eligible: {assessment['eligible']}\n"
                + (
                    f"DeviceLens may open the exact Properties dialog; the user must manually disable and re-enable it.\n"
                    f"Manual recovery command: {manual_recovery_command}"
                    if assessment["eligible"]
                    else f"Blocked: {'; '.join(assessment['blocked_reasons'])}"
                )
            ),
        }

    def _driver_inventory(self, connected_only: bool = False) -> list[dict[str, Any]]:
        return [detail.to_dict() for detail in self.provider.list_device_details(connected_only=connected_only)]

    @staticmethod
    def _snapshot_payload(
        containers: list[DeviceContainer],
        drivers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": "current",
            "label": "Current live inventory",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "device_count": len(containers),
            "devices": [container.to_dict() for container in containers],
            "driver_count": len(drivers),
            "drivers": drivers,
        }

    def capture_snapshot(self, label: str | None = None) -> dict[str, Any]:
        devices = [container.to_dict() for container in self._inventory(include_disconnected=True)]
        drivers = self._driver_inventory(connected_only=False)
        saved = self.snapshots.save(devices, label, drivers=drivers)
        return {
            "ok": True,
            "snapshot": saved,
            "report": (
                f"Saved snapshot {saved['snapshot_id']} with {saved['device_count']} grouped devices "
                f"and {saved['driver_count']} installed device-driver records."
            ),
        }

    def list_snapshots(self) -> dict[str, Any]:
        snapshots = self.snapshots.list()
        return {
            "ok": True,
            "count": len(snapshots),
            "snapshots": snapshots,
            "report": "No snapshots saved." if not snapshots else "\n".join(
                f"{item['snapshot_id']} — {item['device_count']} devices — "
                f"{item.get('driver_count', 0)} drivers — {item['captured_at']}"
                for item in snapshots
            ),
        }

    def _load_snapshot_or_current(self, reference: str) -> dict[str, Any]:
        if reference.strip().casefold() == "current":
            return self._snapshot_payload(
                self._inventory(include_disconnected=True),
                self._driver_inventory(connected_only=False),
            )
        return self.snapshots.load(reference)

    @staticmethod
    def _driver_changes(
        before_payload: dict[str, Any],
        after_payload: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if "drivers" not in before_payload or "drivers" not in after_payload:
            return [], [
                "At least one snapshot predates driver-aware schema 2; driver versions were not compared."
            ]
        before = {
            str(item.get("instance_id", "")).casefold(): item
            for item in before_payload.get("drivers", [])
            if item.get("instance_id")
        }
        after = {
            str(item.get("instance_id", "")).casefold(): item
            for item in after_payload.get("drivers", [])
            if item.get("instance_id")
        }
        changes: list[dict[str, Any]] = []
        for instance_id in sorted(set(before) & set(after)):
            old = before[instance_id]
            new = after[instance_id]
            fields: list[str] = []
            if old.get("driver_version") != new.get("driver_version"):
                fields.append(f"version: {old.get('driver_version')} -> {new.get('driver_version')}")
            if old.get("driver_inf") != new.get("driver_inf"):
                fields.append(f"INF: {old.get('driver_inf')} -> {new.get('driver_inf')}")
            if old.get("driver_provider") != new.get("driver_provider"):
                fields.append(f"provider: {old.get('driver_provider')} -> {new.get('driver_provider')}")
            if fields:
                changes.append(
                    {
                        "instance_id": new.get("instance_id"),
                        "description": new.get("description") or old.get("description"),
                        "before": {
                            key: old.get(key)
                            for key in ("driver_provider", "driver_version", "driver_date", "driver_inf")
                        },
                        "after": {
                            key: new.get(key)
                            for key in ("driver_provider", "driver_version", "driver_date", "driver_inf")
                        },
                        "changes": fields,
                    }
                )
        return changes, []

    @staticmethod
    def _interface_signature(device: dict[str, Any]) -> set[tuple[str, str]]:
        return {
            (str(interface.get("instance_id", "")).casefold(), str(interface.get("status", "")).casefold())
            for interface in device.get("interfaces", [])
        }

    def compare_snapshots(self, before: str, after: str = "current") -> dict[str, Any]:
        before_payload = self._load_snapshot_or_current(before)
        after_payload = self._load_snapshot_or_current(after)
        before_by_id = {device["stable_id"]: device for device in before_payload.get("devices", [])}
        after_by_id = {device["stable_id"]: device for device in after_payload.get("devices", [])}

        shared = set(before_by_id) & set(after_by_id)
        removed_ids = set(before_by_id) - shared
        added_ids = set(after_by_id) - shared

        # If Windows assigned a new container ID but the hardware fingerprint is unique,
        # report it as re-enumerated instead of a misleading remove+add pair.
        before_fingerprints: dict[str, list[str]] = defaultdict(list)
        after_fingerprints: dict[str, list[str]] = defaultdict(list)
        for stable_id in removed_ids:
            fingerprint = before_by_id[stable_id].get("fingerprint")
            if fingerprint:
                before_fingerprints[fingerprint].append(stable_id)
        for stable_id in added_ids:
            fingerprint = after_by_id[stable_id].get("fingerprint")
            if fingerprint:
                after_fingerprints[fingerprint].append(stable_id)
        reenumerated: list[dict[str, Any]] = []
        for fingerprint in sorted(set(before_fingerprints) & set(after_fingerprints)):
            old_ids = before_fingerprints[fingerprint]
            new_ids = after_fingerprints[fingerprint]
            if len(old_ids) != 1 or len(new_ids) != 1:
                continue
            old_id = old_ids[0]
            new_id = new_ids[0]
            reenumerated.append(
                {
                    "description": after_by_id[new_id].get("description"),
                    "before_stable_id": old_id,
                    "after_stable_id": new_id,
                }
            )
            removed_ids.discard(old_id)
            added_ids.discard(new_id)

        changed: list[dict[str, Any]] = []
        for stable_id in sorted(shared):
            old = before_by_id[stable_id]
            new = after_by_id[stable_id]
            changes: list[str] = []
            if old.get("status") != new.get("status"):
                changes.append(f"state: {old.get('status')} -> {new.get('status')}")
            if self._interface_signature(old) != self._interface_signature(new):
                changes.append("interface set or interface state changed")
            if changes:
                changed.append(
                    {
                        "stable_id": stable_id,
                        "description": new.get("description"),
                        "changes": changes,
                    }
                )

        added = [after_by_id[key] for key in sorted(added_ids)]
        removed = [before_by_id[key] for key in sorted(removed_ids)]
        driver_changes, warnings = self._driver_changes(before_payload, after_payload)
        lines = [
            "DEVICE LENS — SNAPSHOT COMPARISON",
            "",
            f"Before: {before_payload.get('snapshot_id')} ({before_payload.get('captured_at')})",
            f"After: {after_payload.get('snapshot_id')} ({after_payload.get('captured_at')})",
            "",
            f"Added: {len(added)} | Removed: {len(removed)} | Changed: {len(changed)} | Re-enumerated: {len(reenumerated)}",
            f"Installed driver changes: {len(driver_changes)}",
        ]
        for item in added:
            lines.append(f"+ {item.get('description')} [{item.get('status')}]")
        for item in removed:
            lines.append(f"- {item.get('description')} [{item.get('status')}]")
        for item in changed:
            lines.append(f"~ {item['description']}: {'; '.join(item['changes'])}")
        for item in reenumerated:
            lines.append(f"> {item['description']}: Windows assigned a different container identity")
        for item in driver_changes:
            lines.append(f"! {item['description']}: {'; '.join(item['changes'])}")
        for warning in warnings:
            lines.append(f"WARNING: {warning}")

        return {
            "ok": True,
            "before": {key: before_payload.get(key) for key in ("snapshot_id", "captured_at", "device_count")},
            "after": {key: after_payload.get(key) for key in ("snapshot_id", "captured_at", "device_count")},
            "added": added,
            "removed": removed,
            "changed": changed,
            "reenumerated": reenumerated,
            "driver_changes": driver_changes,
            "warnings": warnings,
            "report": "\n".join(lines),
        }

    @staticmethod
    def _is_third_party_driver(detail: DeviceDetail) -> bool:
        provider = (detail.driver_provider or "").casefold()
        manufacturer = (detail.manufacturer or "").casefold()
        return bool(detail.driver_version and detail.hardware_ids) and not (
            "microsoft" in provider
            or "microsoft" in manufacturer
            or provider.startswith("(standard")
            or manufacturer.startswith("(standard")
        )

    @staticmethod
    def _catalog_hardware_id(detail: DeviceDetail) -> str | None:
        for value in detail.hardware_ids:
            normalized = normalize_hardware_id(value)
            if re.search(r"(?:vid_[0-9a-f]{4}&pid_[0-9a-f]{4}|ven_[0-9a-f]{4}&dev_[0-9a-f]{4})", normalized):
                return normalized
        return normalize_hardware_id(detail.hardware_ids[0]) if detail.hardware_ids else None

    def _select_driver_targets(
        self,
        identifier: str | None,
        details: list[DeviceDetail],
        max_catalog_checks: int,
    ) -> tuple[list[DeviceDetail], int]:
        selected = details
        if identifier:
            containers = self._inventory(include_disconnected=True)
            try:
                _, container = self._resolve(identifier, containers)
            except ValueError:
                container = None
            if container is not None:
                instance_ids = {node.instance_id.casefold() for node in container.devices}
                selected = [detail for detail in details if detail.instance_id.casefold() in instance_ids]
            else:
                normalized = identifier.strip().casefold()
                exact = [
                    detail
                    for detail in details
                    if normalized in {detail.instance_id.casefold(), (detail.description or "").casefold()}
                ]
                partial = [
                    detail
                    for detail in details
                    if normalized and normalized in (detail.description or "").casefold()
                ]
                selected = exact or partial
                if not selected:
                    raise ValueError("No connected driver device matched that identifier or name.")

        unique: dict[tuple[str, str], DeviceDetail] = {}
        for detail in selected:
            if not self._is_third_party_driver(detail):
                continue
            query = self._catalog_hardware_id(detail)
            if query:
                unique.setdefault(((detail.driver_inf or detail.instance_id).casefold(), query), detail)
        all_targets = list(unique.values())
        return all_targets[:max_catalog_checks], len(all_targets)

    def check_driver_updates(
        self,
        device: str | None = None,
        max_catalog_checks: int = 100,
    ) -> dict[str, Any]:
        if not 1 <= max_catalog_checks <= 200:
            raise ValueError("max_catalog_checks must be between 1 and 200")
        details = self.provider.list_device_details(connected_only=True)
        windows_offers = [candidate.to_dict() for candidate in self.update_provider.search_driver_updates()]
        targets, eligible_targets = self._select_driver_targets(device, details, max_catalog_checks)

        def check(detail: DeviceDetail) -> dict[str, Any]:
            hardware_id = self._catalog_hardware_id(detail)
            candidates = [] if hardware_id is None else self.catalog.search(
                hardware_id,
                match_ids=[*detail.hardware_ids, *detail.compatible_ids],
            )
            best = candidates[0] if candidates else None
            comparison = compare_versions(detail.driver_version, best.version if best else None)
            if comparison == 1:
                status = "newer_catalog_candidate"
            elif comparison == 0:
                status = "same_version_in_catalog"
            elif comparison == -1:
                status = "installed_version_is_newer"
            else:
                status = "no_verified_catalog_version"
            return {
                "instance_id": detail.instance_id,
                "description": detail.description,
                "hardware_id_searched": hardware_id,
                "installed": {
                    "provider": detail.driver_provider,
                    "version": detail.driver_version,
                    "date": detail.driver_date,
                    "inf": detail.driver_inf,
                    "signer": detail.driver_signer,
                },
                "status": status,
                "catalog_candidate": best.to_dict() if best else None,
                "matched_hardware_ids": best.matched_hardware_ids if best else [],
                "catalog_candidates_verified": len(candidates),
            }

        catalog_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(4, len(targets) or 1)) as executor:
            futures = {executor.submit(check, detail): detail for detail in targets}
            for future in as_completed(futures):
                detail = futures[future]
                try:
                    catalog_results.append(future.result())
                except Exception as exc:
                    catalog_results.append(
                        {
                            "instance_id": detail.instance_id,
                            "description": detail.description,
                            "status": "catalog_search_error",
                            "error": str(exc),
                        }
                    )
        catalog_results.sort(key=lambda item: ((item.get("description") or "").casefold(), item.get("instance_id", "")))
        newer = [item for item in catalog_results if item.get("status") == "newer_catalog_candidate"]
        lines = [
            "DEVICE LENS — READ-ONLY DRIVER UPDATE SEARCH",
            "",
            f"Windows Update applicable offers: {len(windows_offers)}",
            f"Microsoft Update Catalog packages checked: {len(catalog_results)}",
            f"Eligible third-party packages: {eligible_targets} (skipped by limit: {eligible_targets - len(targets)})",
            f"Newer exact-hardware catalog candidates: {len(newer)}",
            "",
            "No driver was downloaded or installed. Catalog candidates are evidence to review, not automatic install approval.",
        ]
        for item in newer:
            candidate = item["catalog_candidate"]
            lines.append(
                f"! {item['description']}: installed {item['installed']['version']} -> "
                f"catalog {candidate['version']} ({candidate['details_url']})"
            )
        if not newer and not windows_offers:
            lines.append(
                "No newer candidate was found in these sources. This does not prove that every manufacturer site has no newer OEM package."
            )
        generated_at = datetime.now(timezone.utc).isoformat()
        handoff_lines = [
            "DEVICE LENS — DRIVER REVIEW HANDOFF",
            f"Generated: {generated_at}",
            "Status: UNAPPROVED RESEARCH CANDIDATES ONLY",
            "DeviceLens authorization: No download or installation is authorized by this result.",
            "Required model workflow:",
            *[f"- {requirement}" for requirement in DRIVER_REVIEW_REQUIREMENTS],
            "",
        ]
        if newer:
            for index, item in enumerate(newer, start=1):
                candidate = item["catalog_candidate"]
                handoff_lines.extend(
                    [
                        f"CANDIDATE {index}",
                        f"Device: {item['description']}",
                        f"Instance: {item['instance_id']}",
                        f"Hardware ID searched: {item['hardware_id_searched']}",
                        f"Installed provider: {item['installed']['provider']}",
                        f"Installed version: {item['installed']['version']}",
                        f"Installed INF: {item['installed']['inf']}",
                        f"Catalog provider: {candidate['provider']}",
                        f"Catalog version: {candidate['version']}",
                        f"Catalog version date: {candidate['version_date'] or candidate['last_updated']}",
                        f"Catalog architecture: {candidate['architecture']}",
                        f"Catalog details: {candidate['details_url']}",
                        "Windows Update applicability: not established by the Catalog result alone",
                        "",
                    ]
                )
        else:
            handoff_lines.append("No newer exact-hardware Catalog candidate was found in this audit.")
        return {
            "ok": True,
            "searched_online": True,
            "sources": ["Windows Update Agent", "Microsoft Update Catalog"],
            "device_filter": device,
            "installed_driver_records": len(details),
            "catalog_targets_checked": len(catalog_results),
            "catalog_targets_eligible": eligible_targets,
            "catalog_targets_skipped": eligible_targets - len(targets),
            "windows_update_offers": windows_offers,
            "catalog_results": catalog_results,
            "newer_catalog_candidates": newer,
            "generated_at": generated_at,
            "install_authorized": False,
            "installation_authorization_required": (
                "A fresh user request in the current conversation explicitly naming every driver to install."
            ),
            "model_review_requirements": DRIVER_REVIEW_REQUIREMENTS,
            "review_handoff": "\n".join(handoff_lines),
            "install_performed": False,
            "download_performed": False,
            "report": "\n".join(lines),
        }

    def check_windows_updates(self) -> dict[str, Any]:
        updates = [candidate.to_dict() for candidate in self.update_provider.search_software_updates()]
        downloaded = sum(1 for item in updates if item["downloaded"])
        reboot_required = sum(1 for item in updates if item["reboot_required"])
        lines = [
            "DEVICE LENS — READ-ONLY WINDOWS SOFTWARE UPDATE SEARCH",
            "",
            f"Pending software/security updates: {len(updates)}",
            f"Already downloaded by Windows: {downloaded}",
            f"Reported as requiring restart: {reboot_required}",
            "",
            "This search did not download, install, accept, hide, or modify any update.",
        ]
        for item in updates:
            kb = ", ".join(f"KB{value}" for value in item["kb_ids"]) or "No KB listed"
            lines.append(
                f"! {item['title']} [{kb}] — downloaded: {item['downloaded']} — "
                f"restart: {item['reboot_required']}"
            )
        if not updates:
            lines.append("Windows Update Agent returned no pending software/security updates.")
        return {
            "ok": True,
            "searched_online": True,
            "source": "Windows Update Agent",
            "category": "software",
            "pending_count": len(updates),
            "already_downloaded_count": downloaded,
            "reboot_required_count": reboot_required,
            "updates": updates,
            "download_performed": False,
            "install_performed": False,
            "report": "\n".join(lines),
        }
