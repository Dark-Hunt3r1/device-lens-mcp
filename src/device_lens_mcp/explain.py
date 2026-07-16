from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InterfaceExplanation:
    meaning: str
    confidence: str

    def to_dict(self) -> dict[str, str]:
        return {"meaning": self.meaning, "confidence": self.confidence}


_EXACT_RULES: dict[str, str] = {
    "usb composite device": (
        "The parent USB record for one physical device that exposes several separate functions to Windows."
    ),
    "usb input device": (
        "A USB Human Interface Device channel. It is commonly the parent of buttons, keys, pointer, or vendor features."
    ),
    "hid-compliant consumer control device": (
        "A media/consumer-control interface, commonly used for volume, playback, headset, or extra-device buttons."
    ),
    "hid-compliant system controller": (
        "A system-control interface used for functions such as power, sleep, wake, or vendor-defined system keys."
    ),
    "hid-compliant device": (
        "A generic Human Interface Device channel. Windows can communicate with it but has no more specific friendly name."
    ),
    "hid-compliant vendor-defined device": (
        "A vendor-specific HID communication channel used for features that are not covered by standard keyboard, mouse, or media controls."
    ),
    "hid keyboard device": (
        "A keyboard-capable interface. Multifunction peripherals can expose one even when the whole product is not just a keyboard."
    ),
    "hid-compliant mouse": (
        "A pointer-capable interface. One physical peripheral can expose more than one mouse interface for separate feature sets."
    ),
    "hid-compliant bar code badge reader": (
        "Windows classified this HID usage as scanner-style input. On multifunction keyboards or controllers it can be an auxiliary interface; it does not prove a physical barcode reader exists."
    ),
    "microsoft input configuration device": (
        "A Windows input-configuration interface used by advanced input hardware, often alongside touchpad or controller features. It belongs to the parent device shown in this group."
    ),
    "hid-compliant game controller": "A game-controller input interface used for buttons, sticks, triggers, or controller sensors.",
    "hid-compliant touch pad": "A touchpad-capable input interface exposed by the parent device.",
    "hid-compliant headset": "A headset-control HID interface, separate from the device's audio playback and microphone endpoints.",
}


def explain_interface(description: str, instance_id: str = "") -> InterfaceExplanation:
    key = " ".join(description.strip().casefold().split())
    if key in _EXACT_RULES:
        return InterfaceExplanation(_EXACT_RULES[key], "high")

    if key.startswith("hid-") or instance_id.upper().startswith("HID\\"):
        return InterfaceExplanation(
            "A Human Interface Device function exposed by the parent hardware. The generic Windows name does not identify a separate physical device.",
            "medium",
        )
    if instance_id.upper().startswith("SWD\\"):
        return InterfaceExplanation(
            "A software-defined Windows device or component associated with the parent hardware.",
            "medium",
        )
    if instance_id.upper().startswith("ROOT\\"):
        return InterfaceExplanation(
            "A root-enumerated software or virtual device rather than a directly connected physical peripheral.",
            "medium",
        )
    return InterfaceExplanation(
        "A Windows device interface grouped under this parent. Its name is already vendor- or function-specific, so no generic-name expansion was applied.",
        "low",
    )

