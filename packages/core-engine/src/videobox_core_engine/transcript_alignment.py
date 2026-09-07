from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Protocol

_PROTECTED_PERIOD = "__VIDEBOX_PERIOD__"
_INITIALISM_PATTERN = re.compile(r"\b(?:[A-Za-z]\.){2,}")
_TITLE_ABBREVIATION_PATTERN = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|Capt|Lt|Col|Gen|Sgt)\.",
    flags=re.IGNORECASE,
)
_INLINE_ABBREVIATION_PATTERNS = (
    re.compile(r"(?i:\bvs)\.(?=\s+(?:[A-Z]\b|[a-z]))"),
    re.compile(r"(?i:\betc)\.(?=\s+[a-z])"),
)


def split_script_units(script_text: str) -> list[str]:
    units: list[str] = []
    for line in script_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        protected = _protect_abbreviations(stripped)
        parts = re.split(r"(?<=[.!?])\s+", protected)
        units.extend(_rejoin_list_markers([part.strip() for part in parts if part.strip()]))
    return [_restore_abbreviations(unit) for unit in units]


# `1.` `2.` 처럼 **번호만 남은 조각**. 뒤 문장에 붙는 이름표이지 문장이 아니다.
_LIST_MARKER_PATTERN = re.compile(r"^\d{1,2}[.)]$")


def _rejoin_list_markers(parts: list[str]) -> list[str]:
    """번호 목록의 번호를 그것이 가리키는 문장에 도로 붙인다.

    문장 나누기는 마침표 뒤에서 자르는데, 번호 매긴 대본(`1. 첫 장면.`)은 번호
    뒤에도 마침표가 있어 **번호가 문장 하나로** 떨어졌다. 유진에게 대본을 써
    달라고 하면 이 꼴로 주기 때문에, 다섯 문장짜리 대본이 열세 장면이 되고
    그중 다섯은 자막이 `1`~`5`인 빈 장면이었다(2026-08-20 실측).

    번호만 있는 조각만 붙인다. `총 3.`처럼 앞에 말이 붙은 것은 그대로 문장이다.
    """
    rejoined: list[str] = []
    for part in parts:
        if rejoined and _LIST_MARKER_PATTERN.match(rejoined[-1]):
            rejoined[-1] = f"{rejoined[-1]} {part}"
            continue
        rejoined.append(part)
    return rejoined


def _protect_abbreviations(value: str) -> str:
    protected = _INITIALISM_PATTERN.sub(lambda match: match.group(0).replace(".", _PROTECTED_PERIOD), value)
    protected = _TITLE_ABBREVIATION_PATTERN.sub(
        lambda match: match.group(0).replace(".", _PROTECTED_PERIOD),
        protected,
    )
    for pattern in _INLINE_ABBREVIATION_PATTERNS:
        protected = pattern.sub(lambda match: match.group(0).replace(".", _PROTECTED_PERIOD), protected)
    return protected


def _restore_abbreviations(value: str) -> str:
    return value.replace(_PROTECTED_PERIOD, ".")


class TranscriptAligner(Protocol):
    def align(
        self,
        *,
        transcript_segments: list[dict[str, Any]],
        script_text: str | None,
    ) -> list[dict[str, Any]]:
        """Align transcript segments to script sentences while preserving timing."""


@dataclass(slots=True)
class HeuristicTranscriptAligner(TranscriptAligner):
    min_similarity: float = 0.55
    min_length_ratio: float = 0.85
    min_rewrite_similarity: float = 0.9

    def align(
        self,
        *,
        transcript_segments: list[dict[str, Any]],
        script_text: str | None,
    ) -> list[dict[str, Any]]:
        normalized_segments = [self._normalize_segment(segment) for segment in transcript_segments]
        script_lines = split_script_units(script_text or "")
        if not script_lines:
            return normalized_segments
        split_target_units = self._select_split_target_units(
            transcript_segments=normalized_segments,
            script_lines=script_lines,
        )
        if len(normalized_segments) < len(split_target_units):
            normalized_segments = self._expand_coarse_segments(
                transcript_segments=normalized_segments,
                script_lines=split_target_units,
            )

        aligned_segments: list[dict[str, Any]] = []
        transcript_index = 0

        for script_index, script_line in enumerate(script_lines):
            if transcript_index >= len(normalized_segments):
                break

            remaining_scripts = len(script_lines) - script_index
            remaining_transcripts = len(normalized_segments) - transcript_index
            max_take = max(1, remaining_transcripts - max(0, remaining_scripts - 1))

            best_take = 1
            best_score = -1.0
            for take in range(1, max_take + 1):
                candidate_segments = normalized_segments[transcript_index : transcript_index + take]
                candidate_text = " ".join(str(segment["text"]).strip() for segment in candidate_segments).strip()
                score = SequenceMatcher(
                    None,
                    self._normalize_text(candidate_text),
                    self._normalize_text(script_line),
                ).ratio()
                if score > best_score:
                    best_score = score
                    best_take = take

            if best_score < self.min_similarity:
                aligned_segments.append(normalized_segments[transcript_index])
                transcript_index += 1
                continue

            candidate_segments = normalized_segments[transcript_index : transcript_index + best_take]
            candidate_text = " ".join(str(segment["text"]).strip() for segment in candidate_segments).strip()
            use_script_text = self._should_use_script_text(
                candidate_text=candidate_text,
                script_line=script_line,
                similarity=best_score,
            )
            confidence_values = [
                float(segment.get("confidence", 1.0))
                for segment in candidate_segments
                if segment.get("confidence") is not None
            ]
            aligned_segments.append(
                {
                    "start_sec": float(candidate_segments[0]["start_sec"]),
                    "end_sec": float(candidate_segments[-1]["end_sec"]),
                    "text": script_line if use_script_text else candidate_text,
                    "confidence": min(confidence_values) if confidence_values else 1.0,
                }
            )
            transcript_index += best_take

        aligned_segments.extend(normalized_segments[transcript_index:])
        return aligned_segments

    def _normalize_segment(self, segment: dict[str, Any]) -> dict[str, Any]:
        return {
            "start_sec": float(segment["start_sec"]),
            "end_sec": float(segment["end_sec"]),
            "text": str(segment["text"]).strip(),
            "confidence": float(segment.get("confidence", 1.0)),
        }

    def _normalize_text(self, value: str) -> str:
        lowered = value.casefold()
        alnum_only = re.sub(r"[^\w]+", "", lowered, flags=re.UNICODE)
        return alnum_only

    def _should_use_script_text(
        self,
        *,
        candidate_text: str,
        script_line: str,
        similarity: float,
    ) -> bool:
        if similarity < self.min_similarity:
            return False
        normalized_candidate = self._normalize_text(candidate_text)
        normalized_script = self._normalize_text(script_line)
        if not normalized_candidate or not normalized_script:
            return False
        if similarity < self.min_rewrite_similarity:
            return False
        shorter = min(len(normalized_candidate), len(normalized_script))
        longer = max(len(normalized_candidate), len(normalized_script))
        return shorter / longer >= self.min_length_ratio and normalized_candidate == normalized_script

    def _select_split_target_units(
        self,
        *,
        transcript_segments: list[dict[str, Any]],
        script_lines: list[str],
    ) -> list[str]:
        transcript_units: list[str] = []
        for segment in transcript_segments:
            transcript_units.extend(split_script_units(str(segment["text"])))
        if len(transcript_units) > len(script_lines):
            return transcript_units
        return script_lines

    def _expand_coarse_segments(
        self,
        *,
        transcript_segments: list[dict[str, Any]],
        script_lines: list[str],
    ) -> list[dict[str, Any]]:
        expanded_segments: list[dict[str, Any]] = []
        transcript_index = 0
        script_index = 0

        while transcript_index < len(transcript_segments):
            segment = transcript_segments[transcript_index]
            remaining_transcripts = len(transcript_segments) - transcript_index
            remaining_scripts = len(script_lines) - script_index
            max_take = max(1, remaining_scripts - max(0, remaining_transcripts - 1))

            best_take = 1
            best_score = -1.0
            for take in range(1, max_take + 1):
                candidate_script = " ".join(script_lines[script_index : script_index + take]).strip()
                score = SequenceMatcher(
                    None,
                    self._normalize_text(str(segment["text"])),
                    self._normalize_text(candidate_script),
                ).ratio()
                if score > best_score:
                    best_score = score
                    best_take = take

            joined_script = " ".join(script_lines[script_index : script_index + best_take]).strip()
            if best_take > 1 and self._should_use_script_text(
                candidate_text=str(segment["text"]),
                script_line=joined_script,
                similarity=best_score,
            ):
                expanded_segments.extend(
                    self._split_segment_by_script_units(
                        segment=segment,
                        script_units=script_lines[script_index : script_index + best_take],
                    )
                )
                script_index += best_take
            else:
                expanded_segments.append(segment)
                script_index += 1
            transcript_index += 1

        return expanded_segments

    def _split_segment_by_script_units(
        self,
        *,
        segment: dict[str, Any],
        script_units: list[str],
    ) -> list[dict[str, Any]]:
        start_sec = float(segment["start_sec"])
        end_sec = float(segment["end_sec"])
        total_duration = max(0.0, end_sec - start_sec)
        normalized_lengths = [
            max(1, len(self._normalize_text(script_unit)))
            for script_unit in script_units
        ]
        total_length = sum(normalized_lengths)
        split_segments: list[dict[str, Any]] = []
        current_start = start_sec

        for index, script_unit in enumerate(script_units):
            if index == len(script_units) - 1:
                current_end = end_sec
            else:
                portion = normalized_lengths[index] / total_length
                current_end = current_start + total_duration * portion
                remaining_units = len(script_units) - index - 1
                max_end = end_sec - (remaining_units * 1e-6)
                current_end = min(max_end, current_end)
                if current_end <= current_start:
                    current_end = min(max_end, current_start + 1e-6)
            split_segments.append(
                {
                    "start_sec": current_start,
                    "end_sec": current_end,
                    "text": script_unit,
                    "confidence": float(segment.get("confidence", 1.0)),
                }
            )
            current_start = current_end

        return split_segments

__all__ = ["HeuristicTranscriptAligner", "TranscriptAligner", "split_script_units"]
