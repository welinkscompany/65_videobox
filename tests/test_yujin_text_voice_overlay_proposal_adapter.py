from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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
                    "start_sec": 2.0,
                    "end_sec": 7.0,
                    "text": "첫 장면",
                },
            ),
            "media_candidates": (
                {
                    "asset_id": "asset-image",
                    "kind": "image",
                    "title": "장면 이미지",
                    "duration_sec": None,
                    "tags": (),
                },
            ),
            "approved_tts_candidates": (
                {
                    "candidate_id": "tts_candidate_001",
                    "asset_id": "asset-tts",
                    "segment_id": "segment-1",
                    "source_text": "첫 장면",
                    "technical_status": "accepted",
                    "operator_review_status": "approved",
                    "asset_revision": "tts-r1",
                    "expected_content_sha256": "a" * 64,
                },
            ),
            "timeline_summary": {
                "duration_sec": 7.0,
                "track_count": 2,
                "clip_count": 1,
                "gap_count": 2,
            },
            "supported_controls": (
                {"kind": "broll", "mode": "recommendation_only"},
                {"kind": "bgm", "mode": "recommendation_only"},
                {"kind": "caption", "mode": "recommendation_only"},
                {"kind": "output_check", "mode": "read_only"},
                {"kind": "overlay", "mode": "recommendation_only"},
                {"kind": "sfx", "mode": "recommendation_only"},
                {"kind": "voice", "mode": "recommendation_only"},
            ),
        }
    )


def _operation(kind: str, variant: str = "") -> dict[str, object]:
    if kind == "caption" and variant == "style":
        parameters: dict[str, object] = {
            "action": "set_style",
            "style": {
                "font_family": "Arial",
                "font_size_px": 54,
                "text_color": "#FFFFFFFF",
                "outline_color": "#000000FF",
                "outline_width_px": 3,
                "background_color": "#00000000",
                "position_x_percent": 50,
                "position_y_percent": 88,
                "horizontal_align": "center",
                "safe_area_enabled": True,
                "shadow_blur_px": 0,
            },
        }
    elif kind == "caption":
        parameters = {"action": "set_text", "text": "바꾼 자막"}
    elif kind == "voice":
        parameters = {
            "candidate_id": "tts_candidate_001",
            "asset_id": "asset-tts",
        }
    elif kind == "overlay" and variant == "image":
        parameters = {
            "overlay_kind": "image",
            "asset_id": "asset-image",
            "text": "장면 이미지",
        }
    elif kind == "overlay" and variant == "table":
        parameters = {
            "overlay_kind": "table",
            "columns": ["항목", "값"],
            "rows": [["속도", "빠름"]],
            "text": "장면 표",
        }
    elif kind == "overlay":
        parameters = {
            "overlay_kind": "explanation_card",
            "title": "핵심",
            "body": "설명",
            "text": "장면 설명",
        }
    else:
        parameters = {"check": "timeline_gaps"}
    target = (
        {"track_id": "output-primary"}
        if kind == "output_check"
        else {
            "script_id": "script-1",
            "segment_id": "segment-1",
            "track_id": "caption-primary" if kind == "caption" else "voice-primary",
        }
        if kind in {"caption", "voice"}
        else {"segment_id": "segment-1", "track_id": "video-overlay"}
    )
    return {
        "operation_id": f"operation-{kind}-{variant or 'default'}",
        "kind": kind,
        "target": target,
        "parameters": parameters,
        "requires_materialization": False,
        "preview_summary": f"{kind} 추천",
    }


def _raw(operations: list[dict[str, object]]) -> str:
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": "현재 편집본에 맞는 항목입니다.",
        "proposal": {
            "proposal_id": "untrusted-id",
            "base_revision": "session:session-1:revision:7:assets:3",
            "title": "편집 추천",
            "rationale": "현재 장면에만 적용합니다.",
            "operations": operations,
        },
    }
    return (
        "현재 편집본에 맞는 항목입니다.\n"
        "```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n```"
    )


class _Store:
    def __init__(self, root: Path) -> None:
        self.image_path = root / "image.bin"
        self.tts_path = root / "tts.bin"
        self.image_path.write_bytes(b"current-image")
        self.tts_path.write_bytes(b"current-tts")
        self.image_kind = "image"
        self.tts_status = "accepted"
        self.tts_review = "approved"

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict:
        return {
            "project_id": project_id,
            "session_id": session_id,
            "session_revision": 7,
        }

    def get_asset_index_revision(self, project_id: str) -> int:
        return 3

    def get_asset(self, *, project_id: str, asset_id: str) -> dict:
        if asset_id == "asset-image":
            return {
                "project_id": project_id,
                "asset_id": asset_id,
                "asset_type": self.image_kind,
                "storage_uri": "storage://image",
                "created_at": "image-r1",
                "metadata": {},
            }
        if asset_id == "asset-tts":
            return {
                "project_id": project_id,
                "asset_id": asset_id,
                "asset_type": "generated_tts_audio",
                "storage_uri": "storage://tts",
                "created_at": "tts-r1",
                "metadata": {},
            }
        raise KeyError(asset_id)

    def resolve_storage_uri(self, *, project_id: str, storage_uri: str) -> Path:
        return self.image_path if storage_uri.endswith("image") else self.tts_path

    def get_tts_candidate(self, *, project_id: str, candidate_id: str) -> dict:
        if candidate_id != "tts_candidate_001":
            raise KeyError(candidate_id)
        return {
            "candidate_id": candidate_id,
            "project_id": project_id,
            "segment_id": "segment-1",
            "asset_id": "asset-tts",
            "source_text": "첫 장면",
            "technical_status": self.tts_status,
            "operator_review_status": self.tts_review,
        }


def _activate(store: _Store, operations: list[dict[str, object]]):
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        activate_yujin_media_projection,
        parse_and_project_yujin_creator_output,
    )

    context = _context()
    projection = parse_and_project_yujin_creator_output(
        _raw(operations),
        context,
        trusted_project_id=context.project_id,
        trusted_run_id="run-b4",
    )
    assert projection.proposal is not None
    return activate_yujin_media_projection(
        store=store,
        project_id=context.project_id,
        context=context,
        projection=projection,
    )


@pytest.mark.parametrize(
    ("kind", "variant", "command_kind"),
    (
        ("caption", "", "set_caption_text"),
        ("caption", "style", "set_caption_style"),
        ("voice", "", "apply_tts_candidate"),
        ("overlay", "", "apply_overlay"),
        ("overlay", "image", "apply_overlay"),
        ("overlay", "table", "apply_overlay"),
    ),
)
def test_exact_supported_b4_operation_becomes_one_actionable_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    variant: str,
    command_kind: str,
) -> None:
    import videobox_core_engine.yujin_creator_proposal_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "sha256_file",
        lambda path: "a" * 64 if path.name == "tts.bin" else "b" * 64,
    )
    activated = _activate(_Store(tmp_path), [_operation(kind, variant)])

    assert activated.proposal is not None
    assert activated.proposal.status == "ready"
    assert activated.proposal.diff["proposal_mode"] == "yujin_actionable_v1"
    candidate = activated.proposal.candidates[0]
    assert candidate.availability == "actionable"
    assert candidate.review_status == "approved"
    assert candidate.canonical_metadata["yujin_actionable_operation"] is True
    assert candidate.canonical_metadata["command_kind"] == command_kind
    assert candidate.canonical_metadata["target_segment_id"] == "segment-1"
    if kind == "voice":
        assert candidate.asset_id == "asset-tts"
        assert candidate.expected_content_sha256 == "a" * 64
        assert candidate.canonical_metadata["candidate_id"] == "tts_candidate_001"
        assert candidate.canonical_metadata["requires_materialization"] is False


def test_output_check_is_backend_attested_read_only_finding(tmp_path: Path) -> None:
    operation = _operation("output_check")
    operation["preview_summary"] = "미디어, 미리보기, 내보내기 준비가 모두 끝났습니다."
    activated = _activate(_Store(tmp_path), [operation])

    assert activated.proposal is not None
    assert activated.proposal.status == "candidate_only"
    candidate = activated.proposal.candidates[0]
    assert candidate.availability == "read_only"
    assert candidate.review_status == "not_applicable"
    assert dict(candidate.controls) == {
        "check": "timeline_gaps",
        "gap_count": 2,
    }
    assert candidate.canonical_metadata["yujin_read_only_finding"] is True
    assert candidate.canonical_metadata["selectable"] is False
    assert candidate.canonical_metadata["render_calls"] == 0
    assert (
        candidate.canonical_metadata["preview_summary"]
        == "타임라인 빈 구간 검사 결과: 2개"
    )
    assert candidate.reason_chips == ("타임라인 빈 구간 검사 결과: 2개",)
    assert "준비" not in candidate.canonical_metadata["preview_summary"]


@pytest.mark.parametrize(
    "operation",
    (
        {
            **_operation("caption"),
            "parameters": {"action": "set_text", "text": "자막", "placement": "bottom"},
        },
        {
            **_operation("caption", "style"),
            "parameters": {
                "action": "set_style",
                "style": {"font_family": "Arial"},
            },
        },
        {
            **_operation("caption", "style"),
            "parameters": {
                **_operation("caption", "style")["parameters"],
                "style": {
                    **_operation("caption", "style")["parameters"]["style"],
                    "position_y_percent": 95,
                },
            },
        },
        {
            **_operation("caption", "style"),
            "parameters": {
                **_operation("caption", "style")["parameters"],
                "style": {
                    **_operation("caption", "style")["parameters"]["style"],
                    "text_color": "#FFFFFF",
                },
            },
        },
        {
            **_operation("voice"),
            "parameters": {
                "candidate_id": "legacy-recommendation-1",
                "asset_id": "asset-tts",
            },
        },
        {
            **_operation("voice"),
            "parameters": {
                "candidate_id": "tts_candidate_001",
                "asset_id": "asset-tts",
                "speed": 1.0,
            },
        },
        {
            **_operation("overlay", "image"),
            "parameters": {
                **_operation("overlay", "image")["parameters"],
                "x": 0.5,
            },
        },
        {
            **_operation("output_check"),
            "parameters": {"check": "preview_readiness"},
        },
        {
            **_operation("voice"),
            "requires_materialization": True,
        },
    ),
)
def test_partial_generic_or_unbounded_b4_payload_is_rejected(
    operation: dict[str, object],
) -> None:
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        parse_and_project_yujin_creator_output,
    )

    projection = parse_and_project_yujin_creator_output(
        _raw([operation]),
        _context(),
        trusted_project_id="project-1",
        trusted_run_id="run-invalid",
    )

    assert projection.proposal is None
    assert projection.validation_outcome == "invalid"


@pytest.mark.parametrize("kind", ("effect", "transition", "keyframe", "mask", "filter", "animation"))
def test_unsupported_opencut_operations_are_rejected(kind: str) -> None:
    from videobox_domain_models.yujin_creator_proposals import (
        validate_yujin_creator_response,
    )

    payload = json.loads(_raw([_operation("caption")]).split("\n", 2)[2][:-4])
    payload["proposal"]["operations"][0]["kind"] = kind

    with pytest.raises((ValidationError, ValueError)):
        validate_yujin_creator_response(payload, _context())


def test_wrong_image_or_changed_tts_approval_never_activates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import videobox_core_engine.yujin_creator_proposal_adapter as adapter

    monkeypatch.setattr(adapter, "sha256_file", lambda _path: "a" * 64)
    image_store = _Store(tmp_path)
    image_store.image_kind = "broll_video"
    image = _activate(image_store, [_operation("overlay", "image")])
    assert image.proposal is not None
    assert image.proposal.candidates[0].availability == "candidate_only"

    voice_store = _Store(tmp_path)
    voice_store.tts_review = "rejected"
    voice = _activate(voice_store, [_operation("voice")])
    assert voice.proposal is not None
    assert voice.proposal.candidates[0].availability == "candidate_only"
