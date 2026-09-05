from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import wave

import pytest


SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))


def test_research_ledger_loads_the_exact_approved_release_candidate_set() -> None:
    from build_starter_media_pack import load_approved_candidates

    ledger = Path(__file__).resolve().parents[1] / "docs" / "starter-media-pack-license-research.ko.md"

    candidates = load_approved_candidates(ledger)

    # 2026-09-05: 브이로그용 효과음 23개를 더했다(100 → 123).
    # 2026-09-06: 게임 전용 49개를 뺐다(123 → 74). 참조하는 프로젝트가 하나도
    # 없는 것을 확인한 뒤에 뺐다.
    assert len(candidates) == 104
    assert sum(candidate.media_type == "music" for candidate in candidates) == 30
    assert sum(candidate.media_type == "sfx" for candidate in candidates) == 74
    assert {candidate.asset_id for candidate in candidates} >= {
        "music-mindstream", "music-peaceful-drift", "sfx-power-up-v1", "sfx-various-bangs",
        "sfx-swish-1", "sfx-typing-medium", "sfx-keypress-1", "sfx-paper-ripped",
        # 브이로그에도 쓰는 것들은 남는다.
        "sfx-n4-bell1", "sfx-n4-success", "sfx-various-click", "sfx-various-pop",
    }
    # 게임 전용은 하나도 안 남는다.
    assert not {candidate.asset_id for candidate in candidates} & {
        "sfx-sea-ship-destroyed", "sfx-n4-gunshot", "sfx-rpg-baseballbat",
        "sfx-various-batwings", "sfx-various-teleport",
    }
    assert all(candidate.source_url.startswith("https://") for candidate in candidates)
    assert all(candidate.official_url.startswith("https://") for candidate in candidates)
    assert all(len(candidate.selection_evidence_sha256) == 64 for candidate in candidates)


def test_build_asset_converts_sfx_and_records_source_and_output_provenance(tmp_path: Path) -> None:
    from build_starter_media_pack import ApprovedCandidate, build_asset

    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(44100)
        stream.writeframes(b"\0\0\0\0" * 44100)
    candidate = ApprovedCandidate(
        asset_id="sfx-fixture",
        media_type="sfx",
        title="Fixture",
        creator="Fixture Creator",
        official_url="https://example.com/official",
        selection_evidence_sha256="a" * 64,
        source_url="https://example.com/source.wav",
    )

    asset = build_asset(
        candidate,
        output_root=tmp_path / "pack",
        source_root=tmp_path / "sources",
        download=lambda _url, destination: destination.write_bytes(source.read_bytes()),
    )

    output = tmp_path / "pack" / asset["pack_path"]
    archived_source = tmp_path / "pack" / "source-archive" / "sfx-fixture.wav"
    evidence = tmp_path / "pack" / "evidence" / "sfx-fixture.txt"
    assert output.suffix == ".wav"
    assert asset["duration_seconds"] == 1.0
    assert asset["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert archived_source.read_bytes() == source.read_bytes()
    evidence_text = evidence.read_text(encoding="utf-8")
    assert "source_sha256=" + hashlib.sha256(source.read_bytes()).hexdigest() in evidence_text
    assert "source_duration_seconds=1.000000" in evidence_text
    assert "source_format=" in evidence_text
    assert "converted_sha256=" + asset["sha256"] in evidence_text


def test_research_ledger_rejects_a_same_count_set_with_a_modified_source_url(tmp_path: Path) -> None:
    from build_starter_media_pack import load_approved_candidates

    ledger = Path(__file__).resolve().parents[1] / "docs" / "starter-media-pack-license-research.ko.md"
    tampered = tmp_path / "ledger.md"
    tampered.write_text(
        ledger.read_text(encoding="utf-8").replace(
            "https://opengameart.org/sites/default/files/DST-MindStream.mp3",
            "https://opengameart.org/sites/default/files/unapproved.mp3",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="approved release set"):
        load_approved_candidates(tampered)


def test_build_asset_upsamples_low_rate_music_before_enforcing_320k_cbr(tmp_path: Path) -> None:
    from build_starter_media_pack import ApprovedCandidate, build_asset

    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 16000)
    candidate = ApprovedCandidate(
        asset_id="music-fixture", media_type="music", title="Fixture", creator="Fixture Creator",
        official_url="https://example.com/official", selection_evidence_sha256="a" * 64,
        source_url="https://example.com/source.wav",
    )

    asset = build_asset(
        candidate, output_root=tmp_path / "pack", source_root=tmp_path / "sources",
        download=lambda _url, destination: destination.write_bytes(source.read_bytes()),
    )

    assert asset["pack_path"] == "assets/music-fixture.mp3"


def test_release_metadata_binds_each_asset_to_its_immutable_evidence(tmp_path: Path) -> None:
    from build_starter_media_pack import ApprovedCandidate, write_release_metadata

    output = tmp_path / "pack"
    (output / "assets").mkdir(parents=True)
    (output / "evidence").mkdir()
    (output / "assets" / "sfx-fixture.wav").write_bytes(b"converted")
    (output / "evidence" / "sfx-fixture.txt").write_text("provenance", encoding="utf-8")
    candidate = ApprovedCandidate(
        asset_id="sfx-fixture", media_type="sfx", title="Fixture", creator="Fixture Creator",
        official_url="https://example.com/official", selection_evidence_sha256="a" * 64,
        source_url="https://example.com/source.wav",
    )
    asset = {
        "asset_id": "sfx-fixture", "pack_path": "assets/sfx-fixture.wav",
        "sha256": hashlib.sha256(b"converted").hexdigest(), "media_type": "sfx",
        "duration_seconds": 1.0, "source": candidate.source_url, "creator": candidate.creator,
    }

    manifest = write_release_metadata(output, pack_id="starter-v1", version="1.0.0", candidates=[candidate], assets=[asset])

    stored = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert stored == manifest
    assert stored["assets"][0]["license"]["evidence_sha256"] == hashlib.sha256(b"provenance").hexdigest()
    assert "CC0-1.0" in (output / "LICENSES.md").read_text(encoding="utf-8")


def test_build_pack_rejects_an_unapproved_direct_candidate_before_it_downloads(tmp_path: Path) -> None:
    from build_starter_media_pack import ApprovedCandidate, build_pack

    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(b"\0\0" * 48000)
    candidate = ApprovedCandidate(
        asset_id="sfx-fixture", media_type="sfx", title="Fixture", creator="Fixture Creator",
        official_url="https://example.com/official", selection_evidence_sha256="a" * 64,
        source_url="https://example.com/source.wav",
    )

    with pytest.raises(ValueError, match="approved release set"):
        build_pack(
            [candidate], output_root=tmp_path / "pack", source_root=tmp_path / "sources",
            download=lambda _url, destination: destination.write_bytes(source.read_bytes()),
        )


def test_downloader_identifies_the_release_builder_to_hosts_that_block_default_urllib(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import build_starter_media_pack as builder

    received: list[object] = []

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b"" if hasattr(self, "done") else setattr(self, "done", True) or b"bytes"

    def fake_urlopen(request: object, *, timeout: int) -> Response:
        assert timeout == 120
        received.append(request)
        return Response()

    monkeypatch.setattr(builder, "urlopen", fake_urlopen)

    builder._download("https://files.freemusicarchive.org/track.mp3", tmp_path / "track.mp3")

    assert received[0].get_header("User-agent").startswith("VideoBox/")


def test_build_asset_takes_one_file_out_of_an_approved_zip(tmp_path: Path) -> None:
    """묶음으로만 받을 수 있는 소리가 있다 (2026-09-05).

    브이로그에 필요한 전환음·타이핑·종이 소리는 OpenGameArt에 **zip 하나로만**
    올라와 있다. 지금까지 승인 목록은 전부 개별 파일 주소여서 zip을 받으면
    ffmpeg가 zip을 소리로 읽으려다 실패한다.

    주소 뒤에 `#`로 묶음 안 경로를 적으면 그 파일 하나만 꺼내 쓴다. 나머지
    (증거·해시·변환)는 개별 파일과 똑같이 남는다 -- 출처를 덜 남기지 않는다.
    """
    import zipfile

    from build_starter_media_pack import ApprovedCandidate, build_asset

    member = tmp_path / "swish-1.wav"
    with wave.open(str(member), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(44100)
        stream.writeframes(b"\0\0" * 22050)
    archive = tmp_path / "swishes.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(member, "swishes/swish-1.wav")
        bundle.writestr("swishes/readme.txt", "not a sound")

    candidate = ApprovedCandidate(
        asset_id="sfx-swish-1",
        media_type="sfx",
        title="Swish 1",
        creator="artisticdude",
        official_url="https://opengameart.org/content/swishes-sound-pack",
        selection_evidence_sha256="b" * 64,
        source_url="https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-1.wav",
    )

    asset = build_asset(
        candidate,
        output_root=tmp_path / "pack",
        source_root=tmp_path / "sources",
        download=lambda _url, destination: destination.write_bytes(archive.read_bytes()),
    )

    output = tmp_path / "pack" / asset["pack_path"]
    assert output.suffix == ".wav"
    assert asset["duration_seconds"] == 0.5
    evidence = (tmp_path / "pack" / "evidence" / "sfx-swish-1.txt").read_text(encoding="utf-8")
    # 묶음 안 어느 파일이었는지까지 남는다.
    assert "swishes.zip#swishes/swish-1.wav" in evidence
    # 보관하는 원본은 **꺼낸 파일**이지 묶음 전체가 아니다.
    assert (tmp_path / "pack" / "source-archive" / "sfx-swish-1.wav").read_bytes() == member.read_bytes()
