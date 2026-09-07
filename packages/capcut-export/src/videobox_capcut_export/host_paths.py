"""컨테이너가 보는 경로를 **이 컴퓨터(호스트)** 경로로 바꿔 적는다.

캡컷 초안(`draft_content.json`) 안의 소재 경로는 초안을 만든 쪽이 보는 경로로
적힌다. 컨테이너가 만들면 `/videobox-data/projects/.../assets/imported/xxx.jpg`가
되는데, **윈도우 캡컷은 그 경로를 못 읽는다.**

그런데 그 `/videobox-data`는 실제로 이 컴퓨터의 폴더를 그대로 연결한 것이다
(compose의 bind mount). 즉 **같은 파일을 서로 다른 이름으로 부르고 있을 뿐이라,
경로 문자열만 바꿔 주면 캡컷이 소재를 전부 찾는다**(2026-09-07 실측 확인).

대응표는 코드에 박지 않는다 -- `VIDEOBOX_CAPCUT_HOST_PATH_MAP` 환경변수로 받는다.

    /videobox-data=D:/AI_Workspace_louis_office_50/20_project/65_videobox-project/runtime

`;`나 줄바꿈으로 여러 쌍을 적을 수 있다. 값이 없으면 아무것도 바꾸지 않는다 --
컨테이너가 아닌 곳(호스트에서 직접 도는 개발 서버)에서는 이미 호스트 경로다.

경로 구분자는 항상 `/`로 적는다. 캡컷이 `D:/...` 꼴을 읽는 것은 실측으로
확인했고, `/`만 쓰면 JSON 안에서 역슬래시를 escape할 일도 없다.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: 대응표를 담는 환경변수. compose가 채운다.
ENVIRONMENT_VARIABLE = "VIDEOBOX_CAPCUT_HOST_PATH_MAP"


def _normalise(value: str) -> str:
    text = value.strip().strip('"').strip("'").replace("\\", "/")
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


@dataclass(frozen=True, slots=True)
class CapCutHostPathMap:
    """`(컨테이너 접두사, 호스트 접두사)` 쌍 목록. 긴 접두사를 먼저 본다."""

    entries: tuple[tuple[str, str], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.entries

    @classmethod
    def parse(cls, text: str | None) -> "CapCutHostPathMap":
        if not text or not text.strip():
            return cls()
        entries: list[tuple[str, str]] = []
        for raw in re.split(r"[;\n]", text):
            chunk = raw.strip()
            if not chunk:
                continue
            if "=" not in chunk:
                raise ValueError(
                    f"{ENVIRONMENT_VARIABLE} entry must look like "
                    f"'/container/path=D:/host/path', got {chunk!r}"
                )
            container_prefix, host_prefix = (_normalise(part) for part in chunk.split("=", 1))
            if not container_prefix or not host_prefix:
                raise ValueError(
                    f"{ENVIRONMENT_VARIABLE} entry needs both sides filled in, got {chunk!r}"
                )
            entries.append((container_prefix, host_prefix))
        # 더 긴 접두사가 먼저 걸려야 한다. `/videobox-data`와
        # `/videobox-data/projects`가 함께 있으면 짧은 쪽이 먼저 먹는다.
        entries.sort(key=lambda entry: len(entry[0]), reverse=True)
        return cls(tuple(entries))

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "CapCutHostPathMap":
        source = environment if environment is not None else os.environ
        return cls.parse(source.get(ENVIRONMENT_VARIABLE))

    def map_path(self, value: str | Path) -> str:
        """대응하는 접두사가 있으면 호스트 경로로, 없으면 원래 값 그대로."""
        text = str(value).replace("\\", "/")
        for container_prefix, host_prefix in self.entries:
            if text == container_prefix:
                return host_prefix
            if text.startswith(container_prefix + "/"):
                return host_prefix + text[len(container_prefix) :]
        return str(value)

    def maps(self, value: str | Path) -> bool:
        """이 값이 실제로 호스트 경로로 바뀌는가."""
        return self.map_path(value) != str(value)


def _rewrite_value(value: object, mapping: CapCutHostPathMap, counter: list[int]) -> object:
    if isinstance(value, str):
        mapped = mapping.map_path(value)
        if mapped != value:
            counter[0] += 1
            return mapped
        return value
    if isinstance(value, list):
        return [_rewrite_value(item, mapping, counter) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_value(item, mapping, counter) for key, item in value.items()}
    return value


def rewrite_draft_for_host(draft_path: str | Path, mapping: CapCutHostPathMap) -> int:
    """초안 폴더 안 모든 `.json`의 경로를 호스트 경로로 바꾸고, 바꾼 개수를 돌려준다.

    **문자열을 통째로 갈아 끼운다.** 접두사만 바꾸면 뒤가 윈도우 구분자로 남는데
    (`D:/host\\projects\\...`), 그 꼴이 캡컷에서 열린다는 것을 확인한 적이 없다.
    확인한 것은 `D:/...` 한 가지뿐이라(2026-09-07 실측) 그 꼴로만 적는다.

    JSON을 읽어서 다시 쓴다. 원본 문자열을 정규식으로 건드리면 윈도우 경로가
    `"D:\\\\store\\\\projects"`처럼 escape된 채 들어 있어 접두사가 안 맞는다 --
    실제로 이 시험에서 그렇게 새 나갔다. 읽을 수 없는 json은 그냥 지나간다.
    """
    if mapping.is_empty:
        return 0
    counter = [0]
    for json_file in sorted(Path(draft_path).rglob("*.json")):
        try:
            document = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        before = counter[0]
        rewritten = _rewrite_value(document, mapping, counter)
        if counter[0] != before:
            json_file.write_text(
                json.dumps(rewritten, ensure_ascii=False, indent=4), encoding="utf-8"
            )
    return counter[0]


__all__ = ["ENVIRONMENT_VARIABLE", "CapCutHostPathMap", "rewrite_draft_for_host"]
