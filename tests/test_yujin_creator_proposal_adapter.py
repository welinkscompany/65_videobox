from __future__ import annotations

import json

import pytest

from videobox_domain_models.yujin_creator_context import YujinCreatorContext


def _context() -> YujinCreatorContext:
    return YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": "project-1",
            "session_id": "session-1",
            "session_revision": 7,
            "asset_index_revision": 3,
            "timeline_id": "timeline-1",
            "timeline_version": "v007",
            "selected_script_id": "script-1",
            "selected_segment_id": "segment-1",
            "segment_summaries": (
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 5.0,
                    "text": "첫 장면",
                },
            ),
            "media_candidates": (
                {
                    "asset_id": "asset-video",
                    "kind": "broll_video",
                    "title": "산책",
                    "duration_sec": 5.0,
                    "tags": (),
                },
            ),
            "timeline_summary": {
                "duration_sec": 5.0,
                "track_count": 1,
                "clip_count": 1,
                "gap_count": 0,
            },
            "supported_controls": (
                {"kind": "broll", "mode": "recommendation_only"},
            ),
        }
    )


def _raw(*, reply_text: str = "산책 영상을 추천합니다.") -> str:
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": reply_text,
        "proposal": {
            "proposal_id": "proposal-yujin-1",
            "base_revision": "session:session-1:revision:7:assets:3",
            "title": "첫 장면 B-roll",
            "rationale": "장면을 보강합니다.",
            "operations": [
                {
                    "operation_id": "operation-1",
                    "kind": "broll",
                    "target": {
                        "segment_id": "segment-1",
                        "track_id": "video-primary",
                    },
                    "parameters": {
                        "asset_id": "asset-video",
                        "start_sec": 0.0,
                        "duration_sec": 3.0,
                        "fit": "cover",
                    },
                    "requires_materialization": True,
                    "preview_summary": "첫 장면에 3초 산책 영상",
                }
            ],
        },
    }
    return (
        "산책 영상을 추천합니다.\n"
        "```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```"
    )


def _variant_raw() -> str:
    machine_payload = _raw().split("```videobox-yujin-response\n", 1)[1]
    payload = json.loads(machine_payload.rsplit("\n```", 1)[0])
    payload["proposal"].update(
        {
            "variant_id": "variant-vertical",
            "base_variant_revision": 4,
            "title": "세로 변형 화면 보정",
            "operations": [
                {
                    "operation_id": "variant-crop",
                    "kind": "output_variant",
                    "target": {
                        "variant_id": "variant-vertical",
                        "track_id": "output-variant",
                    },
                    "parameters": {
                        "action": "set_crop",
                        "x": 0.1,
                        "y": 0.0,
                        "width": 0.8,
                        "height": 1.0,
                    },
                    "requires_materialization": False,
                    "preview_summary": "세로 변형 crop 미리보기",
                }
            ],
        }
    )
    payload["reply_text"] = "세로 변형을 제안합니다."
    return (
        "세로 변형을 제안합니다.\n"
        "```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```"
    )


def test_variant_projection_preserves_variant_lineage_in_candidate_dto() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    context = _context()
    context = YujinCreatorContext.model_validate(
        {
            **context.model_dump(mode="python"),
            "current_surface": "output",
            "selection_kind": "variant",
            "master_session_id": "session-1",
            "master_session_revision": 7,
            "variant_id": "variant-vertical",
            "variant_kind": "vertical_highlight",
            "variant_revision": 4,
            "supported_controls": (
                {"kind": "output_variant", "mode": "recommendation_only"},
            ),
        }
    )

    result = parse_and_project_yujin_creator_output(
        _variant_raw(),
        context,
        revision=5,
        trusted_project_id="project-1",
        trusted_run_id="run-variant",
    )

    assert result.validation_outcome == "valid"
    assert result.proposal is not None
    assert result.proposal.diff["variant_id"] == "variant-vertical"
    assert result.proposal.diff["base_variant_revision"] == 4
    assert result.proposal.candidates[0].media_type == "output_variant"


def _short_form_context() -> YujinCreatorContext:
    return YujinCreatorContext.model_validate(
        {
            **_context().model_dump(mode="python"),
            "current_surface": "edit",
            "selection_kind": "variant",
            "master_session_id": "session-1",
            "master_session_revision": 7,
            "variant_id": "variant-short",
            "variant_kind": "vertical_highlight",
            "variant_revision": 4,
            "segment_summaries": (
                {"segment_id": "segment-1", "start_sec": 0.0, "end_sec": 5.0, "text": "훅"},
                {"segment_id": "segment-2", "start_sec": 5.0, "end_sec": 9.0, "text": "설명"},
                {"segment_id": "segment-3", "start_sec": 9.0, "end_sec": 12.0, "text": "결론"},
            ),
            "supported_controls": (
                {"kind": "output_variant", "mode": "recommendation_only"},
            ),
        }
    )


def _short_form_raw(segment_ids: list[str]) -> str:
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": "숏폼으로 쓸 장면을 골랐어요.",
        "proposal": {
            "proposal_id": "proposal-yujin-short",
            "base_revision": "session:session-1:revision:7:assets:3",
            "title": "숏폼 장면 고르기",
            "rationale": "훅과 결론만 남깁니다.",
            "variant_id": "variant-short",
            "base_variant_revision": 4,
            "operations": [
                {
                    "operation_id": "short-form-selection",
                    "kind": "output_variant",
                    "target": {
                        "variant_id": "variant-short",
                        "track_id": "output-variant",
                    },
                    "parameters": {
                        "action": "select_segments",
                        "segment_ids": segment_ids,
                    },
                    "requires_materialization": False,
                    "preview_summary": "숏폼에 넣을 장면 목록",
                }
            ],
        },
    }
    return (
        "숏폼으로 쓸 장면을 골랐어요.\n"
        "```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```"
    )


def _short_form_candidate(segment_ids: list[str]):
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    projection = parse_and_project_yujin_creator_output(
        _short_form_raw(segment_ids),
        _short_form_context(),
        revision=1,
        trusted_project_id="project-1",
        trusted_run_id="run-short",
    )
    assert projection.proposal is not None, projection.validation_outcome
    return projection.proposal.candidates[0]


def test_short_form_scene_selection_becomes_a_selected_segment_ids_patch() -> None:
    """장면 고르기는 `overrides`가 아니라 `selected_segment_ids` 자리로 간다.

    다섯 기존 동작은 전부 `overrides.<필드>`(모양 조정)로 갔다. 장면 구성은
    `apply_variant_patch`에서 완전히 다른 가지이고, 세로 하이라이트에서만
    허용된다.
    """
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        variant_patch_from_yujin_candidate,
    )

    patch = variant_patch_from_yujin_candidate(
        _short_form_candidate(["segment-1", "segment-3"])
    )

    assert patch == {"selected_segment_ids": ["segment-1", "segment-3"]}


def test_a_chat_scene_selection_carries_how_many_scenes_yujin_actually_saw() -> None:
    """채팅으로 고를 때 유진은 **판 전체를 보지 않는다.**

    단추 경로(`pick_short_form_scenes`)는 48개를 추려 읽고 그 수를 화면에
    말하지만, 채팅 경로는 창작 context의 `segment_summaries`만 본다 -- 32개에서
    잘린다. 그 사실을 후보에 실어 화면까지 보내지 않으면, 롱폼에서 유진이
    앞부분만 보고 고른 숏폼을 화면이 아무 단서 없이 보여 주게 된다.
    """
    context = _short_form_context().model_copy(update={"segment_total": 243})
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    projection = parse_and_project_yujin_creator_output(
        _short_form_raw(["segment-1", "segment-3"]),
        context,
        revision=1,
        trusted_project_id="project-1",
        trusted_run_id="run-short",
    )

    assert projection.proposal is not None, projection.validation_outcome
    metadata = projection.proposal.candidates[0].canonical_metadata
    assert metadata["scenes_read_by_yujin"] == 3
    assert metadata["scenes_total"] == 243


def test_one_message_can_carry_both_a_shape_change_and_a_scene_selection() -> None:
    """적용기는 후보 여럿을 한 patch로 합친다 -- 모양과 장면이 섞여도 한 번에."""
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        merged_variant_patch_from_yujin_candidates,
    )

    crop_projection = _variant_crop_candidate()
    merged = merged_variant_patch_from_yujin_candidates(
        [crop_projection, _short_form_candidate(["segment-3"])]
    )

    assert merged["selected_segment_ids"] == ["segment-3"]
    assert merged["overrides"]["crop"] == {
        "x": 0.1,
        "y": 0.0,
        "width": 0.8,
        "height": 1.0,
    }


def _variant_crop_candidate():
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    payload = json.loads(
        _short_form_raw(["segment-1"])
        .split("```videobox-yujin-response\n", 1)[1]
        .rsplit("\n```", 1)[0]
    )
    payload["proposal"]["operations"][0]["operation_id"] = "variant-crop"
    payload["proposal"]["operations"][0]["parameters"] = {
        "action": "set_crop",
        "x": 0.1,
        "y": 0.0,
        "width": 0.8,
        "height": 1.0,
    }
    raw = (
        "숏폼으로 쓸 장면을 골랐어요.\n"
        "```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "```"
    )
    projection = parse_and_project_yujin_creator_output(
        raw,
        _short_form_context(),
        revision=1,
        trusted_project_id="project-1",
        trusted_run_id="run-crop",
    )
    assert projection.proposal is not None, projection.validation_outcome
    return projection.proposal.candidates[0]


def test_exact_trailing_frame_projects_existing_candidate_only_dto() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        derive_yujin_persisted_proposal_id,
        parse_and_project_yujin_creator_output,
    )

    result = parse_and_project_yujin_creator_output(
        _raw(),
        _context(),
        revision=4,
        trusted_project_id="project-1",
        trusted_run_id="run-1",
    )

    assert result.reply_text == "산책 영상을 추천합니다."
    assert result.validation_outcome == "valid"
    assert result.proposal.status == "candidate_only"
    assert result.proposal.proposal_id == derive_yujin_persisted_proposal_id(
        project_id="project-1",
        run_id="run-1",
    )
    assert result.proposal.proposal_id != "proposal-yujin-1"
    assert result.proposal.candidates[0].candidate_id != "operation-1"
    assert result.proposal.base_session_revision == 7
    assert result.proposal.asset_index_revision == 3
    assert result.proposal.candidates[0].preview_uri is None
    assert result.proposal.candidates[0].controls["kind"] == "broll"
    assert result.proposal.diff["proposal_mode"] == "candidate_only"


def test_trusted_proposal_namespace_is_project_scoped_and_model_id_independent() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        derive_yujin_persisted_proposal_id,
    )

    first = derive_yujin_persisted_proposal_id(
        project_id="project-a", run_id="same-run"
    )
    second = derive_yujin_persisted_proposal_id(
        project_id="project-b", run_id="same-run"
    )

    assert first != second
    assert first.startswith("yujin-proposal-")
    assert second.startswith("yujin-proposal-")
    assert "/" not in first
    assert "\\" not in first
    assert "%" not in first


def test_legacy_plain_text_remains_conversational_without_proposal() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    result = parse_and_project_yujin_creator_output("기존 일반 답변", _context())

    assert result.reply_text == "기존 일반 답변"
    assert result.proposal is None
    assert result.validation_outcome == "legacy_text"
    assert result.manual_fallback is False


def test_prose_followed_by_machine_like_json_keeps_only_visible_prefix() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        MANUAL_FALLBACK,
        parse_and_project_yujin_creator_output,
    )

    cases = (
        (
            'Here is JSON: {"schema_version":"videobox.yujin-response.v1",'
            '"password":"must-not-publish"}',
            "Here is JSON:",
        ),
        (
            '추천 결과입니다.\n[\n  {"password":"must-not-publish"}\n]',
            "추천 결과입니다.",
        ),
        (
            '설명입니다.\n{"schema_version":"videobox.yujin-response.v1",'
            '"password":"must-not-publish"',
            "설명입니다.",
        ),
        (
            "설명입니다.\nschema_version: videobox.yujin-response.v1 "
            "password=must-not-publish",
            "설명입니다.",
        ),
    )
    for raw, visible_prefix in cases:
        result = parse_and_project_yujin_creator_output(raw, _context())
        assert result.validation_outcome == "invalid"
        assert result.proposal is None
        assert result.reply_text == f"{visible_prefix}\n\n{MANUAL_FALLBACK}"
        assert "schema_version" not in result.reply_text
        assert "password" not in result.reply_text
        assert "must-not-publish" not in result.reply_text


@pytest.mark.parametrize(
    "machine_suffix",
    (
        '{"reply_text":"must-not-publish"',
        '{"password":"must-not-publish"',
        '[["must-not-publish"',
        '[{"password":"must-not-publish"',
        "[1",
        "[true",
        "[false",
        "[null",
        "[-1",
        "{password=must-not-publish",
        "{token:must-not-publish",
        "{schema_version=must-not-publish",
        "{operations:must-not-publish",
        "api_key = sk-proj-must-not-publish",
        "access_token: ghp_must-not-publish",
        "refresh_token = must-not-publish",
        "client_secret: must-not-publish",
        "authorization = Bearer must-not-publish",
        "aws_secret_access_key = must-not-publish",
        "openai_api_key: must-not-publish",
        "github_token = must-not-publish",
        "proposal = {must-not-publish",
        "schema_version: must-not-publish",
        "operations = [must-not-publish",
        "reply_text: must-not-publish",
    ),
)
def test_incomplete_json_token_suffix_is_fail_closed(
    machine_suffix: str,
) -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        MANUAL_FALLBACK,
        parse_and_project_yujin_creator_output,
    )

    result = parse_and_project_yujin_creator_output(
        f"Visible reply\n{machine_suffix}",
        _context(),
    )

    assert result.validation_outcome == "invalid"
    assert result.proposal is None
    assert result.reply_text == f"Visible reply\n\n{MANUAL_FALLBACK}"
    assert "must-not-publish" not in result.reply_text
    assert machine_suffix not in result.reply_text


@pytest.mark.parametrize(
    "raw",
    (
        "1번 항목은 [1]입니다.",
        "템플릿 변수 {1}을 유지하세요.",
        "검사 결과 [true]는 예시 표기입니다.",
        "목록: [1, 2, 3]",
        "목록\n[1] 첫째",
        "placeholder: {1}",
        "연도: [2024]년 기준입니다.",
        '설정: {"mode":"safe"}를 예시로 듭니다.',
    ),
)
def test_inline_json_like_notation_remains_legacy_text(raw: str) -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    result = parse_and_project_yujin_creator_output(raw, _context())

    assert result.reply_text == raw
    assert result.validation_outcome == "legacy_text"
    assert result.manual_fallback is False


@pytest.mark.parametrize(
    "assignment",
    (
        "api_key = sk-proj-must-not-publish",
        "refresh_token: must-not-publish",
        "client_secret = must-not-publish",
        "proposal = {must-not-publish",
        "schema_version: must-not-publish",
        "operations = [must-not-publish",
        "reply_text = must-not-publish",
    ),
)
def test_assignment_boundary_is_split_safe_with_crlf(assignment: str) -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        safe_yujin_stream_visible_prefix,
    )

    raw = f"Visible reply\r\n{assignment}"
    for split in range(1, len(raw) + 1):
        visible = safe_yujin_stream_visible_prefix(raw[:split])
        assert assignment not in visible
        assert "must-not-publish" not in visible


def test_harmless_credential_policy_prose_remains_visible() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    raw = "API keys and client secrets should never be included in a proposal."
    result = parse_and_project_yujin_creator_output(raw, _context())
    assert result.validation_outcome == "legacy_text"
    assert result.reply_text == raw


def test_harmless_braces_and_natural_language_remain_legacy_text() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    harmless = (
        "중괄호 {예시}는 일반 설명입니다.",
        "목록 [첫째, 둘째]를 확인하세요.",
        "JSON이라는 단어의 뜻만 설명합니다.",
        '문자열 값 "answer"를 그대로 사용하세요.',
    )
    for raw in harmless:
        result = parse_and_project_yujin_creator_output(raw, _context())
        assert result.reply_text == raw
        assert result.validation_outcome == "legacy_text"
        assert result.manual_fallback is False


def test_only_exact_machine_frame_is_parsed_and_invalid_payload_keeps_reply() -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    invalid_outputs = (
        '{"schema_version":"videobox.yujin-response.v1"}',
        "설명\n```json\n{}\n```",
        _raw(reply_text="보이는 답변과 다름"),
        _raw() + "\n추가 prose",
        "설명\n```videobox-yujin-response\n{}\n```\n```json\n{}\n```",
    )
    for raw in invalid_outputs:
        result = parse_and_project_yujin_creator_output(raw, _context())
        assert result.proposal is None
        assert result.validation_outcome == "invalid"
        assert result.manual_fallback is True
        assert "```" not in result.reply_text
        assert '{"schema_version"' not in result.reply_text

    mismatch = parse_and_project_yujin_creator_output(
        _raw(reply_text="보이는 답변과 다름"), _context()
    )
    assert mismatch.reply_text.startswith("산책 영상을 추천합니다.")
    assert "수동" in mismatch.reply_text
    assert mismatch.validation_outcome == "invalid"
    assert mismatch.manual_fallback is True
