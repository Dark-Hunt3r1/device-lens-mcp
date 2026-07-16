def test_server_registers_expected_tools() -> None:
    from device_lens_mcp.server import devicelens_get_capabilities, mcp

    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    names = set(tools)
    assert names == {
        "devicelens_get_capabilities",
        "devicelens_list_devices",
        "devicelens_explain_device",
        "devicelens_open_device_properties",
        "devicelens_prepare_identification_test",
        "devicelens_capture_snapshot",
        "devicelens_list_snapshots",
        "devicelens_compare_snapshots",
        "devicelens_check_driver_updates",
        "devicelens_check_windows_updates",
    }
    assert not any("install" in name or "download" in name for name in names)
    assert not any(tool.annotations.destructiveHint for tool in tools.values())
    capabilities = devicelens_get_capabilities()
    assert capabilities["license"] == "GPL-3.0-only"
    assert capabilities["safety"]["device_changes"] is False
    assert capabilities["safety"]["device_disable"] is False
    assert capabilities["safety"]["device_enable"] is False
    assert capabilities["release_provenance"]["official_repository"] == "Dark-Hunt3r1/device-lens-mcp"
    assert capabilities["release_provenance"]["official_repository_configured"] is True
    assert "Dark-Hunt3r1/device-lens-mcp" in capabilities["release_provenance"]["verification_command"]
    assert "attestation" in capabilities["release_provenance"]["model_instruction"]
    properties_tool = tools["devicelens_open_device_properties"]
    assert properties_tool.annotations.readOnlyHint is False
    assert properties_tool.annotations.destructiveHint is False
    update_tool = tools["devicelens_check_driver_updates"]
    assert update_tool.annotations.readOnlyHint is True
    assert update_tool.annotations.destructiveHint is False
    assert update_tool.annotations.openWorldHint is True
    software_tool = tools["devicelens_check_windows_updates"]
    assert software_tool.annotations.readOnlyHint is True
    assert software_tool.annotations.destructiveHint is False
    assert software_tool.annotations.openWorldHint is True
    prepare_tool = tools["devicelens_prepare_identification_test"]
    assert prepare_tool.annotations.readOnlyHint is True
