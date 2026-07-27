from __future__ import annotations

from pathlib import Path

import pytest

from videobox_domain_models.yujin_creator_context import YujinCreatorContext


def _context(*, media_kind: str = "broll_video") -> YujinCreatorContext:
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
                    "asset_id": "asset-media",
                    "kind": media_kind,
                    "title": "추천 미디어",
                    "duration_sec": 12.0,
                    "tags": (),
                },
            ),
            "timeline_summary": {
                "duration_sec": 7.0,
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
    )


def _raw(context: YujinCreatorContext, *, kind: str, **parameter_changes: object) -> str:
    target = (
        {"track_id": "audio-bgm"}
        if kind == "bgm"
        else {
            "segment_id": "segment-1",
            "track_id": "video-primary" if kind == "broll" else "audio-sfx",
        }
    )
    parameters: dict[str, object] = {
        "asset_id": "asset-media",
        "start_sec": 2.0,
    }
    if kind == "broll":
        parameters.update(duration_sec=5.0, fit="contain")
    elif kind == "bgm":
        parameters.update(
            duration_sec=5.0,
            volume=0.6,
            fade_in_sec=0.5,
            fade_out_sec=0.75,
        )
    else:
        parameters.update(volume=0.4)
    parameters.update(parameter_changes)
    reply = "현재 장면에 맞는 미디어를 추천합니다."
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": reply,
        "proposal": {
            "proposal_id": "untrusted-provider-id",
            "base_revision": (
                f"session:{context.session_id}:revision:{context.session_revision}:"
                f"assets:{context.asset_index_revision}"
            ),
            "title": "장면 미디어 추천",
            "rationale": "현재 장면의 의미를 보강합니다.",
            "operations": (
                {
                    "operation_id": f"operation-{kind}",
                    "kind": kind,
                    "target": target,
                    "parameters": parameters,
                    "requires_materialization": True,
                    "preview_summary": f"{kind} 추천 세부 내용",
                },
            ),
        },
    }
    import json

    return (
        f"{reply}\n```videobox-yujin-response\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n```"
    )


class _Store:
    def __init__(
        self,
        root: Path,
        *,
        asset_type: str,
        metadata: dict[str, object] | None = None,
        created_at: str = "media-r1",
        asset_revision: int = 3,
        analysis_ok: bool = True,
    ) -> None:
        self.path = root / "media.bin"
        self.path.write_bytes(b"current-media-bytes")
        self.asset_type = asset_type
        self.metadata = metadata or {}
        self.created_at = created_at
        self.asset_revision = asset_revision
        self.analysis_ok = analysis_ok
        self.external_calls = 0

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict:
        return {
            "project_id": project_id,
            "session_id": session_id,
            "session_revision": 7,
        }

    def get_asset_index_revision(self, project_id: str) -> int:
        return self.asset_revision

    def get_asset(self, *, project_id: str, asset_id: str) -> dict:
        if asset_id != "asset-media":
            raise KeyError(asset_id)
        return {
            "project_id": project_id,
            "asset_id": asset_id,
            "asset_type": self.asset_type,
            "storage_uri": "storage://media",
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    def resolve_storage_uri(self, *, project_id: str, storage_uri: str) -> Path:
        return self.path

    def list_media_analysis(self, *, project_id: str) -> list[dict[str, object]]:
        return [
            {
                "analysis_id": "analysis-1",
                "asset_id": "asset-media",
                "status": "succeeded",
                "result": {"objects": ["dog"]} if self.analysis_ok else None,
            }
        ]

    def can_apply_media_analysis(self, *, project_id: str, analysis_id: str) -> bool:
        return self.analysis_ok


def _activate(store: _Store, context: YujinCreatorContext, *, kind: str, **changes: object):
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        activate_yujin_media_projection,
        parse_and_project_yujin_creator_output,
    )

    projection = parse_and_project_yujin_creator_output(
        _raw(context, kind=kind, **changes),
        context,
        trusted_project_id=context.project_id,
        trusted_run_id=f"run-{kind}",
    )
    return activate_yujin_media_projection(
        store=store,
        project_id=context.project_id,
        context=context,
        projection=projection,
    )


@pytest.mark.parametrize(
    ("kind", "media_kind", "asset_type", "expected_controls"),
    (
        ("broll", "raw_video", "raw_video", {"fit": "fit"}),
        ("broll", "broll_video", "broll_video", {"fit": "fit"}),
        (
            "bgm",
            "bgm",
            "bgm",
            {
                "volume": 0.6,
                "fade_in_sec": 0.5,
                "fade_out_sec": 0.75,
            },
        ),
        ("sfx", "sfx", "sfx", {"volume": 0.4}),
    ),
)
def test_fresh_attestation_activates_exact_aligned_media(
    tmp_path: Path,
    kind: str,
    media_kind: str,
    asset_type: str,
    expected_controls: dict[str, object],
) -> None:
    metadata = (
        {"canonical_metadata_indexed": True, "mood": "calm", "energy": "low", "genre": "ambient", "recommended_use": "intro"}
        if kind == "bgm"
        else {"canonical_metadata_indexed": True, "action_event": "step", "intensity": "low", "recommended_use": "scene"}
        if kind == "sfx"
        else {}
    )
    context = _context(media_kind=media_kind)
    activated = _activate(
        _Store(tmp_path, asset_type=asset_type, metadata=metadata),
        context,
        kind=kind,
    )

    assert activated.proposal is not None
    assert activated.proposal.status == "ready"
    candidate = activated.proposal.candidates[0]
    assert candidate.availability == "actionable"
    assert candidate.review_status == "approved"
    assert candidate.expected_content_sha256 is not None
    assert candidate.media_revision == "media-r1"
    assert dict(candidate.controls) == expected_controls
    assert candidate.canonical_metadata["source_media_kind"] == media_kind
    assert candidate.canonical_metadata["target_segment_id"] == "segment-1"
    assert candidate.canonical_metadata["preview_summary"] == f"{kind} 추천 세부 내용"
    assert candidate.canonical_metadata["yujin_actionable_media"] is True


@pytest.mark.parametrize(
    ("media_kind", "asset_type"),
    (
        ("image", "image"),
        ("broll_video", "image"),
        ("bgm", "sfx"),
        ("sfx", "bgm"),
    ),
)
def test_image_and_wrong_real_media_kinds_remain_non_actionable(
    tmp_path: Path,
    media_kind: str,
    asset_type: str,
) -> None:
    kind = "broll" if media_kind in {"image", "broll_video"} else media_kind
    context = _context(media_kind=media_kind)
    activated = _activate(
        _Store(tmp_path, asset_type=asset_type),
        context,
        kind=kind,
    )

    assert activated.proposal is not None
    assert activated.proposal.status == "candidate_only"
    assert activated.proposal.candidates[0].availability == "candidate_only"


@pytest.mark.parametrize(
    ("store_changes", "parameter_changes"),
    (
        ({"created_at": ""}, {}),
        ({"asset_revision": 4}, {}),
        ({"analysis_ok": False}, {}),
        ({}, {"start_sec": 2.1}),
        ({}, {"duration_sec": 4.9}),
    ),
)
def test_bad_revision_analysis_index_or_alignment_never_activates(
    tmp_path: Path,
    store_changes: dict[str, object],
    parameter_changes: dict[str, object],
) -> None:
    context = _context()
    activated = _activate(
        _Store(tmp_path, asset_type="broll_video", **store_changes),
        context,
        kind="broll",
        **parameter_changes,
    )

    assert activated.proposal is not None
    assert activated.proposal.status == "candidate_only"
    assert activated.proposal.candidates[0].availability == "candidate_only"


def test_missing_asset_bad_bytes_and_unindexed_audio_never_activate(
    tmp_path: Path,
) -> None:
    context = _context(media_kind="bgm")
    store = _Store(tmp_path, asset_type="bgm")
    store.path.unlink()
    missing = _activate(store, context, kind="bgm")
    assert missing.proposal is not None
    assert missing.proposal.status == "candidate_only"

    store = _Store(tmp_path, asset_type="bgm")
    unindexed = _activate(store, context, kind="bgm")
    assert unindexed.proposal is not None
    assert unindexed.proposal.status == "candidate_only"


def test_content_sha_change_during_attestation_never_activates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import videobox_core_engine.yujin_creator_proposal_adapter as adapter

    context = _context()
    digests = iter(("a" * 64, "b" * 64))
    monkeypatch.setattr(adapter, "sha256_file", lambda _path: next(digests))

    activated = _activate(
        _Store(tmp_path, asset_type="broll_video"),
        context,
        kind="broll",
    )

    assert activated.proposal is not None
    assert activated.proposal.status == "candidate_only"
    assert activated.proposal.candidates[0].availability == "candidate_only"


@pytest.mark.parametrize(
    ("kind", "media_kind", "asset_type", "parameter_changes"),
    (
        ("bgm", "bgm", "bgm", {"start_sec": 2.1}),
        ("bgm", "bgm", "bgm", {"duration_sec": 4.9}),
        ("sfx", "sfx", "sfx", {"start_sec": 2.1}),
    ),
)
def test_audio_requires_exact_segment_alignment(
    tmp_path: Path,
    kind: str,
    media_kind: str,
    asset_type: str,
    parameter_changes: dict[str, object],
) -> None:
    metadata = (
        {
            "canonical_metadata_indexed": True,
            "mood": "calm",
            "energy": "low",
            "genre": "ambient",
            "recommended_use": "intro",
        }
        if kind == "bgm"
        else {
            "canonical_metadata_indexed": True,
            "action_event": "step",
            "intensity": "low",
            "recommended_use": "scene",
        }
    )
    context = _context(media_kind=media_kind)

    activated = _activate(
        _Store(tmp_path, asset_type=asset_type, metadata=metadata),
        context,
        kind=kind,
        **parameter_changes,
    )

    assert activated.proposal is not None
    assert activated.proposal.status == "candidate_only"
    assert activated.proposal.candidates[0].availability == "candidate_only"


def test_bgm_with_ambiguous_segment_start_never_activates(tmp_path: Path) -> None:
    base = _context(media_kind="bgm")
    ambiguous = base.segment_summaries[0].model_copy(
        update={
            "segment_id": "segment-ambiguous",
            "text": "같은 시작점의 다른 장면",
        }
    )
    context = base.model_copy(
        update={"segment_summaries": (*base.segment_summaries, ambiguous)}
    )
    store = _Store(
        tmp_path,
        asset_type="bgm",
        metadata={
            "canonical_metadata_indexed": True,
            "mood": "calm",
            "energy": "low",
            "genre": "ambient",
            "recommended_use": "intro",
        },
    )

    activated = _activate(store, context, kind="bgm")

    assert activated.proposal is not None
    assert activated.proposal.status == "candidate_only"
    assert activated.proposal.candidates[0].availability == "candidate_only"


def test_mixed_media_keeps_deferred_candidate_but_only_media_is_actionable(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from videobox_core_engine.yujin_creator_proposal_adapter import (
        activate_yujin_media_projection,
        parse_and_project_yujin_creator_output,
    )

    context = _context()
    projection = parse_and_project_yujin_creator_output(
        _raw(context, kind="broll"),
        context,
        trusted_project_id=context.project_id,
        trusted_run_id="run-mixed",
    )
    assert projection.proposal is not None
    deferred = replace(
        projection.proposal.candidates[0],
        candidate_id="deferred-b4",
        media_type="caption",
        asset_id="deferred-b4",
        expected_content_sha256=None,
    )
    projection = replace(
        projection,
        proposal=replace(
            projection.proposal,
            candidates=(*projection.proposal.candidates, deferred),
        ),
    )
    store = _Store(tmp_path, asset_type="broll_video")

    activated = activate_yujin_media_projection(
        store=store,
        project_id=context.project_id,
        context=context,
        projection=projection,
    )

    assert activated.proposal is not None
    assert activated.proposal.status == "ready"
    assert [item.availability for item in activated.proposal.candidates] == [
        "actionable",
        "candidate_only",
    ]
    assert store.external_calls == 0
