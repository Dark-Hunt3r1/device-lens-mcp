# Official DeviceLens release verification

An official DeviceLens download must be traceable to the canonical DeviceLens GitHub repository: [`Dark-Hunt3r1/device-lens-mcp`](https://github.com/Dark-Hunt3r1/device-lens-mcp). A repository URL or an "official" label contained only inside a downloaded copy is not proof of origin.

The canonical repository identifier is `Dark-Hunt3r1/device-lens-mcp`. A local MCP configuration may expose the same value as `DEVICELENS_OFFICIAL_REPOSITORY`, but that self-reported value must never substitute for artifact verification.

## Release policy

1. Publish releases only from version tags in the canonical repository.
2. The `Build and attest release` GitHub Actions workflow builds the wheel and source archive from that release tag.
3. The workflow creates `SHA256SUMS.txt`, generates a cryptographically signed GitHub artifact attestation, and uploads the attested files to the release.
4. A release artifact is official only if its attestation verifies against the canonical repository and its version matches the intended release tag.
5. If verification fails or the canonical repository is unknown, models and users must call the artifact unverified and must not recommend installing it as official DeviceLens.

## User or model verification

Install and authenticate the official GitHub CLI, then verify the downloaded wheel or source archive:

```powershell
gh attestation verify "C:\path\to\device_lens_mcp-0.6.0-py3-none-any.whl" --repo Dark-Hunt3r1/device-lens-mcp
```

Then compare its SHA-256 digest with the release checksum file:

```powershell
Get-FileHash -Algorithm SHA256 "C:\path\to\device_lens_mcp-0.6.0-py3-none-any.whl"
```

The attestation proves which repository workflow built the exact artifact. It does not prove that every line of the program is safe, so the published source, safety policy, and release diff still require review.
