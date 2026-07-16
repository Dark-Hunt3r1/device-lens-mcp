from pathlib import Path

from device_lens_mcp.models import DeviceContainer, DeviceDetail, DeviceNode
from device_lens_mcp.service import DeviceLensService
from device_lens_mcp.updates import SoftwareUpdateCandidate


class FakeProvider:
    def __init__(self, containers: list[DeviceContainer]) -> None:
        self.containers = containers
        self.driver_version = "1.2.3.4"
        self.device_actions: list[tuple[str, str]] = []

    def list_containers(self, include_disconnected: bool = True) -> list[DeviceContainer]:
        if include_disconnected:
            return self.containers
        return [container for container in self.containers if container.connected]

    def get_container_detail(self, container: DeviceContainer) -> DeviceDetail:
        return DeviceDetail(
            instance_id=container.devices[0].instance_id,
            hardware_ids=[container.devices[0].instance_id],
            bus_description=container.description,
            driver_provider="Example Vendor",
            driver_version=self.driver_version,
            driver_inf="oem1.inf",
        )

    def get_detail(self, instance_id: str) -> DeviceDetail:
        for container in self.containers:
            for node in container.devices:
                if node.instance_id.casefold() == instance_id.casefold():
                    return DeviceDetail(
                        instance_id=node.instance_id,
                        description=node.description,
                        class_name="HIDClass" if node.instance_id.upper().startswith("HID\\") else "USB",
                        status=node.status,
                        hardware_ids=[node.instance_id],
                        parent=container.container_id,
                        driver_provider="Example Vendor",
                        driver_version=self.driver_version,
                        driver_inf="oem1.inf",
                    )
        raise ValueError("Device not found")

    def open_device_properties(self, instance_id: str) -> int:
        self.device_actions.append(("open_properties", instance_id))
        return 4321

    def list_device_details(self, connected_only: bool = False) -> list[DeviceDetail]:
        containers = self.containers if not connected_only else [item for item in self.containers if item.connected]
        return [self.get_container_detail(container) for container in containers]


class FakeUpdateProvider:
    def search_driver_updates(self) -> list[object]:
        return []

    def search_software_updates(self) -> list[SoftwareUpdateCandidate]:
        return [
            SoftwareUpdateCandidate(
                update_id="11111111-2222-4333-8444-555555555555",
                revision=1,
                title="2030-01 Security Update (KB5000001)",
                kb_ids=["5000001"],
                downloaded=True,
                reboot_required=True,
                severity="Critical",
                support_url="https://support.microsoft.com/help/5000001",
                more_info_urls=[],
            )
        ]


class NoCandidateCatalog:
    def search(self, hardware_id: str, match_ids: list[str]) -> list[object]:
        return []


def sample_containers() -> list[DeviceContainer]:
    return [
        DeviceContainer(
            container_id="{11111111-1111-1111-1111-111111111111}",
            description="Ducky One X Wireless",
            status="Connected",
            categories=["Input.Keyboard", "Input.Mouse"],
            devices=[
                DeviceNode(r"USB\VID_3233&PID_0016\SERIAL", "USB Composite Device", "Started"),
                DeviceNode(r"HID\VID_3233&PID_0016&MI_01\A", "HID-compliant bar code badge reader", "Started"),
            ],
        ),
        DeviceContainer(
            container_id="{33333333-3333-3333-3333-333333333333}",
            description="Wireless Controller",
            status="Disconnected",
            categories=["Input.Gaming"],
            devices=[
                DeviceNode(r"USB\VID_054C&PID_09CC\OLD", "USB Composite Device", "Disconnected"),
            ],
        ),
    ]


def test_list_numbers_connected_before_history(tmp_path: Path) -> None:
    service = DeviceLensService(provider=FakeProvider(sample_containers()), data_dir=tmp_path)
    result = service.list_devices()
    assert result["summary"]["device_groups"] == 2
    assert result["devices"][0]["report_number"] == "D01"
    assert result["devices"][0]["description"] == "Ducky One X Wireless"
    assert "D02  [HISTORY]  Wireless Controller" in result["report"]


def test_explain_numbers_interfaces_and_reports_driver(tmp_path: Path) -> None:
    service = DeviceLensService(provider=FakeProvider(sample_containers()), data_dir=tmp_path)
    result = service.explain_device("D01")
    assert result["driver"]["version"] == "1.2.3.4"
    assert [item["report_number"] for item in result["interfaces"]] == ["D01.1", "D01.2"]
    assert "does not prove a physical barcode reader" in result["report"]


def test_snapshot_and_current_comparison(tmp_path: Path) -> None:
    containers = sample_containers()
    service = DeviceLensService(provider=FakeProvider(containers), data_dir=tmp_path)
    saved = service.capture_snapshot("baseline")["snapshot"]
    containers[1].status = "Connected"
    containers[1].devices[0].status = "Started"
    compared = service.compare_snapshots(saved["snapshot_id"], "current")
    assert len(compared["changed"]) == 1
    assert "state: disconnected -> connected" in compared["changed"][0]["changes"]
    assert compared["driver_changes"] == []


def test_snapshot_detects_installed_driver_version_change(tmp_path: Path) -> None:
    provider = FakeProvider(sample_containers())
    service = DeviceLensService(provider=provider, data_dir=tmp_path)
    saved = service.capture_snapshot("before-driver-update")["snapshot"]
    provider.driver_version = "2.0.0.0"

    compared = service.compare_snapshots(saved["snapshot_id"], "current")

    assert len(compared["driver_changes"]) == 2
    assert all("version: 1.2.3.4 -> 2.0.0.0" in item["changes"] for item in compared["driver_changes"])


def test_d_number_keeps_the_device_from_the_last_report(tmp_path: Path) -> None:
    containers = sample_containers()
    service = DeviceLensService(provider=FakeProvider(containers), data_dir=tmp_path)
    first = service.list_devices()
    assert first["devices"][0]["description"] == "Ducky One X Wireless"

    for node in containers[0].devices:
        node.status = "Disconnected"
    containers[0].status = "Disconnected"
    containers[1].status = "Connected"
    containers[1].devices[0].status = "Started"

    explained = service.explain_device("D01")
    assert explained["device"]["description"] == "Ducky One X Wireless"


def test_absent_d_number_returns_the_last_reported_device_instead_of_failing(tmp_path: Path) -> None:
    provider = FakeProvider(sample_containers())
    service = DeviceLensService(provider=provider, data_dir=tmp_path)
    service.list_devices()
    provider.containers = provider.containers[1:]

    explained = service.explain_device("D01")

    assert explained["device"]["description"] == "Ducky One X Wireless"
    assert explained["inventory_presence"] == "last_report_cache"
    assert "ABSENT SINCE LAST REPORT" in explained["report"]


def test_duplicate_fingerprints_are_not_guessed_as_reenumeration(tmp_path: Path) -> None:
    service = DeviceLensService(provider=FakeProvider([]), data_dir=tmp_path)

    def record(stable_id: str) -> dict[str, object]:
        return {
            "stable_id": stable_id,
            "fingerprint": "same-hardware-fingerprint",
            "description": "Identical USB Device",
            "status": "disconnected",
            "interfaces": [],
        }

    before = service.snapshots.save([record("container:old-1"), record("container:old-2")], "before")
    after = service.snapshots.save([record("container:new-1"), record("container:new-2")], "after")
    compared = service.compare_snapshots(before["snapshot_id"], after["snapshot_id"])

    assert compared["reenumerated"] == []
    assert len(compared["removed"]) == 2
    assert len(compared["added"]) == 2


def test_windows_software_update_search_is_separate_and_read_only(tmp_path: Path) -> None:
    service = DeviceLensService(
        provider=FakeProvider([]),
        update_provider=FakeUpdateProvider(),
        data_dir=tmp_path,
    )

    result = service.check_windows_updates()

    assert result["pending_count"] == 1
    assert result["already_downloaded_count"] == 1
    assert result["reboot_required_count"] == 1
    assert result["updates"][0]["kb_ids"] == ["5000001"]
    assert result["download_performed"] is False
    assert result["install_performed"] is False


def test_identification_assessment_never_changes_device_state(tmp_path: Path) -> None:
    provider = FakeProvider(sample_containers())
    service = DeviceLensService(provider=provider, data_dir=tmp_path)
    service.list_devices()

    prepared = service.prepare_identification_test("D01.1")

    assert prepared["eligible"] is True
    assert prepared["prepared_only"] is True
    assert prepared["detail"]["instance_id"].startswith("HID\\")
    assert prepared["device_action_performed"] is False
    assert prepared["device_action_available"] is False
    assert "user must manually disable and re-enable" in prepared["report"]
    assert provider.device_actions == []


def test_open_properties_resolves_one_exact_interface_without_device_change(tmp_path: Path) -> None:
    provider = FakeProvider(sample_containers())
    service = DeviceLensService(provider=provider, data_dir=tmp_path)
    service.list_devices()

    result = service.open_device_properties("D01.1")

    assert result["opened"] is True
    assert result["exact_instance_id"].startswith("HID\\")
    assert result["device_changed"] is False
    assert result["manual_test_eligible"] is True
    assert provider.device_actions == [("open_properties", result["exact_instance_id"])]


def test_identification_test_blocks_parent_and_primary_input_classes(tmp_path: Path) -> None:
    provider = FakeProvider(sample_containers())
    service = DeviceLensService(provider=provider, data_dir=tmp_path)
    service.list_devices()

    prepared = service.prepare_identification_test("D01.2")

    assert prepared["eligible"] is False
    assert provider.device_actions == []


def test_manual_identification_blocks_mouse_description_and_withholds_recovery_command(tmp_path: Path) -> None:
    containers = sample_containers()
    containers[0].devices[1].description = "HID-compliant mouse"
    provider = FakeProvider(containers)
    service = DeviceLensService(provider=provider, data_dir=tmp_path)
    service.list_devices()

    prepared = service.prepare_identification_test("D01.1")
    opened = service.open_device_properties("D01.1")

    assert prepared["eligible"] is False
    assert prepared["manual_recovery_command"] is None
    assert any("primary input" in reason for reason in prepared["blocked_reasons"])
    assert opened["manual_test_eligible"] is False
    assert "Do not instruct the user to click Disable" in opened["model_instruction"]


def test_driver_result_explicitly_withholds_install_authorization(tmp_path: Path) -> None:
    service = DeviceLensService(
        provider=FakeProvider(sample_containers()),
        update_provider=FakeUpdateProvider(),
        catalog=NoCandidateCatalog(),
        data_dir=tmp_path,
    )

    result = service.check_driver_updates(max_catalog_checks=10)

    assert result["install_authorized"] is False
    assert "explicitly naming every driver" in result["installation_authorization_required"]
    assert any("official computer" in item for item in result["model_review_requirements"])
    assert "UNAPPROVED RESEARCH CANDIDATES ONLY" in result["review_handoff"]
