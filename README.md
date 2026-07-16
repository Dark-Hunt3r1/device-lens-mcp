# DeviceLens MCP

DeviceLens is a local, detection-first Windows MCP server that turns Device Manager's flattened records into understandable physical-device groups. Its inventory and update workflows are read-only. It can open the exact Windows Properties dialog for an interface, but it never disables, enables, removes, updates, or installs a device or driver.

Instead of presenting twenty generic entries such as `HID-compliant device`, DeviceLens uses Windows device containers to show which interfaces belong to the same keyboard, mouse, headset, controller, monitor, or other peripheral.

## Current milestone

Version `0.6.0` implements the Device Explainer, update-audit foundation, exact Properties-dialog inspection, and guarded user-operated interface identification:

- Numbers physical device groups as `D01`, `D02`, and so on.
- Numbers child interfaces as `D01.1`, `D01.2`, and so on.
- Groups interfaces using Windows' real PnP container identity.
- Explains common generic names such as consumer controls, system controls, vendor-defined HID channels, and the misleading barcode-reader classification.
- Separates connected devices from disconnected history.
- Shows the installed driver version for a representative parent interface.
- Captures the complete PnP driver inventory, including internal adapters that are not useful peripheral containers.
- Saves schema-2 snapshots and compares installed driver version, INF, and provider changes.
- Searches Windows Update for currently applicable driver offers without downloading them.
- Searches Microsoft Update Catalog with a broadened discovery query, then accepts a package only when one of Windows' full local hardware or compatible IDs exactly matches a package ID. Revision-specific IDs remain distinct.
- Separately searches Windows Update for pending Windows, .NET, and security software updates without downloading or installing them.
- Can open the Windows Properties dialog for one exact `D03.2`-style interface without clicking or changing anything.
- Can assess whether a user-operated identification test is appropriate for one exact `D03.2`-style interface.
- Leaves every Disable Device and Enable Device action to the user in Windows; DeviceLens contains no device-state command.
- Never installs, downloads, disables, enables, removes, restarts, or updates a Windows device or driver, and never changes firmware, BIOS, or the driver store.

Snapshot capture writes JSON only under `%LOCALAPPDATA%\DeviceLensMCP\snapshots` by default. Set `DEVICELENS_DATA_DIR` to use another location.

## Example

```text
DEVICE D03 — Ducky One X Wireless

Current state:
  State: CONNECTED
  Kind: physical
  Physical identity: 3233:0016
  Windows interfaces: 12

Interfaces:
  D03.1  [ACTIVE]  HID Keyboard Device
        A keyboard-capable interface. Multifunction peripherals can expose one even when the whole product is not just a keyboard.
  D03.2  [ACTIVE]  HID-compliant bar code badge reader
        Windows classified this HID usage as scanner-style input. On multifunction keyboards or controllers it can be an auxiliary interface; it does not prove a physical barcode reader exists.
  D03.3  [ACTIVE]  HID-compliant consumer control device
        A media/consumer-control interface, commonly used for volume, playback, headset, or extra-device buttons.
```

The `D` numbers are positions in the most recently displayed report. DeviceLens remembers exactly which stable container each number referred to. If the inventory changes between listing and explaining, it follows that identity. If the device vanishes from current Windows inventory, DeviceLens returns its cached last-report record as `ABSENT SINCE LAST REPORT`; it never silently reuses `D01` for different hardware. The hidden container ID and hardware fingerprint remain the long-term comparison identities.

## Requirements

- Windows 11 with a recent `pnputil` that supports `/enum-containers` and XML output.
- Python 3.11 or newer.
- No administrator rights for inventory, explanation, snapshots, or update research.
- DeviceLens itself does not require administrator rights. Windows may require the user to approve a manual Device Manager action.
- No API key or account.
- A network connection is used only by the two explicit update-check tools.

Windows 10 fallback collection is planned but is not part of this first milestone.

## Install for development

```powershell
cd C:\path\to\device-lens-mcp
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the server over stdio:

```powershell
.\.venv\Scripts\python.exe -m device_lens_mcp
```

## Configure Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.device_lens]
command = "C:\\path\\to\\device-lens-mcp\\.venv\\Scripts\\python.exe"
args = ["-m", "device_lens_mcp"]
cwd = "C:\\path\\to\\device-lens-mcp"
enabled = true
default_tools_approval_mode = "writes"
startup_timeout_sec = 20
tool_timeout_sec = 180

[mcp_servers.device_lens.env]
DEVICELENS_OFFICIAL_REPOSITORY = "Dark-Hunt3r1/device-lens-mcp"
```

Restart Codex after saving, then use `/mcp` to verify that `device_lens` is connected.

## Beginner walkthrough: identify an ambiguous interface

DeviceLens is an explanation and detection tool, not a one-click driver updater. Read the exact interface information before interacting with Device Manager.

1. Call `devicelens_list_devices` and choose the physical device group you are investigating.
2. Call `devicelens_explain_device` for that group. Do not rely on a generic label such as `HID-compliant device` by itself.
3. Prefer the read-only method first: capture a snapshot, physically unplug or switch off the suspected peripheral, capture another snapshot, and compare them. The removed interface IDs usually identify the relationship without disabling anything.
4. If unplugging is impractical, call `devicelens_prepare_identification_test` for one exact interface such as `D03.2`. Stop if DeviceLens marks it ineligible.
5. Before a manual test, make sure you know how to re-enable a device and have another working input method. DeviceLens blocks descriptions and classes associated with keyboards, mice, touchpads, trackpads, trackballs, pointing devices, touchscreens, displays, network adapters, storage devices, controllers, hubs, firmware, and system devices.
6. Call `devicelens_open_device_properties` for the exact eligible interface. DeviceLens opens that instance's Properties dialog and does nothing else.
7. If needed, verify **Properties > Details > Device instance path** against the exact instance ID reported by DeviceLens. Do not identify duplicate entries only by their position in the list.
8. Copy the exact recovery command returned by DeviceLens before disabling anything. It has the form `pnputil /enable-device "EXACT_INSTANCE_ID"` and must be run by the user from an Administrator terminal if normal Device Manager recovery is unavailable.
9. The user may choose **Disable Device** manually, observe what stops working for no longer than about one minute, and then manually choose **Enable Device** for that same instance. DeviceLens and the model must not click either control.
10. If Windows refuses the action, stop. Do not use `/force`, another administrative tool, or a different selector to bypass the refusal. Return to snapshot comparison, physical unplug/replug testing, screenshots, and read-only metadata.

There is no guaranteed automatic restoration. The user remains responsible for re-enabling anything they manually disable. If that recovery step is not understood and available before the test begins, do not perform the test.

### If a mouse was disabled accidentally

DeviceLens will not approve a mouse or pointing-device interface for a manual test, but recovery should still be understood before opening Device Manager:

- If the exact Properties dialog remains open, use the keyboard to move through its controls and select **Enable Device**.
- Otherwise, connect a second USB mouse, use a touchpad or touchscreen, or use the keyboard to open an Administrator terminal and run the exact recovery command that was copied before the test.
- The recovery command enables only the exact recorded device instance and contains no `/force` option.
- Do not rely on restarting Windows. A device manually disabled in Device Manager may remain disabled after restart.
- If there is no alternate input method and the user cannot operate an Administrator terminal with the keyboard, the test must not begin.

## Tools

### `devicelens_get_capabilities`

Reports the platform, safety boundary, and recommended workflow.

### `devicelens_list_devices`

Returns a structured inventory and a clean text report. Set `include_disconnected=false` to show only current devices.

### `devicelens_explain_device`

Accepts a report number such as `D03`, a container ID, a stable ID, or an unambiguous device name. Returns numbered interfaces, plain-language explanations, an assessment, a recommendation, and representative installed-driver metadata.

### `devicelens_open_device_properties`

UI-only. Accepts one exact interface number such as `D03.2`, resolves and verifies its full Windows instance ID, and opens that instance's Windows Properties dialog using the documented Device Manager entry point. The tool does not click any button, change a setting, require administrator access, or authorize a later action. A model may inspect the dialog, but it must obtain a new explicit request before clicking Disable, Uninstall, Update Driver, Roll Back Driver, or any other modifying control.

### `devicelens_prepare_identification_test`

Read-only. Accepts one exact interface number such as `D03.2` and reports whether a user-operated identification test is appropriate. Parent devices, internal buses, primary keyboard/mouse classes, storage, display, network, firmware, system, controller, adapter, and hub-level entries are excluded. DeviceLens performs no device-state action; the user must manually perform and reverse any Device Manager action.

### `devicelens_capture_snapshot`

Writes a local JSON snapshot without changing Windows. This is intentionally not annotated as protocol-level read-only because it creates a file.

### `devicelens_list_snapshots`

Lists locally saved DeviceLens snapshots.

### `devicelens_compare_snapshots`

Compares two snapshots or a saved snapshot against `current`. Reports added, removed, changed, and re-enumerated device groups plus installed driver version, INF, and provider changes. Version-1 snapshots remain readable, but DeviceLens warns that they do not contain driver inventory.

### `devicelens_check_driver_updates`

Performs a read-only online search. It queries the configured Windows Update service once for applicable, not-installed driver offers. It also searches Microsoft Update Catalog for connected third-party packages, verifies the exact hardware ID in package details, filters for this machine's architecture and Windows 11 products, and compares numeric version components.

Pass a D-number or device name to check one device. Without a device, it checks up to `max_catalog_checks` distinct third-party packages (default 100) and reports the eligible, checked, and skipped counts separately. Internal devices can be addressed by their Windows name, for example `Bluetooth Adapter`, even though they are intentionally omitted from the peripheral-container report.

Catalog results are reported as review candidates. A newer exact-ID Catalog version is not presented as automatically installable when Windows Update is not offering it.

Every update result also includes a `review_handoff` text block designed to be copied into another model or read from the latest tool result. It includes the exact device instance, hardware ID, installed package, candidate package, official details link, and an instruction to obtain fresh user confirmation before any separate download or installation action.

The same result includes structured `model_review_requirements`, `install_authorized: false`, and the required authorization boundary. The receiving model must independently verify the official OEM/model source, exact IDs and revision, OS/build and architecture, release branch, bundle relationships, signature, changelog, known issues, restart impact, and rollback path. A numerically newer Catalog result never authorizes an installation. Installation may only be considered after a fresh user request in the current conversation that explicitly names every driver to install.

### `devicelens_check_windows_updates`

Performs a separate read-only Windows Update Agent search for pending `Type='Software'` items such as Windows cumulative, .NET, and security updates. This is deliberately separate from the driver query because Windows Update categorizes drivers as `Type='Driver'`. It reports KB numbers, whether Windows had already downloaded an item, and whether a restart is required. DeviceLens itself never downloads, installs, accepts, hides, or modifies an update.

## Safety model

DeviceLens distinguishes these operations deliberately:

| Operation | Version 0.6.0 |
|---|---:|
| Read Windows device/container metadata | Yes |
| Read installed driver version | Yes |
| Open one exact Windows device Properties dialog | Yes, explicit UI-only tool |
| Write DeviceLens snapshot JSON | Yes, explicit tool |
| Search driver and software updates plus Microsoft Update Catalog | Yes, explicit read-only tools |
| Download drivers | No |
| Install/update drivers | No |
| Disable or enable a device | No; user-operated in Device Manager only |
| Broad, forced, permanent, parent-device, or critical-device disable | No |
| Remove devices | No |
| Delete driver packages | No |

### No safety-boundary bypass

If Windows refuses to disable an interface, that refusal is the endpoint for DeviceLens. DeviceLens has no device-state command, never uses PnPUtil's `/force` option, and never asks another shell, system tool, model, or MCP to bypass the refusal. Permission given in a conversation to "use force" does not unlock or authorize any hidden DeviceLens capability.

Models using DeviceLens must treat a rejected operation as a safety result, report it to the user, and stop. They must not reproduce the requested change outside DeviceLens with PnPUtil, PowerShell, Device Manager, or another administrative tool. DeviceLens intentionally provides no forced-disable, device-removal, driver-store, firmware, BIOS, or update-installation pathway.

Official DeviceLens releases are detection-first and safety-bounded. A modified copy that adds `/force`, broad device selectors, removal behavior, unattended installation, or a way around these protections is not an official DeviceLens release and is not endorsed by this project. Users should obtain DeviceLens from the official project repository or its linked releases and review these boundaries before granting it access to a Windows computer.

A disconnected historical record is not automatically junk. DeviceLens does not recommend removal solely for tidiness.

There is deliberately no download or installation function in version 0.6.0. A model must not treat DeviceLens output, a prior approval, or a general request to “update drivers” as installation permission. Only a fresh request naming the exact drivers can authorize a separate external installation workflow.

## Official release verification

Every published GitHub release is built by `.github/workflows/attested-release.yml`. That workflow confirms the release tag matches the package version, creates a wheel and source archive, generates a SHA-256 checksum file, and produces a cryptographically signed GitHub artifact attestation before attaching the files to the release.

The canonical source repository is [`Dark-Hunt3r1/device-lens-mcp`](https://github.com/Dark-Hunt3r1/device-lens-mcp). Models and users must independently verify that origin and run the following against a downloaded wheel or source archive before describing it as an official release:

```powershell
gh attestation verify "C:\path\to\downloaded-artifact.whl" --repo Dark-Hunt3r1/device-lens-mcp
```

If the repository is unknown or verification fails, the artifact is unverified and must not be recommended as an official DeviceLens release. A repository URL reported only by the downloaded program is not proof of origin. See [official release verification](docs/release-verification.md) for the complete procedure.

## Update-source confidence

- **Installed fact:** read directly from Windows PnP metadata.
- **Windows Update offer:** Microsoft says the update is currently applicable and not installed.
- **Catalog candidate:** Microsoft Catalog package details include the exact hardware ID, architecture, and Windows product, but Windows Update may not be actively offering it.
- **Manufacturer latest:** not yet claimed. Vendor-specific source adapters are still required before DeviceLens can make that broader statement.

Microsoft Update Catalog is an official source, but it does not publish a stable public search API. The catalog adapter is isolated so an HTML change becomes a structured `catalog_search_error` rather than a guessed result.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change. DeviceLens treats its detection-only boundary as a core feature, not an optional default.

## License

Copyright (C) 2026 Mitch.

DeviceLens is free and open-source software licensed under the **GNU General Public License, version 3 only** (`GPL-3.0-only`). No automatic permission to use a later GPL version is granted. See [LICENSE](LICENSE) for the complete unmodified license text.

Anyone may inspect, use, modify, and redistribute DeviceLens under GPLv3's terms. A distributed modified source version must carry prominent notices stating that it was modified and giving a relevant date, and the covered work must remain under GPLv3. Removing or concealing the required modification notice can violate the license and copyright holder's rights. Enforcement is a legal compliance process, not an automatic repository-deletion mechanism.

## Roadmap

1. Device and interface grouping, explanation, snapshots, and diffs. **Complete**
2. Full installed-driver snapshot inventory, including internal PnP devices. **Complete**
3. Read-only Windows Update and exact-ID Microsoft Catalog discovery. **Complete**
4. Vendor-source adapters with exact model/OEM compatibility and authoritative links.
5. Continue improving vendor-source research and handoff evidence; any installation remains outside DeviceLens.
6. Event logs, services, crash history, temperatures, GPU, and DirectX diagnostic modules.

## Independent implementation

DeviceLens is implemented from Windows' documented PnP interfaces and the MCP SDK. Its architecture, data model, tool contracts, reports, explanations, tests, and safety policy are original to this project. No code was copied from OS Doctor or the controller MCP projects discussed during planning.
