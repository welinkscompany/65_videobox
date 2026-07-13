from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from videobox_api.models import MaterializeLibraryAssetRequest
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore


def build_media_library_router(
    project_store: LocalProjectStore, library_store: MediaLibraryStore,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/media-library/assets/{library_asset_id:path}/materialize",
        status_code=status.HTTP_201_CREATED,
    )
    def materialize_library_asset(
        library_asset_id: str, payload: MaterializeLibraryAssetRequest,
    ) -> dict[str, object]:
        asset = library_store.get_verified_asset(library_asset_id=library_asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")

        media_type = str(asset["media_type"])
        if media_type == "music":
            asset_type = AssetType.BGM
        elif media_type == "sfx":
            asset_type = AssetType.SFX
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported_media_type")

        source_path = Path(str(asset["path"]))
        if not source_path.is_file():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")

        source_pack_id = library_asset_id.split(":", 2)[1] if library_asset_id.startswith("pack:") else ""
        metadata = {
            "source_library_asset_id": library_asset_id,
            "source_pack_id": source_pack_id,
            "source_pack_version": str(asset["version"]),
            "license_snapshot": {
                "official_url": str(asset["official_license_url"]),
                "evidence_timestamp": str(asset["evidence_timestamp"]),
                "evidence_sha256": str(asset["evidence_sha256"]),
                "source": str(asset["source"]),
                "creator": str(asset["creator"]),
            },
        }
        try:
            registered = project_store.register_asset(
                project_id=payload.project_id,
                asset_type=asset_type,
                source_path=source_path,
                source_kind="media_library",
                mime_type=_mime_type(source_path),
                metadata=metadata,
            )
            result = project_store.get_asset(
                project_id=payload.project_id, asset_id=registered.asset_id,
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing") from exc

        # Library usage is a postcondition: failed project registration must not
        # mutate the global library's recent/favorite state.
        library_store.mark_recent_usage(library_asset_id=library_asset_id)
        return result

    return router


def _mime_type(path: Path) -> str | None:
    return {".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(path.suffix.lower())
