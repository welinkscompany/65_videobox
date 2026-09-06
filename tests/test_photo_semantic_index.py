"""사진은 뜻으로 못 찾았다 — owner 요청 2026-09-06.

> "사진 의미검색도 만들어줘"

음악·효과음은 `library_audio_indexer`가, 촬영본은 `library_footage_indexer`가
설명을 만들어 임베딩까지 붙인다. **사진에만 그 자리가 없었다.**

그래서 유진에게 사진 후보를 보내도 `20241208_121938.jpg`라는 이름만 보이고,
"어떤 사진인지 알려주세요"라고 되묻는다(2026-09-06 실측).

**촬영본 색인을 그대로 쓴다.** 사진도 화면 자산이고, `footage_index` 테이블이
이미 사진을 받을 수 있다(`start_sec`/`end_sec`는 NULL 허용, `duration_seconds`는
0). 무엇보다 **유진의 `broll` 후보가 이미 그 색인을 본다** -- 사진을 거기 넣으면
찾기·추천·명령이 한 번에 이어진다. 별도 테이블을 만들면 그 배선을 전부 다시
해야 한다.

막고 있던 것은 대상을 고르는 SQL 한 줄이었다: `media_type = 'broll'`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from videobox_storage.media_library_store import MediaLibraryStore


def _store_with(tmp_path: Path, files: dict[str, tuple[str, bytes]]) -> MediaLibraryStore:
    """자료실 하나에 자산 몇 개. **해시는 실제 파일에서 뜬다** -- 대기열이
    파일을 다시 해싱해 대조하므로 지어낸 해시로는 아무것도 안 걸린다."""
    store = MediaLibraryStore(tmp_path / "library")
    root = Path(store.root)
    root.mkdir(parents=True, exist_ok=True)
    for asset_id, (name, payload) in files.items():
        path = root / name
        path.write_bytes(payload)
        store.register_user_asset(
            library_asset_id=asset_id,
            media_type={"user_clip": "broll", "user_photo": "image", "user_song": "music"}[asset_id],
            origin="user",
            content_sha256=hashlib.sha256(payload).hexdigest(),
            managed_relative_path=name,
            byte_count=len(payload),
            mime_type={"user_clip": "video/mp4", "user_photo": "image/jpeg", "user_song": "audio/mpeg"}[asset_id],
            lifecycle="ready",
        )
    return store


def test_photos_are_queued_for_description_like_footage(tmp_path: Path) -> None:
    """사진도 설명을 기다리는 목록에 들어간다."""
    store = _store_with(tmp_path, {
        "user_clip": ("clip.mp4", b"a synthetic clip"),
        "user_photo": ("shot.jpg", b"a synthetic photo"),
    })

    pending = store.list_footage_needing_analysis(paths=[], description_version=1)

    ids = {str(item.get("library_asset_id")) for item in pending}
    assert "user_clip" in ids
    assert "user_photo" in ids, f"사진이 색인 대기열에 없다: {ids}"


def test_music_is_not_swept_into_the_footage_index(tmp_path: Path) -> None:
    """소리는 오디오 색인이 맡는다 -- 두 색인이 같은 자산을 두고 다투면 안 된다."""
    store = _store_with(tmp_path, {"user_song": ("song.mp3", b"a synthetic song")})

    pending = store.list_footage_needing_analysis(paths=[], description_version=1)

    assert "user_song" not in {str(item.get("library_asset_id")) for item in pending}
