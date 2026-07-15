from __future__ import annotations

from typing import Any

from videobox_domain_models.director_proposals import DirectorCandidate

_SYNONYMS = {"평온": "차분한", "휴가": "여행"}
_SCORE_NAMES = ("semantic_similarity", "lexical_fallback", "structured_tag_match", "duration_match", "aspect_match", "explicit_conditions", "favorite", "recent", "repetition", "diversity", "availability_license", "pinned")

def _words(value: object) -> set[str]:
    words = set(str(value or "").lower().replace(",", " ").split())
    return words | {_SYNONYMS.get(word, word) for word in words}

def _canonical_metadata(asset: dict[str, Any]) -> dict[str, object]:
    keys = ("mood", "energy", "genre", "vocal_presence", "recommended_use", "duration_sec", "license") if _media_type(asset) == "bgm" else ("action_event", "intensity", "mood", "recommended_use", "duration_sec", "license")
    return {key: asset.get(key) for key in keys if asset.get(key) is not None}

def _media_type(asset: dict[str, Any]) -> str:
    return "bgm" if str(asset.get("media_type") or "").lower() in {"music", "bgm"} else str(asset.get("media_type") or "broll").lower()

def rank_candidates(segment: dict[str, Any], assets: list[dict[str, Any]], preferences: dict[str, list[str]] | None = None, weights: dict[str, float] | None = None) -> list[DirectorCandidate]:
    preferences, weights = preferences or {}, weights or {}
    target_words = _words(segment.get("text"))
    results: list[tuple[float, DirectorCandidate]] = []
    for asset in assets:
        asset_id = str(asset.get("asset_id") or "")
        tags = _words(" ".join(map(str, asset.get("tags") or [])))
        eligible = asset_id and str(asset.get("availability", "available")) == "available" and str(asset.get("license", "valid")) == "valid" and str(asset.get("review_status", "approved")) == "approved"
        eligible = eligible and asset_id not in preferences.get("exclude_asset", []) and str(asset.get("creator") or "") not in preferences.get("exclude_creator", []) and not (tags & set(preferences.get("exclude_tag", [])))
        if not eligible:
            continue
        tag_score = len(target_words & tags) / max(1, len(target_words))
        semantic_value = asset.get("semantic_score")
        semantic_score = float(semantic_value) if semantic_value is not None else 0.0
        semantic_provenance = "asset_semantic_score" if semantic_value is not None else "lexical_korean_synonym_fallback"
        explicit_required = {str(value).lower() for value in segment.get("explicit_conditions", [])}
        explicit_available = {str(value).lower() for value in asset.get("explicit_conditions", [])}
        explicit_score = len(explicit_required & explicit_available) / max(1, len(explicit_required))
        duration_score = 1.0 if not asset.get("duration_sec") else max(0.0, 1 - abs(float(asset["duration_sec"]) - float(segment.get("duration_sec") or asset["duration_sec"])) / max(float(asset["duration_sec"]), 1))
        scores = {name: 0.0 for name in _SCORE_NAMES}
        scores.update({"semantic_similarity": semantic_score, "lexical_fallback": tag_score if semantic_value is None else 0.0, "structured_tag_match": tag_score, "duration_match": duration_score, "aspect_match": 1.0 if asset.get("aspect_ratio") else 0.0, "explicit_conditions": explicit_score, "availability_license": 1.0, "favorite": 1.0 if asset.get("favorite") else 0.0, "recent": 1.0 if asset.get("recent") else 0.0, "repetition": -float(asset.get("repetition_count") or 0), "diversity": float(asset.get("diversity") or 0), "pinned": 1.0 if asset_id in preferences.get("pin_asset", []) else 0.0})
        total = sum(value * float(weights.get(name, 1.0)) for name, value in scores.items())
        media_type = _media_type(asset)
        letter = {"broll": "B", "bgm": "M", "sfx": "S"}.get(media_type, "B")
        metadata = _canonical_metadata(asset)
        metadata["semantic_provenance"] = semantic_provenance
        candidate = DirectorCandidate(candidate_id=f"candidate:{asset_id}", visible_reference_code=f"P01-{letter}-00", media_type=media_type, asset_id=asset_id, library_asset_id=asset.get("library_asset_id"), reason_chips=tuple(sorted(target_words & tags)) or ("metadata",), scores=scores, availability=str(asset.get("availability", "available")), review_status=str(asset.get("review_status", "approved")), preview_uri=asset.get("preview_uri"), controls=dict(asset.get("controls") or {}), expected_content_sha256=asset.get("content_sha256"), media_revision=asset.get("media_revision"), canonical_metadata=metadata)
        results.append((total, candidate))
    results.sort(key=lambda item: (-item[0], item[1].asset_id))
    numbered=[]
    per_media: dict[str, int] = {}
    for _, candidate in results:
        per_media[candidate.media_type] = per_media.get(candidate.media_type, 0) + 1
        numbered.append(DirectorCandidate(**{**candidate.__dict__, "visible_reference_code": candidate.visible_reference_code[:-2] + f"{per_media[candidate.media_type]:02d}"}))
    return numbered
