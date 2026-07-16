# Contributing to DeviceLens

Thank you for helping improve DeviceLens. Bug reports, documentation fixes, Windows-version compatibility work, device explanations, safer update research, and tests are welcome.

## Non-negotiable safety invariants

Changes proposed for the official project must preserve all of these boundaries:

- No command or tool that disables, enables, removes, restarts, updates, downloads, or installs a Windows device or driver.
- No modification of Windows Update state, the Windows driver store, firmware, or BIOS.
- No `/force`, broad selector, privilege-bypass, or fallback path that circumvents a Windows refusal.
- No model-operated click on a modifying Device Manager control. Device identification actions remain user-operated.
- No driver recommendation based only on a numerically newer version. Exact hardware identity, revision, Windows build, architecture, release branch, signature, known issues, and rollback implications must remain explicit review requirements.
- No automatic removal recommendation for disconnected historical device records.

A fork may experiment under the GPLv3 license, but a change that breaks these invariants will not be accepted into the official DeviceLens project and must not be represented as an official release.

## Development setup

DeviceLens requires Windows 11 and Python 3.11 or newer.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Before proposing a change, also run:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Behavior changes should include focused tests. Keep fixtures free of personal serial numbers, real machine-specific instance paths, credentials, and private logs.

## Modified distributions

DeviceLens is licensed under `GPL-3.0-only`. Distributed modified source versions must preserve the license and carry prominent notices that the files were changed, including a relevant date, as required by GPLv3. See [LICENSE](LICENSE) for the complete terms.
