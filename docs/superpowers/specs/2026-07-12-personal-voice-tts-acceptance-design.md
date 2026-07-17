# Personal Voice TTS Acceptance Design

## Goal

Make a per-segment personal-voice TTS candidate safe to generate, inspect, and hand off without requiring a real user voice during automated verification.

## Decision

Use a technical acceptance gate plus a separate human listening decision.

- A candidate is technically acceptable only when the provider created a non-empty, probeable, non-silent audio file and its duration is close enough to its target segment window.
- A technically acceptable candidate is still `pending_operator_review`; it cannot represent verified personal-voice similarity until a human listens to it.
- A provider failure, unavailable voice sample, silent file, or duration mismatch preserves the original narration. VideoBox must not silently substitute gTTS or another generic voice.
- The existing review/approval path remains the sole route from an accepted candidate to the timeline, SRT, FFmpeg final render, and CapCut draft.

## Alternatives considered

1. Require a real user voice before implementation. This blocks the acceptance slice and is unsuitable while no sample can be supplied.
2. **Recommended: deterministic Korean WAV fixture plus pending human review.** This verifies all mechanically measurable contracts now while honestly leaving speaker-similarity approval pending.
3. Auto-fallback to generic gTTS. Rejected because it produces a voice that is not the user and would create a misleading personal-voice result.

## Architecture

`LocalPipelineRunner.generate_tts_replacement_candidate` receives the segment target duration, invokes the injected provider, probes and measures the generated audio, and persists a TTS-candidate acceptance record. The record contains provider identity, requested/actual duration, technical status, failure reason when applicable, and the initial `pending_operator_review` state.

The API returns this record rather than an unqualified asset, and the React candidate list exposes its technical and listening-review states. Only technically accepted candidates can be copied into the editing draft. Existing partial regeneration and review approval retain responsibility for applying that selected asset to the timeline, SRT, FFmpeg, and CapCut paths.

## Acceptance rules

| Rule | Result |
| --- | --- |
| No configured provider or no valid voice sample | generation fails clearly; no candidate, timeline, or editing selection mutation |
| Provider raises | generation fails clearly; original narration remains authoritative |
| Output absent, empty, unprobeable, or silent | candidate is rejected; output is not selectable |
| Actual duration differs from target by more than 0.5 seconds | candidate is rejected; output is not selectable |
| Technical checks pass | candidate is saved with `technical_status=accepted`, `operator_review_status=pending` |
| Human marks listening decision approved | the existing selected TTS + regeneration + review flow may hand off to output artifacts |

The 0.5-second tolerance avoids false rejection from codec/container padding. The final renderer and CapCut adapter still pad or trim an approved TTS source to the timeline window; acceptance validates the source before that correction rather than pretending the correction proves speaking quality.

## Scope boundaries

- No speaker-similarity ML score is claimed. That requires a consented real reference recording and human listening review.
- No generic-voice fallback is added.
- No BrollBox code is copied: `execution/tts_engine.py` is `rewrite` because it is coupled to environment globals and automatic gTTS fallback. Voicebox remains `reference only`.
- Existing FFmpeg/CapCut duration fitting is reused, not redesigned.

## Verification

- RED unit/contract tests cover provider failure preservation, silent/invalid output rejection, duration mismatch rejection, and an accepted pending-review candidate.
- API and frontend tests verify serialized state, disabled selection for rejected candidates, error/retry behavior, and reload-safe candidate state.
- The production-readiness Korean 10-minute smoke uses a deterministic wave provider, selects an accepted candidate through the normal review flow, and verifies it persists through SRT, final MP4, and real CapCut draft.
