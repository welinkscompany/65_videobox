"""ingest 때 ffprobe가 실패한 라이브러리 broll 자산의 길이·크기·오디오를 나중에 채운다.

`library_ingest.py`의 `probe_metadata`는 ingest 시점에 딱 1회만 불린다. 실패하면
`technical_metadata`가 영구히 비어 남고, 화면은 정직하게 "길이 정보 없음"을 보여줄
뿐 다시 재지 않는다. 이 모듈은 프로젝트 b-roll의 `broll_assets_needing_media_facts`/
`record_broll_media_facts`(local_pipeline.py)와 같은 방식을 라이브러리 자산에 적용한다.

라이브러리 store에는 `resolve_storage_uri`가 없어서, 실제 파일 경로는 여러 root를
순회하며 내용 해시를 대조해 찾는다(`routers/library_assets.py`의 `source_for_user`와
같은 방식) -- 신뢰할 수 없는 경로로 ffprobe를 돌리지 않기 위해서다.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Iterable

from videobox_domain_models.library_assets import LibraryMediaType

_logger = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def library_assets_needing_media_facts(
    *, store: Any, media_type: LibraryMediaType | str = LibraryMediaType.BROLL, limit: int | None = None
) -> list[dict[str, Any]]:
    """길이를 아직 못 받은 라이브러리 broll 자산.

    `duration_seconds` 유무를 표시로 쓴다 -- ingest 성공 시 반드시 쓰는 값이고
    화면(`assetDurationLabel.ts`)이 읽는 값이기 때문이다.
    """
    pending: list[dict[str, Any]] = []
    for asset in store.list_assets(media_type=media_type):
        if asset.technical_metadata.get("duration_seconds"):
            continue
        pending.append(
            {
                "library_asset_id": asset.library_asset_id,
                "managed_relative_path": asset.managed_relative_path,
                "content_sha256": asset.content_sha256,
            }
        )
        if limit is not None and len(pending) >= limit:
            break
    return pending


def _resolve_verified_path(*, roots: Iterable[Path], managed_relative_path: str, content_sha256: str) -> Path | None:
    for root in roots:
        candidate = (root / managed_relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file() and _sha256(candidate) == content_sha256:
            return candidate
    return None


def record_library_media_facts(
    *,
    store: Any,
    roots: Iterable[Path],
    probe: Any,
    library_asset_id: str,
    managed_relative_path: str,
    content_sha256: str,
) -> bool:
    """ffprobe가 아는 것을 라이브러리 자산에 적는다. 채웠으면 True.

    실패해도 예외를 올리지 않는다 -- 다음 패스에 다시 잰다. 실패 사유는 로그에만
    남긴다: 과거 asset metadata에 남겼다가 ffprobe 예외 문구에 섞인 호스트 절대
    경로가 API 응답으로 새어나가 계약 테스트를 깬 전례가 있다(local_pipeline.py의
    같은 주석 참고).
    """
    path = _resolve_verified_path(roots=roots, managed_relative_path=managed_relative_path, content_sha256=content_sha256)
    if path is None:
        _logger.warning(
            "라이브러리 자산의 원본 파일을 찾지 못해 길이 정보를 채우지 못했습니다 (library_asset_id=%s). "
            "다음 차례에 다시 찾습니다.",
            library_asset_id,
        )
        return False
    try:
        probed = probe.probe_metadata(path)
        if not probed.width or not probed.height:
            raise ValueError("ffprobe가 영상의 가로·세로 크기를 돌려주지 않았습니다")
    except Exception:
        _logger.warning(
            "라이브러리 자산의 영상 정보를 읽지 못했습니다 (library_asset_id=%s). 다음 차례에 다시 잽니다.",
            library_asset_id,
            exc_info=True,
        )
        return False
    store.update_technical_metadata(
        library_asset_id,
        {
            "duration_seconds": float(probed.duration_sec),
            "width": int(probed.width),
            "height": int(probed.height),
            "has_audio": probed.audio_codec is not None,
        },
    )
    return True


__all__ = ["library_assets_needing_media_facts", "record_library_media_facts"]
