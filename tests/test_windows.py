from pathlib import Path

from device_lens_mcp.windows import (
    WindowsPnPProvider,
    choose_anchor,
    parse_containers_xml,
    parse_device_detail_xml,
    parse_device_details_xml,
)


FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_containers_groups_real_interfaces() -> None:
    containers = parse_containers_xml(read_fixture("connected_containers.xml"), source="connected")
    ducky = containers[0]
    assert ducky.description == "Ducky One X Wireless"
    assert ducky.connected is True
    assert ducky.identity_tokens == ["3233:0016"]
    assert len(ducky.devices) == 3
    assert choose_anchor(ducky).instance_id == r"USB\VID_3233&PID_0016\SERIAL"


def test_provider_excludes_the_zero_system_container() -> None:
    connected = read_fixture("connected_containers.xml")
    disconnected = read_fixture("disconnected_containers.xml")

    def runner(args: list[str]) -> str:
        return disconnected if "/disconnected" in args else connected

    containers = WindowsPnPProvider(runner=runner).list_containers(include_disconnected=True)
    assert [container.description for container in containers] == [
        "Ducky One X Wireless",
        "Razer Basilisk V3 Pro 35K",
        "Wireless Controller",
    ]


def test_parse_device_detail_returns_installed_version() -> None:
    detail = parse_device_detail_xml(read_fixture("device_detail.xml"))
    assert detail.bus_description == "Ducky One X Wireless"
    assert detail.driver_provider == "Microsoft"
    assert detail.driver_version == "10.0.26100.8521"
    assert detail.driver_inf == "usb.inf"
    assert detail.hardware_ids[-1] == r"USB\VID_3233&PID_0016"
    assert len(parse_device_details_xml(read_fixture("device_detail.xml"))) == 1


def test_provider_exposes_no_device_state_action_methods() -> None:
    provider = WindowsPnPProvider(runner=lambda _args: "unused")

    assert not hasattr(provider, "disable_device")
    assert not hasattr(provider, "enable_device")


def test_provider_opens_properties_for_one_exact_instance() -> None:
    opened: list[str] = []

    def properties_opener(instance_id: str) -> int:
        opened.append(instance_id)
        return 4321

    provider = WindowsPnPProvider(
        runner=lambda _args: "unused",
        properties_opener=properties_opener,
    )
    instance_id = r"HID\VID_1234&PID_5678&MI_01\7&ABC&0&0000"

    process_id = provider.open_device_properties(instance_id)

    assert process_id == 4321
    assert opened == [instance_id]
