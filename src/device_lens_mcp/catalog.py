from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import platform
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
import httpx


CATALOG_BASE_URL = "https://www.catalog.update.microsoft.com"


def normalize_hardware_id(value: str | None) -> str:
    """Normalize only casing/whitespace; Windows IDs are opaque match strings."""
    return (value or "").strip().casefold()


def broaden_hardware_id_for_search(value: str | None) -> str:
    """Create a broader Catalog query without weakening final verification."""
    return re.sub(r"&rev_[^&\\]+", "", normalize_hardware_id(value))


def matching_hardware_ids(local_ids: Iterable[str], supported_ids: Iterable[str]) -> list[str]:
    local = {normalize_hardware_id(value) for value in local_ids if normalize_hardware_id(value)}
    supported = {
        normalize_hardware_id(value)
        for value in supported_ids
        if normalize_hardware_id(value)
    }
    return sorted(local & supported)


def version_key(value: str | None) -> tuple[int, ...] | None:
    if not value or not re.fullmatch(r"\d+(?:\.\d+)+", value.strip()):
        return None
    return tuple(int(part) for part in value.split("."))


def compare_versions(installed: str | None, available: str | None) -> int | None:
    left = version_key(installed)
    right = version_key(available)
    if left is None or right is None:
        return None
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return (right > left) - (right < left)


def current_catalog_architecture() -> str | None:
    machine = platform.machine().casefold()
    if machine in {"amd64", "x86_64"}:
        return "AMD64"
    if machine in {"arm64", "aarch64"}:
        return "ARM64"
    if machine in {"x86", "i386", "i686"}:
        return "X86"
    return None


@dataclass(slots=True)
class CatalogCandidate:
    update_id: str
    title: str
    products: str | None = None
    classification: str | None = None
    last_updated: str | None = None
    version: str | None = None
    size: str | None = None
    architecture: str | None = None
    provider: str | None = None
    model: str | None = None
    version_date: str | None = None
    supported_hardware_ids: list[str] = field(default_factory=list)
    matched_hardware_ids: list[str] = field(default_factory=list)
    details_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_search_results(html: str) -> list[CatalogCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find(
        "table",
        id=lambda value: bool(value) and str(value).endswith("updateMatches"),
    )
    if table is None:
        return []
    results: list[CatalogCandidate] = []
    for row in table.find_all("tr"):
        row_id = row.get("id", "")
        match = re.match(r"([0-9a-f-]{36})_R\d+$", row_id, re.I)
        cells = row.find_all("td")
        if match is None or len(cells) < 7:
            continue
        results.append(
            CatalogCandidate(
                update_id=match.group(1).lower(),
                title=cells[1].get_text(" ", strip=True),
                products=cells[2].get_text(" ", strip=True) or None,
                classification=cells[3].get_text(" ", strip=True) or None,
                last_updated=cells[4].get_text(" ", strip=True) or None,
                version=cells[5].get_text(" ", strip=True) or None,
                size=cells[6].get_text(" ", strip=True) or None,
            )
        )
    return results


def _text_by_id(soup: BeautifulSoup, element_id: str) -> str | None:
    element = soup.find(id=element_id)
    if element is None:
        return None
    value = element.get_text(" ", strip=True)
    return value or None


def parse_catalog_details(html: str, candidate: CatalogCandidate) -> CatalogCandidate:
    soup = BeautifulSoup(html, "html.parser")
    hardware_box = soup.find(id="driverhwIDs")
    hardware_ids = [] if hardware_box is None else [
        value.get_text(" ", strip=True)
        for value in hardware_box.find_all("div", recursive=False)
        if value.get_text(" ", strip=True)
    ]
    architecture = _text_by_id(soup, "archDiv")
    if architecture and ":" in architecture:
        architecture = architecture.split(":", 1)[1].strip()
    candidate.architecture = architecture
    candidate.provider = _text_by_id(soup, "ScopedViewHandler_driverProvider")
    candidate.model = _text_by_id(soup, "ScopedViewHandler_driverModel")
    candidate.version = _text_by_id(soup, "ScopedViewHandler_version") or candidate.version
    candidate.version_date = _text_by_id(soup, "ScopedViewHandler_versionDate")
    products = _text_by_id(soup, "productsDiv")
    if products and ":" in products:
        products = products.split(":", 1)[1].strip()
    candidate.products = products or candidate.products
    candidate.supported_hardware_ids = hardware_ids
    candidate.details_url = f"{CATALOG_BASE_URL}/ScopedViewInline.aspx?updateid={candidate.update_id}"
    return candidate


class MicrosoftUpdateCatalog:
    def __init__(self, timeout: float = 30.0, client: httpx.Client | None = None) -> None:
        self.timeout = timeout
        self._client = client
        self._cache: dict[tuple[str, tuple[str, ...]], list[CatalogCandidate]] = {}

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"User-Agent": "DeviceLens-MCP/0.6 (read-only driver audit)"}
        if self._client is not None:
            response = self._client.get(url, headers=headers, **kwargs)
        else:
            response = httpx.get(url, headers=headers, timeout=self.timeout, follow_redirects=True, **kwargs)
        response.raise_for_status()
        return response

    def search(
        self,
        hardware_id: str,
        match_ids: Iterable[str] | None = None,
        max_details: int = 12,
    ) -> list[CatalogCandidate]:
        exact_id = normalize_hardware_id(hardware_id)
        if not exact_id:
            return []
        local_ids = tuple(sorted({
            normalize_hardware_id(value)
            for value in (match_ids or [hardware_id])
            if normalize_hardware_id(value)
        }))
        cache_key = (exact_id, local_ids)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Catalog search often returns no rows for a fully qualified USB
        # interface ID even when package details list it. Search the physical
        # VID/PID or VEN/DEV identity, then verify the exact ID in the details.
        search_id = broaden_hardware_id_for_search(exact_id)
        queries = [search_id.upper()]
        broader = re.sub(r"&mi_[0-9a-f]{2}.*$", "", search_id)
        if broader != search_id:
            queries.append(broader.upper())
        candidates: list[CatalogCandidate] = []
        for query in queries:
            response = self._get(f"{CATALOG_BASE_URL}/Search.aspx", params={"q": query})
            candidates = parse_search_results(response.text)
            if candidates:
                break
        candidates.sort(
            key=lambda item: (version_key(item.version) or (), _date_key(item.last_updated)),
            reverse=True,
        )
        verified: list[CatalogCandidate] = []
        expected_architecture = current_catalog_architecture()
        for candidate in candidates[:max_details]:
            detail = self._get(
                f"{CATALOG_BASE_URL}/ScopedViewInline.aspx",
                params={"updateid": candidate.update_id},
            )
            parse_catalog_details(detail.text, candidate)
            matched_ids = matching_hardware_ids(local_ids, candidate.supported_hardware_ids)
            architecture_matches = (
                expected_architecture is None
                or candidate.architecture is None
                or candidate.architecture.casefold() == expected_architecture.casefold()
            )
            product_matches = not candidate.products or "windows 11" in candidate.products.casefold()
            if matched_ids and architecture_matches and product_matches:
                candidate.matched_hardware_ids = matched_ids
                verified.append(candidate)
                break
        self._cache[cache_key] = verified
        return verified


def _date_key(value: str | None) -> datetime:
    try:
        return datetime.strptime(value or "", "%m/%d/%Y")
    except ValueError:
        return datetime.min
