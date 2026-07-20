from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "DEFAULT_PROJECTS_ROOT",
    "KeywordBrollRecommender",
    "LocalOnlyKeywordBrollRecommender",
    "LocalOnlyMusicRecommender",
    "LocalPipelineRunner",
    "RuleBasedMusicRecommender",
    "TimelineBuilder",
]

_LAZY_EXPORTS = {
    "DEFAULT_PROJECTS_ROOT": ("videobox_core_engine.settings", "DEFAULT_PROJECTS_ROOT"),
    "KeywordBrollRecommender": (
        "videobox_core_engine.recommenders",
        "KeywordBrollRecommender",
    ),
    "LocalOnlyKeywordBrollRecommender": (
        "videobox_core_engine.recommenders",
        "LocalOnlyKeywordBrollRecommender",
    ),
    "LocalOnlyMusicRecommender": (
        "videobox_core_engine.recommenders",
        "LocalOnlyMusicRecommender",
    ),
    "LocalPipelineRunner": ("videobox_core_engine.local_pipeline", "LocalPipelineRunner"),
    "RuleBasedMusicRecommender": (
        "videobox_core_engine.recommenders",
        "RuleBasedMusicRecommender",
    ),
    "TimelineBuilder": ("videobox_core_engine.timeline_builder", "TimelineBuilder"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
