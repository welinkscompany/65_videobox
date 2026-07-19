# VideoBox 유진 versioned profile contract 인수인계

**날짜:** 2026-07-20
**브랜치:** `codex/videobox-container-compatibility`
**상태:** 실제 provider 호출 없는 첫 read-only profile contract 완료.

## 완료 범위

- `yujin-video-director` 하나만 허용한다. profile ID, prompt/policy/template version, system/developer/context policy, task template, 1,500 ms timeout, strict response schema와 declared status-read capability는 exact built-in artifact와 literal SHA-256 manifest로 pin된다. 재계산한 custom manifest도 거부한다. immutable registry와 prompt envelope은 `system → developer → task → user` 역할 순서를 고정한다.
- context는 사용자가 선택한 한 project의 allowlisted status 6개 field만 immutable digest와 함께 user text와 분리된 untrusted context data로 묶는다. public envelope constructor도 key set·project binding·canonical digest를 재검증한다. status name/revision에 raw path·secret·prompt injection·다른 project ID가 있으면 생성 단계에서 거부한다. revision은 `revision-*`만 허용하며 embedded `project-*`도 거부한다.
- response는 `clarification_question`, `status_summary`, `actionless_proposal`, `blocked`의 strict union이다. capability는 `declared_read_capability`일 뿐 executor 호출이 아니며, 모든 response는 `action=null`, `authority_state=needs_human_review`, `non_authorizing=true`다. timeout 또는 invalid structured response는 executor 없이 bounded `blocked` fallback으로 끝난다.
- 한국어·영어 injection, 승인·렌더·export·CapCut·memory·credential·다른 project 요청은 `blocked`로 끝난다. 현재 선택 project ID를 포함한 정상 status 문의는 허용한다.

## 검증

- TDD RED: custom self-consistent manifest, 한국어 우회 요청, status reflection, operational response claim, revision `None` schema mismatch, literal JSON-schema pattern, revision의 cross-project token 및 selected-project overblocking을 재현했다.
- independent spec review와 quality review의 최종 결과는 P0/P1/P2 0이다.
- focused provider/profile suite는 `134 passed`, `compileall`, `git diff --check`, production image build와 `--network none --read-only` image import를 통과했다. runtime은 4-role envelope, selected-project context/status, 다른 project `blocked`, timeout fallback을 검증했다. full Python suite는 최신 코드에서 63초 timeout 뒤 pytest stdout `OSError`로 끝나 full-pass로 주장하지 않는다. 기존 Starlette multipart PendingDeprecationWarning 1건은 비차단이다.

## 계속 금지된 범위

Hermes bridge/container runtime, OAuth, GPT/Qwen/Gemini provider call, tool executor, DB/API route/UI activation, mem0, mutation/render/export, CapCut/host bridge는 이 contract로 시작하거나 허용되지 않는다. Gemini provider call은 0을 유지한다.

## 다음 Goal

기존 §23 범위 안에서 actual provider 호출 없이 **versioned ToolSpec/Gateway registry와 context filtering의 static fail-closed contract**를 구현한다. ToolSpec은 backend-derived selected-project scope, response/result schema, redaction, byte/time limit, allowed phase를 명시하고, 모델 문자열은 authority가 아님을 TDD로 고정한다. capability signer, Hermes network/OAuth, GPT/Qwen/Gemini call, DB/API route activation, mem0, mutation/render/export는 계속 시작하지 않는다.
