"""관리 경로 확인이 한 곳으로 모이면서, 그 전에는 어디에도 없던 커버리지를 만든다.

이 검사는 원래 두 벌로 복제돼 있었고 -- `services/api`의 자산 다운로드 경로와
`core-engine`의 라이브러리 백필 -- 실패 분기(경로 이탈 / 못 찾음)에는 양쪽 다
직접 테스트가 없었다. 공용으로 옮기면서 두 분기를 여기서 고정한다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from videobox_storage.managed_path_resolution import resolve_managed_path, resolve_verified_path


def _write(path: Path, payload: bytes = b"managed bytes") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_it_finds_the_file_and_confirms_its_bytes(tmp_path: Path) -> None:
    root = tmp_path / "library"
    digest = _write(root / "assets" / "clip.mp4")

    result = resolve_managed_path(roots=(root,), relative_path="assets/clip.mp4", content_sha256=digest)

    assert result.found is True
    assert result.escaped is False
    assert result.path == (root / "assets" / "clip.mp4").resolve()


def test_it_refuses_a_file_whose_bytes_do_not_match(tmp_path: Path) -> None:
    """해시가 다르면 "찾았다"고 하지 않는다 -- 다른 파일을 집어 ffprobe하거나
    내주는 것을 막는 지점이다."""
    root = tmp_path / "library"
    _write(root / "assets" / "clip.mp4")

    result = resolve_managed_path(roots=(root,), relative_path="assets/clip.mp4", content_sha256="0" * 64)

    assert result.found is False
    assert result.escaped is False  # 경로는 정상이었고 내용만 달랐다


def test_a_missing_file_is_not_reported_as_an_escape(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()

    result = resolve_managed_path(roots=(root,), relative_path="assets/absent.mp4", content_sha256="0" * 64)

    assert result.found is False
    assert result.escaped is False


def test_a_path_that_climbs_out_of_the_root_is_flagged_as_escaped(tmp_path: Path) -> None:
    """이 분기가 404("없음")와 422("경로가 잘못됨")를 가른다. 저장 계층이 이런
    경로의 등록을 이미 막지만, 심볼릭 링크와 옛 행을 위한 2차 방어선으로 남긴다."""
    root = tmp_path / "library"
    root.mkdir()
    _write(tmp_path / "outside.mp4")

    result = resolve_managed_path(roots=(root,), relative_path="../outside.mp4", content_sha256="0" * 64)

    assert result.found is False
    assert result.escaped is True


def test_it_keeps_looking_after_one_root_rejects_the_path(tmp_path: Path) -> None:
    """root가 여러 개면 하나가 걸러졌다고 멈추지 않는다. 다만 끝까지 못 찾으면
    이탈이 있었다는 사실은 유지해서 부르는 쪽이 사유를 구분할 수 있게 한다."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    digest = _write(second / "assets" / "clip.mp4")

    found = resolve_managed_path(
        roots=(first, second), relative_path="assets/clip.mp4", content_sha256=digest
    )
    assert found.path == (second / "assets" / "clip.mp4").resolve()

    missed = resolve_managed_path(roots=(first, second), relative_path="../outside.mp4", content_sha256=digest)
    assert missed.found is False
    assert missed.escaped is True


def test_an_unresolved_root_still_matches_its_real_files(tmp_path: Path) -> None:
    """root도 정규화해야 한다. 안 하면 candidate만 정규화돼 서로 어긋나고, 실제로
    있는 파일이 매번 "root 밖"으로 잘못 판정된다 -- 데이터 루트가 심볼릭 링크인
    컨테이너 배포본에서 실제로 그랬다. (이 환경은 심볼릭 링크 권한이 없어
    `..`로 되돌아오는 비정규 경로로 같은 조건을 만든다.)"""
    root = tmp_path / "library"
    digest = _write(root / "assets" / "clip.mp4")
    unresolved_root = root / "detour" / ".."

    result = resolve_managed_path(roots=(unresolved_root,), relative_path="assets/clip.mp4", content_sha256=digest)

    assert result.found is True
    assert result.path == (root / "assets" / "clip.mp4").resolve()


def test_the_thin_form_returns_just_the_path(tmp_path: Path) -> None:
    root = tmp_path / "library"
    digest = _write(root / "assets" / "clip.mp4")

    assert resolve_verified_path(roots=(root,), relative_path="assets/clip.mp4", content_sha256=digest) is not None
    assert resolve_verified_path(roots=(root,), relative_path="../outside.mp4", content_sha256=digest) is None
