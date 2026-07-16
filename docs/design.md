# DeviceLens design notes

## Product contract

DeviceLens answers five questions before it ever considers remediation:

1. What physical or virtual product does Windows mean?
2. Which generic Windows interfaces belong to that product?
3. Is the product currently connected, merely remembered, or software-defined?
4. What changed between two known device and installed-driver states?
5. Does Windows Update offer an applicable driver, or does Microsoft Catalog contain a newer exact-ID candidate?

DeviceLens 0.6 never mutates device state, the driver store, or Windows Update state and contains no update download or install path. It can open the exact Windows Properties dialog for a resolved device instance without operating that dialog. Any Disable Device or Enable Device action is performed and reversed by the user in Windows, never by DeviceLens or the model.

## Data flow

```text
pnputil /enum-containers ... /format xml
                    |
                    v
          WindowsPnPProvider
                    |
                    v
       DeviceContainer + DeviceNode
                    |
          +---------+----------+
          |                    |
          v                    v
 numbered text report     structured MCP data
          |
          v
 optional local snapshot and diff

pnputil /enum-devices /drivers /properties /format xml
                    |
                    v
       complete installed-driver snapshot

Windows Update Agent (separate Driver and Software queries)
                    +
          Microsoft Update Catalog
                    |
                    v
       read-only update evidence and links
```

Windows device containers are the primary grouping boundary. The zero/system container is excluded from the human physical-device view because it contains much of the machine's internal PnP infrastructure rather than one meaningful peripheral.

## Identifier policy

- `D01` is a human-readable position in the latest report, not a permanent identity.
- The server retains the last emitted D-number map and a copy of each reported record. Explanation follows that exact stable ID even if a subsequent live inventory sorts differently. If the stable ID disappears, DeviceLens returns the cached record as absent instead of failing or reusing the number.
- `container:{guid}` is the primary stable identifier returned to clients.
- `fingerprint` is derived from the product description/model plus VID/PID or VEN/DEV tokens.
- A snapshot comparison matches container identity first and uses a unique fingerprint only to recognize a re-enumerated device.

## Generic-name explanations

Explanations are intentionally conservative. They describe what the Windows interface class means without pretending to know undocumented vendor behavior. Rules return a confidence label:

- `high`: exact well-known generic name.
- `medium`: inferred from the PnP instance namespace or HID family.
- `low`: no generic expansion; the vendor/function name is preserved.

## Driver-source policy

Driver freshness must never be inferred from age alone. A future driver checker must match:

- exact hardware and compatible IDs;
- OEM/subsystem and device revision where applicable;
- Windows architecture and supported OS build;
- vendor release branch;
- installed versus available version;
- authoritative source and digital signature.

Catalog discovery may remove a revision suffix only to obtain a broader search-results page. Final package verification treats every Windows identification string as opaque and requires an exact intersection between the machine's full hardware/compatible IDs and the package's supported IDs. For example, `REV_04` cannot satisfy a local `REV_05` ID unless both sides also publish the same broader compatible ID.

The output distinguishes installed facts, Windows Update offers, Catalog candidates, future vendor offers, and unresolved/unknown status.

Snapshot schema 2 stores the full installed PnP driver inventory at the top level. This intentionally includes internal devices from the Windows system container, such as Bluetooth, Wi-Fi, chipset, storage, and audio adapters, without polluting the human peripheral grouping view.

Online discovery has no code path to download or install a package. Any separate external installer must use fresh, single-use confirmation for every operation and is outside DeviceLens.

## User-operated identification policy

The identification workflow is deliberately narrower than Device Manager:

- A read-only prepare call resolves one `Dxx.y` interface to its exact current instance ID.
- Whole-device D-numbers, names, partial matches, parent devices, internal buses, critical classes, and inactive interfaces are rejected.
- DeviceLens may open the exact Windows Properties dialog but never clicks or operates it.
- DeviceLens exposes no disable, enable, remove, restart, or driver-store command.
- The user must understand and perform both the manual disable and manual re-enable steps.
- A Windows refusal is final. The model must return to snapshot comparison, physical unplug/replug testing, screenshots, and read-only metadata rather than bypassing the refusal.

## Model handoff policy

Every driver audit explicitly says that installation is unauthorized. The receiving model must independently establish exact OEM/model suitability, hardware/subsystem/revision matching, OS/build and architecture, branch semantics, coordinated bundle requirements, signature, changes, known issues, and rollback impact. If authoritative sources do not establish the newest optimal package, the result remains unknown. A separate installation may only follow a fresh user request that names each exact driver in the current conversation.
