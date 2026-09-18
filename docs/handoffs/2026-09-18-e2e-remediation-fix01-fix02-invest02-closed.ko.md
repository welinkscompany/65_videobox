**대체됨:** `docs/handoffs/2026-09-18-mem0-removed-native-memory-librarian.ko.md`

# 2026-09-10 진단서 E2E 항목(FIX-01·FIX-02·INVEST-02) 전부 닫음

owner 승인 위임: `docs/system-audit-2026-09-10-claude-remediation.ko.md`가
지정한 후속 수정·재검증 작업. 전체 결과와 표는
`docs/system-audit-2026-09-10-remediation-results-2026-09-18.ko.md`에 있다 —
이 문서는 다음 세션이 바로 이어받을 수 있게 요점만 남긴다.

## 한 줄 요약

2026-09-01 이후 `apps/web/e2e/`가 한 번도 안 고쳐진 채 승인된 UI 변경
(09-01 유진 직접 적용, 09-04 shell, 09-05 단일 시작, 08-27/08-30 편집기
재배치, 09-07 "B-roll→영상")을 못 따라가고 있었다. 제품 결함은 하나도
없었다 — **아홉 E2E 스펙 파일의 locator·fixture만 고쳤다.** 최종 E2E
전체 **48/48 통과**(시작 시점 29 passed/19 failed).

## 고친 파일 (소스 코드는 안 건드림)

`apps/web/e2e/{product-shell,exact-preview,z-script-first-vertical,
release-gates,editor-workbench,library-footage-crosslink,
library-workspace,media-recovery,voice-tts-settings}.spec.mjs`

가장 반복된 원인 두 가지:
1. **왼쪽/오른쪽 도크 재배치**(2026-08-27~09-07 연속 결정): "세부 정보"는
   더 이상 안 접힌다, "미디어"는 도구줄 단추가 아니라 상시 탭, 유진
   패널은 도크와 무관한 독립 열림 상태, 내레이션은 탭이 아니라 팝업.
2. **전역 메뉴 재배치**(2026-09-05 SideNav): `home`/`library`/`voices`/
   `footage`/`settings`에서는 접힌 "전체 메뉴" 대신 상시 노출 왼쪽
   `SideNav`("화면 이동")가 쓰인다. 단계 화면(이야기/편집/확인과
   내보내기)에는 접힌 메뉴가 그대로 있다.

가장 손이 많이 간 것은 `editor-workbench.spec.mjs`의 "owned
conversational-editing fixture…" 시험이다 — 2026-09-01 "말로 시킨 편집은
바로 적용된다" 결정으로 "대화 만들기→편집안 보기→미리보기→적용" 네 단계
확인 흐름이 통째로 없어졌고, `interpretAndApplySpokenEdit`가 메시지 전송
한 번으로 제안 생성과 적용을 다 한다는 것을 확인하고 시험을 다시 썼다.

`voice-tts-settings.spec.mjs`는 `/assets`가 이제 `/editor`로 리다이렉트되는
것까지 따라가야 해서 편집기 전용 API(세션·매니페스트·대화 이어받기 등)
mock을 새로 채워야 했다.

## FIX-00/FIX-02/INVEST-01/03/04/VERIFIED-01

- **FIX-00**: 153개 커밋 격차 확인, E2E 디렉터리가 그 전부터(09-01)
  안 바뀌었다는 사실로 "낡은 테스트, 새 결함 아님"을 뒷받침.
- **FIX-02**: `release-gates.spec.mjs`가 `--output`을 무시하고 고정
  경로에 성능 json을 쓰던 것을 `testInfo.outputPath`로 격리. 실측 확인함.
- **INVEST-01**: 전체 프런트 vitest(1752개) 재현 안 됨 — 재수정 안 함.
- **INVEST-03**: 재현됨(median 116.9ms vs 기준 92ms)이지만 이 기계에
  동시 worktree 30개 이상 떠 있어 환경 잡음 의심 — 원인 미확정, 임계값
  안 건드림. 유휴 기계 재측정 필요.
- **INVEST-04**: 코드 추적으로 유력한 원인 확인(영상 자산은 2026-09-17
  이미지 썸네일 즉석 재생성 수정에서 빠졌다, `services/api/.../assets.py`).
  실행 재현은 못 함 — `task_0373d077`로 다음 세션에 스폰함.
- **VERIFIED-01**: 재발 안 함. 전체 backend pytest 1차 완주에서
  `test_handoff_entry_point.py`가 실제로 깨졌지만, 원인은 인계 중복이
  아니라 **이 handoff 문서 자신의 형식 실수**(아래 참고)였다 — 고치고
  단독 재실행으로 통과 확인함.

## 검증 상태 (최종)

- E2E 전체: **48/48 통과** (확정).
- frontend vitest 전체: 1752/1752 통과 (확정, 이 세션의 e2e 변경 전
  코드베이스 기준 — 이번 세션은 소스 코드를 안 바꿨으므로 그대로 유효).
- frontend tsc --noEmit: 에러 0 (확정).
- backend 전체 pytest: **5147 passed, 56 skipped, 1 xfailed, 3 failed**
  (41분 18초, commit `515779e21` 기준). 첫 시도는 세션 임시 경로가 너무
  길어(Windows MAX_PATH) `test_api.py`가 무더기로 `[WinError 206]`
  오탐이 났다 — 제품 결함이 아니라 이번 세션의 검증 방법 실수였다(짧은
  경로 `D:/vbpt`로 재실행해서 해소). 정식 재실행의 3개 실패는:
  1. `test_handoff_entry_point.py::test_entry_map_points_at_the_newest_handoff`
     — 이 handoff를 처음 쓸 때 "아직 없음" 자리 표시 문구에 대체 표시
     글자가 그대로 들어가 있어서(그 문구 자체가 그 글자를 담고 있다),
     `_newest_handoff()`의 단순 부분 문자열 검사가 이 문서를 "이미
     대체됨"으로 오판했다. **살아 있는 인계 문서는 `대체됨` 줄 자체가
     없어야 한다** — 있으면 무슨 내용이든 무조건 "대체됨"으로 읽힌다.
     지금은 그 줄을 지웠다. 게다가 41분 도는 동안 다른 세션이
     `2026-09-18-transcript-panel-text-delete.ko.md`를 커밋해 들어와서
     "최신" 자리를 다퉜다 — 그 문서에 이 handoff를 가리키는 `대체됨` 줄을
     추가해 체인을 바로잡았다. 단독 재실행 5 passed로 확인함.
  2. `test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`
  3. `test_owner_ready_script.py::test_smoke_continues_after_one_failure_and_records_only_bounded_results`
     — 둘 다 41분 전체 실행 중 실제 subprocess/timeout을 재는 시험인데,
     이 컴퓨터가 그 순간 동시 worktree 30개 이상으로 부하가 있었다.
     격리 재실행 2 passed로 확인함 — 코드는 안 건드렸다.
  **결론: 제품 코드 회귀는 0건.** 다만 문서를 고친 뒤 41분짜리 전체
  스위트를 처음부터 다시 통째로 돌리지는 않았다(아래 참고).
- 실사용 브라우저(격리 Postgres+파일): 하지 않음 — 차단/미검증으로 남김.

## 다음 세션이 할 일

1. `task_0373d077`(영상 썸네일 404) 처리 여부는 owner 판단.
2. INVEST-03 성능 재측정은 이 컴퓨터가 한가할 때 다시.
3. 실사용 브라우저 끝까지(격리 환경) 검증은 아직 안 됐다 — 필요하면
   `scripts/owner-ready.ps1`로 격리 스택을 먼저 확보해야 한다.
4. **여유가 있으면 backend 전체 pytest를 처음부터 한 번 더** 돌려서
   3건 수정 뒤에도 다른 실패가 안 섞이는지 최종 확인해라 — 이번 세션은
   개별/격리 재현으로만 확인하고 전체 재실행(41분)은 하지 않았다.
5. **여러 세션이 동시에 `docs/handoffs/`에 쓸 때는 커밋 직전에
   `test_handoff_entry_point.py`를 마지막으로 한 번 더 돌려라** — 이번
   세션에서 실제로 그 경합이 시험을 깼다.

## 재사용/경계

기존 시험 헬퍼 패턴(`ensureDockOpen`)을 그대로 본떠 `ensureYujinOpen`을
추가했다. 소스 코드는 한 줄도 안 바꿨다 — 전부 테스트 쪽 기대값 갱신.
다른 세션이 동시에 작업 중이던 `packages/core-engine/`·
`packages/storage-abstractions/` 쪽은 건드리지 않았다.
