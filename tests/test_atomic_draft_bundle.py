from __future__ import annotations

from videobox_storage.local_project_store import LocalProjectStore
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.capcut_handoff import CapCutHandoffService
from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest
import subprocess
import json
import pytest
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _ready(
    store: LocalProjectStore,
    project_id: str,
    script_text: str = "제품을 소개합니다.",
) -> tuple[dict, dict]:
    brief = store.create_creation_brief(project_id=project_id, script_filename="script.txt", script_text=script_text, idempotency_key="brief", capability_profile={}, runtime=type("R", (), {"plan_questions": lambda *_args, **_kwargs: []})())
    brief = store.bypass_creation_interview(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    brief = store.update_creation_brief_summary(project_id=project_id, brief_id=brief["brief_id"], summary="제품 소개", expected_revision=brief["revision"])
    brief = store.approve_creation_brief(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    run = store.start_draft_readiness(project_id=project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="ready", expected_brief_revision=brief["revision"], defer=False)
    return brief, run


# 편집이 검토 승인을 내리는 것은 옳다 -- 옛 편집본의 검토로 새 편집본을 승인할 수는
# 없다. 그런데 다시 세우는 경로가 없어서, 한 번 편집하면 그 프로젝트는 내보내기까지
# 갈 수 없었다. 빈 구간을 채우려면 편집해야 하는데 그 편집이 승인을 죽이므로 빠져나갈
# 수도 없었다.
def test_review_can_be_rebuilt_for_the_current_edit(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Rebuild")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="rebuild", allow_placeholder=True,
    )
    session_id, timeline_id = bundle["session_id"], bundle["timeline_id"]
    assert store.get_review_state(project_id=project.project_id, timeline_id=timeline_id)["is_current"] is True

    session = store.get_editing_session(project_id=project.project_id, session_id=session_id)
    session["segments"][0]["caption_text"] = "고친 자막"
    store.update_editing_session(project_id=project.project_id, session_id=session_id, session_payload=session)

    stale = store.get_review_state(project_id=project.project_id, timeline_id=timeline_id)
    assert stale["is_current"] is False
    assert stale["invalidated_reason"] == "editing_session_mutation"

    store.refresh_review_for_current_edit(project_id=project.project_id, session_id=session_id)

    current = store.get_editing_session(project_id=project.project_id, session_id=session_id)
    after = store.get_review_state(project_id=project.project_id, timeline_id=timeline_id)
    assert after["is_current"] is True
    assert after["source_session_revision"] == current["session_revision"]
    # 내보내기 관문은 승인만이 아니라 timeline이 실은 revision도 함께 본다.
    timeline = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id)
    assert timeline["source_session_revision"] == current["session_revision"]


# 2026-09-20: 검토 화면(`GET /timelines/{job_id}` -> 처음엔 `get_timeline_result`를
# 직접 고치려 했다)이 저장된 timeline 문서의 `tracks`를 그대로 읽어서, 장면을 나눈
# 뒤 "현재 편집본으로 검토본 다시 만들기"를 눌러도 화면의 장면 경계가 분할 이전
# 값 그대로였다(실사용 프로젝트 `0907-b26195af`에서 발견). 첫 시도(커밋
# `2183eec0`)는 저장된 `timeline["tracks"]` 자체를 덮어써서 고치려 했다가
# 되돌려졌다 -- 그 값은 `composition_plan.py`가 원본 소스 길이 계산
# (`source_durations`/`source_bounds`)에도 쓰기 때문에 덮어쓰면 broll/overlay
# 클립의 `overlay_type`/`overlay_payload`가 빠져 `playback-manifest`가 422로
# 죽었다(`docs/handoffs/2026-09-20-timeline-manual-editing-bug-hunt.ko.md`).
#
# 두 번째 시도는 `get_timeline_result` 자체에 materialize를 얹었다가, 코드리뷰
# 교차 추적에서 그 함수를 `run_final_render_job`/`start_capcut_export`/
# `start_preview_render`/`start_subtitle_render`가 **그대로 다시 materialize
# 하거나(이중 materialize) 저장된 값 그대로 써야 하는 곳**(CapCut 내보내기)이라는
# 게 드러나 커밋 전에 `get_timeline_result_for_review_display`로 분리했다.
# 이 시험은 그 분리가 지켜지는지 -- **`get_timeline_result`는 그대로**이고
# **검토 화면 전용 메서드만** 최신 편집을 반영하는지 -- 함께 잰다.
def test_timeline_review_response_reflects_the_latest_split_without_mutating_storage(tmp_path):
    from videobox_api.models import TimelinePayloadResponse
    from videobox_api.response_normalizers import _normalize_timeline_payload_for_response
    from videobox_core_engine.editing_session import split_segment

    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("ReviewFollowsEdit")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="review-follows-edit", allow_placeholder=True,
    )
    session_id, timeline_id, timeline_job_id = bundle["session_id"], bundle["timeline_id"], bundle["timeline_job_id"]
    session = store.get_editing_session(project_id=project.project_id, session_id=session_id)
    original_segment_id = session["segments"][0]["segment_id"]

    split = split_segment(session=session, segment_id=original_segment_id, split_sec=2.0)
    # 실사용 재현에는 b-roll override가 걸린 장면이 있었다 -- composition_plan이
    # broll/bgm/sfx/overlay 클립을 자리마다 새로 짓는 사전이라 `clip_type`을 안
    # 채운다. 이 override가 없으면 그 자리(broll 트랙의 일반 경로)를 시험이 안
    # 밟아서 회귀를 놓친다.
    split["segments"][0]["broll_override"] = {"asset_id": "asset_probe"}
    store.update_editing_session(project_id=project.project_id, session_id=session_id, session_payload=split)
    left_id, right_id = [segment["segment_id"] for segment in split["segments"][:2]]

    store.refresh_review_for_current_edit(project_id=project.project_id, session_id=session_id)

    stored = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id)
    stored_narration = next(track for track in stored["tracks"] if track["track_type"] == "narration")
    stored_segment_ids = {clip["segment_id"] for clip in stored_narration["clips"]}
    assert stored_segment_ids == {original_segment_id}, (
        "저장된 timeline['tracks']는 손대지 말아야 한다 -- composition_plan.py가 "
        "그 값을 원본 소스 길이 계산에도 쓴다"
    )

    pipeline = LocalPipelineRunner(store)
    # `get_timeline_result`는 다른 소비자(최종 렌더·CapCut 내보내기·미리보기·자막
    # 렌더)가 그대로 쓰거나 자기가 다시 materialize하는 함수라 손대면 안 된다 --
    # 여기서 그 계약이 지켜지는지도 함께 잠근다.
    internal_result = pipeline.get_timeline_result(project_id=project.project_id, job_id=timeline_job_id)
    internal_narration = next(track for track in internal_result["timeline"]["tracks"] if track["track_type"] == "narration")
    internal_segment_ids = {clip["segment_id"] for clip in internal_narration["clips"]}
    assert internal_segment_ids == {original_segment_id}, (
        "get_timeline_result는 최종 렌더/CapCut 내보내기 등이 그대로 쓰거나 스스로 "
        "다시 materialize하는 함수다 -- 여기서 미리 materialize하면 그 소비자들이 "
        "이미 materialize된 tracks를 다시 materialize하는 이중 처리가 된다"
    )

    result = pipeline.get_timeline_result_for_review_display(project_id=project.project_id, job_id=timeline_job_id)
    response_narration = next(track for track in result["timeline"]["tracks"] if track["track_type"] == "narration")
    response_segment_ids = {clip["segment_id"] for clip in response_narration["clips"]}
    assert response_segment_ids == {left_id, right_id}, (
        f"검토 화면 응답이 분할을 반영하지 못했다: {response_segment_ids}"
    )
    assert {(clip["start_sec"], clip["end_sec"]) for clip in response_narration["clips"]} == {(0.0, 2.0), (2.0, 5.0)}
    # `get_timeline_result`가 준 dict를 그대로 실제 API 응답 계약
    # (`TimelinePayloadResponse`)까지 통과시켜서, `clip_type` 누락 같은 2차
    # 결함(2026-09-19 실측: `pydantic.ValidationError: clip_type Field required`)을
    # 다시 놓치지 않게 한다.
    TimelinePayloadResponse(**_normalize_timeline_payload_for_response(result["timeline"]))


# 2026-09-20 코드리뷰에서 발견: `timeline["source_session_id"]`가 가리키는 세션이
# 그 사이 다른 timeline으로 다시 연결됐을 수 있다(숏폼을 편집본으로 펼치기 같은
# 흐름). `build_editor_playback_manifest`가 이미 이 짝을 검사하는 이유와 같다 --
# 안 맞는 세션으로 materialize하면 이 timeline에 없는 segment_id를 기준으로
# 자르려다 엉뚱하거나 빈 결과가 나온다. 검토 화면 전용 경로도 같은 짝 검사를
# 해야 한다.
def test_review_display_skips_materialize_when_session_points_at_a_different_timeline(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("MismatchedSession")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="mismatched-session", allow_placeholder=True,
    )
    timeline_id, timeline_job_id = bundle["timeline_id"], bundle["timeline_job_id"]

    # `_ready`는 idempotency_key를 고정 문자열로 쓴다 -- 같은 프로젝트에서 두 번째
    # brief를 만들려면 그 키들과 안 겹치는 값으로 직접 만들어야 한다.
    other_brief = store.create_creation_brief(
        project_id=project.project_id, script_filename="other.txt", script_text="다른 대본입니다.",
        idempotency_key="brief-other", capability_profile={},
        runtime=type("R", (), {"plan_questions": lambda *_args, **_kwargs: []})(),
    )
    other_brief = store.bypass_creation_interview(project_id=project.project_id, brief_id=other_brief["brief_id"], expected_revision=other_brief["revision"])
    other_brief = store.update_creation_brief_summary(project_id=project.project_id, brief_id=other_brief["brief_id"], summary="다른 소개", expected_revision=other_brief["revision"])
    other_brief = store.approve_creation_brief(project_id=project.project_id, brief_id=other_brief["brief_id"], expected_revision=other_brief["revision"])
    other_readiness = store.start_draft_readiness(
        project_id=project.project_id, brief_id=other_brief["brief_id"], narration_choice={"kind": "silent"},
        idempotency_key="ready-other", expected_brief_revision=other_brief["revision"], defer=False,
    )
    other_bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=other_brief["brief_id"], expected_brief_revision=other_brief["revision"],
        readiness_id=other_readiness["readiness_id"], expected_readiness_revision=other_readiness["revision"],
        idempotency_key="mismatched-session-other", allow_placeholder=True,
    )
    other_session_id = other_bundle["session_id"]
    assert other_bundle["timeline_id"] != timeline_id

    import json as _json

    stored = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id)
    stored["source_session_id"] = other_session_id
    stored["source_session_revision"] = 1
    file_path = store._timeline_file_path(project_id=project.project_id, timeline_id=timeline_id)
    file_path.write_text(_json.dumps(stored, indent=2, ensure_ascii=True), encoding="utf-8")

    pipeline = LocalPipelineRunner(store)
    result = pipeline.get_timeline_result_for_review_display(project_id=project.project_id, job_id=timeline_job_id)
    assert result["timeline"]["tracks"] == stored["tracks"], (
        "세션과 timeline이 서로 다른 timeline_id를 가리키면 materialize를 건너뛰고 "
        "저장된 tracks를 그대로 돌려줘야 한다"
    )


# 이게 실제로 막힘을 푸는 부분이다. 빈 장면을 채우려면 편집해야 하는데, 그 편집이
# 승인을 죽였다. 채운 뒤 다시 세우면 `확인할 항목`이 사라져야 내보내기까지 갈 수 있다.
def test_filling_an_empty_scene_clears_what_blocked_the_export(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Fill")
    video = tmp_path / "fill.mp4"; video.write_bytes(b"\x00" * 64)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="fill", allow_placeholder=True,
    )
    session_id, timeline_id = bundle["session_id"], bundle["timeline_id"]
    assert bundle["gap_slots"], "이 시험은 빈 장면이 있는 초안을 전제로 한다"
    before = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id)
    assert before["review_flags"], "빈 장면이 있으면 확인할 항목이 있어야 한다"

    session = store.get_editing_session(project_id=project.project_id, session_id=session_id)
    for segment in session["segments"]:
        segment["broll_override"] = {"asset_id": asset.asset_id, "in_sec": 0.0, "out_sec": 1.0}
    store.update_editing_session(project_id=project.project_id, session_id=session_id, session_payload=session)

    store.refresh_review_for_current_edit(project_id=project.project_id, session_id=session_id)

    after = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id)
    assert after["review_flags"] == []
    assert store.get_review_state(project_id=project.project_id, timeline_id=timeline_id)["status"] == "draft"
    # 내보내기 관문은 확인할 항목이 아니라 `gap_slots`와 `placeholder_policy`를 본다
    # (`local_pipeline.assert_timeline_output_allowed`). 이것도 초안 때 적어 둔 값이라
    # 함께 다시 유도하지 않으면 owner가 다 채워도 완성본을 못 만든다.
    assert after["gap_slots"] == []
    assert after.get("placeholder_policy") is None
    pipeline = LocalPipelineRunner(store)
    pipeline.assert_timeline_output_allowed(
        project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"]
    )
    # 채운 장면이 실제 파일을 가리켜야 한다. 여기가 비어 있으면 합성이 없는 파일을
    # 열려다 프레임을 하나도 못 만들고, ffmpeg는 "streams received no packets"로만
    # 끝난다 -- owner에게는 "완성본을 만들지 못했어요"로만 보인다.
    current = store.get_editing_session(project_id=project.project_id, session_id=session_id)
    plan = pipeline.build_composition_plan(
        timeline=store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id),
        editing_session=current,
        project_id=project.project_id,
    )
    applied = [item for item in plan.items if item.asset_id == asset.asset_id and item.track_type == "broll"]
    assert applied, "채운 장면이 합성에 들어가야 한다"
    for item in applied:
        assert item.asset_uri, f"{item.clip_id}에 원본 경로가 없다"
        source = store.resolve_storage_uri(project_id=project.project_id, storage_uri=item.asset_uri)
        assert source.exists(), f"{item.clip_id}이 없는 파일을 가리킨다: {item.asset_uri}"


# 자산 기록이 사라져도 합성 만들기가 통째로 멈추면 안 된다. 대신 조용히 넘어가지도
# 않는다 -- 그 장면이 완성본에서 비어 보이는 이유가 어디엔가는 남아야 한다.
def test_a_missing_asset_record_is_logged_instead_of_stopping_the_whole_plan(tmp_path, caplog):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Missing")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="missing", allow_placeholder=True,
    )
    session = store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"])
    session["segments"][0]["broll_override"] = {"asset_id": "asset_does_not_exist", "in_sec": 0.0, "out_sec": 1.0}
    store.update_editing_session(project_id=project.project_id, session_id=bundle["session_id"], session_payload=session)

    with caplog.at_level("WARNING"):
        plan = LocalPipelineRunner(store).build_composition_plan(
            timeline=store.get_timeline_run(project_id=project.project_id, timeline_id=bundle["timeline_id"]),
            editing_session=store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"]),
            project_id=project.project_id,
        )

    assert plan.items, "자산 하나가 없다고 계획 전체가 사라지면 안 된다"
    assert "asset_does_not_exist" in caplog.text


def test_materializes_one_real_draft_bundle_and_reuses_same_idempotency_result(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Atomic")
    brief, readiness = _ready(store, project.project_id)
    payload = dict(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="approve-once", allow_placeholder=True)
    first = store.materialize_atomic_draft_bundle(**payload)
    second = store.materialize_atomic_draft_bundle(**payload)
    assert first["session_id"] == second["session_id"]
    assert first["timeline_id"] == second["timeline_id"]
    assert first["segment_ids"] and first["asset_ids"] and first["clip_ids"]
    session = store.get_editing_session(project_id=project.project_id, session_id=first["session_id"])
    assert session["timeline_id"] == first["timeline_id"]
    assert any(track["track_type"] == "narration" for track in session["tracks"])
    visible_segment_id = session["segments"][0]["segment_id"]
    placeholder = next(
        clip
        for track in session["tracks"]
        for clip in track["clips"]
        if clip.get("gap_slot_id")
    )
    assert placeholder["segment_id"] == visible_segment_id
    assert placeholder["source_segment_id"] == "script-1"
    assert session["gap_slots"][0]["segment_id"] == visible_segment_id
    assert session["gap_slots"][0]["source_segment_id"] == "script-1"


def test_real_asset_bundle_keeps_unique_tracks_and_places_each_source_on_its_visible_segment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("Aligned real assets")
    for index in range(4):
        source = tmp_path / f"scene-{index}.mp4"
        source.write_bytes(f"scene-{index}".encode())
        store.register_asset(
            project_id=project.project_id,
            asset_type=AssetType.BROLL_VIDEO,
            source_path=source,
        )
    monkeypatch.setattr(
        store,
        "_probe_playable_broll_duration",
        lambda **_kwargs: 6.0,
    )
    brief, readiness = _ready(
        store,
        project.project_id,
        "첫 장면입니다. 둘째 장면입니다. 셋째 장면입니다. 마지막 장면입니다.",
    )

    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"],
        expected_readiness_revision=readiness["revision"],
        idempotency_key="aligned-assets",
    )
    session = store.get_editing_session(
        project_id=project.project_id,
        session_id=bundle["session_id"],
    )
    timeline = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=bundle["timeline_id"],
    )
    manifest = build_editor_playback_manifest(
        project_id=project.project_id,
        session=session,
        timeline=timeline,
        asset_content_url_prefix=f"/api/projects/{project.project_id}/assets",
    )
    visible = [
        (segment["segment_id"], segment["start_sec"], segment["end_sec"])
        for segment in session["segments"]
    ]
    broll = next(track for track in manifest["tracks"] if track["track_type"] == "broll")

    assert len({track["track_id"] for track in manifest["tracks"]}) == len(manifest["tracks"])
    assert [
        (clip["segment_id"], clip["start_sec"], clip["end_sec"])
        for clip in broll["clips"]
    ] == visible
    raw_broll = next(track for track in timeline["tracks"] if track["track_type"] == "broll")
    assert [clip["source_segment_id"] for clip in raw_broll["clips"]] == [
        "script-1",
        "script-2",
        "script-3",
        "script-4",
    ]
    assert [
        (clip["media_controls"]["in_sec"], clip["media_controls"]["out_sec"])
        for clip in raw_broll["clips"]
    ] == [(0, 5.0)] * 4
    assert bundle["segment_ids"] == [segment_id for segment_id, _, _ in visible]


def test_concurrent_duplicate_approval_returns_one_atomic_bundle(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Concurrent approval")
    brief, readiness = _ready(store, project.project_id)
    payload = dict(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="one-click", allow_placeholder=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: store.materialize_atomic_draft_bundle(**payload), range(2)))
    assert {result["bundle_id"] for result in results}.__len__() == 1
    assert len(store.list_editing_sessions(project_id=project.project_id)) == 1


def test_failed_materialization_can_retry_same_idempotency_key_without_orphan(tmp_path):
    root = tmp_path / "projects"; failed_once = False

    def fail_once(event: str) -> None:
        nonlocal failed_once
        if event == "after_copy:1" and not failed_once:
            failed_once = True
            raise OSError("one injected failure")

    store = LocalProjectStore(root, atomic_bundle_fault_hook=fail_once); project = store.bootstrap_project("Retry approval")
    brief, readiness = _ready(store, project.project_id)
    payload = dict(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="retry-once", allow_placeholder=True)
    with pytest.raises(OSError, match="one injected failure"):
        store.materialize_atomic_draft_bundle(**payload)
    result = store.materialize_atomic_draft_bundle(**payload)
    assert result["session_id"]
    assert len(store.list_editing_sessions(project_id=project.project_id)) == 1
    assert not list(store.project_root(project.project_id).glob("staging/draft-bundle-*"))


def test_rejects_stale_readiness_and_does_not_leave_partial_session(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Atomic")
    brief, readiness = _ready(store, project.project_id)
    try:
        store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"] + 1, idempotency_key="stale")
    except ValueError as exc:
        assert "revision_conflict" in str(exc)
    else: raise AssertionError("expected stale revision rejection")
    assert store.list_editing_sessions(project_id=project.project_id) == []


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_rejects_source_bytes_changed_after_readiness_without_partial_bundle(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Snapshot")
    video = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=2", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=broll.storage_uri); path.write_bytes(b"after")
    try:
        store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="changed")
    except ValueError as exc: assert "source_sha_conflict" in str(exc)
    else: raise AssertionError("changed source must be rejected")
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_gap_bundle_is_blocked_by_shared_pipeline_before_final_and_capcut(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Gap")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="gap", allow_placeholder=True)
    placeholder = next(asset_id for asset_id in bundle["asset_ids"] if asset_id.startswith("asset_gap_placeholder_"))
    assert store.get_asset(project_id=project.project_id, asset_id=placeholder)["metadata"]["in_app_only"] is True
    pipeline = LocalPipelineRunner(store)
    for action in (pipeline.start_final_render, pipeline.start_capcut_draft_export):
        try: action(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
        except ValueError as exc: assert "gap_blocks" in str(exc)
        else: raise AssertionError("gap draft output must be blocked")
    with pytest.raises(ValueError, match="gap_blocks"):
        pipeline.start_final_render_job(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    direct_job = store.create_job(project_id=project.project_id, job_type=JobType.FINAL_RENDER, input_ref=bundle["timeline_job_id"], status=JobStatus.RUNNING)
    pipeline.run_final_render_job(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"], job=direct_job)
    assert store.get_job(project_id=project.project_id, job_id=direct_job["job_id"])["status"] == JobStatus.FAILED.value


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg and ffprobe are required")
def test_gap_bundle_exact_preview_renders_black_canvas_without_opening_svg_as_video(tmp_path):
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("Gap exact preview")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"],
        expected_readiness_revision=readiness["revision"],
        idempotency_key="gap-exact-preview",
        allow_placeholder=True,
    )
    session = store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"])
    pipeline = LocalPipelineRunner(store)

    generation = pipeline.start_exact_preview(
        project_id=project.project_id,
        session_id=bundle["session_id"],
        expected_revision=session["session_revision"],
    )
    pipeline.run_exact_preview(project_id=project.project_id, generation_id=generation["generation_id"])
    result = pipeline.get_exact_preview_status(project_id=project.project_id, generation_id=generation["generation_id"])

    assert result["state"] == "succeeded", result.get("error_message")
    artifact = store.resolve_storage_uri(project_id=project.project_id, storage_uri=result["artifact_uri"])
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(artifact)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert float(probe.stdout.strip()) > 0


def test_each_gap_slot_gets_its_own_labeled_placeholder_clip_at_its_target_range(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Multiple gaps")
    brief, readiness = _ready(store, project.project_id)
    first_gap = {"gap_slot_id": "gap-opening", "reason": "첫 장면이 없어요.", "target_range": {"start_sec": 0, "end_sec": 2}}
    second_gap = {"gap_slot_id": "gap-closing", "reason": "마지막 장면이 없어요.", "target_range": {"start_sec": 7, "end_sec": 10}}
    updated_result = {**readiness["result"], "gap_slots": [first_gap, second_gap]}
    store._execute(project.project_id, "UPDATE draft_readiness SET result_json = ? WHERE readiness_id = ?", (json.dumps(updated_result, ensure_ascii=False), readiness["readiness_id"]))
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="two-gaps", allow_placeholder=True,
    )
    session = store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"])
    placeholder_clips = [clip for track in session["tracks"] for clip in track["clips"] if clip.get("gap_slot_id")]
    assert bundle["gap_slots"] == [first_gap, second_gap]
    assert len(placeholder_clips) == 2
    assert {(clip["gap_slot_id"], clip["start_sec"], clip["end_sec"], clip["label"]) for clip in placeholder_clips} == {
        ("gap-opening", 0, 2, "자산이 필요한 임시 장면"),
        ("gap-closing", 7, 10, "자산이 필요한 임시 장면"),
    }
    placeholder_assets = [asset_id for asset_id in bundle["asset_ids"] if asset_id.startswith("asset_gap_placeholder_")]
    assert len(placeholder_assets) == 2
    assert all(store.get_asset(project_id=project.project_id, asset_id=asset_id)["metadata"]["in_app_only"] for asset_id in placeholder_assets)


def test_atomic_bundle_session_is_immediately_editable_by_the_legacy_editor_contract(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Editor contract")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="editor-contract", allow_placeholder=True)
    session = store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"])
    assert session["history"] == [] and session["undo_count"] == 0 and session["redo_count"] == 0
    assert session["segments"]
    assert {"segment_id", "caption_text", "start_sec", "end_sec", "cut_action", "review_required", "broll_override", "visual_overlays", "music_override", "sfx_override", "tts_replacement"} <= set(session["segments"][0])


def test_restart_removes_uncommitted_draft_bundle_operation_stage(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Recovery")
    orphan = store.project_root(project.project_id) / "staging" / "draft-bundle-orphan"; orphan.mkdir(parents=True)
    (orphan / "operation.json").write_text('{"kind":"atomic_draft_bundle","status":"staging"}', encoding="utf-8")
    LocalProjectStore(tmp_path / "projects")
    assert not orphan.exists()


@pytest.mark.parametrize("failure_event", ["after_copy:1", "after_copy:2", "before_db_commit"])
def test_atomic_bundle_copy_and_database_failure_leave_no_partial_bundle_or_mirror(tmp_path, failure_event):
    seen_manifests: list[dict] = []
    root = tmp_path / "projects"

    def fail(event: str) -> None:
        if event == failure_event:
            stages = list(root.glob("projects/*/staging/draft-bundle-*"))
            assert len(stages) == 1
            seen_manifests.append(json.loads((stages[0] / "operation.json").read_text(encoding="utf-8")))
            raise OSError(f"injected {event}")

    store = LocalProjectStore(root, atomic_bundle_fault_hook=fail)
    project = store.bootstrap_project("Injected failure")
    brief, readiness = _ready(store, project.project_id)
    with pytest.raises(OSError, match="injected"):
        store.materialize_atomic_draft_bundle(
            project_id=project.project_id, brief_id=brief["brief_id"],
            expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"],
            expected_readiness_revision=readiness["revision"], idempotency_key=failure_event,
            allow_placeholder=True,
        )
    assert seen_manifests and seen_manifests[0]["artifacts"]
    for artifact in seen_manifests[0]["artifacts"]:
        assert len(artifact["sha256"]) == 64
    assert store.list_editing_sessions(project_id=project.project_id) == []
    assert not list(store.project_root(project.project_id).glob("staging/draft-bundle-*"))
    assert not list((store.project_root(project.project_id) / "timelines").glob("timeline_draft_*.json"))
    assert not list((store.project_root(project.project_id) / "editing_sessions").glob("editing_session_draft_*.json"))
    assert not list((store.project_root(project.project_id) / "assets" / "narration_audio").glob("asset_silence_*.wav"))


def test_ready_asset_bundle_reaches_real_ffmpeg_final_render_after_explicit_review(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Render")
    video = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=1", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    assert readiness["status"] == "ready"
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="render")
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    pipeline = LocalPipelineRunner(store)
    result = pipeline.start_final_render(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    assert result["status"] == "succeeded"
    render = pipeline.get_final_render_result(project_id=project.project_id, job_id=result["job_id"])["render"]
    assert render and render["source_session_revision"] == 1 and render["is_current"] is True
    assert store.resolve_storage_uri(project_id=project.project_id, storage_uri=render["file_uri"]).read_bytes()[:4]


def test_ready_asset_bundle_reaches_real_capcut_draft_export_after_explicit_review(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("CapCut")
    video = tmp_path / "scene.mp4"; subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=1", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id); bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="capcut")
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    pipeline = LocalPipelineRunner(store, pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=15))
    result = pipeline.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    export = pipeline.get_capcut_draft_export_result(project_id=project.project_id, job_id=result["job_id"])["export"]
    assert result["status"] == "succeeded" and export and store.resolve_storage_uri(project_id=project.project_id, storage_uri=export["file_uri"]).is_dir()


def _ffprobe_streams(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
@pytest.mark.parametrize("narration_kind", ["source_video", "existing", "recorded", "silent"])
def test_each_approved_narration_path_reaches_ffmpeg_and_pycapcut_with_playable_bundle_output(tmp_path, narration_kind):
    """Task 9 matrix: all user-visible narration choices share both real output paths."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(f"Narration {narration_kind}")
    broll = tmp_path / "broll.mp4"
    source_video = tmp_path / "source.mp4"
    audio = tmp_path / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=15:d=1", "-an", "-c:v", "libx264", str(broll)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=15:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(source_video)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(audio)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll)
    raw = store.register_asset(project_id=project.project_id, asset_type=AssetType.RAW_VIDEO, source_path=source_video)
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=audio, source_kind="browser_recording_normalized" if narration_kind == "recorded" else "local_file")
    brief = store.create_creation_brief(project_id=project.project_id, script_filename="script.txt", script_text="한 문장 소개", idempotency_key="brief", capability_profile={}, runtime=type("R", (), {"plan_questions": lambda *_args, **_kwargs: []})())
    brief = store.bypass_creation_interview(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    brief = store.update_creation_brief_summary(project_id=project.project_id, brief_id=brief["brief_id"], summary="소개", expected_revision=brief["revision"])
    brief = store.approve_creation_brief(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    choice = {"kind": narration_kind if narration_kind != "recorded" else "existing"}
    if narration_kind == "source_video": choice["asset_id"] = raw.asset_id
    elif narration_kind in {"existing", "recorded"}: choice["asset_id"] = narration.asset_id
    readiness = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice=choice, idempotency_key="ready", expected_brief_revision=brief["revision"], defer=False)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="bundle")
    timeline = store.get_timeline_run(project_id=project.project_id, timeline_id=bundle["timeline_id"])
    narration_clip = next(clip for track in timeline["tracks"] if track["track_type"] == "narration" for clip in track["clips"])
    assert len(narration_clip["expected_content_sha256"]) == 64
    assert narration_clip["media_revision"]
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    pipeline = LocalPipelineRunner(store, pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=15))
    render_job = pipeline.start_final_render(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    render = pipeline.get_final_render_result(project_id=project.project_id, job_id=render_job["job_id"])["render"]
    assert render is not None
    streams = _ffprobe_streams(store.resolve_storage_uri(project_id=project.project_id, storage_uri=render["file_uri"]))
    assert float(streams["format"]["duration"]) > 0
    assert {stream["codec_type"] for stream in streams["streams"]} >= {"video", "audio"}
    capcut_job = pipeline.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    exported = pipeline.get_capcut_draft_export_result(project_id=project.project_id, job_id=capcut_job["job_id"])["export"]
    assert exported is not None and store.resolve_storage_uri(project_id=project.project_id, storage_uri=exported["file_uri"]).is_dir()


def test_voice_sample_is_rejected_before_atomic_bundle_can_be_built(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Voice sample boundary")
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"not output narration")
    sample = store.register_asset(project_id=project.project_id, asset_type=AssetType.VOICE_SAMPLE_AUDIO, source_path=voice)
    brief, _ = _ready(store, project.project_id)
    with pytest.raises(ValueError, match="voice_sample_invalid"):
        store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "existing", "asset_id": sample.asset_id}, idempotency_key="sample", expected_brief_revision=brief["revision"], defer=False)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_bundle_derived_pycapcut_draft_registers_in_writable_local_capcut_smoke_environment(tmp_path):
    """This is a local fake installation smoke only; Desktop CapCut launch remains owner-gated."""
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("CapCut handoff smoke")
    video = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=15:d=1", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="handoff")
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    local_app_data = tmp_path / "fake-local-app-data"
    executable = local_app_data / "CapCut" / "Apps" / "8.9.1" / "CapCut.exe"
    executable.parent.mkdir(parents=True); executable.write_bytes(b"fake executable")
    project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    project_root.mkdir(parents=True)
    pipeline = LocalPipelineRunner(
        store,
        pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=15),
        capcut_handoff_service=CapCutHandoffService(local_app_data=local_app_data),
    )
    export_job = pipeline.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    handoff = pipeline.register_capcut_draft_handoff(project_id=project.project_id, job_id=export_job["job_id"])
    registered = Path(handoff["registered_project_path"])
    assert handoff["status"] == "ready" and registered.parent == project_root
    assert (registered / "draft_content.json").is_file()


def test_draft_bundle_renders_landscape_by_default_and_honours_a_vertical_choice(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Task 33 / F-9 follow-up: F-9 made build_timeline default to landscape,
    but the owner never goes through build_timeline -- every draft comes from
    materialize_atomic_draft_bundle, which set no output at all and so fell
    back to CompositionPlan's vertical default. Long-form videos were still
    being rendered 1080x1920.
    """
    from videobox_core_engine.composition_plan import CompositionPlan

    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("orientation")
    source = tmp_path / "scene.mp4"
    source.write_bytes(b"scene")
    store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    monkeypatch.setattr(store, "_probe_playable_broll_duration", lambda **_kwargs: 6.0)

    brief, readiness = _ready(store, project.project_id, "한 장면입니다.")
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"],
        expected_readiness_revision=readiness["revision"],
        idempotency_key="orientation-default",
    )
    timeline = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=bundle["timeline_id"],
    )
    plan = CompositionPlan.from_timeline(timeline=timeline)
    assert (plan.width, plan.height) == (1920, 1080)

    shortform = store.bootstrap_project("shortform")
    shortform_source = tmp_path / "shortform.mp4"
    shortform_source.write_bytes(b"shortform")
    store.register_asset(
        project_id=shortform.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=shortform_source,
    )
    brief2, readiness2 = _ready(store, shortform.project_id, "세로 장면입니다.")
    vertical = store.materialize_atomic_draft_bundle(
        project_id=shortform.project_id,
        brief_id=brief2["brief_id"],
        expected_brief_revision=brief2["revision"],
        readiness_id=readiness2["readiness_id"],
        expected_readiness_revision=readiness2["revision"],
        idempotency_key="orientation-vertical",
        orientation="vertical",
    )
    vertical_timeline = store.get_timeline_run(
        project_id=shortform.project_id,
        timeline_id=vertical["timeline_id"],
    )
    vertical_plan = CompositionPlan.from_timeline(timeline=vertical_timeline)
    assert (vertical_plan.width, vertical_plan.height) == (1080, 1920)
