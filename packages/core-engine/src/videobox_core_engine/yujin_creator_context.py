"""Build one bounded, current-revision creator context from local project data."""

from __future__ import annotations

from collections.abc import Callable
import json
from math import isfinite
from typing import Any

from videobox_core_engine.editor_playback_manifest import (
    build_editor_playback_manifest,
)
from videobox_domain_models.yujin_creator_context import (
    ApprovedTtsCandidateSummary,
    MediaCandidateSummary,
    SegmentSummary,
    SupportedControl,
    TimelineSummary,
    UserApprovedPreference,
    YujinCreatorContext,
)


MAX_CONTEXT_BYTES = 48_000
MAX_SEGMENTS = 32
MAX_MEDIA_CANDIDATES = 48
MAX_SEGMENT_TEXT_BYTES = 256
MAX_MEDIA_TITLE_BYTES = 128
MAX_TAGS = 8
MAX_TAG_BYTES = 64

_ASSET_KINDS = frozenset(
    {
        "narration_audio",
        "raw_video",
        "broll_video",
        "image",
        "bgm",
        "sfx",
        "script_document",
        "voice_sample_audio",
        "generated_tts_audio",
    }
)
_BASE_CONTROLS = (
    SupportedControl(kind="bgm", mode="recommendation_only"),
    SupportedControl(kind="broll", mode="recommendation_only"),
    SupportedControl(kind="caption", mode="recommendation_only"),
    SupportedControl(kind="output_check", mode="read_only"),
    SupportedControl(kind="overlay", mode="recommendation_only"),
    SupportedControl(kind="sfx", mode="recommendation_only"),
    SupportedControl(kind="voice", mode="recommendation_only"),
)


class YujinCreatorContextError(ValueError):
    """A safe deterministic creator-context fence failure."""


def canonical_creator_context_json(context: YujinCreatorContext) -> str:
    return json.dumps(
        context.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def build_yujin_creator_context(
    *,
    store: object,
    project_id: str,
    session_id: str,
    expected_session_revision: int,
    selected_segment_id: str | None = None,
    current_surface: str = "edit",
    selected_variant_id: str | None = None,
    playback_builder: Callable[..., dict[str, Any]] = build_editor_playback_manifest,
) -> YujinCreatorContext:
    """Read a project-scoped snapshot and return only allowlisted scalar data."""

    store.get_project(project_id=project_id)  # type: ignore[attr-defined]
    session_before = store.get_editing_session(  # type: ignore[attr-defined]
        project_id=project_id,
        session_id=session_id,
    )
    session_revision = _positive_revision(session_before.get("session_revision"))
    if session_revision != expected_session_revision:
        raise YujinCreatorContextError(
            "creator_context_session_revision_mismatch"
        )
    if (
        str(session_before.get("project_id") or "") != project_id
        or str(session_before.get("session_id") or "") != session_id
    ):
        raise YujinCreatorContextError("creator_context_session_identity_mismatch")

    raw_segments = [
        item
        for item in session_before.get("segments", [])
        if isinstance(item, dict) and str(item.get("segment_id") or "").strip()
    ]
    segment_ids = {str(item["segment_id"]) for item in raw_segments}
    normalized_selection = (
        str(selected_segment_id).strip() if selected_segment_id is not None else None
    )
    if normalized_selection == "":
        normalized_selection = None
    if normalized_selection is not None and normalized_selection not in segment_ids:
        raise YujinCreatorContextError("creator_context_segment_mismatch")

    asset_revision_before = int(  # type: ignore[attr-defined]
        store.get_asset_index_revision(project_id)
    )
    timeline_id = str(session_before.get("timeline_id") or "")
    if not timeline_id:
        raise YujinCreatorContextError("creator_context_timeline_identity_mismatch")
    timeline = store.get_timeline_run(  # type: ignore[attr-defined]
        project_id=project_id,
        timeline_id=timeline_id,
    )
    if (
        str(timeline.get("project_id") or "") != project_id
        or str(timeline.get("timeline_id") or "") != timeline_id
    ):
        raise YujinCreatorContextError("creator_context_timeline_identity_mismatch")

    manifest = playback_builder(
        project_id=project_id,
        session=session_before,
        timeline=timeline,
        asset_content_url_prefix="",
    )
    _validate_current_playback(
        manifest=manifest,
        project_id=project_id,
        session_id=session_id,
        session_revision=session_revision,
        timeline_id=timeline_id,
        timeline_version=str(timeline.get("version") or "v001"),
    )
    assets = store.list_assets(project_id=project_id)  # type: ignore[attr-defined]
    approved_tts_before = _approved_tts_candidates(
        store=store,
        project_id=project_id,
        segment_ids=segment_ids,
        assets=assets,
    )

    session_after = store.get_editing_session(  # type: ignore[attr-defined]
        project_id=project_id,
        session_id=session_id,
    )
    asset_revision_after = int(  # type: ignore[attr-defined]
        store.get_asset_index_revision(project_id)
    )
    approved_tts_after = _approved_tts_candidates(
        store=store,
        project_id=project_id,
        segment_ids=segment_ids,
        assets=assets,
    )
    variant: dict[str, Any] | None = None
    if selected_variant_id is not None:
        try:
            variant = store.get_output_variant(  # type: ignore[attr-defined]
                project_id=project_id,
                variant_id=selected_variant_id,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            raise YujinCreatorContextError("creator_context_variant_not_current") from None
        if (
            str(variant.get("project_id") or "") != project_id
            or str(variant.get("source_session_id") or "") != session_id
            or int(variant.get("source_session_revision") or 0) != session_revision
        ):
            raise YujinCreatorContextError("creator_context_variant_not_current")
    if (
        _positive_revision(session_after.get("session_revision"))
        != session_revision
        or str(session_after.get("session_id") or "") != session_id
        or str(session_after.get("timeline_id") or "") != timeline_id
        or asset_revision_after != asset_revision_before
        or approved_tts_after != approved_tts_before
    ):
        raise YujinCreatorContextError("creator_context_snapshot_changed")

    segments = tuple(
        SegmentSummary(
            segment_id=str(item["segment_id"]),
            start_sec=_nonnegative_float(item.get("start_sec")),
            end_sec=_nonnegative_float(item.get("end_sec")),
            text=_truncate_utf8(
                str(item.get("caption_text") or item.get("text") or ""),
                MAX_SEGMENT_TEXT_BYTES,
            ),
        )
        for item in _bounded_segments(
            raw_segments,
            selected_segment_id=normalized_selection,
        )
    )
    candidates = tuple(
        candidate
        for candidate in (
            _media_candidate(item, project_id=project_id)
            for item in sorted(
                (item for item in assets if isinstance(item, dict)),
                key=lambda item: (
                    str(item.get("asset_type") or ""),
                    str(item.get("asset_id") or ""),
                ),
            )
        )
        if candidate is not None
    )[:MAX_MEDIA_CANDIDATES]
    timeline_summary = _timeline_summary(manifest)
    context = YujinCreatorContext(
        schema_version="videobox.yujin-context.v1",
        project_id=project_id,
        session_id=session_id,
        session_revision=session_revision,
        asset_index_revision=asset_revision_before,
        timeline_id=timeline_id,
        timeline_version=str(manifest["timeline_version"]),
        selected_script_id=(
            str(session_before["script_asset_id"])
            if session_before.get("script_asset_id")
            else None
        ),
        selected_segment_id=normalized_selection,
        segment_summaries=segments,
        media_candidates=candidates,
        approved_tts_candidates=approved_tts_before,
        timeline_summary=timeline_summary,
        supported_controls=(
            _BASE_CONTROLS
            + (SupportedControl(kind="output_variant", mode="recommendation_only"),)
            if variant is not None
            else _BASE_CONTROLS
        ),
        current_surface=current_surface,  # type: ignore[arg-type]
        selection_kind="variant" if variant is not None else ("segment" if normalized_selection is not None else "none"),
        master_session_id=session_id,
        master_session_revision=session_revision,
        variant_id=str(variant["variant_id"]) if variant is not None else None,
        variant_kind=str(variant["kind"]) if variant is not None else None,  # type: ignore[arg-type]
        variant_revision=int(variant["variant_revision"]) if variant is not None else None,
    )
    return _fit_context(context)


def _fit_context(context: YujinCreatorContext) -> YujinCreatorContext:
    memories = context.memories
    segments = context.segment_summaries
    candidates = context.media_candidates
    approved_tts = context.approved_tts_candidates
    while len(canonical_creator_context_json(context).encode("utf-8")) > MAX_CONTEXT_BYTES:
        if memories:
            memories = ()
        elif candidates:
            candidates = candidates[:-1]
        elif approved_tts:
            approved_tts = approved_tts[:-1]
        elif segments:
            segments = segments[:-1]
        else:
            raise YujinCreatorContextError("creator_context_size_limit")
        context = context.model_copy(
            update={
                "memories": memories,
                "segment_summaries": segments,
                "media_candidates": candidates,
                "approved_tts_candidates": approved_tts,
            }
        )
    return context


def attach_yujin_memories(
    context: YujinCreatorContext,
    memories: tuple[UserApprovedPreference, ...],
) -> YujinCreatorContext:
    """Attach bounded advisory memory and drop it before creator data if needed."""

    return _fit_context(context.model_copy(update={"memories": memories}))


def _bounded_segments(
    segments: list[dict[str, Any]],
    *,
    selected_segment_id: str | None,
) -> tuple[dict[str, Any], ...]:
    key = lambda item: (  # noqa: E731 - shared deterministic ordering key
        _nonnegative_float(item.get("start_sec")),
        str(item["segment_id"]),
    )
    ordered = sorted(segments, key=key)
    bounded = ordered[:MAX_SEGMENTS]
    if (
        selected_segment_id is not None
        and all(str(item["segment_id"]) != selected_segment_id for item in bounded)
    ):
        selected = next(
            item
            for item in ordered
            if str(item["segment_id"]) == selected_segment_id
        )
        bounded[-1] = selected
        bounded.sort(key=key)
    return tuple(bounded)


def _validate_current_playback(
    *,
    manifest: dict[str, Any],
    project_id: str,
    session_id: str,
    session_revision: int,
    timeline_id: str,
    timeline_version: str,
) -> None:
    source = manifest.get("source_status")
    if not isinstance(source, dict):
        raise YujinCreatorContextError("creator_context_playback_stale")
    if (
        str(manifest.get("project_id") or "") != project_id
        or str(manifest.get("session_id") or "") != session_id
        or int(manifest.get("session_revision") or 0) != session_revision
        or str(manifest.get("timeline_id") or "") != timeline_id
        or str(manifest.get("timeline_version") or "") != timeline_version
        or source.get("status") != "current"
        or str(source.get("source_session_id") or "") != session_id
        or int(source.get("source_session_revision") or 0) != session_revision
    ):
        raise YujinCreatorContextError("creator_context_playback_stale")


def _media_candidate(
    item: dict[str, Any], *, project_id: str
) -> MediaCandidateSummary | None:
    kind = str(item.get("asset_type") or "")
    asset_id = str(item.get("asset_id") or "").strip()
    if (
        str(item.get("project_id") or "") != project_id
        or not asset_id
        or kind not in _ASSET_KINDS
    ):
        return None
    metadata = item.get("metadata")
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    raw_tags = safe_metadata.get("tags")
    tags = tuple(
        _truncate_utf8(str(tag), MAX_TAG_BYTES)
        for tag in (raw_tags if isinstance(raw_tags, (list, tuple)) else ())
        if str(tag).strip()
    )[:MAX_TAGS]
    raw_duration = item.get("duration_sec")
    duration = (
        _nonnegative_float(raw_duration) if raw_duration is not None else None
    )
    return MediaCandidateSummary(
        asset_id=asset_id,
        kind=kind,  # type: ignore[arg-type]
        title=_truncate_utf8(
            str(safe_metadata.get("title") or asset_id),
            MAX_MEDIA_TITLE_BYTES,
        ),
        duration_sec=duration,
        tags=tags,
    )


def _approved_tts_candidates(
    *,
    store: object,
    project_id: str,
    segment_ids: set[str],
    assets: list[dict[str, Any]],
) -> tuple[ApprovedTtsCandidateSummary, ...]:
    list_candidates = getattr(store, "list_tts_candidates", None)
    resolve_storage_uri = getattr(store, "resolve_storage_uri", None)
    if not callable(list_candidates) or not callable(resolve_storage_uri):
        return ()
    assets_by_id = {
        str(item.get("asset_id") or ""): item
        for item in assets
        if isinstance(item, dict)
        and str(item.get("project_id") or "") == project_id
    }
    result: list[ApprovedTtsCandidateSummary] = []
    for segment_id in sorted(segment_ids):
        try:
            candidates = list_candidates(
                project_id=project_id,
                segment_id=segment_id,
            )
        except (KeyError, OSError, TypeError, ValueError):
            continue
        for item in candidates:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "")
            asset_id = str(item.get("asset_id") or "")
            asset = assets_by_id.get(asset_id)
            if (
                not candidate_id.startswith("tts_candidate_")
                or str(item.get("project_id") or "") != project_id
                or str(item.get("segment_id") or "") != segment_id
                or item.get("technical_status") != "accepted"
                or item.get("operator_review_status") != "approved"
                or not isinstance(asset, dict)
                or str(asset.get("asset_type") or "") != "generated_tts_audio"
            ):
                continue
            try:
                source = resolve_storage_uri(
                    project_id=project_id,
                    storage_uri=str(asset["storage_uri"]),
                )
                asset_revision = str(asset.get("created_at") or "").strip()
                if not source.is_file() or not asset_revision:
                    continue
                from videobox_storage.local_project_store import sha256_file

                digest = sha256_file(source)
            except (KeyError, OSError, TypeError, ValueError):
                continue
            result.append(
                ApprovedTtsCandidateSummary(
                    candidate_id=candidate_id,
                    asset_id=asset_id,
                    segment_id=segment_id,
                    source_text=_truncate_utf8(
                        str(item.get("source_text") or ""),
                        MAX_SEGMENT_TEXT_BYTES,
                    ),
                    technical_status="accepted",
                    operator_review_status="approved",
                    asset_revision=asset_revision,
                    expected_content_sha256=digest,
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda item: (item.segment_id, item.candidate_id, item.asset_id),
        )[:32]
    )


def _timeline_summary(manifest: dict[str, Any]) -> TimelineSummary:
    tracks = manifest.get("tracks")
    safe_tracks = tracks if isinstance(tracks, list) else []
    clip_count = sum(
        len(track.get("clips", []))
        for track in safe_tracks
        if isinstance(track, dict) and isinstance(track.get("clips"), list)
    )
    gaps = manifest.get("gap_slots")
    output = manifest.get("output")
    safe_output = output if isinstance(output, dict) else {}
    return TimelineSummary(
        duration_sec=_nonnegative_float(safe_output.get("duration_sec")),
        track_count=len(safe_tracks),
        clip_count=clip_count,
        gap_count=len(gaps) if isinstance(gaps, list) else 0,
    )


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _positive_revision(value: object) -> int:
    try:
        revision = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise YujinCreatorContextError(
            "creator_context_session_revision_mismatch"
        ) from None
    if revision < 1:
        raise YujinCreatorContextError(
            "creator_context_session_revision_mismatch"
        )
    return revision


def _nonnegative_float(value: object) -> float:
    try:
        number = float(value or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) and number >= 0 else 0.0
