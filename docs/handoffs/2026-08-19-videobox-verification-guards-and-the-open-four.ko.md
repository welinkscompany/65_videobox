# 검증 장치 둘을 세웠다 — 나머지 셋은 안 건드렸다

> **대체됨:** `docs/handoffs/2026-08-19-videobox-open-four-closed-and-review-fixes.ko.md`
> 아래 2·3·4는 그 문서에서 전부 닫혔다. 여기 "안 건드림" 목록을 현재로 믿으면 틀린다.

- 작성: 2026-08-19
- **읽는 순서:** 이 문서 →
  `docs/handoffs/2026-08-19-videobox-navigation-and-spacing-audit.ko.md`
- 커밋: `832b10c09 test: guard the two places verification was leaking out`

## 왜 이걸 먼저 했나

owner가 물었다 — **"왜 계속 검증을 할 때마다 오류가 나오는거야?"**

서브에이전트 10개로 일괄 점검한 결과, 답은 "검증이 새고 있었다"였다. owner가
정한 순서가 이것이다:

> 1. 검증 장치부터 — compose 기본값 가드, e2e가 진짜 백엔드를 한 번은 밟게.
>    **이걸 안 하면 아래를 고쳐도 또 새어 나갑니다**
> 2. 내레이션 음량 + 무음 B-roll 가드
> 3. 자막 모양·포맷 불러오기
> 4. 화면이 거짓말하는 것들

**이 세션에서 끝낸 것은 1번뿐이다.** 2·3·4는 손대지 않았다.

## 1번 — 끝냄

### compose 기본값 가드 (`tests/test_compose_contract.py`)

`VIDEOBOX_STT_ENABLED`가 **아무 기본값 없이** 실려 있었다. 변수를 안 넘긴
컨테이너는 조용히 자막 없이 돈다. 실패하지 않고 조용히 다르게 도는 것이
제일 나쁘다.

- `VIDEOBOX_STT_ENABLED` → `${...:-1}`, `VIDEOBOX_STT_LANGUAGE` → `${...:-ko}`
- `VIDEOBOX_LOCAL_RUNTIME_BASE_URL` → `host.docker.internal:1234/v1` 못 박음
  (이 한 줄이 빠지면 분석·의미검색·대화가 한꺼번에 멈춘다 — 전에 겪었다)

`:-1`을 `:-0`으로 바꿔 보고 실제로 깨지는 것을 확인했다.

### e2e ↔ 진짜 API 경로 대조 (`tests/test_e2e_fake_api_matches_the_real_one.py`)

**e2e 48개가 전부 가짜를 상대하고 있었다.** 손으로 쓴 318줄짜리
`apps/web/e2e/support/fake-api-server.mjs`가 20여 개 경로를 흉내 내고,
실제 FastAPI는 **한 번도 불리지 않는다.** 즉 백엔드가 경로를 바꾸거나 없애도
e2e는 전부 초록이고, 화면은 배포된 뒤에야 404가 된다.

가짜를 없애자는 게 아니다 — 가짜 덕에 e2e가 빠르고 결정적이다. 다만 **그것이
진짜와 같은 모양인지 아무도 재지 않고 있었다.**

가짜가 서빙하는 경로를 전부 걷어 **진짜 라우터에게 직접 물어본다.**
없는 경로를 하나 심어 실제로 깨지는 것을 확인했다.

**두 번 헛짚었다.** 경로의 자리표시자를 정규식으로 흉내 내려 했는데, 진짜 쪽은
`{job_id}`·`{readiness_id}`·`{generation_id}`처럼 이름이 제각각이라 규칙으로
맞출 수 없다. Starlette의 `route.matches()`를 그대로 쓰니 사라졌다.
**흉내 내지 말고 그 시스템에게 물어라.**

## 여기서 못 한 것 — 다음 사람이 이어받을 자리

**응답 본문의 키까지는 못 잰다.** 그러려면 가짜 서버를 띄워 HTTP로 불러야 하는데
`tests/conftest.py:118`이 테스트의 모든 네트워크 연결을 막는다
(`"Tests must not open network connections."`). 그 가드는 옳으므로 뚫지 않았다.

즉 **경로는 맞는데 응답 키가 바뀌는 드리프트는 여전히 안 잡힌다.**
본문 모양 대조는 웹 쪽(vitest)에 따로 세워야 한다 — 가짜 서버 모듈을 import해
응답 객체의 키를 백엔드 스키마와 맞춰 보는 식이 맞다.

`PLAYWRIGHT_SKIP_FAKE_API=1`로 가짜를 끄고 진짜 백엔드에 e2e를 붙이는 길은
설정에 이미 있고, 그 갈래가 사라지지 않게 가드를 걸어 뒀다. 다만 **실제로 그렇게
돌려 보지는 않았다.**

## 2·3·4 — 안 건드림

점검에서 나왔고 내가 직접 확인한 것들이다. 순서는 owner가 정한 그대로다.

**2. 내레이션 음량 + 무음 B-roll**
- `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py:353`
  근처의 `amix`에 `normalize=0`이 아직 없다. 같은 함정에 **이미 두 번** 걸렸다
  (`414`행과 `1091`행은 고쳤다). 렌더 경로가 둘이라는 것을 잊지 마라.
- `preserve_source_audio`를 켠 채 소리 없는 B-roll이 섞이면 막힌다. 가드가 없다.

**3. 자막 모양·포맷 불러오기** — 프리셋을 저장하고 다시 적용하는 왕복이 끊겨
있고, 포맷 템플릿 적용은 **항상 500**이다.

**4. 화면이 거짓말하는 것들**
- 의미검색이 **결과 0건인데 `SEMANTIC_MATCH` 성공**이라고 표시한다
- `hsl(var(--token))` 13곳이 무효 (토큰이 이미 완성색이라 `hsl()`이 죽는다)
- 설정 저장이 실패해도 화면은 조용하다
- `apps/web/src/features/editor/preview/…`의 `vb-preview-stage__elsewhere`에
  대응하는 CSS가 없다
- `searchLibraryAssets`를 부르는 곳이 하나도 없다
- `scripts/verify_container_stack.ps1`이 이미 없앤 서비스를 참조한다

## owner 결정이 필요한 것

**유진의 대본·제목 금지.** `packages/core-engine/src/videobox_core_engine/`
`yujin_local_conversation.py:56-58`의 정규식이 "대본 써 줘"·"제목 만들어 줘"를
막는다. 2026-08-16에 owner가 이걸 푸는 것을 승인했는데 **코드에 반영되지 않았다.**
둘 중 하나를 골라야 한다 — 코드에서 실제로 풀거나, 문서를 "승인됐으나 미구현"으로
고치거나. 지금은 문서와 코드가 서로 다른 말을 하고 있다.

## 남은 사람 확인

- 미리보기 전체화면 실제 진입
- 소리 살린 B-roll을 실제로 들어 보기
- 임시 프로젝트 `project-92f12825`, `project-8536fd6d` 삭제 여부

## 한 가지 더 — 전체 pytest

직전 전체 실행은 3,648 통과 / 1 실패였고, 그 1건
(`test_owner_ready_script.py::…[FAKE_UNTRACKED_CHILD]`)은 **단독으로 돌리면
통과한다.** 30분짜리 실행 중에 내가 커밋을 해서 트리를 흔들었다.
**전체 pytest는 단독으로, 아무것도 건드리지 말고 돌려라.**

이번 커밋은 테스트 파일 추가뿐이라 전체를 다시 돌리지 않았다.
