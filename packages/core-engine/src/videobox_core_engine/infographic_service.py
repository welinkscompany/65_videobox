"""주제와 숫자 몇 개로 **인포그래픽 한 장**을 만들어 자료실에 넣는다.

## 순서

1. 지시문을 짠다 (`infographic_brief.build_infographic_prompt`)
2. 유진의 두뇌(로컬 모델)가 HTML을 쓴다
3. **그리기 전에 검사한다** -- 지어낸 숫자, 바깥 주소, 너무 작은 글씨
4. **브라우저에 올려 놓고 자리를 잰다** -- 판을 넘었는지, 글자가 겹쳤는지
   (`infographic_layout_audit`; HTML만 봐서는 알 수 없다)
5. 문제가 있으면 무엇이 틀렸는지 적어 **한 번 더 시킨다**
6. 이 컴퓨터의 크롬이 PNG로 그린다 (`infographic_host_bridge`, 8201)
7. 자료실 `그림`에 넣는다 -- 60초 뒤 의미검색 색인에도 들어간다

## 왜 다시 시키는가

`github.com/OrRon/EpicInfographics`(MIT)에서 가져온 규칙이다. 그쪽은 **에이전트가
자기 그림을 보고 고친다.** 여기서 되돌이를 도는 것은 기계가 확실히 판정할 수 있는
것뿐이다 -- 지어낸 숫자는 대조하면 나오고, 바깥 주소는 정규식으로 잡히고,
판을 넘었는지·글자가 겹쳤는지는 브라우저 안에서 자리를 재면 나온다.
"촌스럽다"·"색이 안 어울린다" 같은 것은 아직 사람이 본다. 확실하지 않은 판정으로 되돌이를 돌리면 좋은 그림을 버리고
나쁜 그림을 얻는다.

## 자료실 등록이 실패해도 그림은 돌려준다

`SceneVideoService._ingest_into_library`와 같은 이유다 -- 등록 실패로 방금 만든
그림을 잃지 않는다. 대신 왜 실패했는지 값으로 돌려준다.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from videobox_domain_models.library_assets import LibraryMediaType
from videobox_provider_interfaces.llm import LLMTaskType

from videobox_core_engine.infographic_brief import (
    INFOGRAPHIC_HEIGHT,
    INFOGRAPHIC_WIDTH,
    MINIMUM_FONT_PX,
    InfographicFact,
    build_infographic_prompt,
    check_infographic_html,
    extract_document,
    resolve_style,
)
from videobox_core_engine.infographic_layout_audit import (
    apply_layout_audit,
    describe_layout_problems,
    read_audit,
)
from videobox_core_engine.infographic_host_bridge import (
    InfographicHostBridge,
    InfographicHostBridgeRefused,
    InfographicHostBridgeUnavailable,
)

#: 모델은 앞뒤에 말을 붙이는 버릇이 있다. 구조화 출력으로 받아 그 버릇을 없앤다 --
#: ``` 로 자르는 방법은 ``` 를 안 쓴 답에서 통째로 날아간다(2026-09-07에 겪었다).
INFOGRAPHIC_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"html": {"type": "string"}},
    "required": ["html"],
}

#: 두 번까지만 시킨다. 세 번째는 대개 같은 실수를 되풀이하고, 그동안 owner는 기다린다.
MAXIMUM_ATTEMPTS = 2

#: **전체 시간 예산.** nginx가 330초에서 끊는다(`docker/workspace-nginx.conf`).
#: 거기서 잘리면 화면은 우리가 쓴 한국어 대신 프록시의 504 HTML을 받는다 --
#: owner에게는 제품이 고장 난 것으로 보인다. 그림 만들기와 **정확히 같은 자리**다
#: (`tests/test_compose_contract.py`).
#:
#: 한 판이 63~115초다(2026-09-07 실측). 두 판이면 230초쯤이라 대개 들어가지만,
#: 모델이 느린 날에는 안 들어간다. 그래서 시계를 보고 판단한다.
#:
#: **한 판 상한(`VIDEOBOX_INFOGRAPHIC_TIMEOUT_SECONDS`, 140초)의 두 배가 여기
#: 들어와야 한다.** 안 그러면 두 판째가 애초에 못 돌아 되돌이가 문서에만 있는
#: 것이 된다 -- `tests/test_compose_contract.py`가 세 값을 함께 잡는다.
TOTAL_BUDGET_SECONDS = 300


class InfographicUnavailable(RuntimeError):
    """만들지 못했다. 이유를 `reason`으로 들고 다닌다 -- 화면이 그걸 보고
    "다시 해 보세요"와 "크롬을 켜 주세요"를 구분해서 말한다."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(slots=True)
class GeneratedInfographic:
    """만들어진 그림 한 장."""

    png_bytes: bytes
    html: str
    style_key: str
    title: str
    attempts: int
    #: 앞 판에서 잡아 고치라고 되돌려 준 것들. 비어 있으면 한 번에 통과한 것이다.
    corrected: tuple[str, ...] = ()
    #: **아직 남은 아쉬운 점.** 비어 있어야 정상이다. 시간이 모자라 더 못 고쳤을 때
    #: 채워져 나온다 -- 화면이 이걸 그대로 보여 주면 owner가 보고 판단한다.
    remaining_problems: tuple[str, ...] = ()
    library_asset_id: str | None = None
    library_error: str | None = None


@dataclass(slots=True)
class InfographicService:
    """주제 → 그림 한 장. 부품은 전부 밖에서 넣는다(시험에서 실물 없이 돈다)."""

    runtime_service: Any
    bridge: InfographicHostBridge | None = None
    library_ingest: Any = None
    #: 시험이 실제 파일을 안 만들도록 갈아 끼울 수 있게 열어 둔다.
    _scratch_factory: Any = field(default=tempfile.TemporaryDirectory, repr=False)
    #: 시험이 시간 예산을 밟아 볼 수 있게. 실제로는 벽시계다.
    _clock: Any = field(default=time.monotonic, repr=False)

    def generate(
        self,
        *,
        project_id: str,
        topic: str,
        facts: Sequence[InfographicFact],
        style: str | None = None,
        title: str | None = None,
    ) -> GeneratedInfographic:
        subject = (topic or "").strip()
        if not subject:
            raise InfographicUnavailable("infographic_topic_empty")
        if self.bridge is None:
            # **기능이 꺼진 것과 고장난 것을 나눈다.** 다리가 없으면 아무리 다시
            # 눌러도 안 되는데, "잠시 뒤 다시"라고 말하면 owner는 계속 누른다.
            raise InfographicUnavailable("infographic_bridge_not_configured")

        chosen = resolve_style(style)
        prompt = build_infographic_prompt(topic=subject, facts=facts, style=chosen.key)
        started = self._clock()
        best: tuple[str, bytes, tuple[str, ...]] | None = None
        corrected: tuple[str, ...] = ()
        attempt = 0
        for attempt in range(1, MAXIMUM_ATTEMPTS + 1):
            html = self._write_html(project_id=project_id, prompt=prompt)
            png = b""
            problems = check_infographic_html(html, facts)
            if not problems:
                # 글로 잡을 게 없으면 **브라우저에 올려 놓고 자리를 잰다.**
                # 판을 넘겼는지·겹쳤는지는 실제로 놓아 봐야 안다.
                png = self._render(html)
                problems = self._layout_problems(html)
            # 그림이 있는 판만 후보다 -- 글 검사에서 막힌 판은 그린 적이 없다.
            if png and (best is None or len(problems) < len(best[2])):
                best = (html, png, problems)
            if not problems:
                break
            if attempt >= MAXIMUM_ATTEMPTS:
                break
            spent = self._clock() - started
            # **한 판 더 돌 시간이 없으면 돌지 않는다.** 프록시에서 잘리면 owner는
            # 4분을 기다리고 우리 문구 대신 504 HTML을 받는다.
            if spent * 2 > TOTAL_BUDGET_SECONDS:
                break
            corrected = problems
            prompt = _retry_prompt(prompt, problems)

        if best is None:
            # 두 판 다 그려 보지도 못했다 -- 글 검사에서 막혔다는 뜻이다.
            raise InfographicUnavailable(
                "infographic_did_not_pass_checks", "; ".join(problems)
            )
        html, png, remaining = best
        made = GeneratedInfographic(
            png_bytes=png,
            html=html,
            style_key=chosen.key,
            title=(title or subject).strip()[:120],
            attempts=attempt,
            corrected=corrected,
            remaining_problems=remaining,
        )
        made.library_asset_id, made.library_error = self._ingest(
            png=png, project_id=project_id, made=made
        )
        return made

    def _write_html(self, *, project_id: str, prompt: str) -> str:
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.INFOGRAPHIC_HTML,
                prompt=prompt,
                response_schema=INFOGRAPHIC_RESPONSE_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001 - 로컬 런타임 경계
            # `ScriptDraftWriter`와 같은 이유로 **제 시간에 못 끝낸 것**을 따로 뗀다.
            # 인포그래픽 HTML은 대본보다 훨씬 길어서 상한에 실제로 닿는다.
            if str(getattr(exc, "error_code", "") or "").upper() == "LOCAL_TIMEOUT":
                raise InfographicUnavailable("infographic_took_too_long") from exc
            raise InfographicUnavailable("infographic_writer_unavailable", str(exc)) from exc
        output = getattr(response, "output_data", None) or {}
        raw = str(output.get("html") or "")
        # 구조화 출력이라도 모델이 설명을 앞에 붙이는 일이 있다. 문서만 꺼낸다.
        return extract_document(raw) or raw

    def _render(self, html: str) -> bytes:
        assert self.bridge is not None  # generate()가 이미 확인했다
        try:
            return self.bridge.render(
                html=html, width=INFOGRAPHIC_WIDTH, height=INFOGRAPHIC_HEIGHT
            )
        except InfographicHostBridgeUnavailable as exc:
            raise InfographicUnavailable("infographic_bridge_not_running", str(exc)) from exc
        except InfographicHostBridgeRefused as exc:
            raise InfographicUnavailable("infographic_render_failed", str(exc)) from exc

    def _layout_problems(self, html: str) -> tuple[str, ...]:
        """브라우저가 실제로 놓은 자리를 재서 문제를 뽑는다.

        **못 재면 통과로 다루지 않는다.** 다리가 답을 안 주는 것과 배치가
        멀쩡한 것은 다른 말이다 -- 다만 그 때문에 이미 만든 그림을 버리지도
        않는다. 재지 못했다고 적어 두고 owner가 보게 한다.
        """

        assert self.bridge is not None
        try:
            title = self.bridge.measure(
                html=apply_layout_audit(
                    html,
                    width=INFOGRAPHIC_WIDTH,
                    height=INFOGRAPHIC_HEIGHT,
                    minimum_font_px=MINIMUM_FONT_PX,
                ),
                width=INFOGRAPHIC_WIDTH,
                height=INFOGRAPHIC_HEIGHT,
            )
        except (InfographicHostBridgeUnavailable, InfographicHostBridgeRefused):
            return ("배치를 재지 못했다 — 눈으로 한 번 봐 주세요",)
        audit = read_audit(title)
        if audit is None:
            return ("배치를 재지 못했다 — 눈으로 한 번 봐 주세요",)
        return describe_layout_problems(audit)

    def _ingest(
        self, *, png: bytes, project_id: str, made: GeneratedInfographic
    ) -> tuple[str | None, str | None]:
        """자료실 `그림`에 넣는다. 실패해도 방금 만든 그림을 잃지 않는다
        (`SceneVideoService._ingest_into_library`와 같은 관례)."""

        if self.library_ingest is None:
            return None, None
        try:
            with self._scratch_factory(prefix="videobox-infographic-") as scratch:
                path = Path(scratch) / f"{_file_stem(made.title)}.png"
                path.write_bytes(png)
                ingested = self.library_ingest.ingest(
                    media_type=LibraryMediaType.IMAGE,
                    source=path,
                    filename=path.name,
                    # 같은 그림을 두 번 넣지 않도록 **내용**으로 열쇠를 만든다.
                    # 제목으로 만들면 같은 제목의 다른 그림이 409로 막힌다.
                    idempotency_key=f"infographic:{_digest(png)}",
                    provenance={
                        "generated_by": "videobox-infographic",
                        "source_kind": "generated_infographic",
                        "project_id": project_id,
                        "title": made.title,
                        "style": made.style_key,
                    },
                )
            return str(ingested["library_asset_id"]), None
        except Exception as exc:  # noqa: BLE001 - 자료실 등록 실패가 그림을 지우면 안 된다
            return None, type(exc).__name__


def _digest(png: bytes) -> str:
    from hashlib import sha256

    return sha256(png).hexdigest()


def _file_stem(title: str) -> str:
    """파일 이름으로 쓸 수 있게. 한글은 그대로 둔다 -- 자료실이 한글 이름을 다룬다."""

    cleaned = "".join(character if character.isalnum() else "-" for character in title)
    return cleaned.strip("-")[:60] or "infographic"


def _retry_prompt(prompt: str, problems: Sequence[str]) -> str:
    """무엇이 틀렸는지 **구체적으로** 말해 준다. "다시 해"만으로는 안 고쳐진다."""

    listed = "\n".join(f"- {problem}" for problem in problems)
    return f"""{prompt}

# 방금 만든 것이 아래에서 틀렸다. **고쳐서 다시 내라.**
{listed}

특히 숫자를 지어냈다면, 그 숫자를 **빼거나** 위에서 허용한 숫자로 바꿔라.
설명하지 마라. 고친 HTML만 낸다."""


__all__ = [
    "INFOGRAPHIC_RESPONSE_SCHEMA",
    "MAXIMUM_ATTEMPTS",
    "GeneratedInfographic",
    "InfographicService",
    "InfographicUnavailable",
]
