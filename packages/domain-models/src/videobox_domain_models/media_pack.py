from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import PureWindowsPath
import re
from typing import Mapping
from urllib.parse import urlparse


_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_MEDIA_TYPES = frozenset({"music", "sfx"})
_MIN_PACK_BYTES = 300 * 1024**2
_MAX_PACK_BYTES = 500 * 1024**2


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is required")
    return value


def _non_empty_string(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(data: Mapping[str, object], field: str) -> str:
    value = _non_empty_string(data, field)
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


def _identifier(data: Mapping[str, object], field: str) -> str:
    value = _non_empty_string(data, field)
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{field} is invalid")
    return value


def _pack_path(data: Mapping[str, object]) -> str:
    value = _non_empty_string(data, "pack_path")
    path = value.replace("\\", "/")
    windows_path = PureWindowsPath(value)
    if windows_path.drive or windows_path.root or path.startswith("/") or path.startswith("//") or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("pack_path must be a safe relative path")
    return path


@dataclass(slots=True, frozen=True)
class MediaPackLicense:
    official_url: str
    commercial_use: bool
    redistribution: bool
    evidence_timestamp: datetime
    evidence_sha256: str
    attribution_required: bool
    attribution_text: str

    @classmethod
    def from_dict(cls, data: object) -> "MediaPackLicense":
        license_data = _mapping(data, "license")
        commercial_use = license_data.get("commercial_use")
        if type(commercial_use) is not bool or not commercial_use:
            raise ValueError("commercial_use must be explicitly true")
        redistribution = license_data.get("redistribution")
        if type(redistribution) is not bool or not redistribution:
            raise ValueError("redistribution must be explicitly true")

        official_url = _non_empty_string(license_data, "official_url")
        parsed_url = urlparse(official_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("official_url must be an absolute HTTP(S) URL")

        timestamp = _non_empty_string(license_data, "evidence_timestamp")
        try:
            evidence_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("evidence_timestamp must be ISO-8601") from error
        if evidence_timestamp.tzinfo is None:
            raise ValueError("evidence_timestamp must include a timezone")

        attribution_required = license_data.get("attribution_required", False)
        if type(attribution_required) is not bool:
            raise ValueError("attribution_required must be boolean")
        attribution_text = license_data.get("attribution_text", "")
        if not isinstance(attribution_text, str):
            raise ValueError("attribution_text must be a string")
        attribution_text = attribution_text.strip()
        if attribution_required and not attribution_text:
            raise ValueError("attribution_text is required when attribution_required")
        return cls(
            official_url=official_url,
            commercial_use=commercial_use,
            redistribution=redistribution,
            evidence_timestamp=evidence_timestamp,
            evidence_sha256=_sha256(license_data, "evidence_sha256"),
            attribution_required=attribution_required,
            attribution_text=attribution_text,
        )


@dataclass(slots=True, frozen=True)
class MediaPackAsset:
    asset_id: str
    library_asset_id: str
    pack_path: str
    sha256: str
    media_type: str
    duration_seconds: float
    source: str
    creator: str
    tags: tuple[str, ...]
    license: MediaPackLicense

    @classmethod
    def from_dict(
        cls, data: object, *, pack_id: str | None = None
    ) -> "MediaPackAsset":
        asset_data = _mapping(data, "asset")
        pack_id = _identifier({"pack_id": pack_id}, "pack_id")
        license_data = MediaPackLicense.from_dict(asset_data.get("license"))
        asset_id = _identifier(asset_data, "asset_id")
        media_type = _non_empty_string(asset_data, "media_type")
        if media_type not in _MEDIA_TYPES:
            raise ValueError("media_type must be music or sfx")
        duration_seconds = asset_data.get("duration_seconds")
        if (
            type(duration_seconds) not in {int, float}
            or isinstance(duration_seconds, bool)
            or not math.isfinite(duration_seconds)
            or duration_seconds <= 0
        ):
            raise ValueError("duration_seconds must be positive")

        raw_tags = asset_data.get("tags", [])
        if not isinstance(raw_tags, list) or any(not isinstance(tag, str) or not _TAG_PATTERN.fullmatch(tag) for tag in raw_tags):
            raise ValueError("tags must contain canonical lower snake_case strings")
        return cls(
            asset_id=asset_id,
            library_asset_id=f"pack:{pack_id}:{asset_id}",
            pack_path=_pack_path(asset_data),
            sha256=_sha256(asset_data, "sha256"),
            media_type=media_type,
            duration_seconds=float(duration_seconds),
            source=_non_empty_string(asset_data, "source"),
            creator=_non_empty_string(asset_data, "creator"),
            tags=tuple(raw_tags),
            license=license_data,
        )


@dataclass(slots=True, frozen=True)
class MediaPackManifest:
    pack_id: str
    version: str
    declared_bytes: int
    sha256: str
    assets: tuple[MediaPackAsset, ...]

    @classmethod
    def from_dict(cls, data: object) -> "MediaPackManifest":
        manifest_data = _mapping(data, "manifest")
        pack_id = _identifier(manifest_data, "pack_id")
        version = _non_empty_string(manifest_data, "version")
        if not _SEMVER_PATTERN.fullmatch(version):
            raise ValueError("version must be semantic version")
        declared_bytes = manifest_data.get("declared_bytes")
        if (
            type(declared_bytes) is not int
            or not _MIN_PACK_BYTES <= declared_bytes <= _MAX_PACK_BYTES
        ):
            raise ValueError("declared_bytes must be within 300-500 MiB")
        assets_data = manifest_data.get("assets")
        if not isinstance(assets_data, list) or not assets_data:
            raise ValueError("assets must be a non-empty list")
        assets = tuple(
            MediaPackAsset.from_dict(asset, pack_id=pack_id) for asset in assets_data
        )
        if len({asset.library_asset_id for asset in assets}) != len(assets):
            raise ValueError("library asset IDs must be unique")

        return cls(
            pack_id=pack_id,
            version=version,
            declared_bytes=declared_bytes,
            sha256=_sha256(manifest_data, "sha256"),
            assets=assets,
        )
