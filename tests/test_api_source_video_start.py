"""찍어 둔 영상으로 시작하는 길. owner 지시 2026-08-21.

**지금까지는 대본이 있어야만 시작할 수 있었다.** `create_creation_brief`가
`script_text`를 필수로 받는다. 그래서 "영상은 찍어 뒀는데 대본은 없다"는 흔한
상황에서 owner는 첫 걸음을 뗄 수가 없었다.

부품은 다 있었다 -- Whisper 받아쓰기가 켜져 있고(`VIDEOBOX_STT_ENABLED`),
`start_transcription`은 자산 종류를 가리지 않아 **영상 파일에도 그대로 돈다**.
없던 것은 영상을 올리는 문과, 받아쓴 글을 대본으로 돌려주는 한 걸음뿐이다.
이 저장소에서 반복되는 "부품은 있는데 이어 붙인 데가 없다"의 또 한 번이다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.stt import STTProvider, STTRequest, STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore


class _SpokenVideo(STTProvider):
    """찍은 영상에서 말을 받아쓴 척한다. 실제 Whisper는 컨테이너에서 돈다."""

    provider_name = "fake_whisper"

    def __init__(self) -> None:
        self.heard: list[Path] = []

    def transcribe(self, request: STTRequest) -> STTResult:
        self.heard.append(request.source_path)
        return STTResult(
            provider_name=self.provider_name,
            text="오늘은 편집 시간을 줄이는 방법을 말씀드릴게요. 첫째는 템플릿입니다.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=3.2, text="오늘은 편집 시간을 줄이는 방법을 말씀드릴게요.", confidence=0.9),
                STTSegment(start_sec=3.2, end_sec=5.4, text="첫째는 템플릿입니다.", confidence=0.9),
            ],
        )


def _client(tmp_path: Path, stt: STTProvider | None = None) -> tuple[TestClient, str]:
    client = TestClient(create_app(projects_root=tmp_path, stt_provider=stt or _SpokenVideo()))
    project_id = client.post("/api/projects", json={"name": "영상으로 시작"}).json()["project_id"]
    return client, project_id


def _upload(client: TestClient, project_id: str, name: str = "촬영본.mp4"):
    return client.post(
        f"/api/projects/{project_id}/source-video/upload",
        files={"file": (name, b"\x00\x00\x00\x18ftypmp42" + b"0" * 512, "video/mp4")},
    )


def test_an_uploaded_video_comes_back_as_a_script(tmp_path: Path) -> None:
    """owner가 대본 없이 시작할 수 있는 **유일한 길**이다."""
    client, project_id = _client(tmp_path)

    response = _upload(client, project_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["script_text"].startswith("오늘은 편집 시간을")
    # 자막이 어디에 놓일지는 받아쓴 구간이 정한다. 문장만 돌려주면 자막이
    # 말한 자리에 안 붙는다 -- 2026-08-11에 같은 이유로 자막이 어긋났다.
    assert body["spoken_segment_count"] == 2
    assert body["asset_id"]


def test_the_video_is_kept_as_the_projects_own_footage(tmp_path: Path) -> None:
    """올린 영상은 대본 재료로만 쓰고 버리는 것이 아니다. 그 영상이 곧 본편이므로
    프로젝트 자산으로 남아야 내레이션으로도 고를 수 있다."""
    client, project_id = _client(tmp_path)

    asset_id = _upload(client, project_id).json()["asset_id"]

    stored = LocalProjectStore(tmp_path).get_asset(project_id=project_id, asset_id=asset_id)
    assert stored["asset_type"] == AssetType.RAW_VIDEO.value

    options = client.get(f"/api/projects/{project_id}/draft-readiness/narration-options").json()
    assert asset_id in [item["asset_id"] for item in options["assets"]]


def test_the_transcript_is_read_from_the_video_itself(tmp_path: Path) -> None:
    stt = _SpokenVideo()
    client, project_id = _client(tmp_path, stt)

    _upload(client, project_id)

    assert len(stt.heard) == 1
    assert stt.heard[0].exists() is False or stt.heard[0].suffix == ".mp4"


def test_a_file_that_is_not_a_video_is_refused_before_anything_is_stored(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/source-video/upload",
        files={"file": ("대본.txt", b"hello", "text/plain")},
    )

    assert response.status_code in {400, 422}
    assert LocalProjectStore(tmp_path).list_assets(project_id=project_id) == []


def test_a_video_with_no_speech_says_so_instead_of_making_an_empty_script(tmp_path: Path) -> None:
    """무음 영상으로 빈 대본을 만들면 다음 화면이 전부 빈 채로 흘러간다.
    2026-08-16에 완전 무음 완성본이 그렇게 나갔다 -- 여기서 멈춰 세운다."""
    class _Silent(STTProvider):
        provider_name = "fake_whisper"

        def transcribe(self, request: STTRequest) -> STTResult:
            return STTResult(provider_name=self.provider_name, text="   ", segments=[])

    client, project_id = _client(tmp_path, _Silent())

    response = _upload(client, project_id)

    assert response.status_code == 422
    assert response.json()["detail"] == "source_video_has_no_speech"
