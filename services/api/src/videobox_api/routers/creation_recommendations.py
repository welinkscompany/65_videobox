"""주제 하나로 BGM·이미지 스타일·목소리까지 세트로 미리 보여준다.

owner 요청(2026-08-28, 반드시 만들어야 하는 항목으로 지정): "주제 하나로
BGM+이미지스타일+AI보이스까지 세트로 자동 추천." Vrew의 "주제 선택만으로도
완성된 영상이 당신을 기다려요" 튜토리얼을 참고했다.

**정직하게 밝혀 둘 것**: 세 추천 모두 이미 있는 재료 위에서 고르는 것이지,
새로 만들어 내는 것이 아니다.
- BGM은 `/api/library/search`가 쓰는 것과 같은 의미 기반 색인(`media_library_store.
  find_audio_matches`)에 대본/주제 글을 그대로 물어본다. 임베딩 모델이 없으면
  조용히 빈 목록을 주지 않고 `bgm_semantic=False`로 사실을 말한다.
- 이미지 스타일은 학습된 분류기가 아니다. 주제 글에 든 낱말을 미리 정해 둔
  스타일 카탈로그와 맞춰 보는 낱말 매칭이다(`_STYLE_CATALOG`). 실제로 이미지
  생성 프롬프트에 적용하는 배선은 이번 범위 밖이다 -- 추천만 한다.
- 목소리는 이 프로젝트에 이미 등록된 샘플 중 가장 최근 것을 그대로 추천한다.
  하나도 없으면 등록 화면으로 가라고 말로 알려 준다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    BgmRecommendationResponse,
    CreationRecommendationSetRequest,
    CreationRecommendationSetResponse,
    ImageStyleRecommendationResponse,
    VoiceRecommendationResponse,
)
from videobox_domain_models.assets import AssetType
from videobox_domain_models.library_assets import LibraryMediaType
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore

#: 주제/대본 글에 이 낱말이 있으면 그 스타일을 추천한다. 순서가 우선순위다 --
#: 여러 낱말이 동시에 맞으면 먼저 오는 것이 이긴다. 마지막(`realistic`)은
#: 아무 낱말도 안 맞을 때의 기본값이다.
_STYLE_CATALOG: tuple[dict[str, object], ...] = (
    {
        "style_id": "fairytale_watercolor",
        "name": "동화 수채화풍",
        "prompt_suffix": "storybook watercolor illustration, soft pastel colors, gentle brush texture",
        "keywords": ("동화", "아이", "어린이", "옛날", "이야기책"),
    },
    {
        "style_id": "flat_vector",
        "name": "미니멀 벡터",
        "prompt_suffix": "flat vector illustration, clean minimal shapes, limited color palette",
        "keywords": ("비즈니스", "설명", "가이드", "튜토리얼", "인포그래픽", "정리"),
    },
    {
        "style_id": "cinematic_realistic",
        "name": "실사 시네마틱",
        "prompt_suffix": "cinematic realistic photo, dramatic lighting, shallow depth of field",
        "keywords": ("브이로그", "여행", "일상", "인터뷰", "다큐"),
    },
    {
        "style_id": "comic_bold",
        "name": "만화풍",
        "prompt_suffix": "bold comic book illustration, dynamic linework, vivid colors",
        "keywords": ("게임", "액션", "히어로", "만화", "웃긴", "개그"),
    },
    # 기본값 -- 아무 낱말도 안 맞으면 여기로 떨어진다.
    {
        "style_id": "realistic_default",
        "name": "실사 기본",
        "prompt_suffix": "photorealistic, natural lighting, high detail",
        "keywords": (),
    },
)


def _recommend_style(query_text: str) -> ImageStyleRecommendationResponse:
    lowered = query_text.lower()
    for style in _STYLE_CATALOG:
        keywords = style["keywords"]
        if not keywords:
            continue
        matched = next((keyword for keyword in keywords if keyword in lowered), None)
        if matched:
            return ImageStyleRecommendationResponse(
                style_id=str(style["style_id"]),
                name=str(style["name"]),
                prompt_suffix=str(style["prompt_suffix"]),
                reason=f'"{matched}" 낱말이 있어 추천했어요.',
            )
    default = _STYLE_CATALOG[-1]
    return ImageStyleRecommendationResponse(
        style_id=str(default["style_id"]),
        name=str(default["name"]),
        prompt_suffix=str(default["prompt_suffix"]),
        reason="주제에 맞는 특정 스타일을 찾지 못해 기본 스타일을 추천했어요.",
    )


def _recommend_voice(store: LocalProjectStore, *, project_id: str) -> VoiceRecommendationResponse:
    samples = store.list_assets(project_id=project_id, asset_type=AssetType.VOICE_SAMPLE_AUDIO)
    if not samples:
        return VoiceRecommendationResponse(
            asset_id=None,
            filename=None,
            note="등록된 목소리가 아직 없어요. 미디어 단계의 내레이션에서 먼저 등록해 주세요.",
        )
    latest = max(samples, key=lambda asset: str(asset.get("created_at") or ""))
    filename = str(latest.get("storage_uri") or "").rsplit("/", 1)[-1] or None
    return VoiceRecommendationResponse(
        asset_id=str(latest["asset_id"]),
        filename=filename,
        note="이미 등록한 목소리 중 가장 최근 것을 추천했어요.",
    )


def build_creation_recommendations_router(
    *, store: LocalProjectStore, media_library_store: MediaLibraryStore
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/creation-recommendations")
    def create_recommendation_set(
        project_id: str, payload: CreationRecommendationSetRequest, request: Request
    ) -> CreationRecommendationSetResponse:
        try:
            store.get_project(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

        query_text = (payload.script_text or payload.topic).strip()

        bgm: list[BgmRecommendationResponse] = []
        bgm_semantic = False
        provider = getattr(request.app.state, "media_analysis_embedding_provider", None)
        model_name = (getattr(request.app.state, "media_analysis_profile", None) or {}).get(
            "embedding_model_name"
        )
        if provider is not None and model_name:
            try:
                vector = [
                    float(value)
                    for value in provider.embed(
                        EmbeddingRequest(model_name=model_name, inputs=(query_text,))
                    ).vectors[0]
                ]
                matches = media_library_store.find_audio_matches(
                    query_embedding=vector, media_type=LibraryMediaType.MUSIC.value, limit=3
                )
                bgm = [
                    BgmRecommendationResponse(
                        library_asset_id=str(match["library_asset_id"]),
                        description=str(match.get("description") or ""),
                        duration_seconds=(
                            float(match["duration_seconds"])
                            if match.get("duration_seconds") is not None
                            else None
                        ),
                        score=float(match.get("score") or 0.0),
                    )
                    for match in matches
                ]
                bgm_semantic = bool(bgm)
            except Exception:
                # 의미 기반 검색은 로컬 임베딩 모델이 꺼져 있으면 실패할 수 있다.
                # `library_assets.py`의 같은 자리와 마찬가지로 조용히 빈 목록으로
                # 접는다 -- 거짓 점수를 만들어내지 않는다.
                bgm = []
                bgm_semantic = False

        try:
            voice = _recommend_voice(store, project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

        return CreationRecommendationSetResponse(
            bgm=bgm,
            image_style=_recommend_style(query_text),
            voice=voice,
            bgm_semantic=bgm_semantic,
        )

    return router


__all__ = ["build_creation_recommendations_router"]
