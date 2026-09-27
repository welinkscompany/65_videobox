"""Domain vocabulary for the global, owner-managed media library.

Pack assets intentionally use a different schema and identity.  User assets
are content addressed and carry an explicit lifecycle so an ingest retry can
never silently create a second copy or delete a project dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping


class LibraryMediaType(StrEnum):
    BROLL = "broll"
    MUSIC = "music"
    SFX = "sfx"
    # 사진·일러스트. 프로젝트 안 이미지는 원래 됐고, 여러 프로젝트가 나눠 쓰는
    # 자리가 없었다 (owner 승인 2026-08-20).
    IMAGE = "image"


class LibraryAssetOrigin(StrEnum):
    BUILTIN = "builtin"
    USER = "user"


class LibraryAssetRights(StrEnum):
    """이 자산을 누가 만들었고 써도 되는가 (AK W1215-4, 2026-09-28).

    **기본은 `UNKNOWN`이다.** 값을 지어내지 않는다 -- 모르면 모른다고 두고, 모르는
    자산은 수익 채널로 나가는 업로드 승인 요청에서 막힌다. 남의 것
    (`THIRD_PARTY_LICENSED`)은 허락 내용을 `rights_license_note`에 적어야 한다.
    """

    UNKNOWN = "unknown"
    OWN_FOOTAGE = "own_footage"
    AI_GENERATED = "ai_generated"
    THIRD_PARTY_LICENSED = "third_party_licensed"


def resolve_library_asset_rights(
    rights_source: "LibraryAssetRights | str", license_note: str | None
) -> tuple["LibraryAssetRights", str | None]:
    try:
        resolved = LibraryAssetRights(rights_source)
    except ValueError as error:
        raise ValueError("rights_source_invalid") from error
    note = (license_note or "").strip() or None
    if resolved is LibraryAssetRights.THIRD_PARTY_LICENSED and note is None:
        raise ValueError("rights_license_note_required")
    return resolved, note


class LibraryAssetLifecycle(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    NEEDS_ATTENTION = "needs_attention"
    TRASHED = "trashed"


# Friendly aliases for callers that used the shorter vocabulary in early
# design notes.  The canonical names above are what gets persisted.
LibraryAssetState = LibraryAssetLifecycle
LibraryAssetStatus = LibraryAssetLifecycle
LibraryAssetType = LibraryMediaType

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _json_mapping(value: Mapping[str, Any] | None, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return json.loads(json.dumps(dict(value), ensure_ascii=False))


@dataclass(slots=True, frozen=True)
class LibraryUserAsset:
    library_asset_id: str
    media_type: LibraryMediaType
    origin: LibraryAssetOrigin
    lifecycle: LibraryAssetLifecycle
    content_sha256: str
    managed_relative_path: str
    byte_count: int
    mime_type: str
    technical_metadata: dict[str, Any]
    machine_metadata: dict[str, Any]
    user_metadata: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    rights_source: LibraryAssetRights = LibraryAssetRights.UNKNOWN
    rights_license_note: str | None = None

    @property
    def cleared_for_monetized_use(self) -> bool:
        """수익 채널에 내보내도 되는가. 모르면(`unknown`) 아니다."""
        if self.rights_source is LibraryAssetRights.UNKNOWN:
            return False
        if self.rights_source is LibraryAssetRights.THIRD_PARTY_LICENSED:
            return bool(self.rights_license_note)
        return True

    @classmethod
    def create(
        cls,
        *,
        library_asset_id: str,
        media_type: LibraryMediaType | str,
        origin: LibraryAssetOrigin | str,
        content_sha256: str,
        managed_relative_path: str,
        byte_count: int,
        mime_type: str,
        technical_metadata: Mapping[str, Any] | None = None,
        machine_metadata: Mapping[str, Any] | None = None,
        user_metadata: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
        lifecycle: LibraryAssetLifecycle | str = LibraryAssetLifecycle.PROCESSING,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        trashed_at: datetime | None = None,
        rights_source: LibraryAssetRights | str = LibraryAssetRights.UNKNOWN,
        rights_license_note: str | None = None,
    ) -> "LibraryUserAsset":
        if not isinstance(library_asset_id, str) or not library_asset_id.strip():
            raise ValueError("library_asset_id is required")
        try:
            resolved_type = LibraryMediaType(media_type)
        except ValueError as error:
            raise ValueError("media_type must be broll, music, sfx or image") from error
        try:
            resolved_origin = LibraryAssetOrigin(origin)
        except ValueError as error:
            raise ValueError("origin must be builtin or user") from error
        try:
            resolved_lifecycle = LibraryAssetLifecycle(lifecycle)
        except ValueError as error:
            raise ValueError("lifecycle is invalid") from error
        if not isinstance(content_sha256, str) or not _SHA256.fullmatch(content_sha256):
            raise ValueError("content_sha256 must be a SHA-256 hex digest")
        if not isinstance(managed_relative_path, str) or not managed_relative_path.strip():
            raise ValueError("managed_relative_path is required")
        if type(byte_count) is not int or byte_count < 0:
            raise ValueError("byte_count must be a non-negative integer")
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError("mime_type is required")
        normalized_path = managed_relative_path.strip().replace("\\", "/")
        windows_path = PureWindowsPath(normalized_path)
        path_parts = PurePosixPath(normalized_path).parts
        if windows_path.drive or normalized_path.startswith("/") or any(part in {"", ".", ".."} for part in path_parts):
            raise ValueError("managed_relative_path must be a safe relative path")
        resolved_rights, resolved_note = resolve_library_asset_rights(rights_source, rights_license_note)
        now = created_at or _utc_now()
        return cls(
            library_asset_id=library_asset_id.strip(),
            media_type=resolved_type,
            origin=resolved_origin,
            lifecycle=resolved_lifecycle,
            content_sha256=content_sha256.lower(),
            managed_relative_path=normalized_path,
            byte_count=byte_count,
            mime_type=mime_type.strip(),
            technical_metadata=_json_mapping(technical_metadata, "technical_metadata"),
            machine_metadata=_json_mapping(machine_metadata, "machine_metadata"),
            user_metadata=_json_mapping(user_metadata, "user_metadata"),
            provenance=_json_mapping(provenance, "provenance"),
            created_at=now,
            updated_at=updated_at or now,
            trashed_at=trashed_at,
            rights_source=resolved_rights,
            rights_license_note=resolved_note,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LibraryUserAsset":
        def parse_timestamp(value: Any) -> datetime | None:
            if value in (None, ""):
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        return cls.create(
            library_asset_id=str(row["library_asset_id"]),
            media_type=str(row["media_type"]),
            origin=str(row["origin"]),
            lifecycle=str(row["lifecycle"]),
            content_sha256=str(row["content_sha256"]),
            managed_relative_path=str(row["managed_relative_path"]),
            byte_count=int(row["byte_count"]),
            mime_type=str(row["mime_type"]),
            technical_metadata=json.loads(str(row.get("technical_json", "{}"))),
            machine_metadata=json.loads(str(row.get("machine_json", "{}"))),
            user_metadata=json.loads(str(row.get("user_json", "{}"))),
            provenance=json.loads(str(row.get("provenance_json", "{}"))),
            created_at=parse_timestamp(row["created_at"]),
            updated_at=parse_timestamp(row["updated_at"]),
            trashed_at=parse_timestamp(row.get("trashed_at")),
            # 칸이 생기기 전 기록은 모른다(`unknown`) -- 값을 지어내지 않는다.
            rights_source=str(row.get("rights_source") or LibraryAssetRights.UNKNOWN.value),
            rights_license_note=row.get("rights_license_note"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "library_asset_id": self.library_asset_id,
            "media_type": self.media_type.value,
            "origin": self.origin.value,
            "lifecycle": self.lifecycle.value,
            "content_sha256": self.content_sha256,
            "managed_relative_path": self.managed_relative_path,
            "byte_count": self.byte_count,
            "mime_type": self.mime_type,
            "technical_metadata": self.technical_metadata,
            "machine_metadata": self.machine_metadata,
            "user_metadata": self.user_metadata,
            "provenance": self.provenance,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "trashed_at": self.trashed_at.isoformat() if self.trashed_at else None,
            "rights_source": self.rights_source.value,
            "rights_license_note": self.rights_license_note,
            "cleared_for_monetized_use": self.cleared_for_monetized_use,
        }


LibraryUserAssetRecord = LibraryUserAsset
