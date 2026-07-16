from __future__ import annotations

from dataclasses import asdict, dataclass
import gc
import re
from typing import Any

from .windows import DeviceLensPlatformError


def extract_version(title: str | None) -> str | None:
    matches = re.findall(r"(?<!\d)(\d+(?:\.\d+){2,5})(?!\d)", title or "")
    return matches[-1] if matches else None


def _safe_attr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name)
    except Exception:
        return default


def _string_collection(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        return [str(value.Item(index)) for index in range(value.Count)]
    except Exception:
        return []


@dataclass(slots=True)
class WindowsUpdateCandidate:
    update_id: str | None
    revision: int | None
    title: str
    version: str | None
    hardware_id: str | None
    manufacturer: str | None
    model: str | None
    provider: str | None
    version_date: str | None
    support_url: str | None
    more_info_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SoftwareUpdateCandidate:
    update_id: str | None
    revision: int | None
    title: str
    kb_ids: list[str]
    downloaded: bool
    reboot_required: bool
    severity: str | None
    support_url: str | None
    more_info_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WindowsUpdateProvider:
    """Read-only online discovery through the Windows Update Agent COM API."""

    DRIVER_SEARCH_CRITERIA = "IsInstalled=0 and IsHidden=0 and Type='Driver'"
    SOFTWARE_SEARCH_CRITERIA = "IsInstalled=0 and IsHidden=0 and Type='Software'"

    def search_driver_updates(self) -> list[WindowsUpdateCandidate]:
        return self._search(
            self.DRIVER_SEARCH_CRITERIA,
            "DeviceLens MCP read-only driver scan",
            self._driver_candidate,
        )

    def search_software_updates(self) -> list[SoftwareUpdateCandidate]:
        return self._search(
            self.SOFTWARE_SEARCH_CRITERIA,
            "DeviceLens MCP read-only software update scan",
            self._software_candidate,
        )

    def _search(self, criteria: str, client_id: str, converter: Any) -> list[Any]:
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise DeviceLensPlatformError("pywin32 is required for Windows Update discovery.") from exc

        pythoncom.CoInitialize()
        session = searcher = result = update = None
        try:
            session = win32com.client.Dispatch("Microsoft.Update.Session")
            session.ClientApplicationID = client_id
            searcher = session.CreateUpdateSearcher()
            searcher.Online = True
            try:
                searcher.CanAutomaticallyUpgradeService = False
            except Exception:
                pass
            result = searcher.Search(criteria)
            if int(result.ResultCode) not in {2, 3}:
                raise DeviceLensPlatformError(f"Windows Update search returned result code {result.ResultCode}.")
            candidates: list[Any] = []
            for index in range(result.Updates.Count):
                update = result.Updates.Item(index)
                candidates.append(converter(update))
            return candidates
        except DeviceLensPlatformError:
            raise
        except Exception as exc:
            raise DeviceLensPlatformError(f"Windows Update search failed: {exc}") from exc
        finally:
            update = result = searcher = session = None
            gc.collect()
            pythoncom.CoUninitialize()

    @staticmethod
    def _driver_candidate(update: Any) -> WindowsUpdateCandidate:
        identity = _safe_attr(update, "Identity")
        title = str(_safe_attr(update, "Title", "Unnamed driver update"))
        return WindowsUpdateCandidate(
            update_id=str(_safe_attr(identity, "UpdateID")) if identity else None,
            revision=int(_safe_attr(identity, "RevisionNumber")) if identity else None,
            title=title,
            version=extract_version(title),
            hardware_id=_optional_string(_safe_attr(update, "DriverHardwareID")),
            manufacturer=_optional_string(_safe_attr(update, "DriverManufacturer")),
            model=_optional_string(_safe_attr(update, "DriverModel")),
            provider=_optional_string(_safe_attr(update, "DriverProvider")),
            version_date=_optional_string(_safe_attr(update, "DriverVerDate")),
            support_url=_optional_string(_safe_attr(update, "SupportUrl")),
            more_info_urls=_string_collection(_safe_attr(update, "MoreInfoUrls")),
        )

    @staticmethod
    def _software_candidate(update: Any) -> SoftwareUpdateCandidate:
        identity = _safe_attr(update, "Identity")
        return SoftwareUpdateCandidate(
            update_id=str(_safe_attr(identity, "UpdateID")) if identity else None,
            revision=int(_safe_attr(identity, "RevisionNumber")) if identity else None,
            title=str(_safe_attr(update, "Title", "Unnamed software update")),
            kb_ids=_string_collection(_safe_attr(update, "KBArticleIDs")),
            downloaded=bool(_safe_attr(update, "IsDownloaded", False)),
            reboot_required=bool(_safe_attr(update, "RebootRequired", False)),
            severity=_optional_string(_safe_attr(update, "MsrcSeverity")),
            support_url=_optional_string(_safe_attr(update, "SupportUrl")),
            more_info_urls=_string_collection(_safe_attr(update, "MoreInfoUrls")),
        )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
