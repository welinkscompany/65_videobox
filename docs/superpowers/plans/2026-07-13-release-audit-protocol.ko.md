# VideoBox 개발 종료 Release Audit Protocol 실행 계획

> **For agentic workers:** 이 계획은 code change가 아닌 종료 검증·문서화·정리 작업이다. 각 gate는 증거를 남기고, Critical/Important finding이 없을 때만 다음 gate로 진행한다.

**목표:** 배포·개발 종료 전에 6개 release-audit gate를 일관되게 수행하고, 현재 HEAD의 pass/fail 및 정리 판단을 SSOT에 남긴다.

**구조:** 기존 테스트·verifier·Git metadata를 우선 사용한다. 코드리뷰와 역방향 검증은 서로 다른 관점의 read-only audit이며, 파일 삭제는 분류 결과가 `safe-to-delete`인 항목에만 제한한다.

---

## Gate 1. 코드리뷰

입력: 마지막 release 관련 변경 범위(`438fea0..HEAD`), 최신 계획서, API/core/frontend handoff 경로.

방법:

1. `git diff 438fea0..HEAD -- packages/core-engine services/api apps/web tests`를 읽는다.
2. source immutability, nullable failure, persisted handoff, diagnostics read-only, UI recovery 경계를 코드와 테스트에서 대조한다.
3. Critical/Important/Minor로 finding을 기록한다.

Pass: Critical/Important finding이 없거나 수정·재검증이 끝났다.

기록: `docs/development-status-2026-06-29.ko.md` 최신 release-audit section.

## Gate 2. 계획 대비 갭 검증

입력: `docs/implementation-plan.ko.md` section 14–21, `docs/development-status-2026-06-29.ko.md` 최신 section, 관련 superpowers implementation plan.

방법:

1. 각 명시 완료 주장에 구현 파일·테스트·live evidence를 하나씩 연결한다.
2. 자동화가 증명하지 못하는 human acceptance를 별도 pending으로 남긴다.
3. 문서의 오래된 next-step 문구가 authoritative 최신 상태와 충돌하는지 확인한다.

Pass: 필수 요구사항은 evidence가 있고, 미검증 항목은 완료로 오기되지 않는다.

## Gate 3. 역방향 동작 검증

입력: 3/3 CapCut final MP4, FFprobe/SHA-256, local CapCut project, VideoBox draft/timeline/SRT artifact.

방법:

1. MP4 file → FFprobe duration/SHA-256을 확인한다.
2. CapCut project → 10분 timeline 및 해당 profile track/overlay surface를 확인한다.
3. project → VideoBox `draft_content.json` → timeline/editing-session/SRT source path를 역으로 연결한다.

Pass: 3개 profile 모두 final output에서 source contract까지 끊기지 않고 추적된다.

## Gate 4. 전체 시스템 점검

입력: 현재 HEAD.

방법:

1. `.venv\\Scripts\\python.exe -m pytest -q`
2. `npm --prefix apps/web test`
3. `npm --prefix apps/web run build`
4. `git diff --check`, `git status --short`, upstream divergence 확인.

Pass: test/build exit 0, whitespace error 없음, commit 대상 외 untracked는 분류되어 있음.

## Gate 5. 문서·지침 점검

입력: `AGENTS.md`, `docs/development-fast-path.ko.md`, implementation plan, status log, latest closeout plans.

방법:

1. authoritative pointer가 최신 closeout을 가리키는지 확인한다.
2. 실제 검증 수치, next recommendation, artifacts policy가 문서들 사이에 충돌하지 않는지 확인한다.
3. historical log는 삭제 대신 historical role을 유지한다.

Pass: current truth와 historical snapshot이 구분되고, current pointer·운영 규정이 일치한다.

## Gate 6. 찌꺼기 파일 분류·정리

입력: `git status --short`, `.gitignore`, `rg --files -g` inventory, document references.

분류:

| 분류 | 기준 | 조치 |
| --- | --- | --- |
| preserve-evidence | QA/reproduction output, active handoff, status document가 참조 | 보존·Git 제외 |
| tracked-source | Git tracked source/test/doc | 삭제 금지 |
| historical-reference | 오래된 closeout/plan이지만 evidence 역할 | 삭제 금지, 역할 유지 |
| safe-to-delete | Git 미추적, 문서/스크립트/테스트 비참조, 재생성 가능, 현재 실행 미사용 | 삭제 전 목록·근거 기록 후 삭제 |

Pass: 무단 삭제 없음. `safe-to-delete`가 없으면 삭제하지 않은 판단 자체를 기록한다.

## Closeout

1. finding severity와 수정 여부를 상태 문서에 기록한다.
2. Critical/Important는 TDD와 범위 검증으로 수정한 뒤 Gate 1–4 relevant check를 재실행한다.
3. `artifacts/`와 CapCut local export는 Git에 stage하지 않는다.
4. 계획서·상태 문서·운영 규정을 갱신하고 commit/push한다.

## 현재 HEAD 실행 기록 (2026-07-13)

| Gate | 결과 | 근거 및 조치 |
| --- | --- | --- |
| 1. 코드리뷰 | pass | Critical 1건(소유 확인 없는 incomplete destination 삭제), Important 2건(미검증 CapCut 버전 ready 판정, reload가 최신 failed draft export를 숨김)을 발견했다. 모두 TDD로 수정하고 focused backend 18 passed, frontend `app.test.tsx` 96 passed로 재검증했다. |
| 2. 갭 검증 | pass with human pending | CapCut 3 profile의 final MP4·draft·timeline·editing session·SRT 연결을 확인했다. 실제 사용자 녹음 listening approval과 일반 사용자 PC 1대 handoff smoke는 자동화 대체 불가 acceptance로 남긴다. |
| 3. 역방향 검증 | pass | `loop`, `crop_pad_overlay`, `audio_ducking`의 local MP4가 모두 FFprobe 600.026848초와 기록된 SHA-256으로 확인됐고, 각 CapCut draft, VideoBox final MP4, `draft_content.json`, timeline, editing session, SRT가 존재했다. |
| 4. 전체 시스템 | pass | `.venv\\Scripts\\python.exe -m pytest -q` 700 passed, `npm --prefix apps/web test` 102 passed, `npm --prefix apps/web run build` 성공, `git diff --check` clean, upstream divergence 0/0을 확인했다. |
| 5. 문서·지침 | pass | 이 protocol을 `development-fast-path` 10.12 고정 운영 규정에 연결하고, status SSOT 최신 section을 갱신한다. |
| 6. 파일 정리 | pass | `artifacts/`는 약 1GB의 QA/reproduction evidence이므로 보존하고 `.gitignore`에 명시했다. 비-artifact backup/tmp/orig/rej/pyc 후보는 없었다. safe-to-delete 0건이라 삭제하지 않는다. |
