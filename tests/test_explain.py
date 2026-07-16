from device_lens_mcp.explain import explain_interface


def test_barcode_reader_explanation_does_not_claim_physical_scanner() -> None:
    result = explain_interface("HID-compliant bar code badge reader")
    assert result.confidence == "high"
    assert "does not prove a physical barcode reader" in result.meaning


def test_generic_hid_is_explained_as_an_interface() -> None:
    result = explain_interface("HID-compliant device", r"HID\VID_1234&PID_5678\A")
    assert "generic Human Interface Device channel" in result.meaning

