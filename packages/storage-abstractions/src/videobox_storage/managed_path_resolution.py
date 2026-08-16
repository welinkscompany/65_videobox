"""관리 중인 root 안에서 파일을 찾되, 내용 해시로 신원을 확인한다.

이 검사는 두 곳에서 똑같이 필요했고 실제로 두 벌로 복제돼 있었다 --
`services/api`의 자산 다운로드/미리보기 경로와 `core-engine`의 라이브러리 백필.
보안에 직결되는 검사(설정된 root 밖으로 나가지 않는가, 바이트가 우리가 아는 그
파일이 맞는가)가 두 벌이면 한쪽만 고쳐지고 다른 쪽은 남는다. 실제로 한쪽에만
`root.resolve()`가 빠져 있어, 데이터 루트가 심볼릭 링크인 배포본에서는 멀쩡한
파일도 영영 못 찾는 상태였다. 그래서 한 곳으로 모은다.

**실패 이유를 구분해서 돌려준다.** 부르는 쪽이 둘을 다르게 다뤄야 하기 때문이다 --
"root를 벗어났다"는 저장된 경로 자체가 잘못된 것이고, "못 찾았다"는 파일이
사라졌거나 내용이 바뀐 것이다. API는 앞을 422, 뒤를 404로 답한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from videobox_storage._store_media_analysis import sha256_file


@dataclass(frozen=True, slots=True)
class ManagedPathResolution:
    """`path`가 있으면 확인된 파일이다. 없으면 `escaped`로 이유를 가른다."""

    path: Path | None
    escaped: bool

    @property
    def found(self) -> bool:
        return self.path is not None


def resolve_managed_path(
    *, roots: Iterable[Path], relative_path: str, content_sha256: str
) -> ManagedPathResolution:
    """root들을 훑어 `relative_path`가 가리키는 검증된 파일을 찾는다.

    root 자체도 `resolve()`한다. 이걸 빠뜨리면 root가 심볼릭 링크로 마운트된
    환경(컨테이너 볼륨에서 흔하다)에서 candidate만 정규화돼 서로 어긋나고,
    실제로 존재하는 파일이 매번 "root 밖"으로 잘못 판정된다.
    """
    escaped = False
    for root in roots:
        resolved_root = Path(root).resolve()
        candidate = (resolved_root / relative_path).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            escaped = True
            continue
        if candidate.is_file() and sha256_file(candidate) == content_sha256:
            return ManagedPathResolution(path=candidate, escaped=False)
    return ManagedPathResolution(path=None, escaped=escaped)


def resolve_verified_path(
    *, roots: Iterable[Path], relative_path: str, content_sha256: str
) -> Path | None:
    """실패 이유를 구분할 필요가 없는 호출부를 위한 얇은 형태."""
    return resolve_managed_path(roots=roots, relative_path=relative_path, content_sha256=content_sha256).path


__all__ = ["ManagedPathResolution", "resolve_managed_path", "resolve_verified_path", "sha256_file"]
