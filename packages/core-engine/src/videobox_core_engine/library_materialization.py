"""자료실 자산 하나를 프로젝트로 들여오는 한 걸음.

`snapshot → materialize → 스냅숏 정리`는 순서와 뒷정리가 정해져 있다. 스냅숏을
지우지 않으면 임시 파일이 쌓이고, 지우는 것을 성공 경로에만 두면 실패했을 때
남는다. 그래서 `finally`가 필요하고, 그 묶음이 **두 벌이 되면 한쪽만 고쳐진다.**

부르는 자리가 둘이다.

- 화면에서 자료실 자산을 프로젝트로 가져올 때(`media_library` 라우터).
- 유진이 말로 고른 자산을 적용할 때(`director_proposals` 라우터, 2026-09-01).

두 자리의 **나머지**는 다르다 -- 화면 쪽은 최근 사용 표시와 장면 분석까지 걸고,
유진 쪽은 편집안 적용 안에서 조용히 들여오기만 한다. 그래서 공통인 이 세 걸음만
여기 둔다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def materialize_library_asset(
    *,
    library_store: Any,
    materializer: Any,
    project_id: str,
    library_asset_id: str,
    mime_type_for: Any,
) -> dict[str, Any] | None:
    """자료실 자산을 이 프로젝트의 자산으로. 못 들여오면 ``None``.

    이미 들여온 것이면 `materialize_verified_library_snapshot`이 그대로 돌려준다
    (프로젝트·SHA당 한 번). 그래서 같은 곡을 두 장면에 깔아도 파일이 두 벌
    생기지 않는다.

    **터뜨리지 않고 ``None``을 돌려준다.** 부르는 두 자리가 실패를 다르게
    다뤄야 하기 때문이다 -- 화면은 422로 답해야 하고, 편집안 적용은 그 한
    자산만 건너뛰고 나머지를 살릴 수 있어야 한다.
    """
    try:
        snapshot = library_store.snapshot_verified_asset(library_asset_id=library_asset_id)
    except Exception:
        return None
    if snapshot is None:
        return None
    library_asset, snapshot_path = snapshot
    try:
        return materializer.materialize_verified_library_snapshot(
            project_id=project_id,
            library_asset_id=library_asset_id,
            library_asset=library_asset,
            snapshot_path=snapshot_path,
            mime_type=mime_type_for(Path(snapshot_path)),
        )
    except Exception:
        return None
    finally:
        # 성공하든 실패하든 스냅숏은 지운다. 성공 경로에만 두면 실패했을 때 남는다.
        try:
            library_store.remove_verified_snapshot(snapshot_path)
        except Exception:
            pass


__all__ = ["materialize_library_asset"]
