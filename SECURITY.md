# Security policy

## Supported versions

Security fixes are provided for the latest published DeviceLens release. Older releases may be asked to upgrade before a report is investigated.

## Reporting a vulnerability

Do not open a public issue for a suspected security vulnerability. Use GitHub's private vulnerability-reporting page for the canonical repository:

<https://github.com/Dark-Hunt3r1/device-lens-mcp/security/advisories/new>

Include the affected version, Windows version, exact reproduction steps, observed behavior, expected behavior, and the smallest safe proof of concept you can provide. Do not include personal device identifiers, serial numbers, credentials, or private logs.

Reports that involve device-state mutation, driver installation, driver-store modification, firmware or BIOS changes, forced Windows operations, or a bypass of the user-operated safety boundary are treated as security-sensitive even if no immediate damage occurred.

## Safety boundary

Official DeviceLens releases inspect and explain device state. They do not disable, enable, remove, update, download, or install devices or drivers. They do not modify Windows Update, the driver store, firmware, or BIOS, and they do not use `/force` to bypass Windows.

An artifact should not be trusted as official merely because it contains this text. Verify release provenance using [the release-verification guide](docs/release-verification.md).
