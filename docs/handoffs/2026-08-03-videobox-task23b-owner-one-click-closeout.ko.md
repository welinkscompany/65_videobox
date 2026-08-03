# VideoBox Task 23B owner one-click 실행·진단 closeout

## 한 줄 결론

VideoBox를 시작하기 전에 현재 PC 상태를 안전하게 확인하고, 필요한 경우에만 시작·정적 점검·화면 열기를 따로 실행하는 `scripts/owner-ready.ps1`을 추가했다.

## 실제 범위

- 기본 `Check`: Git/도구/Compose/data root/Windows path headroom/loopback health/CapCut을 읽기 전용으로 확인한다.
- 명시적 `Start`: 실제 `.env.container`를 raw 출력 없이 검증한 뒤 `videobox-postgres`, `videobox-workspace`만 시작하고 `/health`를 제한 시간 안에서 확인한다.
- 명시적 `Smoke`: 기존 non-live/static verifier 여섯 개만 실행하고 짧은 sanitized JSON receipt를 `artifacts/owner-ready`에 원자 게시한다.
- 명시적 `Open`: exact VideoBox loopback root만 기본 브라우저로 연다.
- 명시적 `OpenCapCut`: 발견한 exact `CapCut.exe`만 인자 없이 연다. project 선택·편집·export는 하지 않는다.

## 유지한 안전 경계

- 기본 Check의 service/app start, write probe, 외부 provider call은 0이다.
- loopback 이외 URL, user-info/query/fragment는 실제 요청 전에 거부한다. HTTP proxy와 redirect follow도 끈다.
- stdout/stderr와 receipt에는 env 값, credential, 절대 경로, 전체 command, raw child output, container ID를 기록하지 않는다.
- missing env/credential/runtime 준비는 고장으로 과장하지 않고 `blocked`와 쉬운 복구 행동으로 표시한다.
- 사용자 샘플은 읽거나 수정하지 않았다. 보호 residue 세 폴더도 열거나 stage/remove/delete하지 않았다.
- live Hermes/Mem0, 자동 apply, source copy, SaaS, 게시, credential 생성은 범위 밖이다.

## 실제 환경 확인

`Check -Json` 결과는 overall `blocked`였다. 이는 실패가 아니라 현재 `.env.container`와 전용 data root가 아직 준비되지 않았기 때문이다.

- workspace/branch/upstream: pass
- Python `3.12.10`, Node `24.16.0`, npm `11.13.0`: pass
- FFmpeg/ffprobe `8.1.1`, Docker `29.5.3`, Compose parse: pass
- VideoBox health `200`: pass
- Hermes dashboard login redirect `302`: pass, redirect follow 0
- CapCut `9.1.0.3879` 및 project root: pass, write probe 0
- `.env.container`, data root, path headroom: blocked

실제 `Start`, 브라우저 `Open`, `OpenCapCut`은 실행하지 않았다. 해당 분기는 fake Docker/loopback과 `-WhatIf` 계약으로만 검증했다.

## 검증 결과

- `tests/test_owner_ready_script.py`: **25 passed**
- 관련 Hermes/Compose 계약: **142 passed, 1 skipped**
- 실제 `Smoke`: **6/6 pass**, `external_provider_calls=0`
- receipt schema: top-level bounded fields + 각 check의 `id/status/action`만 보존
- receipt/test report ignore 확인: `.gitignore`의 `artifacts/` 규칙
- 독립 code/reverse review의 process-tree timeout, chunked/invalid health, redirect, exception classification Important finding은 RED→GREEN으로 보완했고 재리뷰는 **Critical 0, Important 0, ready**
- `git diff --check`: closeout 직전 재실행 대상

기존 Starlette multipart PendingDeprecationWarning 1건은 비실패 출력이다. 전체 Python regression, frontend 전체 suite/build/provenance, live provider, 사람의 브라우저·CapCut 조작은 이번 slice에서 실행하지 않았고 통과로 주장하지 않는다.

## 진행률과 다음 goal

- Task 23: **2/4 (50.0%)**
- 잔여: **50.0%**
- 다음 goal: **23C 사용자 샘플 repeatable edit package**

다음 시작 prompt:

> VideoBox의 exact container-compatibility worktree에서 Task 23C만 진행해. 사용자 샘플은 read-only로 유지하고, 이미 검증된 ingest/HEVC preview/BGM/SFX/caption/voice/overlay/CapCut 흐름을 하나의 반복 가능한 owner edit package로 묶어 TDD로 구현해. 자동 apply, source mutation, 외부 provider, 게시를 추가하지 말고, code review·gap·역방향 검증과 focused 검증 후 SSOT/handoff/commit/push까지 닫아.
