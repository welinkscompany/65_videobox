# VideoBox P1-1 실제 CapCut 자막 시험 입력 인계 — 2026-08-24

**대체됨:** `docs/handoffs/2026-08-24-videobox-p1-render-overlay-fixture-handoff.ko.md`

## 현재 작업선

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch: `codex/videobox-container-compatibility`
- 다음 세션은 먼저 `git rev-parse HEAD`, `git status --short`,
  `git rev-list --left-right --count @{upstream}...HEAD`를 직접 확인한다.
- 이 세션에서는 push하지 않았다.

## 실제로 한 일

P1-1의 출력 우선 후보에서 `tests/test_pycapcut_adapter.py`의 실제 CapCut 초안 자막
스타일 시험 하나를 바꿨다.

바꾸기 전에는 시험이 수제 editing session과 완성 timeline을
`PyCapCutRealExportAdapter`에 바로 넣었다. 바꾼 뒤에는 제품의
`build_editing_session`으로 session을 만들고,
`materialize_editing_session_timeline`의 결과만 어댑터에 전달한다.
그러므로 이 시험은 실제 편집 세션의 caption style·caption window·narration clip이
초안으로 가는 모양을 확인한다.

변환한 focused 시험은 통과했다. 이번 전환에서는 숨은 제품 결함이 나오지 않았다.
수제 raw timeline 자체가 저수준 CompositionPlan·필터 계약을 검사하는 다른 시험은
바꾸지 않았다.

`docs/2026-08-24-test-fixture-shape-audit.ko.md`도 갱신했다.
실제 경로로 전환한 출력 시험은 3개가 되었고, 다음 검토 대상은 8개다.

## 자동 검증 결과

| 검증 | 결과 |
|---|---|
| 새 실제 경로 focused pytest | 1 passed / warning 1 |
| `tests/test_pycapcut_adapter.py` 전체 | 17 passed / warning 1 |
| 인계 진입점 시험 | 5 passed / warning 1 |
| `owner-ready` 타임아웃 재현 | 1 passed / warning 1 |
| `.venv\Scripts\python.exe -m pytest -q` 단독 전체 재실행 | **4046 passed / 56 skipped / warning 1**, 32분 17초 |

첫 전체 실행에는 두 실패가 있었다. 하나는 같은 날 인계를 두 번 쓰면서 이전 인계에
`대체됨` 줄을 빼뜨린 문서 규칙 위반이었고, 수정했다. 다른 하나는
`test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`가 30초에
시간 초과한 것이며, 단독 재현은 3.79초에 통과했다. 문서 수정 뒤 전체 재실행은
위 표처럼 모두 통과했다.

기존 `python_multipart` 폐기 예정 경고 1건은 남는다.

## 검증했지만 못 끝낸 것

1. 출력 우선 후보를 전부 변환하지 않았다. 남은 8개는 파일 전체가 아니라 실제 편집
   세션 결과를 주장하는 시험만 한 개씩 판단해야 한다.
2. 이번 전환에서는 제품 결함이 나오지 않았지만, 남은 후보가 안전하다는 뜻은 아니다.
3. 실제 CapCut Desktop에서 draft를 열고 사람 눈·귀로 재생하는 검증은 하지 않았다.

## 목요일에 화면으로 확인해야 할 것

1. 실제 CapCut Desktop에서 VideoBox가 만든 초안의 자막 스타일·시간·내레이션이
   예상대로 보이고 들리는지
2. 화면 캡처, 출력 화면 문구, 장면 리플 배속의 실제 MP4 재생은 이전 인계의
   목요일 사람 확인 항목대로 진행할 것

자동 시험은 화면·음향·CapCut 사용성의 사람 확인을 대신하지 않는다.

## 다음 파일·시험 작업

`CLAUDE.md` §0, `docs/development-fast-path.ko.md` §10, 이 인계를 읽는다.
그 다음 `docs/2026-08-24-test-fixture-shape-audit.ko.md`의 남은 출력 후보 중 하나만
선택한다. 먼저 그 시험이 세션 결과를 주장하는지 확인하고, 그렇다면
`build_editing_session → materialize_editing_session_timeline → renderer/export adapter`
경로로 바꾼다. 붉어지면 시험을 되돌리지 말고 제품 데이터 흐름을 추적한다.

백엔드 시험은 반드시 `.venv\Scripts\python.exe -m pytest`를 쓴다. 전체 pytest는
다른 장기 작업과 병행하지 않는다. UI·컨테이너 확인은
`./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`만 사용하며,
push·외부 게시·운영 변경은 별도 명시 승인이 필요하다.
