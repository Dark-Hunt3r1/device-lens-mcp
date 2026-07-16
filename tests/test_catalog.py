from device_lens_mcp.catalog import (
    CatalogCandidate,
    broaden_hardware_id_for_search,
    compare_versions,
    matching_hardware_ids,
    normalize_hardware_id,
    parse_catalog_details,
    parse_search_results,
)
from device_lens_mcp.updates import extract_version


def test_version_comparison_is_numeric() -> None:
    assert compare_versions("2.10.3.7", "2.11.0.3") == 1
    assert compare_versions("2.10.0", "2.9.9") == -1
    assert compare_versions("1.2.3", "1.2.3.0") == 0
    assert compare_versions("unknown", "1.2.3") is None


def test_hardware_id_normalization_preserves_revision_for_exact_matching() -> None:
    assert normalize_hardware_id(r"USB\VID_1234&PID_5678&REV_0100&MI_00") == (
        r"usb\vid_1234&pid_5678&rev_0100&mi_00"
    )


def test_catalog_query_can_be_broadened_without_weakening_final_match() -> None:
    assert broaden_hardware_id_for_search(r"PCI\VEN_10EC&DEV_8125&REV_05") == (
        r"pci\ven_10ec&dev_8125"
    )
    assert matching_hardware_ids(
        [r"PCI\VEN_10EC&DEV_8125&SUBSYS_87D71043&REV_05"],
        [r"PCI\VEN_10EC&DEV_8125&SUBSYS_87D71043&REV_04"],
    ) == []
    assert matching_hardware_ids(
        [r"PCI\VEN_10EC&DEV_8125&SUBSYS_87D71043"],
        [r"PCI\VEN_10EC&DEV_8125&SUBSYS_87D71043"],
    ) == [r"pci\ven_10ec&dev_8125&subsys_87d71043"]


def test_catalog_search_and_detail_parsing() -> None:
    update_id = "11111111-2222-4333-8444-555555555555"
    search_html = f"""
    <table id="updateMatches">
      <tr id="headerRow"><th>Title</th></tr>
      <tr id="{update_id}_R0">
        <td></td><td>Example Devices Inc. Widget Driver Update (2.11.0.3)</td>
        <td>Windows 11 Client, version 22H2 and later</td><td>Drivers (Other Hardware)</td>
        <td>1/15/2030</td><td>2.11.0.3</td><td>2.0 MB</td><td></td>
      </tr>
    </table>
    """
    candidates = parse_search_results(search_html)
    assert len(candidates) == 1
    assert candidates[0].version == "2.11.0.3"

    detail_html = """
    <div id="archDiv"><span>Architecture:</span> AMD64</div>
    <span id="ScopedViewHandler_driverProvider">Example Devices Inc.</span>
    <span id="ScopedViewHandler_driverModel">Example USB Widget</span>
    <span id="ScopedViewHandler_version">2.11.0.3</span>
    <span id="ScopedViewHandler_versionDate">1/15/2030</span>
    <div id="productsDiv"><span>Products:</span> Windows 11 Client, version 22H2 and later</div>
    <div id="driverhwIDs"><div>usb\\vid_1234&amp;pid_5678&amp;mi_00</div></div>
    """
    parsed = parse_catalog_details(detail_html, CatalogCandidate(update_id, "Example Widget"))
    assert parsed.architecture == "AMD64"
    assert parsed.products == "Windows 11 Client, version 22H2 and later"
    assert parsed.supported_hardware_ids == [r"usb\vid_1234&pid_5678&mi_00"]


def test_windows_update_title_version_extraction() -> None:
    assert extract_version("Intel Corporation - Bluetooth - 23.60.0.1") == "23.60.0.1"
    assert extract_version("Driver metadata without a version") is None
