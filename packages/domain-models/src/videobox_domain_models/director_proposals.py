from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_freeze(item) for item in value)
    return value

def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return _freeze(value)  # type: ignore[return-value]


@dataclass(frozen=True)
class DirectorCandidate:
    candidate_id: str
    visible_reference_code: str
    media_type: str
    asset_id: str
    library_asset_id: str | None
    reason_chips: tuple[str, ...]
    scores: Mapping[str, float]
    availability: str
    review_status: str
    preview_uri: str | None
    controls: Mapping[str, object]
    expected_content_sha256: str | None
    media_revision: str | None
    canonical_metadata: Mapping[str, object]
    license_policy: str = "verified"
    warning_provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_chips", tuple(self.reason_chips))
        object.__setattr__(self, "scores", _frozen_mapping(self.scores))
        object.__setattr__(self, "controls", _frozen_mapping(self.controls))
        object.__setattr__(self, "canonical_metadata", _frozen_mapping(self.canonical_metadata))
        object.__setattr__(self, "warning_provenance", tuple(self.warning_provenance))


@dataclass(frozen=True)
class DirectorProposal:
    proposal_id: str
    revision_code: str
    revision: int
    base_session_revision: int
    asset_index_revision: int
    source_session_id: str
    target_segment_ids: tuple[str, ...]
    source_script_segment_ids: tuple[str, ...]
    status: str
    diff: Mapping[str, object]
    expires_at: str | None
    candidates: tuple[DirectorCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_segment_ids", tuple(self.target_segment_ids))
        object.__setattr__(self, "source_script_segment_ids", tuple(self.source_script_segment_ids))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "diff", _frozen_mapping(self.diff))
