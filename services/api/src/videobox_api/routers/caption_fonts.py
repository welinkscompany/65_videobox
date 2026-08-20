"""고를 수 있는 자막 글꼴과, 자주 쓰는 글꼴을 위로 올리는 데 필요한 것들.

목록은 `videobox_domain_models.caption_fonts` 한 곳에만 있다. 화면은 여기서
받아 쓰고 따로 들고 있지 않는다 -- 두 벌을 두면 이미지에 든 글꼴과 화면이
반드시 어긋나고, 그러면 owner는 없는 글꼴을 고른 뒤 완성본에서야 안다.

주소가 프로젝트 아래가 아닌 것은 일부러다. 글꼴 취향은 프로젝트가 아니라
사람에게 붙는다. 저장한 포맷(`/api/format-templates`)이 같은 이유로 이미
사용자 단위에 있다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from videobox_domain_models.caption_fonts import (
    DEFAULT_CAPTION_FONT_FAMILY,
    caption_font_catalog,
    is_installed_caption_font,
)
from videobox_storage.user_library_store import UserLibraryStore


class CaptionFontFavoriteRequest(BaseModel):
    enabled: bool


def build_caption_fonts_router(store: UserLibraryStore) -> APIRouter:
    router = APIRouter()

    def _require_installed(family: str) -> None:
        # 없는 글꼴을 담아 두면 다음에 골랐을 때 조용히 다른 글꼴로 떨어진다.
        # 담기는 자리에서 막는 것이 가장 싸다.
        if not is_installed_caption_font(family):
            raise HTTPException(status_code=422, detail="설치되지 않은 글꼴이에요.")

    @router.get("/api/caption-fonts")
    def list_caption_fonts() -> dict[str, Any]:
        """목록·즐겨찾기·최근을 한 번에 준다.

        화면이 나눠 부르면 그중 하나만 실패해도 글꼴을 아예 못 고르게 된다.
        """
        return {
            "fonts": caption_font_catalog(),
            "default_family": DEFAULT_CAPTION_FONT_FAMILY,
            "favorites": store.list_favorite_fonts(),
            "recents": store.list_recent_font_families(),
        }

    @router.put("/api/caption-fonts/{family}/favorite")
    def toggle_caption_font_favorite(family: str, payload: CaptionFontFavoriteRequest) -> dict[str, Any]:
        _require_installed(family)
        return {"favorites": store.toggle_favorite_font(family=family, enabled=payload.enabled)}

    @router.put("/api/caption-fonts/{family}/recent")
    def mark_recent_caption_font(family: str) -> dict[str, Any]:
        _require_installed(family)
        return {"recents": store.mark_recent_font(family=family)}

    return router
