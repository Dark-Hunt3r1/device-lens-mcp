from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from typing import Callable, Iterable

from .models import DeviceContainer, DeviceDetail, DeviceNode, is_zero_container, normalize_container_id


class DeviceLensPlatformError(RuntimeError):
    """Raised when Windows device inventory cannot be collected safely."""


Runner = Callable[[list[str]], str]
PropertiesOpener = Callable[[str], int]


def _xml_payload(output: str) -> str:
    start = output.find("<?xml")
    if start < 0:
        raise DeviceLensPlatformError("PnPUtil did not return XML output.")
    return output[start:]


def _text(parent: ET.Element, name: str) -> str | None:
    element = parent.find(name)
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def parse_containers_xml(output: str, source: str = "unknown") -> list[DeviceContainer]:
    root = ET.fromstring(_xml_payload(output))
    containers: list[DeviceContainer] = []
    for element in root.findall("Container"):
        container_id = normalize_container_id(element.attrib.get("ContainerId"))
        categories = [
            category.text.strip()
            for category in element.findall("./Categories/Category")
            if category.text and category.text.strip()
        ]
        devices = [
            DeviceNode(
                instance_id=device.attrib.get("InstanceId", "").strip(),
                description=_text(device, "DeviceDescription") or "Unknown Windows device interface",
                status=_text(device, "Status") or "Unknown",
            )
            for device in element.findall("./Devices/Device")
        ]
        containers.append(
            DeviceContainer(
                container_id=container_id,
                description=_text(element, "Description") or _text(element, "ModelName") or "Unnamed device",
                status=_text(element, "Status") or source,
                categories=categories,
                manufacturer=_text(element, "Manufacturer"),
                model_name=_text(element, "ModelName"),
                model_number=_text(element, "ModelNumber"),
                devices=devices,
                source=source,
            )
        )
    return containers


def _property_values(device: ET.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for prop in device.findall("./Properties/Property"):
        key = prop.attrib.get("Key", "")
        entries = [value.text.strip() for value in prop.findall("Value") if value.text and value.text.strip()]
        if key:
            values[key] = entries
    return values


def parse_device_detail_xml(output: str) -> DeviceDetail:
    root = ET.fromstring(_xml_payload(output))
    device = root.find("Device")
    if device is None:
        raise DeviceLensPlatformError("PnPUtil did not return the requested device.")
    return _parse_device_detail(device)


def _parse_device_detail(device: ET.Element) -> DeviceDetail:
    props = _property_values(device)

    def first(key: str) -> str | None:
        entries = props.get(key, [])
        return entries[0] if entries else None

    matching_driver = next(
        (
            candidate
            for candidate in device.findall("./MatchingDrivers/DriverName")
            if "installed" in (_text(candidate, "Status") or "").casefold()
        ),
        None,
    )

    matching_version: str | None = None
    matching_date: str | None = None
    if matching_driver is not None:
        combined_version = _text(matching_driver, "DriverVersion")
        match = re.match(r"^(\S+)\s+([0-9]+(?:\.[0-9]+)+)$", combined_version or "")
        if match:
            matching_date, matching_version = match.groups()

    hardware_ids = [
        value.text.strip()
        for value in device.findall("./HardwareIds/HardwareId")
        if value.text and value.text.strip()
    ] or props.get("DEVPKEY_Device_HardwareIds", [])
    compatible_ids = [
        value.text.strip()
        for value in device.findall("./CompatibleIds/CompatibleId")
        if value.text and value.text.strip()
    ] or props.get("DEVPKEY_Device_CompatibleIds", [])

    return DeviceDetail(
        instance_id=device.attrib.get("InstanceId", ""),
        description=_text(device, "DeviceDescription"),
        class_name=_text(device, "ClassName") or first("DEVPKEY_Device_Class"),
        manufacturer=_text(device, "ManufacturerName") or first("DEVPKEY_Device_Manufacturer"),
        status=_text(device, "Status"),
        hardware_ids=hardware_ids,
        compatible_ids=compatible_ids,
        parent=_text(device, "Parent") or first("DEVPKEY_Device_Parent"),
        service=first("DEVPKEY_Device_Service"),
        bus_description=first("DEVPKEY_Device_BusReportedDeviceDesc"),
        driver_provider=first("DEVPKEY_Device_DriverProvider")
        or (_text(matching_driver, "ProviderName") if matching_driver is not None else None),
        driver_version=first("DEVPKEY_Device_DriverVersion") or matching_version,
        driver_date=first("DEVPKEY_Device_DriverDate") or matching_date,
        driver_inf=first("DEVPKEY_Device_DriverInfPath")
        or _text(device, "DriverName")
        or (matching_driver.attrib.get("DriverName") if matching_driver is not None else None),
        driver_signer=_text(matching_driver, "SignerName") if matching_driver is not None else None,
        problem_code=first("DEVPKEY_Device_ProblemCode"),
    )


def parse_device_details_xml(output: str) -> list[DeviceDetail]:
    root = ET.fromstring(_xml_payload(output))
    return [_parse_device_detail(device) for device in root.findall("Device")]


def merge_containers(containers: Iterable[DeviceContainer]) -> list[DeviceContainer]:
    merged: dict[str, DeviceContainer] = {}
    for container in containers:
        key = normalize_container_id(container.container_id)
        if key not in merged:
            merged[key] = container
            continue
        current = merged[key]
        by_id = {node.instance_id.casefold(): node for node in current.devices}
        for node in container.devices:
            by_id.setdefault(node.instance_id.casefold(), node)
        current.devices = list(by_id.values())
        if container.connected:
            current.status = "Connected"
        if not current.manufacturer:
            current.manufacturer = container.manufacturer
        if not current.model_name:
            current.model_name = container.model_name
        current.categories = sorted(set(current.categories) | set(container.categories))
    return list(merged.values())


def choose_anchor(container: DeviceContainer) -> DeviceNode:
    root_usb = re.compile(r"^USB\\VID_[^\\]+\\", re.I)
    for node in container.devices:
        if root_usb.search(node.instance_id) and "&MI_" not in node.instance_id.upper() and "&IG_" not in node.instance_id.upper():
            return node
    for node in container.devices:
        if node.description.casefold() in {
            container.description.casefold(),
            (container.model_name or "").casefold(),
        }:
            return node
    active = [node for node in container.devices if node.active]
    return active[0] if active else container.devices[0]


class WindowsPnPProvider:
    def __init__(
        self,
        runner: Runner | None = None,
        properties_opener: PropertiesOpener | None = None,
    ) -> None:
        self._runner = runner or self._run_pnputil
        self._properties_opener = properties_opener or self._open_device_properties

    @staticmethod
    def _run_pnputil(args: list[str]) -> str:
        if os.name != "nt":
            raise DeviceLensPlatformError("DeviceLens currently requires Windows 11.")
        executable = shutil.which("pnputil") or str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "pnputil.exe")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "PnPUtil failed").strip()
            raise DeviceLensPlatformError(message)
        return completed.stdout

    @staticmethod
    def _open_device_properties(instance_id: str) -> int:
        if os.name != "nt":
            raise DeviceLensPlatformError("DeviceLens currently requires Windows 11.")
        executable = shutil.which("rundll32") or str(
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "rundll32.exe"
        )
        process = subprocess.Popen(
            [
                executable,
                "devmgr.dll,DeviceProperties_RunDLL",
                "/DeviceID",
                instance_id,
            ],
            close_fds=True,
        )
        return process.pid

    def list_containers(self, include_disconnected: bool = True) -> list[DeviceContainer]:
        connected = parse_containers_xml(
            self._runner(["/enum-containers", "/connected", "/devices", "/format", "xml"]),
            source="connected",
        )
        items = connected
        if include_disconnected:
            disconnected = parse_containers_xml(
                self._runner(["/enum-containers", "/disconnected", "/devices", "/format", "xml"]),
                source="disconnected",
            )
            items = [*connected, *disconnected]
        return [container for container in merge_containers(items) if not is_zero_container(container.container_id)]

    def get_detail(self, instance_id: str) -> DeviceDetail:
        return parse_device_detail_xml(
            self._runner(
                [
                    "/enum-devices",
                    "/instanceid",
                    instance_id,
                    "/deviceids",
                    "/relations",
                    "/drivers",
                    "/properties",
                    "/format",
                    "xml",
                ]
            )
        )

    def get_container_detail(self, container: DeviceContainer) -> DeviceDetail | None:
        if not container.devices:
            return None
        return self.get_detail(choose_anchor(container).instance_id)

    def list_device_details(self, connected_only: bool = False) -> list[DeviceDetail]:
        args = ["/enum-devices"]
        if connected_only:
            args.append("/connected")
        args.extend(["/deviceids", "/drivers", "/properties", "/format", "xml"])
        return parse_device_details_xml(self._runner(args))

    def open_device_properties(self, instance_id: str) -> int:
        """Open the Windows Properties dialog for exactly one PnP instance."""
        if not instance_id or "\\" not in instance_id:
            raise ValueError("A full device instance ID is required.")
        return self._properties_opener(instance_id)
