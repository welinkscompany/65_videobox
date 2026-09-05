from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
import asyncio
import logging
import os
import json
from threading import Event, Thread
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from videobox_core_engine.caption_translation import caption_text_for_language
from videobox_core_engine.director_media_focus import media_focus_for_request
from videobox_core_engine.library_materialization import materialize_library_asset
from videobox_core_engine.mojibake import repair_mojibake_metadata
from videobox_core_engine.director_proposal_service import (
    DirectorProposalBlockedError,
    DirectorProposalService,
    is_actionable_yujin_media_candidate,
)
from videobox_core_engine.yujin_local_conversation import (
    YujinLocalConversationService,
    YujinProjectContext,
)
from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext
from videobox_core_engine.yujin_editing_proposal_service import YujinEditingProposalService
from videobox_core_engine.editing_session import apply_yujin_editing_proposal
from videobox_domain_models.caption_style import DEFAULT_CAPTION_FONT_SIZE_PX
from videobox_domain_models.director_proposals import DirectorProposal
from videobox_core_engine.director_proposals import proposal_to_payload
from videobox_core_engine.yujin_creator_proposal_adapter import variant_patch_from_yujin_candidate
from videobox_core_engine.output_variants import apply_variant_patch
from videobox_domain_models.output_variants import OutputVariant
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.local_project_store import EditingSessionRevisionConflict, sha256_file
from videobox_core_engine.editing_transactions import apply_user_transaction
from videobox_core_engine.director_commands import director_timeline_references, resolve_director_command
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_api.models import (
    DirectorConversationCreateRequest, DirectorConversationResponse,
    DirectorMessageExchangeResponse, DirectorMessageListResponse, DirectorMessageSubmitRequest,
)


def _approved_memories(
    request: Request, *, project_id: str, conversation_id: str, query: str
) -> tuple:
    """Look up the memories the owner approved for this conversation.

    The local-first chat is the route the editor screen actually calls, so
    without this an approved memory never reaches a real conversation.  The
    service already bounds itself (0.75s, 5 items) and answers empty on any
    failure, so a missing or slow memory store never blocks a reply.
    """
    service = getattr(request.app.state, "yujin_memory_service", None)
    if service is None:
        return ()
    try:
        return asyncio.run(
            service.retrieve_approved_memories(
                project_id=project_id,
                conversation_id=conversation_id,
                query=query,
            )
        )
    except Exception:
        return ()


def _project_context(
    store: LocalProjectStore, *, project_id: str, session: dict
) -> YujinProjectContext:
    """Gather the title, script, and scene captions the reply may cite.

    Originally loaded only for thumbnail-prompt requests (owner, 2026-08-19).
    실측(2026-08-20): 그래서 편집 화면에서 "이 장면에 어울리는 B-roll 추천해 줘"라고
    물으면 유진이 **자기가 열어 놓고 있는 영상**을 두고 "영상의 분위기나 주제를
    알려주시면"이라고 되물었다. 대화로 편집한다는 것이 성립하지 않는다.

    이제 모든 대화에 싣는다. 양은 `yujin_local_conversation`의 상한이 자르므로
    (제목 200B·대본 4KB·자막 32개) 프롬프트가 무한정 커지지는 않는다. 각 조각은
    실패하면 빈 값으로 떨어진다 -- 대본이 없다고 대화가 오류가 되면 안 된다.
    """
    title = ""
    try:
        title = str(store.get_project(project_id=project_id).get("name") or "")
    except Exception:
        pass
    script_excerpt = ""
    try:
        briefs = store.list_creation_briefs(project_id=project_id)
        if briefs:
            script_excerpt = str(briefs[0].get("script_text") or "")
    except Exception:
        pass
    captions = tuple(
        text
        for item in session.get("segments", [])
        if isinstance(item, dict)
        for text in (str(item.get("caption_text") or item.get("text") or "").strip(),)
        if text
    )
    return YujinProjectContext(
        title=title, script_excerpt=script_excerpt, scene_captions=captions
    )


class ProposalCreateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    expires_at: str | None = None
    # 창작자가 방금 한 말. 종류 판단은 **백엔드 한 곳**에서 한다 -- 같은 규칙을
    # 화면에도 두면 두 벌이 어긋난다(이 저장소가 여러 번 겪은 일이다).
    request_text: str | None = None

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_iso8601(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    raise ValueError("expires_at must include timezone")
            except ValueError as exc:
                raise ValueError("expires_at must be ISO-8601") from exc
        return value


class YujinEditingProposalCreateRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4_096)


class YujinEditingProposalApplyRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class PreferencesRequest(BaseModel):
    pin_asset: list[str] = []
    exclude_asset: list[str] = []
    exclude_creator: list[str] = []
    exclude_tag: list[str] = []


class ProposalApplyRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1)
    expected_revision: int = Field(ge=1)


class ProposalBatchApplyRequest(ProposalApplyRequest):
    """A single explicit user action; materialization happens only inside this endpoint."""


_LOGGER = logging.getLogger(__name__)


def _asset_label(asset: dict) -> str:
    """자산 하나를 **사람이 아는 말로** 한 줄로. 고를 근거가 없으면 빈 문자열.

    `01-새벽-바다 · 6초 · 가로`처럼 창작자가 파일에 붙여 둔 이름이 가장 쓸모
    있다 -- 그 이름이 곧 그 사람이 그 소재를 부르는 말이기 때문이다.
    """
    metadata = repair_mojibake_metadata(asset.get("metadata"))
    if not isinstance(metadata, dict):
        return ""
    parts: list[str] = []
    title = str(metadata.get("title") or "").strip()
    if title:
        parts.append(title)
    tags = metadata.get("tags")
    if isinstance(tags, (list, tuple)):
        joined = ", ".join(str(tag).strip() for tag in tags if str(tag).strip())
        if joined:
            parts.append(joined)
    duration = metadata.get("duration_sec")
    if isinstance(duration, (int, float)) and duration > 0:
        parts.append(f"{round(float(duration))}초")
    return " · ".join(parts)


def _library_mime_type(path) -> str | None:
    """스냅숏 파일의 형식. 자료실 라우터가 쓰는 것과 같은 기준(확장자)이다."""
    import mimetypes

    return mimetypes.guess_type(str(path))[0]


def _current_caption_font_size(session: dict) -> int:
    """지금 자막 글자 크기. 한 번도 안 고쳤으면 기본값이다.

    유진에게 이 값을 줘야 "더 크게"에 되묻지 않는다 -- 창작자는 px 숫자를
    모른다(2026-09-06 실측: 유진이 "크기를 알려주세요"라고 답했다).
    """
    style = session.get("caption_style")
    if isinstance(style, dict):
        value = style.get("font_size_px")
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return DEFAULT_CAPTION_FONT_SIZE_PX


def _library_label(match: dict) -> str:
    """자료실 후보 하나를 **고를 수 있는 말**로. 이름이 아니라 설명이 온다.

    자료실 음악은 파일 이름이 `music-005`처럼 뜻이 없는 대신, 색인이 만들어 둔
    설명(`description`)이 있다 -- owner가 화면에서 검색할 때 걸리는 바로 그 글이다.
    유진에게도 같은 글을 줘야 둘이 같은 기준으로 고른다.
    """
    parts: list[str] = []
    description = str(match.get("description") or "").strip()
    if description:
        parts.append(description)
    words = match.get("words")
    if isinstance(words, (list, tuple)):
        joined = ", ".join(str(word).strip() for word in words if str(word).strip())
        if joined:
            parts.append(joined)
    duration = match.get("duration_seconds")
    if isinstance(duration, (int, float)) and duration > 0:
        parts.append(f"{round(float(duration))}초")
    return " · ".join(parts)


def _apply_failure_detail(exc: BaseException) -> str:
    """무엇이 잘못됐는지 그대로 흘려보낸다.

    이 자리는 원래 원인 여덟 가지를 `candidate_unavailable` 하나로 뭉개고
    `from None`으로 어디서 터졌는지까지 지웠다. **원인을 지우는 오류는 잘못된
    진단을 만들어 낸다** -- 2026-08-20에 실제로 그랬다. 단서가 없으니 "지문이
    80자에서 잘렸다"는 그럴듯하고 틀린 이야기가 나왔고, 재 보니 지문은 149자로
    온전했고 파일 해시도 정확히 일치했다.

    이 저장소의 `ValueError`는 이미 코드를 들고 다닌다(`candidate_ids_duplicate`,
    `target_segment_missing`, `candidate_analysis_unavailable` …). 여기에 목록을
    또 적으면 두 벌이 갈라지므로, **코드처럼 생겼으면 그대로 내보낸다.**

    `KeyError`는 다르다. 그 문자열은 없는 열쇠 자체라 화면에 내보낼 말이 아니다.
    예전 이름을 그대로 쓰되 **기록에는 남긴다** -- 조용히 사라지지 않게.
    """
    if isinstance(exc, ValueError):
        code = str(exc).strip()
        if code and " " not in code and code.replace("_", "").isalnum():
            return code
    _LOGGER.warning("추천 적용이 막혔습니다.", exc_info=exc)
    return "candidate_unavailable"


#: 유진에게 한 번에 보여 줄 자료실 후보 수(종류마다). 자료실에는 음악 30곡·
#: 효과음 100개가 있는데 그것을 통째로 프롬프트에 실으면 목록이 본문보다 길어지고
#: 모델이 뒤쪽을 안 본다. **의미검색으로 추린 위쪽만** 준다 -- owner가 화면에서
#: 쓰는 것과 같은 색인이라, 유진과 owner가 같은 기준으로 고르게 된다.
_LIBRARY_SUGGESTION_LIMIT = 8

#: 의미검색이 없을 때 이름만 보고 고르라고 줄 개수. 순위가 없으니 조금 넉넉히
#: 주되, 효과음 100개를 통째로 실으면 목록이 본문보다 길어진다.
_LIBRARY_FALLBACK_LIMIT = 24


def build_director_proposals_router(
    store: LocalProjectStore, *, orchestrator: object, embedding_provider: object = None, embedding_model_name: str | None = None,
    library_store: object = None, library_search: object = None,
) -> APIRouter:
    router = APIRouter()
    service = DirectorProposalService(store, embedding_provider=embedding_provider, embedding_model_name=embedding_model_name)
    materializer = ProjectAssetMaterializer(store)

    def payload(project_id, proposal):
        return proposal_to_payload(proposal) | {"status": proposal.status, "lifecycle": store.get_director_proposal_lifecycle(project_id, proposal.proposal_id)}

    def _with_materialized_library_asset(project_id: str, operation: dict) -> dict:
        """자료실 자산을 고른 편집 항목이면 **먼저 프로젝트로 들여온다.**

        편집본은 프로젝트 자산만 가리킬 수 있다. 유진이 자료실에서 고른 것은
        `pack:starter-v1:music-005` 같은 자료실 id라, 그대로 저장하면 렌더러가
        찾지 못한다. 화면에서 자료실 곡을 적용할 때와 **같은 경로**로 들여오고
        (라이선스 기록까지 함께 복사된다) 프로젝트 자산 id로 바꿔 준다.

        못 들여오면 원래 항목을 그대로 둔다 -- 그러면 검증에서 걸려 422가 되고,
        창작자는 "적용하지 못했어요"를 본다. 조용히 다른 자산으로 바꾸는 것보다
        낫다.
        """
        asset_id = str(operation.get("asset_id") or "")
        # 꾸러미 자산은 `pack:`, owner가 직접 넣은 것은 `user_`로 시작한다.
        # 영상 후보가 들어오면서 뒤쪽도 지나가야 한다 -- 자료실 촬영본은 전부
        # `user_`다. 넓히지 않으면 유진이 고른 영상이 자료실 id 그대로 저장되고
        # 렌더러가 찾지 못한다.
        if not asset_id.startswith(("pack:", "user_")) or library_store is None:
            return operation
        result = materialize_library_asset(
            library_store=library_store, materializer=materializer,
            project_id=project_id, library_asset_id=asset_id, mime_type_for=_library_mime_type,
        )
        if result is None:
            _LOGGER.warning("자료실 자산을 프로젝트로 들여오지 못했습니다 (자산=%s).", asset_id)
            return operation
        return {**operation, "asset_id": str(result["asset_id"])}

    def _library_assets_by_name(media_type: str) -> list[dict]:
        """순위 없이 자료실 목록 그대로. 의미검색이 없을 때 쓰는 대비책.

        `find_audio_matches`와 **같은 모양**으로 돌려준다 -- 부르는 쪽이 두 경우를
        구분하지 않아도 되게. 설명(`description`)은 색인이 만드는 값이라 여기서는
        없고, 대신 이름이 그 자리를 맡는다.
        """
        if library_store is None:
            return []
        try:
            assets = library_store.inspect_active_assets()
        except Exception:
            _LOGGER.warning("자료실 목록을 읽지 못해 유진에게 프로젝트 안 자산만 보입니다.", exc_info=True)
            return []
        rows = [item for item in assets if str(item.get("media_type") or "") == media_type]
        return [{
            "library_asset_id": str(item.get("library_asset_id") or ""),
            "description": str(item.get("asset_id") or ""),
            "words": [],
            "duration_seconds": item.get("duration_seconds"),
        } for item in rows[:_LIBRARY_FALLBACK_LIMIT]]

    def _library_candidates(instruction: str) -> list[dict]:
        """이 요청에 어울리는 자료실 음악·효과음 후보.

        **owner가 쓰는 것과 같은 의미검색**(`find_audio_matches`)이다. 유진에게
        자료실을 통째로 읽히지 않는 이유는 프롬프트 크기 때문만이 아니다 --
        고르는 일을 잘하려면 목록이 아니라 **추린 것**을 봐야 한다.

        검색이 없거나(임베딩 모델 미설치) 실패하면 빈 목록을 돌려준다. 그때
        유진은 예전처럼 프로젝트 안 자산만 보고 고른다 -- 자료실을 못 본다고
        대화 편집이 통째로 멈추면 안 된다.
        """
        found: list[dict] = []
        # **영상도 함께 훑는다**(2026-09-05). 음악·효과음만 훑던 동안 "도시 거리
        # 걷는 영상 깔아줘"에 유진이 `music-lost-in-city`를 골랐다 -- 고를 영상이
        # 후보에 하나도 없으니 이름이 비슷한 음악을 집은 것이다. 자료실 촬영본은
        # 색인이 장소·시간·날씨를 한국어로 적어 두므로 고를 근거가 이미 있다.
        for media_type in ("music", "sfx", "broll"):
            matches: list[dict] = []
            # **촬영본 색인은 자산이 아닌 행도 돌려준다.** 영상 한 편을 여러
            # 구간으로 쪼갠 행에는 `library_asset_id`가 없어 아래에서 걸러진다.
            # 여덟 개만 뽑으면 그 여덟이 전부 구간일 수 있고, 실제로 그랬다 --
            # 검색을 고친 뒤에도 유진에게 가는 영상 후보가 0개였다(2026-09-05).
            # 넉넉히 뽑아 자산인 것만 세고, 개수는 아래에서 다시 맞춘다.
            wanted = _LIBRARY_SUGGESTION_LIMIT * 3 if media_type == "broll" else _LIBRARY_SUGGESTION_LIMIT
            if library_search is not None:
                try:
                    matches = list(library_search(instruction, wanted, media_type) or [])
                except Exception:
                    _LOGGER.warning("자료실 의미검색이 막혔습니다. 이름만 보고 고르는 쪽으로 떨어집니다.", exc_info=True)
            if not matches:
                # **의미검색이 없어도 자료실은 보인다.** 임베딩 모델이 안 올라와
                # 있으면(이 owner의 LM Studio가 지금 그렇다) 위 검색이 늘 빈손이라,
                # 여기서 멈추면 자료실을 열어 준 것이 화면에서는 아무 일도 안
                # 일어난 것과 같다 -- 이 저장소가 "완료"라고 부르지 않는 상태다.
                #
                # 대신 이름을 그대로 준다. 자료실 이름은 `music-peaceful-drift`처럼
                # 뜻을 담고 있고, 고르는 쪽은 어차피 말을 이해하는 모델이다.
                # 순위가 없으니 개수를 조금 넉넉히 준다.
                matches = _library_assets_by_name(media_type)
            taken = 0
            for match in matches or []:
                library_asset_id = str(match.get("library_asset_id") or "")
                if not library_asset_id:
                    continue
                if taken >= _LIBRARY_SUGGESTION_LIMIT:
                    break
                taken += 1
                found.append({
                    "asset_id": library_asset_id,
                    # 자료실은 `music`이라 부르고 편집본은 `bgm`이라 부른다.
                    # 검증기가 보는 이름으로 맞춰 준다.
                    "asset_type": {"music": "bgm", "sfx": "sfx", "broll": "broll_video"}[media_type],
                    "label": _library_label(match),
                })
        # 유진에게 실제로 몇 개가 갔는지 남긴다. 이게 없어서 "영상 추천이 안
        # 된다"의 원인을 세 겹이나 추측으로 좇았다(2026-09-05) -- 검색 함수,
        # 구간 행, 그리고 세 번째. 종류별 개수 한 줄이면 다음엔 바로 보인다.
        by_type: dict[str, int] = {}
        for item in found:
            by_type[str(item["asset_type"])] = by_type.get(str(item["asset_type"]), 0) + 1
        _LOGGER.info("유진에게 보낸 자료실 후보: %s", by_type or "없음")
        return found

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals", status_code=status.HTTP_201_CREATED)
    def create_yujin_editing_proposal(project_id: str, session_id: str, body: YujinEditingProposalCreateRequest, request: Request) -> dict:
        try:
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_session_missing") from exc
        # **없으면 승인된 것으로 본다.** 이 저장소의 관례가 그것이다 --
        # `media_ranking.py`(추천 후보를 고르는 자리)도, `director_proposal_service.py`
        # (후보를 만드는 자리)도 `metadata.get("review_status", "approved")`로 읽는다.
        # owner가 자기 컴퓨터에서 넣은 파일에는 검토 표시가 애초에 안 붙는다.
        #
        # 여기만 "있고 approved일 때만"이라 **승인 목록이 늘 비어 있었다.**
        # 그러면 `_approved_asset_catalogue`가 "승인된 자산이 없다 --
        # apply_media를 시도하지 마라"를 프롬프트에 싣고, 유진은 규칙대로
        # 거절한다. 2026-09-01 실사용에서 "1번 장면에 어울리는 배경 음악을 넣어
        # 줘"가 정확히 이렇게 막혔다 -- 말로 음악·효과음을 넣는 길이 설계상
        # 지원 동작인데도 한 번도 성공할 수 없었다는 뜻이다.
        #
        # 게이트를 여는 것이 아니다. **명시적으로 `pending`·`rejected`인 자산은
        # 그대로 빠진다** -- 비어 있는 것과 거절된 것을 가르는 것뿐이다.
        approved_assets = tuple(
            item for item in store.list_assets(project_id=project_id)
            if isinstance(item.get("metadata"), dict)
            and str(item["metadata"].get("review_status") or "approved").strip().lower() == "approved"
        )
        library_candidates = _library_candidates(body.instruction)
        context = YujinEditingContext(
            session_id=session_id,
            session_revision=int(session["session_revision"]),
            segment_ids=tuple(str(item["segment_id"]) for item in session.get("segments", []) if isinstance(item, dict) and item.get("segment_id")),
            # **유진에게 지금 자막을 보여 준다.** 안 보여 주면 "짧게 다듬어 줘"에
            # 지금 뭐라고 적혀 있는지 모르는 채로 새 문장을 지어낸다(2026-09-03).
            #
            # 창작자가 보고 있는 언어로 보여 주고, 적용도 그 언어에 한다 --
            # 보는 것과 고치는 것이 다르면 눈에는 아무 일도 안 일어난다.
            caption_language=str(session.get("caption_language") or "") or None,
            # 지금 자막 크기. 없으면 아직 한 번도 안 고친 편집본이라 기본값이다.
            caption_font_size_px=_current_caption_font_size(session),
            captions=tuple(
                (str(item["segment_id"]), text)
                for item in session.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id")
                for text in [caption_text_for_language(item, str(session.get("caption_language") or "") or None).strip()]
                if text
            ),
            approved_asset_ids=tuple(
                [str(item["asset_id"]) for item in approved_assets]
                + [item["asset_id"] for item in library_candidates]
            ),
            approved_asset_types=tuple(
                [(str(item["asset_id"]), str(item["asset_type"])) for item in approved_assets]
                + [(item["asset_id"], item["asset_type"]) for item in library_candidates]
            ),
            # **이름을 같이 준다.** 예전에는 `asset_id(종류)`만 실어서 유진이
            # 고를 근거가 하나도 없었고, 실측(2026-09-01) 결과 장면이 달라도
            # 분위기를 지정해도 **늘 같은 자산 하나**를 집었다. 고르는 일이
            # 이 제품의 차별점인데(`implementation-plan` §4.2) 그 자리에서
            # 아무것도 고르지 않고 있었다는 뜻이다.
            #
            # 새로 읽어 오는 것이 아니라 이미 손에 든 값이다 -- `list_assets`가
            # `metadata`를 통째로 돌려준다.
            approved_asset_labels=tuple(
                [(str(item["asset_id"]), _asset_label(item)) for item in approved_assets]
                + [(item["asset_id"], item["label"]) for item in library_candidates]
            ),
            # 색감은 화면이 깔린 장면에만 걸 수 있다. 모델에게 알려 주고
            # 검증기가 다시 막는다 -- 알려 주지 않으면 지어내고, 지어낸 것은
            # 항상 거절돼서 "말로 보정하기"가 한 번도 성공하지 못한다
            # (`apply_media`의 자산 목록에서 이미 겪은 그 사고다).
            # 소리 정리도 같은 이유로 "깔려 있는 장면"을 알려 준다.
            segment_ids_with_bgm=tuple(
                str(item["segment_id"]) for item in session.get("segments", [])
                if isinstance(item, dict) and isinstance(item.get("music_override"), dict)
                and str(item["music_override"].get("asset_id") or "").strip()
            ),
            segment_ids_with_sfx=tuple(
                str(item["segment_id"]) for item in session.get("segments", [])
                if isinstance(item, dict) and isinstance(item.get("sfx_override"), dict)
                and str(item["sfx_override"].get("asset_id") or "").strip()
            ),
            segment_ids_with_broll=tuple(
                str(item["segment_id"])
                for item in session.get("segments", [])
                if isinstance(item, dict)
                and isinstance(item.get("broll_override"), dict)
                and str(item["broll_override"].get("asset_id") or "").strip()
            ),
        )
        result = YujinEditingProposalService(request.app.state.local_only_runtime_service_factory(store)).create(
            project_id=project_id, instruction=body.instruction, context=context
        )
        if result.proposal is None:
            # `clarification`은 유진이 실제로 물은 말(`result.reply_text`)을 그대로
            # 보인다 -- 코드리뷰(Task 4, 2026-08-26 계획서)로 잡힌 결함: 예전엔
            # 여기서 사용자가 방금 쓴 문장(`body.instruction`)을 그대로 되돌려줘서,
            # 유진이 실제로 무엇을 물었는지 화면에 한 번도 안 보였다. `rejected`는
            # 우리 쪽 검증이 막은 것이라 모델의 말이 지금 상황과 안 맞을 수 있어
            # (`YujinEditingResult.reply_text` 주석 참고) 그대로 두 지 않는다 -- 이
            # 경우엔 `reply_text`가 비어 있으므로 예전 동작(사용자 문장 반사)이
            # 그대로 유지된다(범위는 Task 4와 같이 clarification으로만 좁힌다).
            if result.status == "rejected":
                # **거절 사유가 어디에도 안 남았다**(2026-09-05). 화면에는 창작자
                # 문장을 되비추는 것이 맞지만(위 주석), 그러면 owner도 나도 왜
                # 막혔는지 알 방법이 없다 -- "음악이랑 효과음 같이 넣어줘"가
                # 거절된 이유를 좇다가 이 빈자리를 만났다. 창작자 화면은 그대로
                # 두고 사유만 남긴다.
                _LOGGER.info(
                    "유진의 편집 제안을 검증이 막았습니다 (사유=%s, 시킨 말=%r).",
                    result.reason or "알 수 없음", body.instruction[:120],
                )
            return {"status": result.status, "reply_text": result.reply_text or body.instruction, "proposal": None}
        revision = store.next_director_proposal_revision(project_id)
        proposal = DirectorProposal(
            proposal_id=f"yujin-edit-{__import__('uuid').uuid4().hex}",
            revision_code=f"YE{revision:02d}", revision=revision,
            base_session_revision=context.session_revision,
            asset_index_revision=store.get_asset_index_revision(project_id),
            source_session_id=session_id,
            target_segment_ids=tuple(sorted({str(getattr(item, "segment_id", "")) for item in result.proposal.operations if getattr(item, "segment_id", None)})),
            source_script_segment_ids=(), status="ready",
            diff={"proposal_mode": "yujin_editing_candidate_v1", "operations": [item.model_dump(mode="json") for item in result.proposal.operations], "follow_up_questions": _editing_follow_ups(result.proposal.operations)},
            expires_at=None, candidates=(),
        )
        store.save_director_proposal(project_id, proposal)
        return payload(project_id, proposal)

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals/{proposal_id}/preflight")
    def preflight_yujin_editing_proposal(project_id: str, session_id: str, proposal_id: str) -> dict:
        try:
            proposal = store.get_director_proposal(project_id, proposal_id)
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_proposal_missing") from exc
        if proposal.source_session_id != session_id or proposal.base_session_revision != int(session["session_revision"]):
            return JSONResponse(status_code=409, content={"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."})
        return {"proposal_id": proposal_id, "status": "ready", "diff": proposal_to_payload(proposal)["diff"]}

    def _proposal_preview_payload(project_id: str, record: dict) -> dict:
        state = "stale" if record.get("state") == "obsolete" else str(record.get("state") or "failed")
        return {"status": state, "generation_id": str(record["generation_id"]), "proposal_id": str(record["proposal_id"]), "artifact_revision": int(record["expected_revision"]), "fingerprint": str(record["fingerprint"]), "content_url": f"/api/projects/{project_id}/proposal-previews/{record['generation_id']}/content" if state == "succeeded" and record.get("artifact_uri") else None, "error_message": record.get("error_message")}

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals/{proposal_id}/preview", status_code=status.HTTP_202_ACCEPTED)
    def preview_yujin_editing_proposal(project_id: str, session_id: str, proposal_id: str):
        try:
            proposal = store.get_director_proposal(project_id, proposal_id)
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_proposal_missing") from exc
        if proposal.source_session_id != session_id or int(proposal.base_session_revision) != int(session["session_revision"]):
            return JSONResponse(status_code=409, content={"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."})
        try:
            record = orchestrator.pipeline.start_proposal_preview(project_id=project_id, session_id=session_id, proposal_id=proposal_id)
            Thread(target=orchestrator.pipeline.run_proposal_preview, kwargs={"project_id": project_id, "generation_id": record["generation_id"]}, daemon=True).start()
            return _proposal_preview_payload(project_id, record)
        except EditingSessionRevisionConflict:
            return JSONResponse(status_code=409, content={"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."})
        except ValueError as exc:
            if str(exc) == "editing_proposal_needs_refresh":
                return JSONResponse(status_code=409, content={"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."})
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/projects/{project_id}/proposal-previews/{generation_id}")
    def get_yujin_editing_proposal_preview(project_id: str, generation_id: str):
        try:
            record = orchestrator.pipeline.get_proposal_preview_status(project_id=project_id, generation_id=generation_id)
            if record.get("state") == "obsolete":
                return JSONResponse(status_code=409, content={"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."})
            return _proposal_preview_payload(project_id, record)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="proposal_preview_missing") from exc

    @router.get("/api/projects/{project_id}/proposal-previews/{generation_id}/content")
    def get_yujin_editing_proposal_preview_content(project_id: str, generation_id: str):
        try:
            record = orchestrator.pipeline.get_proposal_preview_status(project_id=project_id, generation_id=generation_id)
            if record.get("state") == "obsolete":
                return JSONResponse(status_code=409, content={"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."})
            if record.get("state") != "succeeded" or not record.get("artifact_uri"):
                raise KeyError("proposal_preview_not_current")
            path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(record["artifact_uri"]))
            if not path.is_file(): raise KeyError("proposal_preview_content_missing")
            return FileResponse(path, media_type="video/mp4")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="proposal_preview_not_current") from exc

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals/{proposal_id}/apply")
    def apply_yujin_editing_proposal_route(project_id: str, session_id: str, proposal_id: str, body: YujinEditingProposalApplyRequest) -> dict:
        try:
            proposal = store.get_director_proposal(project_id, proposal_id)
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            if proposal.source_session_id != session_id or proposal.base_session_revision != body.expected_revision or int(session["session_revision"]) != body.expected_revision:
                raise HTTPException(status_code=409, detail="editing_proposal_needs_refresh")
            from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal
            operations = proposal.diff.get("operations") if hasattr(proposal.diff, "get") else None
            if not isinstance(operations, (list, tuple)):
                raise ValueError("editing_proposal_operations_required")
            editing = YujinEditingProposal.model_validate({
                "proposal_id": proposal_id,
                "base_session_revision": proposal.base_session_revision,
                "operations": [_with_materialized_library_asset(project_id, dict(item)) for item in operations],
            })
            updated = apply_yujin_editing_proposal(session=session, proposal=editing)
            return store.update_editing_session(project_id=project_id, session_id=session_id, session_payload=updated, expected_revision=body.expected_revision)
        except HTTPException:
            raise
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/projects/{project_id}/director/sessions/{session_id}/reload")
    def reload_session(project_id: str, session_id: str) -> dict:
        """Read durable Director state only; a reload must never create or mutate it."""
        try:
            store.get_editing_session(project_id=project_id, session_id=session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_session_missing") from exc
        conversation = store.latest_director_conversation(project_id=project_id, session_id=session_id)
        proposal = next((item for item in reversed(store.list_director_proposals(project_id)) if item.source_session_id == session_id), None)
        messages = store.list_director_messages(project_id=project_id, conversation_id=str(conversation["conversation_id"])) if conversation else []
        return {
            "conversation": conversation,
            "messages": messages,
            "proposal": payload(project_id, proposal) if proposal else None,
            "references": [
                {
                    "reference_code": str(item["reference_code"]),
                    "immutable_id": {
                        "segment_id": str(item["segment_id"]),
                        "track_type": str(item["track_type"]),
                    },
                    "source": "timeline",
                }
                for item in director_timeline_references(
                    store.get_editing_session(project_id=project_id, session_id=session_id)
                ).get("segments", [])
            ],
        }

    @router.post("/api/projects/{project_id}/director/conversations", status_code=status.HTTP_201_CREATED, response_model=DirectorConversationResponse)
    def create_conversation(project_id: str, body: DirectorConversationCreateRequest) -> dict:
        try:
            conversation_id = __import__("uuid").uuid4().hex
            return store.create_director_conversation(project_id=project_id, session_id=body.session_id, conversation_id=conversation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_session_missing") from exc

    @router.get("/api/projects/{project_id}/director/conversations")
    def list_conversations(project_id: str) -> dict:
        """대화가 쌓이기만 하고 지울 방법이 없었다 -- 점검 시점에 28건이었다.
        지우려면 무엇이 있는지부터 보여야 한다."""
        return {"conversations": store.list_director_conversations(project_id=project_id)}

    @router.delete(
        "/api/projects/{project_id}/director/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_conversation(project_id: str, conversation_id: str) -> None:
        # 지울 것이 없으면 지웠다고 하지 않는다. 목록이 그대로인 이유를
        # owner가 알 수 있어야 한다.
        if not store.delete_director_conversation(
            project_id=project_id, conversation_id=conversation_id
        ):
            raise HTTPException(status_code=404, detail="director_conversation_missing")

    @router.get("/api/projects/{project_id}/director/conversations/{conversation_id}/messages", response_model=DirectorMessageListResponse)
    def list_conversation_messages(project_id: str, conversation_id: str, session_id: str) -> dict:
        try:
            conversation = store.get_director_conversation(project_id=project_id, conversation_id=conversation_id)
            if str(conversation["session_id"]) != session_id:
                raise KeyError("director_conversation_missing")
            return {"messages": store.list_director_messages(project_id=project_id, conversation_id=conversation_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="director_conversation_missing") from exc

    @router.post(
        "/api/projects/{project_id}/director/conversations/{conversation_id}/messages",
        response_model=DirectorMessageExchangeResponse,
        responses={202: {"description": "A duplicate client message is still generating locally; retry after the Retry-After header."}},
    )
    def submit_conversation_message(project_id: str, conversation_id: str, body: DirectorMessageSubmitRequest, request: Request) -> dict:
        try:
            store.get_editing_session(project_id=project_id, session_id=body.session_id)
            conversation = store.get_director_conversation(project_id=project_id, conversation_id=conversation_id)
            if str(conversation["session_id"]) != body.session_id:
                raise KeyError("director_conversation_missing")
            existing = store.get_director_exchange_by_client_message_id(
                project_id=project_id, conversation_id=conversation_id,
                session_id=body.session_id,
                client_message_id=body.client_message_id, user_text=body.text,
            )
            if existing is not None:
                return existing | dict(existing["assistant_message"].get("metadata") or {})
            owner_token = store.claim_director_message(
                project_id=project_id, session_id=body.session_id, conversation_id=conversation_id,
                client_message_id=body.client_message_id, user_text=body.text,
            )
            if not owner_token:
                # Generation may use the full 30-second local-runtime request
                # budget.  A duplicate is therefore immediately retryable,
                # rather than waiting a shorter, contradictory server timeout.
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"status": "director_message_in_progress", "retry_after_seconds": 1},
                    headers={"Retry-After": "1"},
                )
            session = store.get_editing_session(project_id=project_id, session_id=body.session_id)
            proposals = [proposal for proposal in store.list_director_proposals(project_id) if proposal.source_session_id == body.session_id and proposal.status == "ready"]
            open_proposal = proposal_to_payload(proposals[-1]) if proposals else None
            resolution = resolve_director_command(body.text, open_proposal=open_proposal, timeline=director_timeline_references(session))
            resolution_metadata: dict[str, object] = {}
            proposal_id: str | None = open_proposal["proposal_id"] if open_proposal else None
            if resolution.status == "needs_disambiguation":
                resolution_metadata["disambiguation"] = {
                    "status": "needs_disambiguation",
                    "options": [{"reference_code": option.reference_code, "immutable_id": option.immutable_id, "source": option.source} for option in resolution.options],
                }
                assistant_text = "어느 참조인지 선택해주세요."
            elif resolution.status == "resolved" and resolution.reference is not None:
                resolution_metadata["reference"] = {"reference_code": resolution.reference.reference_code, "immutable_id": resolution.reference.immutable_id, "source": resolution.reference.source}
                assert resolution.action_intent is not None
                resolution_metadata["action_intent"] = {
                    "action": resolution.action_intent.action,
                    "target": {
                        "reference_code": resolution.action_intent.target.reference_code,
                        "immutable_id": resolution.action_intent.target.immutable_id,
                        "source": resolution.action_intent.target.source,
                    },
                    "proposal_preflight": resolution.action_intent.proposal_preflight,
                }
                assistant_text = "참조를 확인했습니다."
            else:
                assistant_text = ""
            # Generate before opening the persistence writer transaction.  No
            # fallback graph is present: only the app-injected local runtime is used.
            if not assistant_text:
                runtime = request.app.state.local_only_runtime_service_factory(store)
                conversation_service = YujinLocalConversationService(runtime=runtime)
                stop_heartbeat = Event()
                def heartbeat() -> None:
                    while not stop_heartbeat.wait(1.0):
                        store.heartbeat_director_message_claim(project_id=project_id, conversation_id=conversation_id, client_message_id=body.client_message_id, owner_token=owner_token)
                heartbeat_thread = Thread(target=heartbeat, daemon=True)
                heartbeat_thread.start()
                try:
                    result = conversation_service.reply(
                        project_id=project_id,
                        user_text=body.text,
                        memories=_approved_memories(
                            request,
                            project_id=project_id,
                            conversation_id=conversation_id,
                            query=body.text,
                        ),
                        project_context=_project_context(
                            store, project_id=project_id, session=session
                        ),
                    )
                    assistant_text = result.reply
                    if result.status == "blocked":
                        resolution_metadata.update({
                            "status": "blocked",
                            "error_code": result.blocked_reason or "policy_restricted_intent",
                        })
                except Exception as exc:
                    assistant_text = f"local_only_blocked: {exc}"
                    trace = getattr(exc, "provider_trace", None)
                    safe_trace = trace if isinstance(trace, dict) and trace.get("routing_mode") == "local_only" else build_provider_trace(
                        final_provider=str(getattr(exc, "provider_name", "local_only_runtime")),
                        fallback_reasons=["local_provider_error"], routing_mode="local_only",
                    )
                    resolution_metadata.update({
                        "status": "blocked",
                        "error_code": str(getattr(exc, "error_code", "local_runtime_error")),
                        "provider_trace": safe_trace,
                    })
                finally:
                    stop_heartbeat.set()
                    heartbeat_thread.join(timeout=1.5)
            exchange = store.append_director_exchange(
                project_id=project_id, session_id=body.session_id, conversation_id=conversation_id,
                client_message_id=body.client_message_id, user_text=body.text, assistant_text=assistant_text,
                proposal_id=proposal_id, assistant_metadata=resolution_metadata, owner_token=owner_token,
            )
            return exchange | resolution_metadata
        except KeyError as exc:
            detail = str(exc).strip("'")
            raise HTTPException(status_code=404, detail=detail) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/projects/{project_id}/director/proposals", status_code=status.HTTP_201_CREATED)
    def create(project_id: str, body: ProposalCreateRequest) -> dict:
        try:
            return payload(project_id, service.create(project_id=project_id, session_id=body.session_id, expires_at=body.expires_at, media_types=media_focus_for_request(body.request_text)))
        except DirectorProposalBlockedError as exc:
            return JSONResponse(status_code=409, content={"code": "director_analysis_blocked", "lifecycle": exc.lifecycle})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/projects/{project_id}/director/proposals/{proposal_id}")
    def get(project_id: str, proposal_id: str) -> dict:
        try:
            return payload(project_id, service.get(project_id=project_id, proposal_id=proposal_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/preflight")
    def preflight(project_id: str, proposal_id: str) -> dict:
        try:
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        require_ready(proposal)
        reasons = service.stale_reasons(project_id=project_id, proposal=proposal)
        immutable_diff = proposal_to_payload(proposal)["diff"]
        if reasons:
            return JSONResponse(status_code=409, content={"code": "stale_proposal", "stale_reasons": reasons, "action": "refresh", "diff": immutable_diff})
        return {"proposal_id": proposal.proposal_id, "status": "ready", "reasons": [], "diff": immutable_diff}

    def candidate_for(project_id: str, proposal_id: str, candidate_id: str):
        proposal = service.get(project_id=project_id, proposal_id=proposal_id)
        require_ready(proposal)
        if service.stale_reasons(project_id=project_id, proposal=proposal):
            raise HTTPException(status_code=409, detail="stale_proposal")
        candidate = next((item for item in proposal.candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise HTTPException(status_code=404, detail="candidate_missing")
        require_actionable_yujin_candidate(proposal, candidate)
        require_current_yujin_source(
            store=store,
            project_id=project_id,
            proposal=proposal,
            candidate=candidate,
        )
        return candidate

    @router.get("/api/projects/{project_id}/director/proposals/{proposal_id}/candidates/{candidate_id:path}/preview")
    def preview_candidate(project_id: str, proposal_id: str, candidate_id: str):
        try:
            candidate = candidate_for(project_id, proposal_id, candidate_id)
            source = materializer.preview_snapshot(project_id=project_id, candidate=candidate)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=_apply_failure_detail(exc)) from exc
        return FileResponse(source, media_type=_mime_type(source), background=BackgroundTask(_remove_preview_snapshot, source), headers={"X-VideoBox-Proposal-Controls": json.dumps(dict(candidate.controls), sort_keys=True), "X-VideoBox-Autoplay": "false", "X-VideoBox-In-Sec": str(candidate.controls.get("in_sec", "")), "X-VideoBox-Out-Sec": str(candidate.controls.get("out_sec", ""))})

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/candidates/{candidate_id:path}/materialize", status_code=status.HTTP_201_CREATED)
    def materialize_candidate(project_id: str, proposal_id: str, candidate_id: str) -> dict:
        try:
            candidate = candidate_for(project_id, proposal_id, candidate_id)
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
            require_ready(proposal)
            return materializer.materialize(project_id=project_id, candidate=candidate, expected_asset_index_revision=proposal.asset_index_revision)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=_apply_failure_detail(exc)) from exc

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/refresh", status_code=status.HTTP_201_CREATED)
    def refresh(project_id: str, proposal_id: str) -> dict:
        try:
            return payload(project_id, service.refresh(project_id=project_id, proposal_id=proposal_id))
        except DirectorProposalBlockedError as exc:
            # **`create`와 같은 말을 한다(2026-09-04).** `refresh`는 안에서 `create`를
            # 다시 부르므로(`director_proposal_service.py:151`) 같은 예외가 나는데,
            # 위 `create` 라우터만 이걸 409로 옮기고 여기는 안 잡았다 -- 편집기가
            # 자동으로 부르는 이 경로가 **500 Internal Server Error**를 냈다
            # (2026-09-04 역방향 검증, 실제 브라우저에서 확인).
            #
            # 이 예외는 고장이 아니라 "분석이 아직 안 됐다"는 안내다 --
            # `recovery_action`까지 들고 있다. 500으로 새면 화면은 "무언가 터졌다"만
            # 알고 창작자에게 무엇을 하라고 말할 수 없다.
            return JSONResponse(status_code=409, content={"code": "director_analysis_blocked", "lifecycle": exc.lifecycle})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/apply")
    def apply(project_id: str, proposal_id: str, body: ProposalApplyRequest) -> dict:
        try:
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
            require_ready(proposal)
            reject_yujin_direct_apply(proposal)
            if proposal.base_session_revision != body.expected_revision:
                raise HTTPException(status_code=409, detail="proposal_revision_mismatch")
            candidates = {item.candidate_id: item for item in proposal.candidates}
            selected = [candidates[item] for item in body.candidate_ids]
            for candidate in selected:
                require_actionable_yujin_candidate(proposal, candidate)
            materialized: dict[str, dict] = {}
            current_asset_index_revision = store.get_asset_index_revision(project_id)
            for candidate in selected:
                candidates_for_id = [
                    asset for asset in store.list_assets(project_id=project_id)
                    if dict(asset.get("metadata") or {}).get("director_proposal_candidate_id") == candidate.candidate_id
                ]
                found = next(
                    (
                        asset for asset in reversed(candidates_for_id)
                        if dict(asset.get("metadata") or {}).get("director_materialized_sha256") == candidate.expected_content_sha256
                        and dict(asset.get("metadata") or {}).get("source_asset_id") == candidate.asset_id
                        and dict(asset.get("metadata") or {}).get("director_materialized_asset_index_revision") == current_asset_index_revision
                    ),
                    None,
                )
                if found is None:
                    if candidates_for_id:
                        raise HTTPException(status_code=409, detail="asset_index_revision_mismatch")
                    raise ValueError("candidate_not_materialized")
                metadata = dict(found.get("metadata") or {})
                if metadata.get("director_materialized_asset_index_revision") != current_asset_index_revision:
                    raise HTTPException(status_code=409, detail="asset_index_revision_mismatch")
                path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(found["storage_uri"]))
                if not path.is_file() or sha256_file(path) != candidate.expected_content_sha256:
                    raise ValueError("materialized_sha_mismatch")
                materialized[candidate.candidate_id] = found
            session = store.get_editing_session(project_id=project_id, session_id=proposal.source_session_id)
            if int(session.get("session_revision") or 1) != body.expected_revision:
                raise HTTPException(status_code=409, detail="session_revision_mismatch")
            def mutate(draft: dict) -> None:
                by_id = {str(segment.get("segment_id")): segment for segment in draft.get("segments", []) if isinstance(segment, dict)}
                for candidate in selected:
                    target = next((item.get("target_segment_id") for item in proposal.diff.get("placements", {}).get("add", []) if item.get("candidate_id") == candidate.candidate_id), None)
                    segment = by_id.get(str(target))
                    if segment is None:
                        raise ValueError("target_segment_missing")
                    key = {"broll": "broll_override", "bgm": "music_override", "sfx": "sfx_override"}[candidate.media_type]
                    asset = materialized[candidate.candidate_id]
                    segment[key] = {"asset_id": asset["asset_id"], "asset_uri": asset["storage_uri"], "media_controls": dict(candidate.controls), "expected_content_sha256": candidate.expected_content_sha256, "media_revision": str(asset.get("created_at") or ""), "warning_provenance": list(candidate.warning_provenance)}
            updated = apply_user_transaction(session=session, label="디렉터 제안 적용", affected_segment_ids=list(proposal.target_segment_ids), mutate=mutate)
            expectations = [
                (str(materialized[item.candidate_id]["asset_id"]), item.expected_content_sha256,
                 int(dict(materialized[item.candidate_id].get("metadata") or {})["director_materialized_asset_index_revision"]))
                for item in selected
            ]
            return store.apply_director_proposal_transaction(project_id=project_id, session_id=proposal.source_session_id, proposal_id=proposal_id, session_payload=updated, expected_revision=body.expected_revision, proposal_base_revision=proposal.base_session_revision, materialized_expectations=expectations)
        except HTTPException:
            raise
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=_apply_failure_detail(exc)) from exc
        except EditingSessionRevisionConflict:
            raise HTTPException(status_code=409, detail="session_revision_mismatch") from None

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/batch-apply")
    def batch_apply(project_id: str, proposal_id: str, body: ProposalBatchApplyRequest) -> dict:
        """Stage all requested bytes, then atomically register and apply them in one CAS write."""
        staged: list[dict] = []
        try:
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
            require_ready(proposal)
            reject_yujin_direct_apply(proposal)
            if proposal.base_session_revision != body.expected_revision:
                raise HTTPException(status_code=409, detail="proposal_revision_mismatch")
            if service.stale_reasons(project_id=project_id, proposal=proposal):
                raise HTTPException(status_code=409, detail="stale_proposal")
            candidates_by_id = {item.candidate_id: item for item in proposal.candidates}
            if len(set(body.candidate_ids)) != len(body.candidate_ids):
                raise ValueError("candidate_ids_duplicate")
            selected = [candidates_by_id[item] for item in body.candidate_ids]
            for candidate in selected:
                require_actionable_yujin_candidate(proposal, candidate)
            if is_yujin_variant_proposal(proposal):
                if len(selected) < 1:
                    raise ValueError("variant_candidate_required")
                variant_id = str(proposal.diff.get("variant_id") or "")
                expected_variant_revision = int(proposal.diff.get("base_variant_revision") or 0)
                current = OutputVariant.model_validate(
                    store.get_output_variant(project_id=project_id, variant_id=variant_id)
                )
                if (
                    current.source_session_id != proposal.source_session_id
                    or current.source_session_revision != proposal.base_session_revision
                    or current.variant_revision != expected_variant_revision
                ):
                    raise HTTPException(status_code=409, detail="stale_variant_proposal")
                merged_overrides: dict[str, object] = {}
                for candidate in selected:
                    candidate_patch = variant_patch_from_yujin_candidate(candidate)
                    merged_overrides.update(dict(candidate_patch["overrides"]))
                updated = apply_variant_patch(
                    current,
                    {"overrides": merged_overrides},
                    expected_variant_revision=expected_variant_revision,
                )
                variant = store.apply_director_variant_proposal_transaction(
                    project_id=project_id,
                    proposal_id=proposal_id,
                    variant_id=variant_id,
                    expected_variant_revision=expected_variant_revision,
                    variant=updated,
                )
                return {"proposal_id": proposal_id, "status": "applied", "variant": variant}
            staged, materialized = materializer.stage_batch(project_id=project_id, candidates=selected)
            session = store.get_editing_session(project_id=project_id, session_id=proposal.source_session_id)
            if int(session.get("session_revision") or 1) != body.expected_revision:
                raise HTTPException(status_code=409, detail="session_revision_mismatch")
            placements = {str(item.get("candidate_id")): str(item.get("target_segment_id")) for item in proposal.diff.get("placements", {}).get("add", [])}
            def mutate(draft: dict) -> None:
                by_id = {str(segment.get("segment_id")): segment for segment in draft.get("segments", []) if isinstance(segment, dict)}
                for candidate in selected:
                    segment = by_id.get(placements.get(candidate.candidate_id, ""))
                    if segment is None:
                        raise ValueError("target_segment_missing")
                    key = {"broll": "broll_override", "bgm": "music_override", "sfx": "sfx_override"}[candidate.media_type]
                    asset = materialized[candidate.candidate_id]
                    segment[key] = {"asset_id": asset["asset_id"], "asset_uri": asset["storage_uri"], "media_controls": dict(candidate.controls), "expected_content_sha256": candidate.expected_content_sha256, "media_revision": asset["created_at"], "warning_provenance": list(candidate.warning_provenance)}
            updated = apply_user_transaction(session=session, label="디렉터 제안 일괄 적용", affected_segment_ids=[placements[item.candidate_id] for item in selected], mutate=mutate)
            return store.batch_apply_director_proposal_transaction(
                project_id=project_id, session_id=proposal.source_session_id, proposal_id=proposal_id,
                session_payload=updated, expected_revision=body.expected_revision, proposal_base_revision=proposal.base_session_revision,
                expected_asset_index_revision=proposal.asset_index_revision, staged_assets=staged,
            )
        except HTTPException:
            raise
        except EditingSessionRevisionConflict:
            raise HTTPException(status_code=409, detail="stale_proposal") from None
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=_apply_failure_detail(exc)) from exc
        finally:
            materializer.cleanup_staged(staged)

    @router.get("/api/projects/{project_id}/director/preferences")
    def get_preferences(project_id: str) -> dict:
        return store.get_director_preferences(project_id)

    @router.put("/api/projects/{project_id}/director/preferences")
    def put_preferences(project_id: str, body: PreferencesRequest) -> dict:
        return store.save_director_preferences(project_id, body.model_dump(exclude_unset=True))

    return router


def require_ready(proposal) -> None:
    if proposal.status != "ready":
        raise HTTPException(status_code=409, detail="proposal_not_ready")


def _editing_follow_ups(operations: tuple[object, ...]) -> list[str]:
    intent = str(getattr(operations[0], "intent", "")) if operations else ""
    values = {
        "set_scene_speed": ("원래 속도로 되돌려 볼까요?", "앞뒤 장면도 같은 속도로 맞출까요?", "이 구간만 미리 볼까요?"),
        "apply_media": ("다른 분위기로 찾아볼까요?", "이 장면부터만 바꿀까요?", "효과음도 함께 넣을까요?"),
        "set_scene_look": ("원래 색으로 되돌려 볼까요?", "앞뒤 장면도 같은 색감으로 맞출까요?", "이 구간만 미리 볼까요?"),
        "set_caption_font": ("다른 글꼴도 보여 드릴까요?", "글자 크기도 같이 맞출까요?", "원래 글꼴로 되돌릴까요?"),
    }.get(intent, ())
    return [item for item in values if item][:3]


def require_actionable_yujin_candidate(proposal, candidate) -> None:
    if proposal.diff.get("proposal_mode") not in {
        "yujin_actionable_media_v1",
        "yujin_actionable_v1",
    }:
        return
    if not is_actionable_yujin_media_candidate(candidate):
        if is_yujin_variant_proposal(proposal) and (
            candidate.media_type == "output_variant"
            and candidate.availability == "actionable"
            and candidate.review_status == "approved"
            and candidate.canonical_metadata.get("yujin_actionable_variant") is True
        ):
            return
        raise HTTPException(status_code=422, detail="candidate_unavailable")


def reject_yujin_direct_apply(proposal) -> None:
    if is_yujin_variant_proposal(proposal):
        return
    if proposal.diff.get("proposal_mode") in {
        "yujin_actionable_media_v1",
        "yujin_actionable_v1",
    }:
        raise HTTPException(
            status_code=422,
            detail="yujin_direct_apply_forbidden",
        )


def is_yujin_variant_proposal(proposal) -> bool:
    return (
        proposal.diff.get("proposal_mode") in {"yujin_actionable_v1", "yujin_actionable_media_v1"}
        and proposal.diff.get("variant_id") is not None
        and any(candidate.media_type == "output_variant" for candidate in proposal.candidates)
    )


def require_current_yujin_source(*, store, project_id, proposal, candidate) -> None:
    if proposal.diff.get("proposal_mode") not in {
        "yujin_actionable_media_v1",
        "yujin_actionable_v1",
    }:
        return
    try:
        asset = store.get_asset(project_id=project_id, asset_id=candidate.asset_id)
        actual_type = str(asset.get("asset_type") or "")
        claimed_source_kind = str(
            candidate.canonical_metadata.get("source_media_kind") or ""
        )
        expected_type_matches = actual_type == claimed_source_kind
        source = store.resolve_storage_uri(
            project_id=project_id,
            storage_uri=str(asset["storage_uri"]),
        )
        if (
            not expected_type_matches
            or str(asset.get("created_at") or "") != candidate.media_revision
            or not source.is_file()
            or (
                candidate.expected_content_sha256 is not None
                and sha256_file(source) != candidate.expected_content_sha256
            )
        ):
            raise ValueError("candidate_source_stale")
    except (KeyError, OSError, TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="candidate_unavailable",
        ) from None


def _mime_type(path) -> str | None:
    return {".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4"}.get(path.suffix.lower())


def _remove_preview_snapshot(path) -> None:
    if path.exists():
        os.remove(path)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        os.rmdir(parent)
