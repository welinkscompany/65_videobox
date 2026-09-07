"""라이브러리 broll 자산의 길이·크기·오디오가 ingest 실패 뒤 영원히 비어 있던 gap.

`library_ingest.py`의 `probe_metadata`는 ingest 시점 1회만 불린다. 실패하면
`technical_metadata`가 영구히 `{}`로 남고, 화면은 정직하게 "길이 정보 없음"을
보여줄 뿐 다시 재는 경로가 없었다(프로젝트 b-roll에는 `_backfill_broll_media_facts`가
있는데 라이브러리 쪽엔 대응물이 없었다 -- 2026-08-16 점검에서 확인).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.library_media_facts import (
    library_assets_needing_media_facts,
    record_library_media_facts,
)
from videobox_core_engine.media_probe import FFmpegMediaProbe
from videobox_domain_models.library_assets import LibraryAssetOrigin, LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.local_project_store import sha256_file


def _write_video(path: Path, *, size: str = "320x180", duration: int = 2) -> Path:
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=15",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac", "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(command, check=True, capture_output=True)
    return path


class _ExplodingProbe:
    def probe_metadata(self, _path):  # noqa: ANN001
        raise RuntimeError("ffprobe binary is unavailable")


class _FixedProbe:
    """probe_metadata를 미리 정한 값으로 즉시 돌려준다 -- 배선/로직 테스트에서
    ffmpeg 서브프로세스를 또 돌리지 않기 위해서다(정확한 프로브 값 자체는
    real ffmpeg를 실제로 쓰는 테스트가 이미 검증한다)."""

    def __init__(self, *, width=320, height=180, duration_sec=2.0, audio_codec="aac") -> None:
        self._result = type("Probed", (), {"width": width, "height": height, "duration_sec": duration_sec, "audio_codec": audio_codec})()

    def probe_metadata(self, _path):  # noqa: ANN001
        return self._result


# ---------------------------------------------------------------------------
# library_assets_needing_media_facts -- broll_assets_needing_media_facts와
# 같은 방식(저장된 상태에서 "아직 안 된 것"을 유도)을 라이브러리에 적용한다.
# ---------------------------------------------------------------------------


def test_an_asset_without_duration_comes_back_for_another_pass() -> None:
    class _Asset:
        def __init__(self, library_asset_id: str, technical_metadata: dict) -> None:
            self.library_asset_id = library_asset_id
            self.managed_relative_path = f"{library_asset_id}.mp4"
            self.content_sha256 = "deadbeef"
            self.technical_metadata = technical_metadata

    class _Store:
        @staticmethod
        def list_assets(*, media_type):
            assert media_type == LibraryMediaType.BROLL
            return [
                _Asset("done", {"duration_seconds": 4.0}),
                _Asset("missing", {}),
                _Asset("failed-before", {"width": 320}),  # 크기는 있어도 길이가 없으면 대상
            ]

    pending = library_assets_needing_media_facts(store=_Store())

    assert [item["library_asset_id"] for item in pending] == ["missing", "failed-before"]
    assert pending[0]["managed_relative_path"] == "missing.mp4"
    assert pending[0]["content_sha256"] == "deadbeef"


def test_the_backfill_pass_is_bounded_like_the_indexers() -> None:
    class _Asset:
        def __init__(self, i: int) -> None:
            self.library_asset_id = f"a{i}"
            self.managed_relative_path = f"a{i}.mp4"
            self.content_sha256 = "x"
            self.technical_metadata = {}

    class _Store:
        @staticmethod
        def list_assets(*, media_type):
            return [_Asset(i) for i in range(5)]

    assert len(library_assets_needing_media_facts(store=_Store(), limit=2)) == 2
    assert len(library_assets_needing_media_facts(store=_Store())) == 5


# ---------------------------------------------------------------------------
# record_library_media_facts -- 실제 store와 실제 파일로 끝까지.
# ---------------------------------------------------------------------------


@pytest.fixture()
def library(tmp_path: Path) -> tuple[LibraryUserAssetStore, Path]:
    root = tmp_path / "library"
    store = LibraryUserAssetStore(root)
    return store, root


def _ingest_broken(store: LibraryUserAssetStore, root: Path, tmp_path: Path, *, name: str) -> str:
    """실제 영상을 root 아래 배치하고, probe가 실패했던 것처럼 빈 technical_metadata로 등록한다."""
    relative = f"assets/broll/{name}.mp4"
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_video(destination, size="320x180")
    content_sha256 = sha256_file(destination)
    asset = store.register_asset(
        library_asset_id=f"user:{name}",
        media_type=LibraryMediaType.BROLL,
        origin=LibraryAssetOrigin.USER,
        content_sha256=content_sha256,
        managed_relative_path=relative,
        byte_count=destination.stat().st_size,
        mime_type="video/mp4",
        technical_metadata={},
        machine_metadata={},
        user_metadata={"filename": f"{name}.mp4"},
        provenance={},
    )
    return asset.library_asset_id


def test_a_missing_source_file_is_not_treated_as_success(library, tmp_path: Path) -> None:
    store, root = library
    asset_id = store.register_asset(
        library_asset_id="user:ghost",
        media_type=LibraryMediaType.BROLL,
        origin=LibraryAssetOrigin.USER,
        content_sha256="a" * 64,
        managed_relative_path="assets/broll/does-not-exist.mp4",
        byte_count=0,
        mime_type="video/mp4",
        technical_metadata={},
        machine_metadata={},
        user_metadata={},
        provenance={},
    ).library_asset_id

    result = record_library_media_facts(
        store=store, roots=(root,), probe=_FixedProbe(),
        library_asset_id=asset_id, managed_relative_path="assets/broll/does-not-exist.mp4",
        content_sha256="a" * 64,
    )

    assert result is False
    assert store.get_asset(asset_id).technical_metadata == {}


def test_a_broken_probe_leaves_no_trace_and_can_retry(library, tmp_path: Path) -> None:
    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="broken")
    asset = store.get_asset(asset_id)

    result = record_library_media_facts(
        store=store, roots=(root,), probe=_ExplodingProbe(),
        library_asset_id=asset_id, managed_relative_path=asset.managed_relative_path,
        content_sha256=asset.content_sha256,
    )

    assert result is False
    assert store.get_asset(asset_id).technical_metadata == {}


def test_a_later_pass_fills_in_what_intake_missed(library, tmp_path: Path) -> None:
    """이것이 핵심이다. wave2-* 4개가 정확히 이 상태로 남아 있었다."""
    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="recovered")
    asset = store.get_asset(asset_id)

    result = record_library_media_facts(
        store=store, roots=(root,), probe=FFmpegMediaProbe(),
        library_asset_id=asset_id, managed_relative_path=asset.managed_relative_path,
        content_sha256=asset.content_sha256,
    )

    assert result is True
    updated = store.get_asset(asset_id).technical_metadata
    assert updated["duration_seconds"] == pytest.approx(2.0, abs=0.3)
    assert updated["width"] == 320
    assert updated["height"] == 180
    assert updated["has_audio"] is True

    # 채운 뒤에는 다시 대상에 안 잡힌다(멱등).
    assert library_assets_needing_media_facts(store=store) == []


def test_zero_second_duration_still_counts_as_recorded(library, tmp_path: Path) -> None:
    """0.0초는 falsy라서 `if ...get("duration_seconds")`로 검사하면 "아직 안 됨"으로
    착각해 매 패스마다 다시 건다. 깨진 업로드가 ffprobe는 성공하되 길이 0을
    돌려주는 경우가 정확히 이 상황이다."""
    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="zero-duration")
    asset = store.get_asset(asset_id)

    result = record_library_media_facts(
        store=store, roots=(root,), probe=_FixedProbe(duration_sec=0.0),
        library_asset_id=asset_id, managed_relative_path=asset.managed_relative_path,
        content_sha256=asset.content_sha256,
    )

    assert result is True
    assert store.get_asset(asset_id).technical_metadata["duration_seconds"] == 0.0
    # 0.0초로 채워졌으면 더 이상 대상이 아니다 -- 영원히 재시도되면 안 된다.
    assert library_assets_needing_media_facts(store=store) == []


def test_content_hash_mismatch_refuses_to_probe(library, tmp_path: Path) -> None:
    """다른 root의 다른 파일을 잘못 집어 ffprobe하지 않도록 해시로 지킨다."""
    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="guarded")
    asset = store.get_asset(asset_id)

    result = record_library_media_facts(
        store=store, roots=(root,), probe=_FixedProbe(),
        library_asset_id=asset_id, managed_relative_path=asset.managed_relative_path,
        content_sha256="0" * 64,  # 저장된 값과 다름
    )

    assert result is False
    assert store.get_asset(asset_id).technical_metadata == {}


def test_an_unresolved_root_still_finds_the_real_file(library, tmp_path: Path) -> None:
    """root 자체를 resolve하지 않으면, root가 정규화되지 않은 경로일 때(컨테이너
    볼륨 마운트가 심볼릭 링크를 거치는 배포본에서 흔하다) candidate(resolve됨)와
    root(안 됨)가 어긋나 relative_to가 매번 ValueError를 던진다 -- 실제로 있는
    파일도 영원히 "못 찾음"으로 남는 회귀다. 이 환경(Windows, 심볼릭 링크 권한
    없음)에서도 재현 가능하도록 `..`로 되돌아오는 정규화 전 경로로 같은 결함
    유형을 재현한다."""
    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="via-unresolved-root")
    asset = store.get_asset(asset_id)

    unresolved_root = root / "detour" / ".."  # resolve()해야만 root와 같아진다

    result = record_library_media_facts(
        store=store, roots=(unresolved_root,), probe=_FixedProbe(),
        library_asset_id=asset_id, managed_relative_path=asset.managed_relative_path,
        content_sha256=asset.content_sha256,
    )

    assert result is True
    assert store.get_asset(asset_id).technical_metadata.get("duration_seconds") is not None


def test_asset_deleted_between_probe_and_write_does_not_raise(library, tmp_path: Path) -> None:
    """probe가 끝난 뒤 store 쓰기 직전에 owner가 자산을 완전히 삭제하면
    `update_technical_metadata`가 KeyError를 던진다. 이 함수는 "실패해도 예외를
    올리지 않는다"고 스스로 약속했으니 그 약속을 지켜야 한다."""
    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="deleted-mid-flight")
    asset = store.get_asset(asset_id)
    store.permanently_delete_asset(asset_id)

    result = record_library_media_facts(
        store=store, roots=(root,), probe=_FixedProbe(),
        library_asset_id=asset_id, managed_relative_path=asset.managed_relative_path,
        content_sha256=asset.content_sha256,
    )

    assert result is False


# ---------------------------------------------------------------------------
# _backfill_library_media_facts -- 실제로 유지보수 루프가 부르는 진입점.
# 시간 민감 TestClient+sleep 통합 테스트는 추가하지 않는다 -- 그 클래스의
# 테스트가 부하에 약하다는 것이 2026-08-15/16에 반복 확인됐다. 직접 호출로
# 같은 것을 더 안전하게 검증한다.
# ---------------------------------------------------------------------------


def test_the_app_entry_point_recovers_missing_facts_directly(library, tmp_path: Path) -> None:
    from types import SimpleNamespace

    from videobox_api.main import _backfill_library_media_facts

    store, root = library
    asset_id = _ingest_broken(store, root, tmp_path, name="via-app")

    media_library_store = SimpleNamespace(user_asset_store=store)
    app = SimpleNamespace(
        state=SimpleNamespace(
            media_library_store=media_library_store,
            media_analysis_probe=_FixedProbe(),
            library_asset_managed_roots=(root,),
        )
    )

    _backfill_library_media_facts(app)

    assert store.get_asset(asset_id).technical_metadata.get("duration_seconds") == 2.0


def test_missing_wiring_does_not_crash_the_loop() -> None:
    from types import SimpleNamespace

    from videobox_api.main import _backfill_library_media_facts

    app = SimpleNamespace(state=SimpleNamespace())  # 아무것도 설정 안 됨

    _backfill_library_media_facts(app)  # 조용히 아무것도 안 하고 리턴해야 한다
