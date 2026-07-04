from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "DEFAULT_PROJECTS_ROOT",
    "KeywordBrollRecommender",
    "LLMTaskRouter",
    "LocalFirstMusicRecommender",
    "LocalFirstStructuredRuntime",
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
    "LLMTaskRouter": ("videobox_core_engine.ai_routing", "LLMTaskRouter"),
    "LocalFirstMusicRecommender": (
        "videobox_core_engine.recommenders",
        "LocalFirstMusicRecommender",
    ),
    "LocalFirstStructuredRuntime": (
        "videobox_core_engine.local_first_runtime",
        "LocalFirstStructuredRuntime",
    ),
    "LocalPipelineRunner": ("videobox_core_engine.local_pipeline", "LocalPipelineRunner"),
    "RuleBasedMusicRecommender": (
        "videobox_core_engine.recommenders",
        "RuleBasedMusicRecommender",
    ),
    "TimelineBuilder": ("videobox_core_engine.timeline_builder", "TimelineBuilder"),
}


def __getattr__(name: str) -> Any:
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
