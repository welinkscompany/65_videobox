"""Safe lifecycle API for the owner-managed personal media library.

The pack API remains under ``/api/media-library``.  This router owns only
content-addressed user assets and never serializes an absolute filesystem
path.  A small derivative manifest is persisted for preview affordances; the
actual preview always streams a re-checked source file.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import mimetypes
from pathlib import Path
import subprocess
from typing import Any, Callable
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from videobox_api.errors import _http_error
from videobox_api.models import (
    CorrectLibraryAssetMediaTypeRequest,
    LibraryIngestPathRequest,
    MaterializeLibraryAssetRequest,
)
from videobox_core_engine.library_ingest import LibraryIngestIdempotencyConflict, LibraryIngestService
from videobox_core_engine.library_usage import scan_library_asset_usage
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_domain_models.library_assets import LibraryAssetLifecycle, LibraryAssetOrigin, LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.managed_path_resolution import resolve_managed_path, sha256_file
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_provider_interfaces.embeddings import EmbeddingRequest

_LOGGER = logging.getLogger(__name__)


DERIVATIVE_VERSION = "v2"

#: 고칠 수 있는 갈래. 같은 갈래 안에서만 종류를 바꾼다 (owner 결정 2026-09-07).
#: 갈래를 넘으면 파일과 화면이 어긋난다 -- 그림 자리에 소리가 들어가면
#: 미리보기가 빈 그림을 그리고, 영상 자리에 소리가 들어가면 촬영본 색인이
#: 음원의 화면을 분석하려 든다.
_MEDIA_TYPE_GROUPS: dict[LibraryMediaType, str] = {
    LibraryMediaType.MUSIC: "audio",
    LibraryMediaType.SFX: "audio",
    LibraryMediaType.BROLL: "visual",
    LibraryMediaType.IMAGE: "visual",
}


class _DerivativeToolUnavailable(RuntimeError):
    pass


def _inside_any(candidate: Path, roots: tuple[Path, ...]) -> bool:
    """받아 줄 폴더 **안**인가. 폴더가 하나도 없으면 아무것도 안 받는다.

    캡컷 다리의 `_is_inside`와 같은 규칙인데 **기본값이 반대다.** 저쪽은 폴더를
    안 주면 전부 받는다(이 컴퓨터에서 손으로 켜는 서비스라 그렇다). 여기는
    밖에서 부르는 문이라, 설정이 빠지면 **닫힌 채로** 있어야 한다.
    """

    if not roots:
        return False
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
        except (ValueError, OSError):
            continue
        return True
    return False


def build_library_assets_router(
    *,
    project_store: object,
    media_library_store: MediaLibraryStore,
    user_asset_store: LibraryUserAssetStore,
    ingest_service: LibraryIngestService,
    managed_root: Path,
    managed_roots: tuple[Path, ...] | None = None,
    # 촬영본이 프로젝트에 들어오면 장면 분석을 건다. 올려서 넣는 길과 수신함은
    # 넣는 순간 걸었는데 라이브러리에서 넣는 길만 안 걸어서, 같은 자산이 어느
    # 문으로 들어왔느냐에 따라 유진의 추천이 되기도 하고 영원히 막히기도 했다.
    schedule_scene_analysis: Callable[[str, str], None] | None = None,
    # **경로로 넣는 문이 받아 줄 폴더.** 비면 그 문은 아무 경로도 안 받는다 --
    # 열어 둔 채로 기본값을 넓게 잡는 것보다, 안 켜진 것이 안전하다.
    allowed_ingest_roots: tuple[Path, ...] | None = None,
) -> APIRouter:
    router = APIRouter()
    materializer = ProjectAssetMaterializer(project_store)

    def user_asset(asset_id: str):
        return user_asset_store.get_asset(asset_id)

    def builtin_asset(asset_id: str) -> dict[str, Any] | None:
        try:
            for item in media_library_store.inspect_active_assets():
                if str(item.get("library_asset_id")) == asset_id:
                    return item
        except Exception:
            return None
        return None

    def public_user(asset: Any) -> dict[str, Any]:
        # ``to_dict`` contains a managed relative path by design.  Never add
        # the resolved root or arbitrary provenance to this response.
        value = asset.to_dict()
        value.pop("provenance", None)
        value["origin"] = LibraryAssetOrigin.USER.value
        value["preview_url"] = f"/api/library/assets/{asset.library_asset_id}/preview"
        value["thumbnail_url"] = f"/api/library/assets/{asset.library_asset_id}/thumbnail"
        # 그림에는 소리가 없다. 파형 주소를 내려보내면 화면이 그 자리를 만들고
        # 아무것도 못 그린 채 남는다.
        if asset.media_type is not LibraryMediaType.IMAGE:
            value["waveform_url"] = f"/api/library/assets/{asset.library_asset_id}/waveform"
        return value

    def public_builtin(item: dict[str, Any]) -> dict[str, Any]:
        asset_id = str(item["library_asset_id"])
        return {
            "library_asset_id": asset_id,
            "asset_id": item.get("asset_id"),
            "media_type": item.get("media_type"),
            "origin": LibraryAssetOrigin.BUILTIN.value,
            "lifecycle": "ready" if item.get("available") else "needs_attention",
            "content_sha256": item.get("sha256"),
            "byte_count": None,
            "mime_type": _mime_type(Path(str(item.get("path") or ""))),
            "duration_seconds": item.get("duration_seconds"),
            "tags": item.get("tags", []),
            "verified": bool(item.get("verified")),
            "available": bool(item.get("available")),
            "preview_url": f"/api/library/assets/{asset_id}/preview",
            "thumbnail_url": f"/api/library/assets/{asset_id}/thumbnail",
            "waveform_url": f"/api/library/assets/{asset_id}/waveform",
        }

    def find_asset(asset_id: str):
        asset = user_asset(asset_id)
        if asset is not None:
            return asset, None
        builtin = builtin_asset(asset_id)
        if builtin is not None:
            return None, builtin
        raise HTTPException(status_code=404, detail="asset_missing")

    roots = tuple(dict.fromkeys(Path(value).resolve() for value in (managed_roots or (managed_root,))))

    def source_for_user(asset: Any) -> Path:
        # Watcher imports may use a dedicated inbox/audio root while sharing
        # the same user-asset DB. Resolve only within configured roots and
        # require the content hash before serving bytes.  The walk itself is
        # shared with the library backfill in core-engine; only the choice of
        # status code lives here.
        resolution = resolve_managed_path(
            roots=roots, relative_path=asset.managed_relative_path, content_sha256=asset.content_sha256
        )
        if resolution.path is not None:
            return resolution.path
        if resolution.escaped:
            raise HTTPException(status_code=422, detail="asset_path_invalid")
        raise HTTPException(status_code=404, detail="asset_unavailable")

    @router.post("/api/library/ingest", status_code=status.HTTP_201_CREATED)
    def ingest_library_assets(
        files: list[UploadFile] = File(...),
        media_type: str = Form(...),
        idempotency_key: str | None = Form(None),
        provenance: str | None = Form(None),
    ) -> dict[str, Any]:
        try:
            resolved_type = LibraryMediaType(media_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        # Missing keys must never collapse unrelated uploads into one durable
        # retry row. Explicit keys remain the caller's retry contract.
        key = (idempotency_key or "").strip() or f"upload_{uuid4().hex}"
        try:
            provenance_value = json.loads(provenance) if provenance else {}
            if not isinstance(provenance_value, dict):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail="provenance_invalid") from exc
        items: list[dict[str, Any]] = []
        for index, upload in enumerate(files):
            item_key = key if len(files) == 1 else f"{key}:{index}"
            try:
                result = ingest_service.ingest(
                    media_type=resolved_type,
                    source=upload.file,
                    filename=upload.filename or "asset",
                    idempotency_key=item_key,
                    batch_idempotency_key=key,
                    provenance=provenance_value,
                )
                items.append(result)
            except LibraryIngestIdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail="idempotency_key_conflict") from exc
            except Exception as exc:  # one bad file does not hide a good drop
                items.append({
                    "filename": upload.filename,
                    "idempotency_key": item_key,
                    "state": "needs_attention",
                    "error_code": type(exc).__name__,
                })
        if not items:
            raise HTTPException(status_code=422, detail="files_required")
        return {
            "ingest_batch_id": ingest_service.store.create_ingest_batch(idempotency_key=key)["ingest_batch_id"],
            "items": items,
            "partial": any(item.get("state") == "needs_attention" for item in items) and any(item.get("state") == "ready" for item in items),
        }

    @router.post("/api/library/ingest-path", status_code=status.HTTP_201_CREATED)
    def ingest_library_asset_by_path(payload: LibraryIngestPathRequest) -> dict[str, Any]:
        """디스크에 이미 있는 파일 하나를 **경로로** 자료실에 넣는다.

        `POST /api/library/ingest`(multipart)와 같은 일을 하되 바이트를 다시
        올리지 않는다. 밖에서 부르는 쪽이 파일을 만들어 함께 보는 폴더에 두고
        경로만 넘긴다(owner 결정 2026-09-07).

        ## 아무 경로나 받지 않는다

        받아 줄 폴더 안의 경로만 받는다. 컨테이너가 볼 수 있는 것은 자기 자료
        폴더 전부인데, 밖에서 부르는 쪽이 그 안 아무 데나 읽게 두면 자료실이
        임의 파일 읽기 창구가 된다. 캡컷 다리가 `--allow-root`로 지키는 것과
        같은 규칙이다.

        ## **"없는 파일"과 "안 보이는 파일"을 가른다**

        둘을 같은 오류로 내면 부르는 쪽이 파일을 다시 만들며 헛돈다. 호스트
        경로(`D:` 로 시작하는 윈도우 경로 같은 것)를 그대로 넘겨서 생기는 일이 대부분인데, 그건 파일이 없는
        것이 아니라 **컨테이너가 그 이름을 모르는 것**이다.
        """
        try:
            resolved_type = LibraryMediaType(payload.media_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        roots = tuple(allowed_ingest_roots or ())
        source = Path(payload.source_path)
        if not _inside_any(source, roots):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "reason": "source_path_not_visible",
                    "message": "컨테이너가 볼 수 없는 경로입니다. 함께 보는 폴더 안에 두고 그 경로를 주세요.",
                    "visible_roots": [str(root) for root in roots],
                },
            )
        if not source.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source_path_not_found")
        if not source.is_file():
            raise HTTPException(status_code=422, detail="source_path_not_a_file")
        try:
            return ingest_service.ingest(
                media_type=resolved_type,
                source=source,
                filename=payload.filename or source.name,
                idempotency_key=payload.idempotency_key,
                provenance=payload.provenance or {},
            )
        except LibraryIngestIdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail="idempotency_key_conflict") from exc
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/library/assets")
    def list_library_assets(
        media_type: str | None = Query(None),
        q: str | None = Query(None),
        include_trashed: bool = Query(False),
        limit: int = Query(100, ge=1, le=500),
    ) -> dict[str, Any]:
        try:
            users = user_asset_store.list_assets(media_type=media_type, include_trashed=include_trashed)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        needle = (q or "").strip().lower()
        values = [public_user(asset) for asset in users if not needle or needle in json.dumps(asset.to_dict(), ensure_ascii=False).lower()]
        builtin_values = []
        for item in media_library_store.inspect_active_assets():
            item_type = str(item.get("media_type") or "")
            if media_type and item_type != media_type:
                continue
            public = public_builtin(item)
            if not needle or needle in json.dumps(public, ensure_ascii=False).lower():
                builtin_values.append(public)
        values.extend(builtin_values)
        return {"assets": values[:limit], "total": len(values)}

    # Asset identities are opaque IDs (``user_<uuid>`` or ``pack:<...>``),
    # never filesystem paths.  Keeping this route non-greedy lets the more
    # specific ``/preview``/lifecycle routes below win reliably.
    @router.get("/api/library/assets/{asset_id}")
    def get_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        return {"asset": public_user(asset) if asset is not None else public_builtin(builtin)}

    @router.get("/api/library/search")
    def search_library_assets(
        request: Request,
        q: str = Query(..., min_length=1),
        media_type: str = Query(...),
        orientation: str | None = Query(None),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            kind = LibraryMediaType(media_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_invalid") from exc
        needle = q.strip().lower()
        matches: list[dict[str, Any]] = []
        for asset in user_asset_store.list_assets(media_type=kind):
            haystack = " ".join([asset.user_metadata.get("filename", ""), json.dumps(asset.machine_metadata, ensure_ascii=False), json.dumps(asset.user_metadata, ensure_ascii=False)]).lower()
            if needle in haystack:
                result = public_user(asset)
                result["score"] = 1.0 if needle in str(asset.user_metadata.get("filename", "")).lower() else 0.5
                result["reason"] = "파일명 또는 분석 메타데이터 일치"
                matches.append(result)
        matches.sort(key=lambda value: (-float(value.get("score", 0)), value["library_asset_id"]))
        # Reuse the verified pack indexer's semantic contract whenever the
        # local embedding model is available.  User assets are merged here as
        # lexical fallbacks until Wave1 Task4 writes their descriptors.
        provider = getattr(request.app.state, "media_analysis_embedding_provider", None)
        model_name = (getattr(request.app.state, "media_analysis_profile", None) or {}).get("embedding_model_name")
        semantic = False
        # **그 "색인이 생기는 날"이 왔다**(2026-09-06). 예전 주석은 그림에 색인이
        # 없어서 음원 색인에 물으면 우연히 0건이 돌아온다고, 그 우연이 깨질 날을
        # 대비해 여기서 막아 두었다. 이제 사진도 촬영본 색인(`footage_index`)에
        # 들어간다 -- 둘 다 화면 자산이라 같은 색인이 맡는다. 그래서 사진 질의도
        # 그 색인으로 보낸다.
        if provider is not None and model_name:
            try:
                vector = [float(value) for value in provider.embed(EmbeddingRequest(model_name=model_name, inputs=(q.strip(),))).vectors[0]]
                if kind in {LibraryMediaType.BROLL, LibraryMediaType.IMAGE}:
                    # **물은 종류만 준다.** 사진과 촬영본이 같은 색인에 있어서,
                    # 안 가리면 사진을 찾는데 영상이 나온다(2026-09-06 실측: 결과
                    # 20개가 전부 촬영본이었다).
                    semantic_matches = media_library_store.find_footage_matches(
                        query_embedding=vector, orientation=orientation,
                        media_type=kind.value, limit=limit,
                    )
                else:
                    semantic_matches = media_library_store.find_audio_matches(query_embedding=vector, media_type=kind.value, limit=limit)
                for value in semantic_matches:
                    value["reason"] = "의미 기반 색인 일치"
                    value["semantic_match"] = True
                    # 색인 행에는 라이브러리 화면이 필터에 쓰는 필드가 없다.
                    # 채우지 않으면 화면이 전부 걸러내서, 배지는 `뜻으로 찾음`인데
                    # 목록에는 단어 매칭만 남는 거짓말이 된다.
                    value.setdefault("media_type", kind.value)
                    asset_ref = str(value.get("library_asset_id") or "")
                    if asset_ref:
                        value.setdefault("lifecycle", "ready")
                        value.setdefault("origin", "builtin" if asset_ref.startswith("pack:") else "user")
                matches.extend(semantic_matches)
                # 조회가 돌았어도 0건이면 보이는 목록은 전부 단어 매칭이다.
                semantic = bool(semantic_matches)
            except Exception:
                # Search remains useful with filename/metadata matches when
                # LM Studio is unavailable; never fabricate semantic scores.
                semantic = False
        matches.sort(key=lambda value: (-float(value.get("score", 0)), str(value.get("library_asset_id", value.get("content_sha256", "")))))
        # 같은 자산이 단어와 뜻 양쪽에서 잡히면 한 번만 내려보낸다. 촬영본
        # 색인 조각(`source_segment_id`가 있는 행)은 자산이 아니라 구간이라
        # 촬영본 정리 화면의 계약이므로 dedup에서 제외하고 그대로 둔다.
        seen_asset_ids: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for value in matches:
            asset_ref = str(value.get("library_asset_id") or "")
            if asset_ref and "source_segment_id" not in value:
                if asset_ref in seen_asset_ids:
                    continue
                seen_asset_ids.add(asset_ref)
            deduped.append(value)
        return {"matches": deduped[:limit], "semantic": semantic}

    def _without_ghost_projects(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """참조 중 **이미 사라진 프로젝트**를 가리키는 것을 걷어낸다.

        프로젝트 목록을 못 읽으면 아무것도 걷지 않는다 -- 목록이 비어 보인다고
        참조를 지우면 살아 있는 자산을 지우게 된다. 지우는 것은 되돌릴 수 없다.
        """
        try:
            known = {
                str(project.get("project_id", ""))
                for project in getattr(project_store, "list_projects", lambda **_: [])(include_archived=True)
            }
        except Exception:  # pragma: no cover - 목록을 못 읽으면 그대로 둔다
            _LOGGER.warning("프로젝트 목록을 못 읽어 유령 참조를 그대로 둡니다", exc_info=True)
            return locations
        # **목록이 비어 있는 것은 정상이다** -- 프로젝트를 다 지운 상태다. 처음에
        # 여기서 그냥 돌아가게 했더니 마지막 프로젝트의 유령이 안 걷혔다. 목록을
        # 못 읽는 경우는 위에서 예외로 이미 갈랐다.
        kept, ghosts = [], []
        for location in locations:
            (kept if str(location.get("project_id") or "") in known else ghosts).append(location)
        for ghost in ghosts:
            reference_id = str(ghost.get("reference_id") or "")
            if reference_id:
                try:
                    user_asset_store.remove_project_reference(reference_id)
                except Exception:  # pragma: no cover - 못 지워도 세지는 않는다
                    _LOGGER.warning("유령 참조를 못 지웠습니다: %s", reference_id, exc_info=True)
        return kept

    @router.get("/api/library/assets/{asset_id}/usage")
    def get_library_asset_usage(asset_id: str, deep: bool = False) -> dict[str, Any]:
        """이 자산을 어디서 쓰고 있나.

        **기본은 빠른 검사다**(명시적 참조만). 화면이 자산을 열 때마다 부르는
        자리인데, 깊은 검사는 **모든 프로젝트의 자산·편집 세션·타임라인을**
        읽는다 -- 실측 **1.67초**였고 프로젝트가 늘수록 그대로 늘어난다
        (2026-09-05, owner: "어느 화면이 느린지 다시 재봐").

        **지우기 전에는 깊게 본다**(`deep=True`). 옛 프로젝트가 쓰고 있는
        자산을 지우면 되돌릴 수 없다 -- 그 안전장치는 그대로 둔다.
        """
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            return {"library_asset_id": asset_id, "locations": []}
        locations = user_asset_store.usage(asset_id)
        if not deep:
            return {"library_asset_id": asset_id, "locations": locations}
        # **없는 프로젝트는 세지 않는다.** 참조 등록부는 프로젝트 폴더가 아니라
        # 자료실 DB에 있어서, 옛 삭제 경로로 지워진 프로젝트의 참조가 유령으로
        # 남았다 -- 실측 2026-09-06에 셋이 시험용 자산 열둘을 막고 있었다.
        #
        # **못 읽은 프로젝트와는 다르다.** 못 읽은 것은 아래에서 세어 알리고
        # 막는다(그 판단은 그대로 둔다). 아예 없는 것은 막을 근거가 못 된다.
        locations = _without_ghost_projects(locations)
        # **못 읽은 프로젝트를 세어 둔다**(코드리뷰 2026-09-06). 아래 훑기는
        # 프로젝트 하나에서 예외가 나면 그 프로젝트를 건너뛰는데, 계속 훑는 것
        # 자체는 맞다 -- 하나를 못 읽는다고 지우기를 통째로 막으면 안 된다.
        # 잘못은 **못 읽었다는 사실을 안 알리는 것**이었다: 그 프로젝트의
        # 사용처가 조용히 0건이 되고, 화면은 "안 쓰는 자산"이라 말하고, 창작자가
        # 쓰고 있는 자산을 지운다. 지우면 되돌릴 수 없다.
        unreadable: list[str] = []
        # Defensive reverse scan catches older projects/timelines created
        # before explicit global references were introduced.
        for project in getattr(project_store, "list_projects", lambda **_: [])(include_archived=True):
            project_id = str(project.get("project_id", ""))
            try:
                project_assets = project_store.list_assets(project_id=project_id)
                for candidate in project_assets:
                    metadata = dict(candidate.get("metadata") or {})
                    if metadata.get("source_library_asset_id") == asset_id and not any(loc.get("materialized_asset_id") == candidate.get("asset_id") for loc in locations):
                        locations.append({"project_id": project_id, "materialized_asset_id": candidate.get("asset_id"), "location": {"kind": "project_asset"}})
                sessions = []
                timelines = []
                for raw_session in getattr(project_store, "list_editing_sessions", lambda **_: [])(project_id=project_id):
                    session = dict(raw_session) if isinstance(raw_session, dict) else raw_session
                    if isinstance(session, dict):
                        session.setdefault("project_id", project_id)
                        session_id = str(session.get("session_id") or "")
                        if session_id:
                            try:
                                hydrated = project_store.get_editing_session(project_id=project_id, session_id=session_id)
                                if isinstance(hydrated, dict):
                                    session = {**hydrated, "project_id": project_id}
                            except Exception:
                                raw_json = session.get("session_json")
                                if isinstance(raw_json, str):
                                    try:
                                        decoded = json.loads(raw_json)
                                    except json.JSONDecodeError:
                                        decoded = None
                                    if isinstance(decoded, dict):
                                        session = {**decoded, **session, "project_id": project_id}
                        sessions.append(session)
                        timeline_id = str(session.get("timeline_id") or "")
                        if timeline_id:
                            try:
                                timeline = project_store.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
                                if isinstance(timeline, dict):
                                    timelines.append({**timeline, "project_id": project_id})
                            except Exception:
                                pass
                scanned = scan_library_asset_usage(
                    asset_id,
                    projects=[{"project_id": project_id, "assets": project_assets}],
                    editing_sessions=sessions,
                    timelines=timelines,
                )
                existing_location_keys = {
                    (str(item.get("project_id")), str(item.get("location", {}).get("kind")), str(item.get("location", {}).get("id") or item.get("materialized_asset_id") or ""))
                    for item in locations
                }
                for match in scanned:
                    if match.get("kind") == "project" and any(
                        str(candidate.get("metadata", {}).get("source_library_asset_id")) == asset_id
                        for candidate in project_assets
                    ):
                        continue
                    location = {key: value for key, value in match.items() if key not in {"record_index"}}
                    location.setdefault("id", location.get("session_id") or location.get("timeline_id") or location.get("variant_id") or location.get("sequence_id") or location.get("derived_sequence_id"))
                    location_key = (project_id, str(location.get("kind")), str(location.get("id") or location.get("path") or ""))
                    if location_key not in existing_location_keys:
                        locations.append({"project_id": project_id, "location": location})
                        existing_location_keys.add(location_key)
            except Exception:
                _LOGGER.warning(
                    "자산 사용처를 훑다가 프로젝트 하나를 읽지 못했습니다 "
                    "(프로젝트=%s, 자산=%s). 이 프로젝트는 '확인 못 함'으로 보고합니다.",
                    project_id, asset_id, exc_info=True,
                )
                unreadable.append(project_id)
                continue
        return {"library_asset_id": asset_id, "locations": locations, "unreadable_projects": unreadable}

    @router.post("/api/library/assets/{asset_id}/trash")
    def trash_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable", "library_asset_id": asset_id})
        # **여기서는 깊게 본다.** 옛 프로젝트가 쓰고 있는 자산을 지우면
        # 되돌릴 수 없다 -- 화면이 부르는 빠른 검사와 다른 무게다.
        scan = get_library_asset_usage(asset_id, deep=True)
        deep_usage = scan["locations"]
        if deep_usage:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": deep_usage})
        # **확인 못 한 것은 "안 쓴다"가 아니다.** 프로젝트 하나를 못 읽어 그
        # 사용처가 0건이 된 상태에서 목록이 비었다고 지우면, 쓰고 있는 자산이
        # 사라지고 되돌릴 수 없다. 막는 쪽이 맞다 -- 창작자는 다시 눌러 볼 수
        # 있지만 지워진 자산은 못 되돌린다.
        if scan.get("unreadable_projects"):
            raise HTTPException(
                status_code=409,
                detail={"code": "usage_scan_incomplete", "unreadable_projects": scan["unreadable_projects"]},
            )
        try:
            return {"asset": public_user(user_asset_store.trash_asset(asset_id))}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": user_asset_store.usage(asset_id)}) from exc

    @router.patch("/api/library/assets/{asset_id}/media-type")
    def correct_library_asset_media_type(
        asset_id: str, payload: CorrectLibraryAssetMediaTypeRequest
    ) -> dict[str, Any]:
        """잘못 갈린 종류를 owner가 고친다 (owner 결정 2026-09-07).

        `docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`가 이
        길을 조건으로 달았다 -- 한 폴더에 넣은 것을 프로그램이 내용으로 가르니
        틀리는 일이 생기고, 고칠 수 없으면 그 기능을 낼 수 없다.

        **같은 갈래 안에서만 고친다.** 음악↔효과음(길이로 갈라서 경계에서
        틀린다), 영상↔그림(정지 화면이라 헷갈린다). 소리를 그림이라 부르는 것은
        고치기가 아니라 파일과 화면이 어긋나는 고장이다 -- 그림 자리에 소리가
        들어가면 미리보기가 빈 그림을 그린다.
        """
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable"})
        try:
            target = LibraryMediaType(payload.media_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="media_type_unknown") from exc
        if _MEDIA_TYPE_GROUPS[target] != _MEDIA_TYPE_GROUPS[asset.media_type]:
            raise HTTPException(status_code=422, detail="media_type_group_mismatch")
        if target is asset.media_type:
            return {"asset": public_user(asset)}
        return {"asset": public_user(user_asset_store.update_media_type(asset_id, target))}

    @router.post("/api/library/assets/{asset_id}/restore")
    def restore_library_asset(asset_id: str) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable"})
        try:
            return {"asset": public_user(user_asset_store.restore_asset(asset_id))}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/api/library/assets/{asset_id}/permanent", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def permanently_delete_library_asset(asset_id: str) -> None:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable"})
        locations = get_library_asset_usage(asset_id)["locations"]
        if locations:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": locations})
        if asset.lifecycle is not LibraryAssetLifecycle.TRASHED:
            raise HTTPException(status_code=409, detail={"code": "asset_must_be_trashed"})
        try:
            user_asset_store.permanently_delete_asset(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "asset_referenced", "locations": user_asset_store.usage(asset_id)}) from exc
        except sqlite3.IntegrityError as exc:
            # **막는 것을 500으로 내지 않는다.** 잘라 둔 구간이 딸린 자산은 못
            # 지우는 것이 맞지만, 창작자에게 "서버 오류"만 보이면 왜 안 되는지
            # 알 수 없다(2026-09-06 실측: 휴지통 비우기가 절반 500이었다).
            raise HTTPException(
                status_code=409,
                detail={"code": "asset_has_derived_footage", "library_asset_id": asset_id},
            ) from exc
        # The row is gone only after the guard/transaction succeeds.  Cleanup
        # is then best-effort and limited to the managed root; a stale file is
        # harmless to the authority, while a path outside this root is never
        # touched.
        if asset is not None:
            for root in roots:
                _remove_managed_file(root, asset.managed_relative_path, expected_sha256=asset.content_sha256)

    @router.delete("/api/library/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def permanently_delete_library_asset_alias(asset_id: str, permanent: bool = Query(False)) -> None:
        if not permanent:
            raise HTTPException(status_code=405, detail="permanent_query_required")
        permanently_delete_library_asset(asset_id)

    @router.get("/api/library/assets/{asset_id}/preview")
    def preview_library_asset(asset_id: str):
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            snapshot = media_library_store.snapshot_verified_asset(library_asset_id=asset_id)
            if snapshot is None:
                raise HTTPException(status_code=404, detail="asset_unavailable")
            _, path = snapshot
            return FileResponse(path, media_type=_mime_type(path), background=BackgroundTask(media_library_store.remove_verified_snapshot, path))
        source = source_for_user(asset)
        return FileResponse(source, media_type=asset.mime_type)

    @router.get("/api/library/assets/{asset_id}/{derivative_kind}")
    def get_derivative(asset_id: str, derivative_kind: str):
        if derivative_kind not in {"thumbnail", "waveform"}:
            raise HTTPException(status_code=404, detail="derivative_missing")
        asset, builtin = find_asset(asset_id)
        if asset is not None and asset.media_type is LibraryMediaType.IMAGE and derivative_kind == "waveform":
            raise HTTPException(status_code=404, detail="derivative_missing")
        if builtin is not None:
            return {"library_asset_id": asset_id, "kind": derivative_kind, "source_hash": builtin.get("sha256"), "version": DERIVATIVE_VERSION}
        source = source_for_user(asset)
        try:
            derivative = _ensure_derivative(user_asset_store, managed_root, asset, derivative_kind, source)
        except _DerivativeToolUnavailable as exc:
            user_asset_store.update_lifecycle(asset.library_asset_id, LibraryAssetLifecycle.NEEDS_ATTENTION)
            raise HTTPException(status_code=503, detail={"state": "needs_attention", "code": "MEDIA_DERIVATIVE_TOOL_UNAVAILABLE"}) from exc
        derivative_path = managed_root / str(derivative["managed_relative_path"])
        return FileResponse(derivative_path, media_type=str(derivative["mime_type"]))

    def _queue_scene_analysis(*, project_id: str, asset: dict[str, Any], media_type: object) -> None:
        """장면 분석은 촬영본을 보는 일이다 -- 음악 서른 개를 넣었다고 로컬
        모델을 서른 번 돌리지 않는다. 예약이 실패해도 자산은 이미 들어갔으므로
        가져오기를 실패로 만들지 않는다. 태그가 안 붙을 뿐이고, 그건 남긴다.
        """
        if schedule_scene_analysis is None or str(media_type) != LibraryMediaType.BROLL.value:
            return
        asset_id = str(asset.get("asset_id") or "")
        if not asset_id:
            return
        try:
            schedule_scene_analysis(project_id, asset_id)
        except Exception:
            _LOGGER.warning(
                "프로젝트에 넣은 촬영본의 장면 분석을 걸지 못했습니다 "
                "(project=%s, 자산=%s). 태그가 붙지 않아 유진의 추천이 막힙니다.",
                project_id, asset_id, exc_info=True,
            )

    @router.post("/api/library/assets/{asset_id}/materialize", status_code=status.HTTP_201_CREATED)
    def materialize_library_asset(asset_id: str, payload: MaterializeLibraryAssetRequest) -> dict[str, Any]:
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=422, detail="builtin_materialize_use_media_library_api")
        source = source_for_user(asset)
        try:
            result = materializer.materialize_user_library_asset(
                project_id=payload.project_id,
                library_asset_id=asset_id,
                library_asset=public_user(asset),
                source_path=source,
                mime_type=asset.mime_type,
            )
            try:
                reference = user_asset_store.add_project_reference(project_id=payload.project_id, library_asset_id=asset_id, materialized_asset_id=str(result.get("asset_id")), location={"project_id": payload.project_id})
            except Exception:
                # Cross-database atomicity is impossible here; compensate the
                # project copy immediately so a failed reference can never
                # leave an unguarded materialized asset behind.
                materializer._compensate_registered_asset(project_id=payload.project_id, asset_id=str(result.get("asset_id")))
                raise
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="project_missing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _queue_scene_analysis(project_id=payload.project_id, asset=result, media_type=asset.media_type)
        return {"asset": result, "reference": reference}

    @router.delete("/api/library/assets/{asset_id}/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def remove_library_reference(asset_id: str, reference_id: str) -> None:
        find_asset(asset_id)
        reference = next((item for item in user_asset_store.list_project_references(library_asset_id=asset_id) if str(item.get("reference_id")) == reference_id), None)
        # Removing a project reference is deliberately idempotent.  The owner
        # may retry after a lost response; the global library row must remain.
        if reference is None:
            return None
        project_id = str(reference.get("project_id") or "")
        materialized_asset_id = str(reference.get("materialized_asset_id") or "")
        if project_id and materialized_asset_id:
            try:
                project_asset = project_store.get_asset(project_id=project_id, asset_id=materialized_asset_id)
            except (KeyError, FileNotFoundError):
                project_asset = None
            if project_asset is not None:
                metadata = dict(project_asset.get("metadata") or {})
                if metadata.get("source_library_asset_id") == asset_id:
                    project_store.delete_asset(project_id=project_id, asset_id=materialized_asset_id)
        user_asset_store.remove_project_reference(reference_id)
        return None

    return router


def _ensure_derivative(store: LibraryUserAssetStore, root: Path, asset: Any, kind: str, source: Path) -> dict[str, Any]:
    extension = ".png"
    relative = Path("derivatives") / asset.content_sha256 / f"{DERIVATIVE_VERSION}-{kind}{extension}"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            rendered = _render_derivative(source=source, media_type=asset.media_type.value, kind=kind)
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            raise _DerivativeToolUnavailable("ffmpeg_unavailable") from exc
        if rendered is None:
            # A corrupt/unsupported file must remain inspectable, but never
            # receive the old fixed-label SVG. The hash-derived bars make the
            # fallback visibly tied to the uploaded bytes and are deterministic.
            bars = "".join(
                f'<rect x="{index * 20}" y="{20 + (int(char, 16) * 8)}" width="12" height="{180 - int(char, 16) * 6}" fill="#e85d04"/>'
                for index, char in enumerate(asset.content_sha256[:32])
            )
            extension = ".svg"
            relative = relative.with_suffix(extension)
            target = root / relative
            target.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="220" viewBox="0 0 640 220"><rect width="640" height="220" fill="#fff7ed"/>{bars}</svg>', encoding="utf-8")
        else:
            target.write_bytes(rendered)
    mime_type = "image/svg+xml" if target.suffix == ".svg" else "image/png"
    digest = _sha256(target)
    return store.upsert_derivative(library_asset_id=asset.library_asset_id, kind=kind, managed_relative_path=relative.as_posix(), content_sha256=digest, byte_count=target.stat().st_size, mime_type=mime_type, metadata={"source_sha256": asset.content_sha256, "version": DERIVATIVE_VERSION, "generator": "ffmpeg" if target.suffix != ".svg" else "hash-fallback"})


def _render_derivative(*, source: Path, media_type: str, kind: str) -> bytes | None:
    if media_type == "image":
        # 파형 필터(`showwavespic`)를 그림에 태우면 ffmpeg가 실패하고, 화면에는
        # 해시 막대 대체 이미지가 떠서 "썸네일이 있다"고 거짓말한다.
        command = ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-frames:v", "1", "-vf", "scale=640:360:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    elif media_type == "broll":
        command = ["ffmpeg", "-y", "-v", "error", "-ss", "0", "-i", str(source), "-frames:v", "1", "-vf", "scale=640:360:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    else:
        height = "220" if kind == "waveform" else "360"
        command = ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-filter_complex", f"aformat=channel_layouts=mono,showwavespic=s=640x{height}:colors=orangered", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    if result.returncode != 0 or not result.stdout:
        return None
    return bytes(result.stdout)


def _sha256(path: Path) -> str:
    # 해시 구현은 `videobox_storage`가 정본이다. 같은 루프를 또 두지 않는다.
    return sha256_file(path)


def _mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _remove_managed_file(root: Path, relative: str, *, expected_sha256: str | None = None) -> None:
    base = root.resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return
    if expected_sha256 is not None and (not candidate.is_file() or _sha256(candidate) != expected_sha256):
        return
    candidate.unlink(missing_ok=True)


__all__ = ["build_library_assets_router"]
