# VideoBox 인계 — P2-1 한 곳, api.ts 한 곳 (2026-08-11 오후)

계획서: `docs/superpowers/plans/2026-08-10-videobox-consolidated-priorities.md` (SSOT)
앞 인계: `docs/handoffs/2026-08-11-videobox-backlog-close-and-local-model-config.ko.md`
(그 인계가 백로그 마감과 로컬 모델 config화까지 다룬다. 이 문서는 그 뒤, 같은 날 오후다.)

**백엔드 3,320 통과 / 53 건너뜀 / 실패 0.** 프런트 850 통과 / 타입체크·빌드 통과.
아직 커밋·푸시하지 않았다 — 변경 파일 3개가 워킹 트리에 그대로 있다.

## 이 세션에서 한 일

1. **컨테이너를 실제로 띄우고 owner 여정을 브라우저로 밟아봤다.** `owner-ready.ps1 -Mode
   Start` 정상, `local_model` 항목도 PASS(LM Studio·설정 일치). `projects/` 폴더(95.3MB)는
   대표님이 이미 삭제해 두신 상태를 확인했다.
2. **브라우저 도구 자체의 한계를 발견했다.** 이 세션의 Browser pane이 실제로
   compositing되지 않는 상태였다 — 고정(fixed) 위치 요소의 화면 좌표가 전부 0×0으로
   나오고(`getBoundingClientRect`), 완성본 mp4의 `range` 요청이 `net::ERR_ABORTED`로
   끊겼다. 클릭은 JS `element.click()` 직접 호출로 우회했지만, **실제 영상 재생 확인은
   이 방식으로 확증할 수 없다.** 다음 세션에서 화면 검증이 필요하면 Browser pane이
   실제로 표시되는지 먼저 확인할 것.
3. **API 레벨로는 확인했다.** `Progress Bar Live Test` 프로젝트가 완성한 영상 3개를
   갖고 있고, jobs·review-approvals·final-renders 메타데이터 조회가 전부 200 OK다.
   검토→승인→완성본 파이프라인 배관 자체는 살아 있다.
4. **P2-1 조용한 곳 1건 수정** (`services/api/src/videobox_api/main.py`,
   `_poll_media_analysis` 안, 원래 462번째 줄 부근). 낡은 분석을 다시 걸기 전에 자산별
   캐시 열쇠를 계산하는데, 원본 파일을 못 읽으면(`resolve_storage_uri`나 `sha256_file`
   실패) 그 자산만 로그 없이 `continue`로 건너뛰었다. 그 자산은 `current_keys`에 안
   들어가므로 이후 재분석 판단 로직에서 계속 애매하게 취급되는데, **왜 안 걸렸는지 남는
   곳이 없었다.** 동작은 그대로 두고(계속 skip) 경고 로그만 추가했다. RED 테스트 먼저
   작성(`tests/test_user_path_failures_are_recorded.py::test_a_stale_check_that_cannot_read_one_asset_still_checks_the_rest`),
   `_poll_media_analysis`를 앱 전체를 띄우지 않고 직접 호출하는 방식이라 빠르다.
5. **api.ts 한 곳 정리** — `getEditingSessionFixedTimeline`. 화면 코드·프런트 테스트
   어디에도 이름이 없고, 대응하는 백엔드 라우터(`/fixed-timeline`)도 백엔드 테스트가
   직접 부르지 않는다는 것까지 확인했다(이전 세션에 지운 3개는 백엔드 테스트가 직접
   불러서 라우터를 남겨야 했는데, 이건 그 경우가 아니다). `FixedTimeline` 타입은
   `SelectedRangePreview`(보류 중인 `previewEditingSessionSelectedRange`가 쓴다)가
   여전히 쓰므로 타입은 남기고 메서드만 지웠다. 타입체크·프런트 850 테스트·빌드 확인.

## 손대지 않은 것과 이유

- **P2-1 나머지 63곳.** 오늘 브라우저 walk에서 나온 증상(미리보기 실패, range 요청
  중단)은 대부분 브라우저 도구 자체의 한계였고 owner가 실제로 겪는 증상과 이어지는
  새 후보를 찾지 못했다. 기계적으로 훑지 않는다는 원칙을 지켰다.
- **api.ts 남은 17개.** 계획서가 이미 분류해 둔 것들이다 — Hermes 스트리밍 4개는
  owner의 로컬 우선 결정(`docs/decisions/2026-08-05-local-first-assistant-decision.ko.md`),
  나머지는 테스트가 "부르지 않음"을 잠가 두었거나(`task22-parity-owners.test.ts:200`,
  `AppRouter.test.tsx:253,405`), `previewEditingSessionSelectedRange`·
  `previewEditingSessionCaptionStyleScope`처럼 **부를 화면을 아직 안 만든 것**이라
  지우면 `CLAUDE.md` §4가 경고하는 "빈칸이 안 보이게 되는" 모양이 된다. 지우지 않았다.

## 다음 세션이 이어서 할 것

1. **Browser pane이 실제로 표시되는 상태에서 owner 여정을 다시 밟아 볼 것.** 오늘은
   pane이 compositing되지 않아 클릭 좌표·영상 재생을 신뢰할 수 없었다. 대표님이 직접
   화면에서 테스트하고 계시므로, 그 결과(막힌 곳·불편한 곳)를 다음 세션 시작에 먼저
   물어볼 것 — 그게 가장 값어치 높은 P2-1 후보 소스다.
2. P2-1 나머지 63곳 — owner 증상이 나오면 그것부터.
3. api.ts 남은 17개 — 계획서 P3-1 표 참고, KEEP/보류 재확인 없이 지우지 않는다.

## 검증 방법

- 백엔드 전체: `.venv/Scripts/python.exe -m pytest -q` (약 25분, 이번 세션 확인:
  3,320 통과 / 53 건너뜀 / 실패 0)
- 새 테스트만: `.venv/Scripts/python.exe -m pytest tests/test_user_path_failures_are_recorded.py -q`
- 프런트: `apps/web`에서 `npx tsc --noEmit` 그리고 `npx vitest run` (850 통과)
- 컨테이너: `.\scripts\owner-ready.ps1 -Mode Start`, 주소는 `http://localhost:5173`

## 함정 (이번에 실제로 걸린 것)

- **Browser pane이 안 보이면 fixed 위치 요소의 클릭 좌표가 0×0으로 나온다.**
  `getBoundingClientRect`가 compositing에 의존하기 때문이다. `element.click()` 직접
  호출로 우회는 되지만, 영상 재생처럼 실제 렌더링이 필요한 확인은 이 우회로 안 된다.
- **api.ts 메서드를 지우기 전에 백엔드 테스트가 그 라우터를 직접 부르는지 반드시
  확인한다.** 안 그러면 이전 세션처럼 "화면에서 안 부른다"만 보고 지웠다가 테스트를
  깨뜨린다.
