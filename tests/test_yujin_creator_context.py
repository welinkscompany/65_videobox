from __future__ import annotations

from copy import deepcopy
import json
import socket

import pytest
from pydantic import ValidationError

from videobox_core_engine.yujin_creator_context import (
    MAX_CONTEXT_BYTES,
    YujinCreatorContextError,
    build_yujin_creator_context,
    canonical_creator_context_json,
)
from videobox_domain_models.yujin_creator_context import YujinCreatorContext
from videobox_domain_models.yujin_creator_context import (
    MediaCandidateSummary,
    SegmentSummary,
)


def _session(*, revision: int = 7) -> dict[str, object]:
    return {
        "project_id": "project-a",
        "session_id": "session-a",
        "session_revision": revision,
        "timeline_id": "timeline-a",
        "script_asset_id": "script-a",
        "segments": [
            {
                "segment_id": f"segment-{index:02d}",
                "start_sec": float(40 - index),
                "end_sec": float(41 - index),
                "caption_text": "가" * 400,
            }
            for index in range(40)
        ],
    }


def _timeline() -> dict[str, object]:
    return {
        "project_id": "project-a",
        "timeline_id": "timeline-a",
        "version": "v009",
    }


def _asset(index: int) -> dict[str, object]:
    return {
        "project_id": "project-a",
        "asset_id": f"asset-{60 - index:02d}",
        "asset_type": "broll_video" if index % 2 else "image",
        "storage_uri": f"project://private/{index}.mp4",
        "mime_type": "video/mp4",
        "duration_sec": float(index + 1),
        "metadata": {
            "title": "나" * 200,
            "tags": ["태그" * 100 for _ in range(10)],
            "path": f"C:/private/{index}.mp4",
            "url": f"https://invalid.test/{index}",
            "credentials": "never-copy",
        },
    }


def _manifest(*, status: str = "current") -> dict[str, object]:
    return {
        "project_id": "project-a",
        "session_id": "session-a",
        "session_revision": 7,
        "timeline_id": "timeline-a",
        "timeline_version": "v009",
        "output": {"duration_sec": 41.0},
        "tracks": [
            {"track_id": "track-b", "clips": [{}, {}]},
            {"track_id": "track-a", "clips": [{}]},
        ],
        "gap_slots": [{}, {}],
        "source_status": {
            "status": status,
            "source_session_id": "session-a",
            "source_session_revision": 7,
        },
        "audition": {"asset_urls": {"secret": "https://invalid.test/private"}},
    }


class _Store:
    def __init__(
        self,
        *,
        sessions: list[dict[str, object]] | None = None,
        asset_revisions: list[int] | None = None,
    ) -> None:
        self.sessions = sessions or [_session(), _session()]
        self.asset_revisions = asset_revisions or [13, 13]
        self.session_reads = 0
        self.asset_revision_reads = 0
        self.list_asset_calls = 0

    def get_project(self, *, project_id: str) -> dict[str, object]:
        assert project_id == "project-a"
        return {
            "project_id": project_id,
            "name": "private project name",
            "root_storage_uri": "project://private",
        }

    def get_editing_session(
        self, *, project_id: str, session_id: str
    ) -> dict[str, object]:
        assert (project_id, session_id) == ("project-a", "session-a")
        item = self.sessions[min(self.session_reads, len(self.sessions) - 1)]
        self.session_reads += 1
        return deepcopy(item)

    def get_asset_index_revision(self, project_id: str) -> int:
        assert project_id == "project-a"
        item = self.asset_revisions[
            min(self.asset_revision_reads, len(self.asset_revisions) - 1)
        ]
        self.asset_revision_reads += 1
        return item

    def get_timeline_run(
        self, *, project_id: str, timeline_id: str
    ) -> dict[str, object]:
        assert (project_id, timeline_id) == ("project-a", "timeline-a")
        return _timeline()

    def list_assets(self, *, project_id: str) -> list[dict[str, object]]:
        assert project_id == "project-a"
        self.list_asset_calls += 1
        return [_asset(index) for index in range(60)]


class _Playback:
    def __init__(self, manifest: dict[str, object] | None = None) -> None:
        self.manifest = manifest or _manifest()
        self.calls = 0

    def __call__(self, **kwargs: object) -> dict[str, object]:
        self.calls += 1
        assert kwargs["project_id"] == "project-a"
        assert kwargs["asset_content_url_prefix"] == ""
        assert kwargs["session"]["session_id"] == "session-a"  # type: ignore[index]
        assert kwargs["timeline"]["timeline_id"] == "timeline-a"  # type: ignore[index]
        return deepcopy(self.manifest)


def _build(
    *,
    store: _Store | None = None,
    playback: _Playback | None = None,
    expected_revision: int = 7,
    selected_segment_id: str | None = "segment-03",
) -> YujinCreatorContext:
    return build_yujin_creator_context(
        store=store or _Store(),
        project_id="project-a",
        session_id="session-a",
        expected_session_revision=expected_revision,
        selected_segment_id=selected_segment_id,
        playback_builder=playback or _Playback(),
    )


def test_strict_nested_dto_rejects_unknown_fields_and_revision_strings() -> None:
    context = _build()
    payload = context.model_dump(mode="json")

    for path, field in [
        ((), "storage_uri"),
        (("segment_summaries", 0), "path"),
        (("media_candidates", 0), "url"),
        (("timeline_summary",), "metadata"),
        (("supported_controls", 0), "ticket"),
    ]:
        invalid = deepcopy(payload)
        target: object = invalid
        for part in path:
            target = target[part]  # type: ignore[index]
        target[field] = "forbidden"  # type: ignore[index]
        with pytest.raises(ValidationError):
            YujinCreatorContext.model_validate(invalid)

    payload["session_revision"] = "7"
    with pytest.raises(ValidationError):
        YujinCreatorContext.model_validate(payload)
    assert context.schema_version == "videobox.yujin-context.v1"

    with pytest.raises(ValidationError):
        SegmentSummary(
            segment_id="segment-a",
            start_sec=0.0,
            end_sec=1.0,
            text="가" * 86,
        )
    with pytest.raises(ValidationError):
        MediaCandidateSummary(
            asset_id="asset-a",
            kind="broll_video",
            title="가" * 43,
            duration_sec=1.0,
            tags=(),
        )
    with pytest.raises(ValidationError):
        MediaCandidateSummary(
            asset_id="asset-a",
            kind="broll_video",
            title="safe",
            duration_sec=1.0,
            tags=("가" * 22,),
        )


def test_builder_is_bounded_deterministic_and_contains_only_allowlisted_scalars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_calls = 0

    def reject_network(*_args: object, **_kwargs: object) -> None:
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("creator context must remain offline")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    store = _Store()
    first = _build(store=store)
    second = _build(store=_Store())

    assert first == second
    assert first.session_revision == 7
    assert first.asset_index_revision == 13
    assert first.timeline_id == "timeline-a"
    assert first.timeline_version == "v009"
    assert first.selected_script_id == "script-a"
    assert first.selected_segment_id == "segment-03"
    assert len(first.segment_summaries) == 32
    assert len(first.media_candidates) <= 48
    assert first.selected_segment_id in {
        item.segment_id for item in first.segment_summaries
    }
    assert [item.segment_id for item in first.segment_summaries] == sorted(
        (item.segment_id for item in first.segment_summaries),
        key=lambda segment_id: (
            next(
                item.start_sec
                for item in first.segment_summaries
                if item.segment_id == segment_id
            ),
            segment_id,
        ),
    )
    assert [item.asset_id for item in first.media_candidates] == sorted(
        (item.asset_id for item in first.media_candidates),
        key=lambda asset_id: (
            next(
                item.kind
                for item in first.media_candidates
                if item.asset_id == asset_id
            ),
            asset_id,
        ),
    )
    assert [item.kind for item in first.supported_controls] == sorted(
        item.kind for item in first.supported_controls
    )
    assert all(
        len(item.text.encode("utf-8")) <= 256 for item in first.segment_summaries
    )
    assert all(
        len(item.title.encode("utf-8")) <= 128
        and len(item.tags) <= 8
        and all(len(tag.encode("utf-8")) <= 64 for tag in item.tags)
        for item in first.media_candidates
    )
    canonical = canonical_creator_context_json(first)
    assert len(canonical.encode("utf-8")) <= MAX_CONTEXT_BYTES
    forbidden = (
        "storage_uri",
        "asset_uri",
        "https://",
        "C:/",
        "credentials",
        "OAuth",
        "Mem0",
        "ticket",
    )
    assert all(item not in canonical for item in forbidden)
    assert first.timeline_summary.duration_sec == 41.0
    assert first.timeline_summary.track_count == 2
    assert first.timeline_summary.clip_count == 3
    assert first.timeline_summary.gap_count == 2
    assert store.list_asset_calls == 1
    assert network_calls == 0
    json.loads(canonical)


@pytest.mark.parametrize(
    ("store", "playback", "expected_revision", "selected_segment_id", "code", "prompt_calls"),
    [
        (_Store(), _Playback(), 6, None, "creator_context_session_revision_mismatch", 0),
        (_Store(), _Playback(), 7, "missing", "creator_context_segment_mismatch", 0),
        (
            _Store(),
            _Playback(_manifest(status="stale")),
            7,
            None,
            "creator_context_playback_stale",
            1,
        ),
        (
            _Store(sessions=[_session(revision=7), _session(revision=8)]),
            _Playback(),
            7,
            None,
            "creator_context_snapshot_changed",
            1,
        ),
        (
            _Store(asset_revisions=[13, 14]),
            _Playback(),
            7,
            None,
            "creator_context_snapshot_changed",
            1,
        ),
    ],
)
def test_stale_selection_playback_and_toctou_fail_closed(
    store: _Store,
    playback: _Playback,
    expected_revision: int,
    selected_segment_id: str | None,
    code: str,
    prompt_calls: int,
) -> None:
    with pytest.raises(YujinCreatorContextError, match=f"^{code}$"):
        _build(
            store=store,
            playback=playback,
            expected_revision=expected_revision,
            selected_segment_id=selected_segment_id,
        )
    assert playback.calls == prompt_calls


def test_context_exposes_only_exact_approved_tts_and_fences_review_race(
    tmp_path,
) -> None:
    class TtsStore(_Store):
        def __init__(self, *, change_review: bool = False) -> None:
            super().__init__()
            self.path = tmp_path / (
                "changed-review.bin" if change_review else "approved.bin"
            )
            self.path.write_bytes(b"approved-tts")
            self.change_review = change_review
            self.tts_reads = 0

        def list_assets(self, *, project_id: str) -> list[dict[str, object]]:
            return [
                {
                    "project_id": project_id,
                    "asset_id": "asset-tts",
                    "asset_type": "generated_tts_audio",
                    "storage_uri": "storage://approved-tts",
                    "created_at": "tts-r1",
                    "duration_sec": 1.0,
                    "metadata": {"title": "승인 음성"},
                }
            ]

        def list_tts_candidates(
            self, *, project_id: str, segment_id: str
        ) -> list[dict[str, object]]:
            if segment_id != "segment-00":
                return []
            self.tts_reads += 1
            return [
                {
                    "candidate_id": "tts_candidate_001",
                    "project_id": project_id,
                    "segment_id": segment_id,
                    "asset_id": "asset-tts",
                    "source_text": "승인한 음성",
                    "technical_status": "accepted",
                    "operator_review_status": (
                        "rejected"
                        if self.change_review and self.tts_reads > 1
                        else "approved"
                    ),
                }
            ]

        def resolve_storage_uri(self, *, project_id: str, storage_uri: str):
            return self.path

    context = build_yujin_creator_context(
        store=TtsStore(),
        project_id="project-a",
        session_id="session-a",
        expected_session_revision=7,
        selected_segment_id="segment-00",
        playback_builder=_Playback(),
    )

    assert len(context.approved_tts_candidates) == 1
    approved = context.approved_tts_candidates[0]
    assert approved.candidate_id == "tts_candidate_001"
    assert approved.asset_id == "asset-tts"
    assert approved.segment_id == "segment-00"
    assert approved.technical_status == "accepted"
    assert approved.operator_review_status == "approved"
    assert approved.asset_revision == "tts-r1"
    assert len(approved.expected_content_sha256) == 64

    with pytest.raises(
        YujinCreatorContextError,
        match="^creator_context_snapshot_changed$",
    ):
        build_yujin_creator_context(
            store=TtsStore(change_review=True),
            project_id="project-a",
            session_id="session-a",
            expected_session_revision=7,
            selected_segment_id="segment-00",
            playback_builder=_Playback(),
        )


def test_playback_identity_must_match_exact_session_and_revision() -> None:
    for patch in (
        {"session_id": "other"},
        {"session_revision": 8},
        {"timeline_id": "other"},
        {"timeline_version": "other"},
        {
            "source_status": {
                "status": "current",
                "source_session_id": "other",
                "source_session_revision": 7,
            }
        },
    ):
        manifest = _manifest()
        manifest.update(patch)
        with pytest.raises(
            YujinCreatorContextError, match="^creator_context_playback_stale$"
        ):
            _build(playback=_Playback(manifest), selected_segment_id=None)


@pytest.mark.parametrize("field", ["session_revision", "asset_index_revision"])
def test_context_rejects_non_finite_revision(field: str) -> None:
    payload = _build().model_dump(mode="python")
    payload[field] = float("inf")
    with pytest.raises(ValidationError):
        YujinCreatorContext.model_validate(payload)
