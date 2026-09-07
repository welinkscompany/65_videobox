"""더빙 엔드포인트 -- 화면이 밟을 경로를 그대로 밟는다.

동영상 번역기 2단계다. 1단계가 만든 번역을 **그대로 대본으로 쓴다.**
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.settings import TTSEngineConfig
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


class _SpokenLength:
    """말한 길이를 우리가 정하는 가짜 엔진.

    진짜 엔진을 부르지 않는 이유: 이 시험이 재려는 것은 **길이가 안 맞을 때
    어떻게 되는가**지 목소리가 어떤가가 아니다. 길이를 직접 정할 수 있어야
    "너무 길어서 못 넣은 장면"을 만들 수 있다.
    """

    provider_name = "test_spoken_length"

    def __init__(self, seconds_by_text: dict[str, float], default_seconds: float) -> None:
        self.seconds_by_text = seconds_by_text
        self.default_seconds = default_seconds
        self.requests: list[TTSRequest] = []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        self.requests.append(request)
        seconds = self.seconds_by_text.get(request.text, self.default_seconds)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"sine=frequency=300:duration={seconds}", str(request.output_path)],
            check=True, capture_output=True, timeout=120,
        )
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


def _dub(client: TestClient, project_id: str, session_id: str, **payload: Any) -> dict[str, Any]:
    """더빙을 걸고 끝날 때까지 기다린다.

    더빙은 **비동기다** -- 장면당 13초라 긴 영상은 nginx 330초 벽에 부딪힌다.
    시험은 `TestClient`가 background task를 응답 뒤에 바로 돌리므로, 한 번
    물어보면 이미 끝나 있다.
    """
    started = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/dubbing", json=payload
    )
    assert started.status_code in (202, 422), started.text
    if started.status_code == 422:
        return {"_status": 422, **started.json()}
    job_id = started.json()["job_id"]
    status_response = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/dubbing/{job_id}"
    )
    assert status_response.status_code == 200, status_response.text
    return {"_status": 200, "started": started.json(), **status_response.json()}


def _client(tmp_path: Path, engine: _SpokenLength) -> tuple[TestClient, str, str]:
    app = create_app(
        projects_root=tmp_path / "projects",
        tts_provider=engine,
        tts_engine_config=TTSEngineConfig(enabled=True, engine="espeak"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "더빙"}).json()["project_id"]
    session_id = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()["session_id"]
    return client, project_id, session_id


def _translate(
    client: TestClient, project_id: str, session_id: str, english: str, projects_root: Path
) -> dict[str, Any]:
    """번역을 직접 심는다 -- 이 시험이 재는 것은 더빙이지 번역이 아니다."""
    body = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    segment_id = body["segments"][0]["segment_id"]
    body = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption",
        json={"caption_text": "안녕하세요", "expected_revision": body["session_revision"]},
    ).json()
    from videobox_core_engine.caption_translation import apply_caption_translations
    from videobox_storage.local_project_store import LocalProjectStore

    store = LocalProjectStore(projects_root)
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    store.update_editing_session(
        project_id=project_id, session_id=session_id,
        session_payload=apply_caption_translations(
            session=session, language="en", texts_by_segment={segment_id: english}
        ),
        expected_revision=session["session_revision"],
    )
    return client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()


def test_a_fitting_take_replaces_the_narration(tmp_path: Path) -> None:
    engine = _SpokenLength({}, default_seconds=5.2)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    response = _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])

    assert response["status"] == "succeeded", response.get("error_detail")
    assert response["result"]["dubbed_scene_count"] == 1
    # 전부 들어갔으면 사정을 말할 것이 없다.
    assert response["result"]["dubbing_notice"] is None
    # 걸어 두자마자 몇 장면짜리 일인지 말해 준다 -- 진행 표시의 모수가 된다.
    assert response["started"]["total_scene_count"] == 1
    session = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    assert session["segments"][0]["tts_replacement"] is not None


def test_the_engine_is_told_which_language_to_read(tmp_path: Path) -> None:
    """엔진에 언어를 안 넘기면 **영어 자막을 한국어로 읽는다.**"""
    engine = _SpokenLength({}, default_seconds=5.0)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])

    assert engine.requests[0].language == "en"
    assert engine.requests[0].text == "Hello there"


def test_a_take_that_cannot_fit_leaves_the_original_voice_alone(tmp_path: Path) -> None:
    """5초 장면에 12초짜리 말은 못 넣는다. **억지로 빠르게 감지 않는다.**"""
    engine = _SpokenLength({}, default_seconds=12.0)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "A very long sentence indeed", tmp_path / "projects")

    response = _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])

    assert response["status"] == "succeeded", response.get("error_detail")
    assert response["result"]["dubbed_scene_count"] == 0
    session = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    assert session["segments"][0]["tts_replacement"] is None
    # 무엇을 못 했는지 반드시 말해 준다 -- 조용히 아무 일 없는 것이 제일 나쁘다.
    # 사유별로 말해 준다 -- "줄여라"와 "늘려라"는 창작자가 할 일이 다르다.
    assert "옮긴 말이 길어서 넣지 못했어요" in response["result"]["dubbing_notice"]


def test_nothing_to_dub_when_the_captions_are_not_translated_yet(tmp_path: Path) -> None:
    engine = _SpokenLength({}, default_seconds=5.0)
    client, project_id, session_id = _client(tmp_path, engine)
    body = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    response = _dub(client, project_id, session_id, language="en", expected_revision=body["session_revision"])

    assert response["status"] == "succeeded", response.get("error_detail")
    assert response["result"]["dubbed_scene_count"] == 0
    assert engine.requests == []


def test_an_unknown_language_is_refused(tmp_path: Path) -> None:
    engine = _SpokenLength({}, default_seconds=5.0)
    client, project_id, session_id = _client(tmp_path, engine)
    body = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    response = _dub(client, project_id, session_id, language="klingon", expected_revision=body["session_revision"])

    assert response["_status"] == 422, response
    assert engine.requests == []


def test_dubbing_triggers_the_rebuild_that_swaps_the_narration(tmp_path: Path) -> None:
    """**세션에 걸어 두는 것만으로는 완성본이 안 바뀐다.**

    2026-09-02에 다섯 장면을 더빙하고 렌더까지 성공했는데 완성본이 이전 파일과
    **바이트까지 같았다.** 내레이션을 실제로 갈아 끼우는 것은 타임라인이고,
    세션의 선택이 거기 닿으려면 부분 재생성(`tts_replacement` -> `tts_refresh` +
    `timeline_build`)을 지나야 한다. 손으로 음성을 고르는 기존 경로도 같은 길이다.

    그때 통과하던 시험들은 **세션만 봤다** -- 그래서 아무도 못 잡았다.
    이 시험은 재생성이 실제로 돌았는지를 본다.
    """
    engine = _SpokenLength({}, default_seconds=4.2)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    dubbed = _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])

    assert dubbed["result"]["dubbed_scene_count"] == 1
    jobs = client.get(f"/api/projects/{project_id}/jobs").json().get("jobs") or []
    regenerations = [job for job in jobs if job.get("job_type") == "partial_regeneration"]
    assert regenerations, "더빙이 타임라인을 다시 만들지 않았다 -- 완성본은 그대로 나간다."
    assert regenerations[-1]["status"] == "succeeded"


def test_nothing_is_rebuilt_when_no_scene_could_be_dubbed(tmp_path: Path) -> None:
    """한 장면도 못 넣었으면 타임라인을 건드릴 이유가 없다."""
    engine = _SpokenLength({}, default_seconds=12.0)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Far too long", tmp_path / "projects")

    _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])

    jobs = client.get(f"/api/projects/{project_id}/jobs").json().get("jobs") or []
    assert [job for job in jobs if job.get("job_type") == "partial_regeneration"] == []


def test_one_broken_scene_does_not_throw_away_the_others(tmp_path: Path) -> None:
    """목소리 복제는 장면당 20초가 넘는다. 열여덟째가 실패했다고 앞의 것을
    전부 버리면 몇 분이 통째로 날아간다(코드리뷰 2026-09-02).
    """
    class _BreaksOnce(_SpokenLength):
        def __init__(self) -> None:
            super().__init__({}, default_seconds=4.6)
            self.seen = 0

        def synthesize(self, request: TTSRequest) -> TTSResult:
            self.seen += 1
            if self.seen == 1:
                raise RuntimeError("engine fell over on this scene")
            return super().synthesize(request)

    engine = _BreaksOnce()
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    response = _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])

    # 장면이 하나뿐인 편집본이라 그 하나가 실패한다. 그래도 **작업이 죽지 않고**
    # 무엇을 못 했는지 말해 준다.
    assert response["status"] == "succeeded", response.get("error_detail")
    assert response["result"]["dubbed_scene_count"] == 0
    assert "목소리를 만들지 못했어요" in response["result"]["dubbing_notice"]


def test_a_dubbed_project_can_still_be_exported(tmp_path: Path) -> None:
    """더빙한 뒤에 **완성본을 만들 수 있어야 한다.**

    출력 화면은 `지금 타임라인을 만든 timeline_build 작업`이 있어야 "편집본
    준비됨"으로 본다. 더빙은 타임라인을 새로 내는데 그 기록을 안 남기고 있어서,
    더빙한 프로젝트는 출력 화면에서 "편집 화면에서 준비해 주세요"라는 막다른
    말만 보였다 -- 편집 화면에서 봐도 같은 말이었다(2026-09-03 실측).
    """
    engine = _SpokenLength({}, default_seconds=4.6)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    dubbed = _dub(client, project_id, session_id, language="en", expected_revision=before["session_revision"])
    assert dubbed["result"]["dubbed_scene_count"] == 1

    session = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    jobs = client.get(f"/api/projects/{project_id}/jobs").json().get("jobs") or []
    builds = [
        job for job in jobs
        if job.get("job_type") == "timeline_build"
        and job.get("status") == "succeeded"
        and job.get("output_ref") == session["timeline_id"]
    ]

    assert builds, (
        "더빙이 만든 타임라인에 timeline_build 기록이 없다 -- "
        "출력 화면이 '편집본 준비 필요'에서 멈춘다."
    )


def test_the_request_only_books_the_work(tmp_path: Path) -> None:
    """**요청은 일을 걸어 두기만 하고 돌아온다.**

    장면당 13초가 걸린다(2026-09-03 실측, chatterbox). 스물세 장면이면 nginx
    330초 벽에 부딪히고, 창작자의 실제 영상은 그보다 훨씬 길다 -- 8분짜리면
    백 장면이 넘는다.

    **"엔진을 아직 안 불렀다"는 여기서 못 잰다.** `TestClient`는 background
    task를 응답 안에서 바로 돌리기 때문이다 -- 시험 환경의 성질이지 제품이
    그런 게 아니다. 그래서 잴 수 있는 것만 잰다: 202로 돌아오고, 그 몸통이
    아직 "처리 중"이며, 몇 장면짜리 일인지 바로 말해 준다는 것.
    """
    engine = _SpokenLength({}, default_seconds=4.6)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    started = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/dubbing",
        json={"language": "en", "expected_revision": before["session_revision"]},
    )

    assert started.status_code == 202, started.text
    body = started.json()
    assert body["status"] == "processing"
    # 몇 장면짜리 일인지 바로 말해 준다 -- 진행 표시의 모수가 된다.
    assert body["total_scene_count"] == 1


def test_asking_about_a_job_that_does_not_exist_is_not_a_crash(tmp_path: Path) -> None:
    engine = _SpokenLength({}, default_seconds=4.6)
    client, project_id, session_id = _client(tmp_path, engine)

    response = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/dubbing/nope"
    )

    assert response.status_code in (404, 422), response.text


def test_a_stale_revision_is_refused_before_any_voice_is_made(tmp_path: Path) -> None:
    """**52분을 돌린 뒤에 충돌로 버리면 안 된다.**

    편집본이 그 사이 바뀌었으면 걸어 두기 전에 막는다. 안 그러면 창작자는
    목소리가 다 만들어진 줄 알고 기다린 뒤에야 헛일이었다는 걸 안다.
    """
    engine = _SpokenLength({}, default_seconds=4.6)
    client, project_id, session_id = _client(tmp_path, engine)
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/dubbing",
        json={"language": "en", "expected_revision": before["session_revision"] - 1},
    )

    assert response.status_code == 409, response.text
    assert engine.requests == [], "낡은 revision인데 목소리를 만들기 시작했다"


def test_a_scene_that_fails_still_moves_the_progress_along(tmp_path: Path) -> None:
    """실패한 장면도 지나간 장면이다. 안 세면 진행 표시가 멈춰서 죽은 줄 안다."""
    seen: list[tuple[int, int]] = []

    class _AlwaysBreaks(_SpokenLength):
        def synthesize(self, request: TTSRequest) -> TTSResult:
            raise RuntimeError("engine down")

    from videobox_api.orchestration import ApiOrchestrator
    from videobox_storage.local_project_store import LocalProjectStore

    client, project_id, session_id = _client(tmp_path, _AlwaysBreaks({}, default_seconds=4.6))
    before = _translate(client, project_id, session_id, "Hello there", tmp_path / "projects")
    orchestrator = ApiOrchestrator(LocalProjectStore(tmp_path / "projects"))
    orchestrator.pipeline.tts_provider = _AlwaysBreaks({}, default_seconds=4.6)

    orchestrator.dub_editing_session(
        project_id=project_id, session_id=session_id, language="en",
        expected_revision=before["session_revision"],
        on_progress=lambda done: seen.append((done, 1)),
    )

    assert seen, "실패만 있었는데 진행이 한 번도 안 움직였다"
