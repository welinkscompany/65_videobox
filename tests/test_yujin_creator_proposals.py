from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from videobox_domain_models.yujin_creator_context import YujinCreatorContext
from videobox_domain_models.yujin_creator_proposals import (
    EditorCaptionStyle,
    TableOverlayParameters,
)


def _context(**changes) -> YujinCreatorContext:
    payload = {
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
            {
                "asset_id": "asset-bgm",
                "kind": "bgm",
                "title": "잔잔한 음악",
                "duration_sec": 20.0,
                "tags": (),
            },
            {
                "asset_id": "asset-sfx",
                "kind": "sfx",
                "title": "효과음",
                "duration_sec": 2.0,
                "tags": (),
            },
            {
                "asset_id": "asset-voice",
                "kind": "voice_sample_audio",
                "title": "목소리",
                "duration_sec": 3.0,
                "tags": (),
            },
        ),
        "approved_tts_candidates": (
            {
                "candidate_id": "tts_candidate_001",
                "asset_id": "asset-voice",
                "segment_id": "segment-1",
                "source_text": "안전한 음성",
                "technical_status": "accepted",
                "operator_review_status": "approved",
                "asset_revision": "voice-r1",
                "expected_content_sha256": "a" * 64,
            },
        ),
        "timeline_summary": {
            "duration_sec": 5.0,
            "track_count": 2,
            "clip_count": 1,
            "gap_count": 0,
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
    payload.update(changes)
    return YujinCreatorContext.model_validate(payload)


def _envelope(**changes) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": "첫 장면에 산책 영상을 추천합니다.",
        "proposal": {
            "proposal_id": "proposal-yujin-1",
            "base_revision": "session:session-1:revision:7:assets:3",
            "title": "첫 장면 B-roll",
            "rationale": "대사의 의미를 시각적으로 보강합니다.",
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
    payload.update(changes)
    return payload


def _validate(payload: dict[str, object], context: YujinCreatorContext | None = None):
    from videobox_domain_models.yujin_creator_proposals import (
        validate_yujin_creator_response,
    )

    return validate_yujin_creator_response(payload, context or _context())


def _caption_style(**changes: object) -> dict[str, object]:
    style: dict[str, object] = {
        "font_family": "Pretendard",
        "font_size_px": 42,
        "text_color": "#FFFFFFFF",
        "outline_color": "#000000FF",
        "outline_width_px": 2,
        "background_color": "#00000000",
        "position_x_percent": 50,
        "position_y_percent": 88,
        "horizontal_align": "center",
        "safe_area_enabled": True,
        "shadow_blur_px": 0,
    }
    style.update(changes)
    return style


def _variant_operation(
    action: str = "set_crop", **parameters: object
) -> dict[str, object]:
    defaults: dict[str, object] = {
        "set_crop": {
            "x": 0.1,
            "y": 0.0,
            "width": 0.8,
            "height": 1.0,
        },
        "set_focal": {"x": 0.5, "y": 0.4},
        "set_caption_layout": {
            "layout": "bottom",
            "max_lines": 2,
            "font_scale": 1.0,
        },
        "set_safe_area": {
            "top_percent": 8,
            "right_percent": 6,
            "bottom_percent": 10,
            "left_percent": 6,
        },
        "correct_audio": {
            "gain_db": -3.0,
            "fade_in_sec": 0.5,
            "fade_out_sec": 0.5,
        },
    }[action]
    defaults.update(parameters)
    return {
        "operation_id": f"variant-{action}",
        "kind": "output_variant",
        "target": {
            "variant_id": "variant-vertical",
            "track_id": "output-variant",
        },
        "parameters": {"action": action, **defaults},
        "requires_materialization": False,
        "preview_summary": f"변형 {action} 미리보기",
    }


def _variant_context(**changes: object) -> YujinCreatorContext:
    controls = tuple(_context().supported_controls) + (
        {"kind": "output_variant", "mode": "recommendation_only"},
    )
    defaults: dict[str, object] = {
        "current_surface": "output",
        "selection_kind": "variant",
        "master_session_id": "session-1",
        "master_session_revision": 7,
        "variant_id": "variant-vertical",
        "variant_kind": "vertical_highlight",
        "variant_revision": 4,
        "supported_controls": controls,
    }
    defaults.update(changes)
    return _context(**defaults)


def test_variant_proposal_binds_master_and_variant_revisions() -> None:
    payload = _envelope()
    payload["proposal"].update(
        {
            "variant_id": "variant-vertical",
            "base_variant_revision": 4,
            "operations": [_variant_operation("set_crop")],
        }
    )

    response = _validate(payload, _variant_context())

    assert response.proposal is not None
    assert response.proposal.variant_id == "variant-vertical"
    assert response.proposal.base_variant_revision == 4
    assert response.proposal.operations[0].parameters.action == "set_crop"


@pytest.mark.parametrize(
    "action",
    (
        "set_crop",
        "set_focal",
        "set_caption_layout",
        "set_safe_area",
        "correct_audio",
    ),
)
def test_variant_proposal_allows_only_bounded_render_overrides(action: str) -> None:
    payload = _envelope()
    payload["proposal"].update(
        {
            "variant_id": "variant-vertical",
            "base_variant_revision": 4,
            "operations": [_variant_operation(action)],
        }
    )

    assert _validate(payload, _variant_context()).proposal is not None


@pytest.mark.parametrize(
    "mutate",
    (
        lambda operation: operation["parameters"].update(
            {"action": "set_story", "story": "replace-master"}
        ),
        lambda operation: operation["parameters"].update(
            {"shell": "ffmpeg", "action": "set_crop"}
        ),
        lambda operation: operation["parameters"].update(
            {"path": "C:\\private\\output.mp4"}
        ),
        lambda operation: operation["parameters"].update(
            {"url": "https://example.invalid/render"}
        ),
    ),
    ids=("vertical-full-story", "shell", "filesystem", "http"),
)
def test_variant_proposal_rejects_story_and_external_effect_payloads(mutate) -> None:
    payload = _envelope()
    operation = _variant_operation("set_crop")
    mutate(operation)
    payload["proposal"].update(
        {
            "variant_id": "variant-vertical",
            "base_variant_revision": 4,
            "operations": [operation],
        }
    )

    with pytest.raises((ValidationError, ValueError)):
        _validate(payload, _variant_context(variant_kind="vertical_full"))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("variant_id", "variant-other"),
        ("base_variant_revision", 3),
    ),
)
def test_variant_proposal_rejects_stale_or_unknown_variant_identity(
    field: str, value: object
) -> None:
    payload = _envelope()
    payload["proposal"].update(
        {
            "variant_id": "variant-vertical",
            "base_variant_revision": 4,
            "operations": [_variant_operation("set_focal")],
        }
    )
    payload["proposal"][field] = value

    with pytest.raises(ValueError, match="variant"):
        _validate(payload, _variant_context())


@pytest.mark.parametrize(
    ("safe_area_enabled", "position_y_percent", "expected_position_y_percent"),
    (
        (False, 100, 100),
        (True, 95, 94),
        (True, 100, 94),
    ),
)
def test_b4_caption_style_matches_backend_safe_area_semantics(
    safe_area_enabled: bool,
    position_y_percent: int,
    expected_position_y_percent: int,
) -> None:
    style = EditorCaptionStyle.model_validate(
        _caption_style(
            safe_area_enabled=safe_area_enabled,
            position_y_percent=position_y_percent,
        )
    )

    assert style.position_y_percent == expected_position_y_percent
    assert set(style.model_dump()) == {
        "font_family",
        "font_size_px",
        "text_color",
        "outline_color",
        "outline_width_px",
        "background_color",
        "position_x_percent",
        "position_y_percent",
        "horizontal_align",
        "safe_area_enabled",
        "shadow_blur_px",
    }


@pytest.mark.parametrize("position_y_percent", (-1, 101))
def test_b4_caption_style_rejects_absolute_position_y_outside_0_to_100(
    position_y_percent: int,
) -> None:
    with pytest.raises(ValidationError):
        EditorCaptionStyle.model_validate(
            _caption_style(position_y_percent=position_y_percent)
        )


def test_b4_table_items_accept_256_code_points_and_1024_utf8_bytes() -> None:
    bounded = "😀" * 256

    table = TableOverlayParameters.model_validate(
        {
            "overlay_kind": "table",
            "columns": (bounded,),
            "rows": ((bounded,),),
            "text": "표 설명",
        }
    )

    assert table.columns == (bounded,)
    assert table.rows == ((bounded,),)
    assert len(bounded) == 256
    assert len(bounded.encode("utf-8")) == 1024


@pytest.mark.parametrize(
    ("columns", "rows"),
    (
        (("a" * 257,), (("값",),)),
        (("항목",), (("a" * 257,),)),
    ),
    ids=("oversized-column", "oversized-cell"),
)
def test_b4_table_rejects_items_over_256_code_points(
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> None:
    with pytest.raises(ValidationError):
        TableOverlayParameters.model_validate(
            {
                "overlay_kind": "table",
                "columns": columns,
                "rows": rows,
                "text": "표 설명",
            }
        )


def _operation(kind: str) -> dict[str, object]:
    operations = {
        "broll": {
            "target": {"segment_id": "segment-1", "track_id": "video-primary"},
            "parameters": {
                "asset_id": "asset-video",
                "start_sec": 0.0,
                "duration_sec": 3.0,
                "fit": "cover",
            },
            "requires_materialization": True,
        },
        "bgm": {
            "target": {"track_id": "audio-bgm"},
            "parameters": {
                "asset_id": "asset-bgm",
                "start_sec": 0.0,
                "volume": 1.0,
            },
            "requires_materialization": True,
        },
        "sfx": {
            "target": {"segment_id": "segment-1", "track_id": "audio-sfx"},
            "parameters": {
                "asset_id": "asset-sfx",
                "start_sec": 1.0,
                "volume": 1.0,
            },
            "requires_materialization": True,
        },
        "caption": {
            "target": {
                "script_id": "script-1",
                "segment_id": "segment-1",
                "track_id": "caption-primary",
            },
            "parameters": {"action": "set_text", "text": "안전한 자막"},
            "requires_materialization": False,
        },
        "voice": {
            "target": {
                "script_id": "script-1",
                "segment_id": "segment-1",
                "track_id": "voice-primary",
            },
            "parameters": {
                "candidate_id": "tts_candidate_001",
                "asset_id": "asset-voice",
            },
            "requires_materialization": False,
        },
        "overlay": {
            "target": {
                "segment_id": "segment-1",
                "track_id": "video-overlay",
            },
            "parameters": {
                "overlay_kind": "explanation_card",
                "title": "안전한 제목",
                "body": "안전한 본문",
                "text": "안전한 오버레이",
            },
            "requires_materialization": False,
        },
        "output_check": {
            "target": {"track_id": "output-primary"},
            "parameters": {"check": "timeline_gaps"},
            "requires_materialization": False,
        },
    }
    return {
        "operation_id": f"operation-{kind}",
        "kind": kind,
        **operations[kind],
        "preview_summary": f"{kind} 미리보기",
    }


def test_strict_frozen_response_accepts_current_attested_broll() -> None:
    response = _validate(_envelope())

    assert response.schema_version == "videobox.yujin-response.v1"
    assert response.proposal.operations[0].kind == "broll"
    with pytest.raises(ValidationError):
        response.reply_text = "changed"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema_version="videobox.yujin-response.v2"),
        lambda value: value["proposal"]["operations"][0].update(kind="execute"),
        lambda value: value["proposal"]["operations"][0].update(target={}),
        lambda value: value["proposal"].update(
            base_revision="session:session-1:revision:6:assets:3"
        ),
        lambda value: value["proposal"]["operations"].append(
            dict(value["proposal"]["operations"][0])
        ),
        lambda value: value["proposal"]["operations"][0]["parameters"].update(
            asset_id="https://example.invalid/video.mp4"
        ),
        lambda value: value["proposal"]["operations"][0]["parameters"].update(
            asset_id="C:\\private\\video.mp4"
        ),
    ],
    ids=[
        "unknown-schema",
        "unknown-kind",
        "missing-target",
        "stale-base",
        "duplicate-operation-id",
        "url-parameter",
        "absolute-path-parameter",
    ],
)
def test_invalid_or_unattested_envelopes_are_rejected(mutate) -> None:
    payload = json.loads(json.dumps(_envelope()))
    mutate(payload)

    with pytest.raises((ValidationError, ValueError)):
        _validate(payload)


def test_unsupported_control_mode_and_incompatible_media_are_rejected() -> None:
    unsupported = _context(
        supported_controls=({"kind": "broll", "mode": "read_only"},)
    )
    with pytest.raises(ValueError, match="unsupported"):
        _validate(_envelope(), unsupported)

    payload = _envelope()
    payload["proposal"]["operations"][0]["parameters"]["asset_id"] = "asset-bgm"
    with pytest.raises(ValueError, match="media"):
        _validate(payload)


def test_bounds_materialization_and_recursive_secret_values_are_rejected() -> None:
    payload = _envelope()
    payload["proposal"]["operations"] *= 17
    for index, operation in enumerate(payload["proposal"]["operations"]):
        operation["operation_id"] = f"operation-{index}"
    with pytest.raises(ValidationError):
        _validate(payload)

    caption = _envelope()
    caption["proposal"]["operations"] = [
        {
            "operation_id": "caption-1",
            "kind": "caption",
            "target": {
                "script_id": "script-1",
                "segment_id": "segment-1",
                "track_id": "caption-primary",
            },
            "parameters": {
                "action": "set_text",
                "text": {"nested": "api_key=should-never-appear"},
            },
            "requires_materialization": False,
            "preview_summary": "자막",
        }
    ]
    with pytest.raises((ValidationError, ValueError)):
        _validate(caption)

    materialization = _envelope()
    materialization["proposal"]["operations"][0]["requires_materialization"] = False
    with pytest.raises((ValidationError, ValueError), match="materialization"):
        _validate(materialization)


def test_utf8_id_bounds_and_token_shaped_parameter_values_are_rejected() -> None:
    oversized = _envelope()
    oversized["proposal"]["operations"][0]["parameters"]["asset_id"] = "가" * 100
    with pytest.raises((ValidationError, ValueError), match="asset_id"):
        _validate(oversized)

    token = _envelope()
    token["proposal"]["operations"] = [
        {
            "operation_id": "caption-1",
            "kind": "caption",
            "target": {
                "script_id": "script-1",
                "segment_id": "segment-1",
                "track_id": "caption-primary",
            },
            "parameters": {
                "action": "set_text",
                "text": "Bearer " + ("a" * 32),
            },
            "requires_materialization": False,
            "preview_summary": "자막",
        }
    ]
    with pytest.raises((ValidationError, ValueError), match="unsafe"):
        _validate(token)


@pytest.mark.parametrize(
    "unsafe_id",
    (
        "line\nbreak",
        "control\x01byte",
        "slash/value",
        "backslash\\value",
        "../traversal",
        "%2e%2e",
        "query?value",
        "fragment#value",
        "sk-" + ("a" * 32),
        "ghp_" + ("a" * 36),
        "AKIA" + ("A" * 16),
        "xoxb-1234567890-1234567890-secret",
        "AIza" + ("a" * 32),
        "hf_" + ("a" * 32),
    ),
)
@pytest.mark.parametrize("field", ("proposal_id", "operation_id"))
def test_model_ids_use_non_authorizing_safe_grammar(
    field: str, unsafe_id: str
) -> None:
    payload = _envelope()
    if field == "proposal_id":
        payload["proposal"]["proposal_id"] = unsafe_id
    else:
        payload["proposal"]["operations"][0]["operation_id"] = unsafe_id

    with pytest.raises((ValidationError, ValueError), match=field):
        _validate(payload)


@pytest.mark.parametrize(
    "unsafe_value",
    (
        "s3://bucket/private-object",
        "mailto:user@example.invalid",
        "data:text/plain,private",
        "\\\\server\\share\\private.txt",
        "//server/share/private.txt",
        "/etc/passwd",
        "D:\\private\\credential.txt",
        "-----BEGIN PRIVATE KEY-----\nnot-a-real-key",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature",
        "AKIA" + ("A" * 16),
        "ghp_" + ("a" * 36),
        "xoxb-1234567890-1234567890-secret",
        "sk-proj-" + ("a" * 32),
        "AIza" + ("a" * 32),
        "ya29." + ("a" * 32),
        "hf_" + ("a" * 32),
        "Bearer " + ("a" * 32),
        "authorization=" + ("a" * 32),
        "token:" + ("a" * 32),
        "password=" + ("a" * 32),
    ),
)
def test_recursive_parameter_values_reject_paths_uris_and_credentials(
    unsafe_value: str,
) -> None:
    payload = _envelope()
    operation = _operation("caption")
    operation["parameters"]["text"] = unsafe_value
    payload["proposal"]["operations"] = [operation]

    with pytest.raises((ValidationError, ValueError), match="unsafe"):
        _validate(payload)


@pytest.mark.parametrize("field", ("title", "rationale", "preview_summary"))
@pytest.mark.parametrize(
    "unsafe",
    (
        "See https://example.invalid/private for details",
        "use C:\\secret\\credential.txt for input",
        "embedded file://server/private.txt reference",
        "never print Bearer abcdefghijklmnop in prose",
    ),
)
def test_all_machine_only_descriptive_strings_reject_unsafe_values(
    field: str, unsafe: str
) -> None:
    payload = _envelope()
    if field == "preview_summary":
        payload["proposal"]["operations"][0][field] = unsafe
    else:
        payload["proposal"][field] = unsafe

    with pytest.raises((ValidationError, ValueError), match="unsafe"):
        _validate(payload)


@pytest.mark.parametrize("field", ("title", "rationale", "preview_summary"))
def test_machine_descriptors_preserve_harmless_policy_prose(field: str) -> None:
    payload = _envelope()
    harmless = "API keys must stay private; this candidate contains none."
    if field == "preview_summary":
        payload["proposal"]["operations"][0][field] = harmless
    else:
        payload["proposal"][field] = harmless

    _validate(payload)


@pytest.mark.parametrize(
    "pem_label",
    (
        "PRIVATE KEY",
        "RSA PRIVATE KEY",
        "EC PRIVATE KEY",
        "OPENSSH PRIVATE KEY",
        "DSA PRIVATE KEY",
        "ENCRYPTED PRIVATE KEY",
    ),
)
def test_all_private_key_pem_variants_are_rejected(pem_label: str) -> None:
    payload = _envelope()
    operation = _operation("caption")
    operation["parameters"]["text"] = (
        f"-----BEGIN {pem_label}-----\nnot-a-real-key"
    )
    payload["proposal"]["operations"] = [operation]

    with pytest.raises((ValidationError, ValueError), match="unsafe"):
        _validate(payload)


@pytest.mark.parametrize(
    ("kind", "field", "unsafe_value"),
    (
        ("broll", "asset_id", "s3://bucket/video"),
        ("bgm", "asset_id", "\\\\server\\share\\music.mp3"),
        ("sfx", "asset_id", "sk-" + ("a" * 32)),
        ("caption", "text", "password=" + ("a" * 32)),
        ("voice", "text", "Bearer " + ("a" * 32)),
        ("overlay", "text", "data:text/plain,private"),
        ("output_check", "check", "file://private/check"),
    ),
)
def test_each_operation_type_rejects_unattested_machine_values(
    kind: str, field: str, unsafe_value: str
) -> None:
    payload = _envelope()
    operation = _operation(kind)
    operation["parameters"][field] = unsafe_value
    payload["proposal"]["operations"] = [operation]

    with pytest.raises((ValidationError, ValueError)):
        _validate(payload)


@pytest.mark.parametrize(
    "text",
    (
        "Token economy is discussed in ordinary prose.",
        "Use strong password hygiene for the audience.",
        "Note: keep the opening bright and welcoming.",
        "C major: a bright opening cue.",
    ),
)
def test_ordinary_prose_is_not_misclassified_as_a_credential(text: str) -> None:
    payload = _envelope()
    operation = _operation("caption")
    operation["parameters"]["text"] = text
    payload["proposal"]["operations"] = [operation]

    assert _validate(payload).proposal is not None


@pytest.mark.parametrize(
    ("kind", "expected_track"),
    (
        ("broll", "video-primary"),
        ("bgm", "audio-bgm"),
        ("sfx", "audio-sfx"),
        ("caption", "caption-primary"),
        ("voice", "voice-primary"),
        ("overlay", "video-overlay"),
        ("output_check", "output-primary"),
    ),
)
def test_every_operation_kind_requires_its_exact_track(
    kind: str, expected_track: str
) -> None:
    missing = _envelope()
    missing_operation = _operation(kind)
    missing_operation["target"].pop("track_id")
    missing["proposal"]["operations"] = [missing_operation]
    with pytest.raises((ValidationError, ValueError), match="track"):
        _validate(missing)

    wrong = _envelope()
    wrong_operation = _operation(kind)
    wrong_operation["target"]["track_id"] = (
        "audio-bgm" if expected_track != "audio-bgm" else "video-primary"
    )
    wrong["proposal"]["operations"] = [wrong_operation]
    with pytest.raises((ValidationError, ValueError), match="track"):
        _validate(wrong)

    valid = _envelope()
    valid["proposal"]["operations"] = [_operation(kind)]
    assert _validate(valid).proposal is not None


@pytest.mark.parametrize(
    ("kind", "foreign_field", "foreign_value"),
    (
        ("broll", "script_id", "script-1"),
        ("bgm", "segment_id", "segment-1"),
        ("sfx", "script_id", "script-1"),
        ("caption", "media_id", "asset-video"),
        ("voice", "control_mode", "recommendation_only"),
        ("overlay", "script_id", "script-1"),
        ("output_check", "segment_id", "segment-1"),
    ),
)
def test_operation_targets_reject_cross_kind_identifier_smuggling(
    kind: str,
    foreign_field: str,
    foreign_value: str,
) -> None:
    payload = _envelope()
    operation = _operation(kind)
    operation["target"][foreign_field] = foreign_value
    payload["proposal"]["operations"] = [operation]

    with pytest.raises((ValidationError, ValueError), match=foreign_field):
        _validate(payload)
