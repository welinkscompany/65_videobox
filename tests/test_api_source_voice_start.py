"""목소리만 녹음해서 시작하는 길. owner 요청 2026-08-29.

`test_api_source_video_start.py`와 짝이다 -- 영상 대신 순수 음성 녹음을 올리면
같은 방식으로 대본이 나온다. 다른 점 하나는 받아쓴 뒤 "다시 들어볼 구간"
후보까지 함께 돌려준다는 것이다(`narration_retake_detection.py`) -- owner가
녹음 끝나고 잘못 발음한 곳을 눈으로 확인하고 뺄 수 있어야 한다는 요청 때문이다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.stt import STTProvider, STTRequest, STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore


class _SpokenVoice(STTProvider):
    """녹음한 목소리를 받아쓴 척한다. 실제 Whisper는 컨테이너에서 돈다.

    일부러 한 구간은 자신도를 낮게, 한 구간은 재시도 표현으로 심어 둔다 --
    다시 들어볼 구간 후보가 실제로 화면까지 오는지 확인하려면 진짜 그런
    받아쓰기 결과가 있어야 한다."""

    provider_name = "fake_whisper"

    def __init__(self) -> None:
        self.heard: list[Path] = []

    def transcribe(self, request: STTRequest) -> STTResult:
        self.heard.append(request.source_path)
        return STTResult(
            provider_name=self.provider_name,
            text="오늘은 라면을 끓여볼게요. 므러 므럴 물을 준비해요. 아 잠깐 다시 할게요. 뜨거운 물을 준비해요.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=2.0, text="오늘은 라면을 끓여볼게요.", confidence=0.95),
                STTSegment(start_sec=2.0, end_sec=4.0, text="므러 므럴 물을 준비해요.", confidence=0.4),
                STTSegment(start_sec=4.0, end_sec=5.5, text="아 잠깐 다시 할게요.", confidence=0.9),
                STTSegment(start_sec=5.5, end_sec=7.5, text="뜨거운 물을 준비해요.", confidence=0.9),
            ],
        )


def _client(tmp_path: Path, stt: STTProvider | None = None) -> tuple[TestClient, str]:
    client = TestClient(create_app(projects_root=tmp_path, stt_provider=stt or _SpokenVoice()))
    project_id = client.post("/api/projects", json={"name": "목소리로 시작"}).json()["project_id"]
    return client, project_id


def _upload(client: TestClient, project_id: str, name: str = "녹음.webm"):
    return client.post(
        f"/api/projects/{project_id}/source-voice/upload",
        files={"file": (name, b"\x1aE\xdf\xa3" + b"0" * 512, "audio/webm")},
    )


def test_an_uploaded_recording_comes_back_as_a_script(tmp_path: Path) -> None:
    """owner가 대본·영상 없이 목소리만으로 시작할 수 있는 길이다."""
    client, project_id = _client(tmp_path)

    response = _upload(client, project_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["script_text"].startswith("오늘은 라면을")
    assert body["spoken_segment_count"] == 4
    assert body["asset_id"]


def test_low_confidence_and_retry_cue_segments_come_back_as_retake_candidates(tmp_path: Path) -> None:
    """owner 요청(2026-08-29): "잘못 발음하는 거 컷 편집으로 날리고" -- 뭉개진
    발음과 스스로 다시 말한 부분이 실제로 후보 목록에 와야 한다."""
    client, project_id = _client(tmp_path)

    body = _upload(client, project_id).json()

    reasons_by_index = {item["segment_index"]: item["reason"] for item in body["retake_candidates"]}
    assert reasons_by_index == {
        1: "low_confidence",
        2: "retry_cue",
        # 재시도 표현(index 2) 바로 앞 구간(index 1)은 이미 low_confidence로
        # 잡혀 있으므로 retry_cue_precursor로 중복해서 잡히지 않는다.
    }
    # 깨끗하게 말한 0, 3번 구간은 후보가 아니다.
    assert 0 not in reasons_by_index
    assert 3 not in reasons_by_index


def test_all_segments_come_back_so_the_screen_can_rebuild_the_script_after_excluding_some(tmp_path: Path) -> None:
    """문자열 치환으로 대본을 다시 만들면 같은 문장이 두 번 나올 때 엉뚱한
    곳이 지워질 수 있다 -- 화면이 구간별로 이어 붙일 수 있게 원문 전체를 준다."""
    client, project_id = _client(tmp_path)

    body = _upload(client, project_id).json()

    assert [item["text"] for item in body["segments"]] == [
        "오늘은 라면을 끓여볼게요.",
        "므러 므럴 물을 준비해요.",
        "아 잠깐 다시 할게요.",
        "뜨거운 물을 준비해요.",
    ]
    assert [item["segment_index"] for item in body["segments"]] == [0, 1, 2, 3]


def test_the_recording_is_kept_as_a_narration_asset(tmp_path: Path) -> None:
    """올린 녹음은 버리지 않고 프로젝트의 내레이션 자산으로 남는다."""
    client, project_id = _client(tmp_path)

    asset_id = _upload(client, project_id).json()["asset_id"]

    stored = LocalProjectStore(tmp_path).get_asset(project_id=project_id, asset_id=asset_id)
    assert stored["asset_type"] == AssetType.NARRATION_AUDIO.value

    options = client.get(f"/api/projects/{project_id}/draft-readiness/narration-options").json()
    assert asset_id in [item["asset_id"] for item in options["assets"]]


def test_a_file_that_is_not_audio_is_refused_before_anything_is_stored(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/source-voice/upload",
        files={"file": ("대본.txt", b"hello", "text/plain")},
    )

    assert response.status_code in {400, 422}
    assert LocalProjectStore(tmp_path).list_assets(project_id=project_id) == []


def test_a_silent_recording_says_so_instead_of_making_an_empty_script(tmp_path: Path) -> None:
    class _Silent(STTProvider):
        provider_name = "fake_whisper"

        def transcribe(self, request: STTRequest) -> STTResult:
            return STTResult(provider_name=self.provider_name, text="   ", segments=[])

    client, project_id = _client(tmp_path, _Silent())

    response = _upload(client, project_id)

    assert response.status_code == 422
    assert response.json()["detail"] == "source_voice_has_no_speech"
