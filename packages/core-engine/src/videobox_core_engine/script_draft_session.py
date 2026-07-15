from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


MIN_PROVISIONAL_DURATION_SEC = 2.0
DEFAULT_KOREAN_CHARACTERS_PER_SECOND = 5.0
DEFAULT_MAX_CHARACTERS = 80
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])(?:\s+|(?=\S))")


def build_provisional_script_draft_session(
    *,
    project_id: str,
    script_asset_id: str,
    script_text: str,
    max_characters: int = DEFAULT_MAX_CHARACTERS,
    korean_characters_per_second: float = DEFAULT_KOREAN_CHARACTERS_PER_SECOND,
) -> dict[str, Any]:
    """Create a narration-free editing session from stable script source units."""
    if not str(script_asset_id).strip():
        raise ValueError("script_asset_id must not be empty.")
    if max_characters < 1:
        raise ValueError("max_characters must be positive.")
    if korean_characters_per_second <= 0:
        raise ValueError("korean_characters_per_second must be positive.")
    units = _segment_script(script_text=script_text, max_characters=max_characters)
    if not units:
        raise ValueError("Script text must not be empty.")

    cursor = 0.0
    segments: list[dict[str, Any]] = []
    for index, text in enumerate(units, start=1):
        duration = max(MIN_PROVISIONAL_DURATION_SEC, _korean_character_count(text) / korean_characters_per_second)
        source_id = f"script:{script_asset_id.strip()}:{index:03d}"
        segments.append(
            {
                "segment_id": source_id,
                "source_script_segment_id": source_id,
                "caption_text": text,
                "start_sec": cursor,
                "end_sec": cursor + duration,
                "cut_action": "keep",
                "review_required": False,
                "broll_override": None,
                "visual_overlays": [],
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
            }
        )
        cursor += duration
    return {
        "project_id": project_id,
        "timeline_id": f"script_draft:{script_asset_id.strip()}",
        "script_asset_id": script_asset_id.strip(),
        "timing_source": "provisional_script",
        "narration_alignment_required": True,
        "stale_proposal_source_script_segment_ids": [],
        "segments": segments,
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
        "session_revision": 1,
    }


def apply_narration_alignment_to_script_draft(
    *,
    session: dict[str, Any],
    aligned_segments: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Replace provisional bounds while retaining source IDs for proposal invalidation.

    Task 8 owns proposal persistence.  This explicit source-ID list is its
    invalidation handoff, so a later proposal aggregate can stale every
    provisional candidate whose timing provenance has been replaced.
    """
    if session.get("timing_source") != "provisional_script":
        raise ValueError("Only provisional script sessions can accept narration alignment.")
    existing_by_source = {
        str(segment.get("source_script_segment_id")): segment
        for segment in session.get("segments", [])
        if isinstance(segment, dict) and str(segment.get("source_script_segment_id") or "")
    }
    aligned_by_source: dict[str, dict[str, Any]] = {}
    for aligned in aligned_segments:
        source_id = str(aligned.get("source_script_segment_id") or "")
        if source_id not in existing_by_source:
            raise ValueError(f"Alignment contains unknown source_script_segment_id: {source_id}")
        if source_id in aligned_by_source:
            raise ValueError(f"Alignment repeats source_script_segment_id: {source_id}")
        start_sec, end_sec = float(aligned.get("start_sec", 0.0)), float(aligned.get("end_sec", 0.0))
        if not math.isfinite(start_sec) or not math.isfinite(end_sec):
            raise ValueError("Aligned segment bounds must be finite.")
        if start_sec < 0 or end_sec <= start_sec:
            raise ValueError("Aligned segment bounds must be positive and ordered.")
        aligned_by_source[source_id] = {"start_sec": start_sec, "end_sec": end_sec}
    if set(aligned_by_source) != set(existing_by_source):
        raise ValueError("Alignment must cover every source_script_segment_id exactly once.")

    ordered = [aligned_by_source[str(segment["source_script_segment_id"])] for segment in session["segments"]]
    for prior, current in zip(ordered, ordered[1:]):
        if prior["end_sec"] > current["start_sec"]:
            raise ValueError("Aligned segment bounds must not overlap.")

    updated = deepcopy(session)
    stale_source_ids: list[str] = []
    for segment in updated["segments"]:
        source_id = str(segment["source_script_segment_id"])
        bounds = aligned_by_source[source_id]
        # Successful alignment replaces provisional timing provenance even if
        # numerical bounds happen to match; proposals must be regenerated from
        # actual narration alignment rather than retained by coincidence.
        stale_source_ids.append(source_id)
        segment["start_sec"] = bounds["start_sec"]
        segment["end_sec"] = bounds["end_sec"]
    updated["timing_source"] = "narration_alignment"
    updated["narration_alignment_required"] = False
    updated["stale_proposal_source_script_segment_ids"] = stale_source_ids
    updated.setdefault("history", []).append(
        {"mutation_type": "narration_alignment", "segment_id": ",".join(stale_source_ids)}
    )
    return updated, stale_source_ids


def _segment_script(*, script_text: str, max_characters: int) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", script_text) if paragraph.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        sentences = [sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(paragraph) if sentence.strip()]
        for sentence in sentences:
            units.extend(_split_to_character_budget(sentence, max_characters=max_characters))
    return units


def _split_to_character_budget(text: str, *, max_characters: int) -> list[str]:
    if _korean_character_count(text) <= max_characters:
        return [text]
    chunks: list[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        if current and _korean_character_count(candidate) > max_characters:
            chunks.append(current)
            current = word
        else:
            current = candidate
        while _korean_character_count(current) > max_characters:
            compact = re.sub(r"\s+", "", current)
            chunks.append(compact[:max_characters])
            current = compact[max_characters:]
    if current:
        chunks.append(current)
    return chunks


def _korean_character_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))
