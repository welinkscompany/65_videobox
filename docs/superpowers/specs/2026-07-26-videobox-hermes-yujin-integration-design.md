# VideoBox Hermes 유진 통합 설계

**날짜:** 2026-07-26
**상태:** written design — 사용자 검토 대기
**대상:** 개인 로컬 VideoBox MVP
**선택안:** 유진 한 명을 총괄 Hermes 에이전트로 두고 영상 제작 기능을 skills/tools로 제공한다.

## 1. 목적

VideoBox 편집기 오른쪽 대화창에서 Hermes 유진과 실제로 대화하고, 유진이 현재 프로젝트를 안전하게 이해해 영상 편집을 돕도록 한다.

유진은 한 명의 총괄 에이전트다. 음악, 효과음, B-roll, TTS, 자막, 검수 기능을 별도 에이전트로 쪼개지 않고 유진의 명시적인 skills/tools로 제공한다. 이 구조는 여러 에이전트 사이의 기억 충돌, 권한 중복, 서로 다른 편집 revision 사용을 피한다.

Mem0는 Hermes 유진의 보조 기억장치로만 사용한다. VideoBox 프로젝트·편집 session·timeline·media·review·output 데이터의 기준은 계속 VideoBox DB와 기존 runtime이다.

## 2. 현재 확인된 상태

현재 checkout과 로컬 runtime 조사에서 다음 상태를 확인했다.

- Hermes Dashboard는 `http://127.0.0.1:9119`에서 응답한다.
- 현재 `videobox-hermes-agent` 컨테이너는 종료 상태다.
- 과거 `videobox-hermes-runtime` 컨테이너도 종료 상태이며 현재 `compose.yaml`의 정식 서비스가 아니다.
- 실행 중이거나 남아 있는 Hermes 컨테이너 이미지와 현재 `compose.yaml`의 pinned digest 사이에 drift가 있다.
- 유진의 Soul, prompt profile, response-only skills, ToolSpec, capability 계약은 source에 정적으로 존재한다.
- 정적 Agent Package가 실제 Hermes agent home에 설치·로드됐다는 runtime 증거는 없다.
- 현재 VideoBox Director 대화는 Hermes가 아니라 `LocalOnlyRuntimeService`를 사용한다.
- `videobox-agent-gateway`와 capability issuance는 선언 상태이며 배포되지 않았다.
- Dashboard HTTP 200은 OAuth provider 성공, Hermes 대화 성공, Mem0 write/search 성공을 증명하지 않는다.
- Mem0는 VideoBox 프로젝트 SSOT가 아니며 실제 유진 대화에 반영된 live 증거가 없다.

따라서 이 작업은 기존 대화창을 새로 만드는 일이 아니라, 이미 영속화된 Director conversation과 안전한 편집 경계를 실제 Hermes 유진에 연결하는 작업이다.

## 3. 범위

### 3.1 포함

- 현재 Hermes 컨테이너·Dashboard·OAuth state의 소유권과 버전 정합성
- 실제 실행 가능한 유진 Hermes agent
- versioned Soul/profile/skills 설치와 runtime 로드 검증
- 별도 내부 Agent Gateway
- VideoBox Director 대화창의 Hermes 실시간 응답
- durable conversation 복구와 idempotent retry
- Mem0 Platform 기반 유진 보조 기억
- 명시적 memory candidate 승인·조회·삭제
- 현재 프로젝트를 읽는 최소 allowlist tools
- B-roll/BGM/SFX/TTS/caption/검수 제안 skills
- 기존 EditorCommandPort와 current-revision 적용 경계 재사용
- 자동화된 코드리뷰, 계획 갭 검증, source-to-runtime 역방향 검증
- local/test 외부 provider call 0

### 3.2 제외

- SaaS auth, team, tenant, billing, cloud storage
- OpenCut runtime 또는 full NLE 도입
- 여러 Hermes 전문 에이전트
- source media 직접 복사·이동·삭제
- Hermes 또는 Mem0의 VideoBox DB/미디어 직접 접근
- Hermes의 직접 편집 mutation, render, export, CapCut 조작
- 사용자 확인 없는 자동 apply
- Telegram intake, 외부 게시, 광고, 업로드
- title/topic/thumbnail/description/hashtag 생성 권한 확대
- Mem0 OSS/self-hosted adapter

Mem0 OSS가 필요해지면 현재 `development-fast-path`의 Platform-only memory 경계를 변경하는 별도 설계와 승인을 먼저 받는다.

## 4. 책임 분리

| 구성요소 | 책임 | 하지 않는 일 |
| --- | --- | --- |
| VideoBox DB/runtime | 프로젝트, media, editing session, timeline, review, output SSOT | Hermes memory를 편집 데이터로 해석하지 않음 |
| VideoBox Editor | 대화 표시, 제안 확인, 기존 revision-safe command 실행 | provider/OAuth/secret 관리 |
| Agent Gateway | context 최소화, capability, Hermes 요청, stream 중계, 감사 | media/DB 직접 mount, 편집 mutation |
| Hermes 유진 | 대화, 설명, 질문, 편집 제안, memory candidate 제안 | 직접 apply, render/export, 승인 대행 |
| Mem0 Platform | 사용자가 승인한 유진 보조 기억 | project/session/revision/output SSOT |
| Hermes Dashboard | owner-operated OAuth/model/memory 설정과 진단 | 일반 VideoBox 사용자 화면, VideoBox 데이터 조회 |

## 5. 목표 아키텍처

```text
VideoBox Editor RightDock
  ├─ POST message / retry / cancel
  └─ SSE response stream
          │
          ▼
VideoBox API conversation owner
          │ durable conversation + route/session/revision fence
          ▼
videobox-agent-gateway
  ├─ selected-project allowlist context
  ├─ short-lived read capability
  ├─ request/idempotency/audit
  └─ Hermes transport
          │
          ▼
Hermes 유진
  ├─ Soul/profile
  ├─ creator skills
  ├─ allowlisted read tools
  └─ approved auxiliary memory ↔ Mem0 Platform
```

Dashboard와 유진 agent는 owner-operated OAuth/model/memory state를 공유할 수 있지만, Dashboard에는 VideoBox network와 data mount를 주지 않는다. 유진 agent도 VideoBox DB·media mount를 직접 받지 않는다. 프로젝트 정보는 Agent Gateway가 발급한 짧은 capability와 allowlisted internal tool을 통해서만 읽는다.

## 6. 유진 Soul과 Agent Package

유진 Soul의 고정 책임은 다음과 같다.

- 한국어로 짧고 이해하기 쉽게 말한다.
- 현재 선택된 프로젝트만 다룬다.
- 사용자가 영상을 완성하는 다음 행동을 중심으로 답한다.
- 불확실한 사실을 확정적으로 말하지 않는다.
- 편집 제안과 실행을 분리한다.
- 사용자가 확인하기 전에는 편집을 적용하지 않는다.
- VideoBox DB와 editing session이 편집 사실의 기준임을 유지한다.
- Mem0 기억을 사실·권한·승인 근거로 사용하지 않는다.
- 다른 프로젝트, secret, raw path, raw media, 계정 정보 요청을 거부한다.

Agent Package는 다음 versioned artifact를 하나의 manifest로 묶는다.

- Soul
- system/developer/task prompt
- creator skills manifest
- ToolSpec allowlist
- memory policy
- response event schema
- package/version/digest

Dashboard에서 model을 선택했다고 Agent Package가 설치된 것으로 보지 않는다. 실제 유진 실행 전에 runtime home에서 package digest, Soul version, skills manifest, memory policy가 모두 일치하는지 verifier로 확인한다.

## 7. 실시간 대화

### 7.1 transport

사용자 메시지는 기존처럼 idempotency key가 포함된 `POST`로 제출한다. 응답은 Server-Sent Events(SSE)로 전달한다.

SSE를 선택하는 이유는 다음과 같다.

- 사용자는 HTTP POST로 말하고 서버가 한 방향으로 답변을 stream하면 충분하다.
- WebSocket보다 재연결, request ownership, 테스트가 단순하다.
- 기존 FastAPI와 durable Director conversation을 유지할 수 있다.
- stream이 끊겨도 최종 메시지를 API로 다시 읽을 수 있다.

### 7.2 event 계약

외부 UI에 노출하는 최소 event는 다음과 같다.

- `run_started`
- `text_delta`
- `memory_reference`
- `proposal_ready`
- `blocked`
- `run_completed`

내부 provider 이름, token, model trace, raw prompt, secret, memory raw payload는 UI event에 넣지 않는다.

### 7.3 durable truth

- 사용자 메시지는 처리 시작 전에 durable claim으로 보호한다.
- 동일 `client_message_id` 재전송은 같은 run을 복구하거나 idempotency conflict로 막는다.
- assistant text는 완료된 교환만 canonical Director message로 확정한다.
- 중간 delta는 편의 표시이며 durable assistant truth가 아니다.
- 새로고침은 기존 Director reload API가 canonical transcript와 proposal을 복구한다.
- project/session/route epoch가 바뀐 뒤 도착한 stream은 UI와 편집 상태를 바꾸지 않는다.
- Hermes 장애 시 기존 수동 Inspector와 EditorCommandPort는 계속 사용할 수 있다.

## 8. Agent Gateway와 tools

Agent Gateway는 Hermes와 VideoBox 사이의 유일한 연결이다.

### 8.1 첫 allowlist

첫 단계에서 허용하는 도구는 읽기 또는 실행 없는 제안에 한정한다.

- 현재 프로젝트 상태 읽기
- 현재 editing session 요약 읽기
- timeline의 장면·track·reference 읽기
- 등록된 media 후보 메타데이터 읽기
- current proposal/review blocker 읽기
- current exact/final/output 상태 읽기

응답은 project/session/revision과 연결된 작은 schema로 제한하며 raw file path, media bytes, credential, 다른 project data는 반환하지 않는다.

### 8.2 편집 적용

Hermes는 mutation tool을 직접 호출하지 않는다.

1. 유진이 typed proposal을 만든다.
2. RightDock가 변경 내용과 대상을 보여준다.
3. 사용자가 적용을 누른다.
4. 기존 EditorCommandPort가 expected revision을 포함해 mutation한다.
5. VideoBox가 authoritative session을 새로 읽는다.
6. conflict면 제안을 stale로 바꾸고 자동 재적용하지 않는다.

따라서 Hermes provider, memory, stream 실패가 직접 편집 변경으로 이어지지 않는다.

## 9. Mem0 보조 기억

### 9.1 저장 가능한 기억

- 선호하는 영상 길이 범위
- 편집 템포
- 자막 표시 방식
- 기본 BGM 음량과 fade 선호
- narration/BGM ducking 선호
- 반복 사용하는 검수 체크
- 사용자가 명시적으로 “기억해”라고 승인한 작업 선호

### 9.2 저장 금지

- source media 또는 media 내용
- script, caption 전문
- file path
- project DB row
- editing session/timeline/revision
- review/approval/publish state
- render/CapCut artifact
- account, OAuth, credential, secret
- 다른 시스템의 업무 데이터

### 9.3 memory candidate 흐름

1. 유진이 대화에서 기억 후보를 제안한다.
2. UI가 저장될 짧은 문장과 scope를 보여준다.
3. 사용자가 명시적으로 승인한다.
4. Gateway가 schema와 금지 항목을 다시 검사한다.
5. Hermes memory provider가 저장한다.
6. 저장 결과는 secret이나 raw provider payload 없이 상태만 표시한다.

자동 대화 수집과 자동 저장은 금지한다.

### 9.4 retrieval

- 유진은 답변 전에 필요한 경우에만 제한된 top-k 기억을 검색한다.
- 검색된 기억은 “저장된 선호”로 표시하고 프로젝트 사실과 섞지 않는다.
- 기억과 현재 VideoBox 상태가 충돌하면 VideoBox 상태가 우선한다.
- 기억만으로 편집 apply, 승인, render, export를 결정하지 않는다.
- 사용자는 Dashboard가 아니라 VideoBox memory surface에서 자신의 기억 목록을 보고 삭제할 수 있다. 이 surface는 provider 설정 화면과 분리한다.

## 10. 영상 제작 skills

Phase D의 유진 skills는 기존 backend와 EditorCommandPort가 실제 지원하는 범위만 노출한다.

- 장면과 media 상태 설명
- B-roll 후보 비교와 추천 이유
- BGM/SFX 후보 비교
- BGM gain/fade/ducking 제안
- SFX 위치·gain 제안
- 승인 가능한 TTS 후보 안내
- caption 문구와 지원되는 style 제안
- overlay/B-roll/caption/audio 누락 검사
- current output blocker 설명
- 부분 재생성 범위 제안
- 최종 출력 전 영상·음악·효과음·TTS·자막 체크

backend가 지원하지 않는 effect, independent caption timing, advanced keyframe/mask/transition은 노출하지 않는다. 새로운 control을 추가할 때는 backend→EditorCommandPort→Inspector→final/CapCut 역방향 trace가 먼저 존재해야 한다.

## 11. 오류와 복구

| 상황 | 사용자 동작 | 시스템 동작 |
| --- | --- | --- |
| Hermes 미기동 | 다시 연결 또는 수동 편집 | 대화만 blocked, Editor 유지 |
| OAuth/model 미설정 | 관리 화면에서 연결 | secret을 VideoBox에 복사하지 않음 |
| stream 중단 | 답변 다시 받기 | 같은 run 복구, 중복 메시지 생성 금지 |
| provider timeout | 재시도 또는 수동 편집 | 자동 provider 변경 금지 |
| stale project/session | 현재 영상 다시 확인 | 오래된 response/proposal 폐기 |
| memory 실패 | 기억 없이 계속 | 편집과 대화 transcript 유지 |
| memory conflict | 현재 설정 사용 | VideoBox 상태 우선 |
| tool capability 만료 | 현재 상태 다시 읽기 | 자동 mutation 금지 |
| Agent Package drift | 관리자 복구 | 유진 실행 fail-closed |

기본 VideoBox 화면에는 provider/runtime/model/API 용어를 노출하지 않는다. Dashboard와 별도 관리 진단 화면에서만 기술 상태를 표시한다.

## 12. 계획서 계층

이 설계 승인 뒤 다음 문서를 작성한다.

### 12.1 총괄 계획서

`docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`

총괄 계획서만 다음 항목의 SSOT가 된다.

- 전체 범위와 제외 범위
- Phase 0, A, B, C, D 순서
- 하위 계획 의존성
- 고정 Task 분모와 전체 진행률
- 공통 acceptance matrix
- 전체 reverse runtime trace
- 현재 next goal
- phase closeout 링크

### 12.2 하위 계획서

1. `2026-07-26-videobox-hermes-yujin-runtime-dashboard.md`
2. `2026-07-26-videobox-hermes-yujin-realtime-chat.md`
3. `2026-07-26-videobox-hermes-yujin-mem0-memory.md`
4. `2026-07-26-videobox-hermes-yujin-creator-tools.md`

각 하위 계획서는 부모 링크, 선행 gate, 입력/출력 계약, TDD task, 검증 명령, closeout evidence, 다음 phase handoff를 갖는다. 하위 계획은 총괄 범위를 다시 정의하지 않는다.

## 13. 지속적인 완료 상태 업데이트

사용자가 요구한 대로 구현 중 실제 완료 상태를 계속 계획서에 반영한다.

상태 표기는 다음 네 개만 사용한다.

- `[ ] pending`: 시작하지 않았거나 완료 근거가 없다.
- `[~] in progress`: RED, 구현 또는 검증이 진행 중이다.
- `[x] complete`: 구현·필수 검증·review·closeout evidence가 모두 있다.
- `[!] blocked`: 사용자 권한, secret, 외부 환경 또는 해결되지 않은 Critical/Important finding이 필요하다.

운영 규칙은 다음과 같다.

1. Task를 시작하는 첫 논리 commit에서 하위 계획을 `[~]`로 바꾼다.
2. 코드만 작성됐다는 이유로 `[x]`로 바꾸지 않는다.
3. 필수 test, code review, plan gap, reverse trace가 모두 끝난 같은 closeout 단위에서 `[x]`로 바꾼다.
4. 하위 Task가 `[x]`가 되면 같은 commit에서 총괄 계획의 Task mirror와 진행률을 갱신한다.
5. `[!]`는 완료 수에 포함하지 않는다.
6. `[~]`는 절반 완료로 계산하지 않는다.
7. 회귀나 잘못된 완료 근거가 발견되면 `[x]`를 다시 `[~]` 또는 `[!]`로 되돌리고 이유를 기록한다.
8. 각 closeout에는 commit, 검증 수치, review finding, 남은 human gate를 기록한다.
9. plan-state verifier는 하위 체크박스와 총괄 mirror가 다르면 실패한다.
10. 턴 종료 보고는 총괄 계획의 고정 Task 분모로 완료율과 잔여율을 계산한다.

기존 22 Task 진행률과 새 Hermes 계획 진행률은 섞지 않는다.

- 기존 VideoBox MVP: 기술 상태와 Task 9 사람 acceptance를 별도로 보고한다.
- 새 Hermes 유진 통합: 총괄 계획서의 고정 Task 수로 별도 보고한다.

## 14. 실행 순서와 gate

### Phase 0 — 기준선 감사

production code를 바꾸기 전에 현재 HEAD를 기준으로 다음을 기록한다.

- Compose/source/live container drift
- Dashboard/OAuth/model/memory 경계
- Soul/package/runtime 설치 gap
- 현재 RightDock→Director API→LocalOnlyRuntimeService reverse trace
- capability/gateway 배포 gap
- full Python/frontend/E2E/build baseline
- 보호된 임시 폴더와 QA artifact 분류

Task 22 전체를 처음부터 다시 리뷰하지 않는다. Task 22에서 검증하지 않았고 새 통합이 실제로 접촉하는 Hermes, conversation, gateway, network, memory 경계를 집중 감사한다.

### Phase A — Hermes 유진 runtime, Soul, Dashboard

Phase A 종료 조건:

- 하나의 pinned runtime image
- current Compose와 live service 정합성
- 유진 Agent Package runtime 설치·digest 검증
- owner-operated OAuth/model 설정 경로
- Dashboard와 agent의 건강 상태 분리
- restart와 fail-closed 복구
- VideoBox DB/media/internal network 비접속

### Phase B — Agent Gateway와 실시간 대화

Phase B 종료 조건:

- gateway-only transport
- POST+SSE 대화
- durable transcript/retry/reload
- project/session/route epoch fence
- manual fallback
- local/test external provider call 0
- 실제 owner-operated Hermes canary는 자동 test와 별도 증거로 기록

### Phase C — Mem0 보조 기억

Phase C 종료 조건:

- Dashboard에서 owner-operated Mem0 Platform 설정
- memory candidate 승인
- store/search/list/delete canary
- 대화 retrieval 반영
- SSOT·권한·민감정보 분리
- memory 장애 시 대화와 편집 지속

### Phase D — 영상 제작 skills/tools

Phase D 종료 조건:

- 지원되는 read tools와 typed proposals
- B-roll/BGM/SFX/TTS/caption/검수 skills
- explicit apply를 기존 EditorCommandPort에 연결
- unsupported control 0
- revision conflict와 stale proposal 복구
- exact/final/CapCut 역방향 trace

### 최종 통합 gate

- 독립 code-quality review
- 총괄/하위 계획 gap review
- RightDock→Gateway→Hermes→tool→proposal→EditorCommandPort reverse trace
- 전체 Python/frontend/E2E/build
- provenance/UI/network/SBOM
- local/test external provider call 0
- live Dashboard/Hermes/Mem0 canary와 자동 검증 분리
- Task 9 사람/환경 acceptance와 별도 보고

## 15. 테스트 전략

### 15.1 TDD

각 하위 Task는 RED를 먼저 관찰하고 GREEN 뒤 관련 회귀를 실행한다. live provider가 필요한 계약도 fake transport와 fixed event fixture로 RED/GREEN을 고정한다.

### 15.2 자동 검증

- Soul/package digest와 tamper rejection
- Compose image/mount/network/user/capability 경계
- Agent Gateway capability, expiry, replay, revoke
- SSE order, reconnect, cancel, duplicate, terminal event
- conversation persistence와 project/session fence
- memory candidate sanitization과 explicit consent
- memory retrieval precedence와 delete
- typed proposal과 EditorCommandPort revision fence
- unsupported effect/control inventory
- external network 0

### 15.3 live 검증

live 검증은 자동 test와 섞지 않는다.

- Dashboard 접근
- owner-operated OAuth/model 연결
- 실제 유진 한 번 대화
- 실제 Mem0 store/search/delete
- VideoBox RightDock의 실제 streamed response

계정, device code, credential, raw memory 내용은 로그·문서·Git에 기록하지 않는다.

## 16. 성공 기준

이 통합은 다음 조건을 모두 만족할 때 완료다.

1. 유진 Agent Package의 Soul/profile/skills가 실제 Hermes runtime에서 검증된다.
2. VideoBox RightDock에서 실제 유진 응답을 stream으로 받는다.
3. 새로고침과 재시도 뒤에도 conversation이 복구된다.
4. 프로젝트 전환 뒤 오래된 응답이 표시되거나 적용되지 않는다.
5. 유진이 막혀도 사용자는 수동으로 편집할 수 있다.
6. Mem0는 승인된 보조 기억만 저장·검색·삭제한다.
7. Mem0가 VideoBox project truth나 권한으로 사용되지 않는다.
8. 유진 제안은 사용자의 명시적 적용 전까지 편집을 바꾸지 않는다.
9. 적용은 기존 current-revision EditorCommandPort를 통한다.
10. 계획서의 실제 완료 항목과 총괄 진행률이 항상 일치한다.
11. Critical/Important review finding이 0이다.
12. 자동 test와 live owner evidence가 구분돼 기록된다.

## 17. 반대 논리와 결정

### 여러 전문 에이전트가 더 전문적이지 않은가?

장기적으로는 가능하지만 현재는 같은 editing session과 memory를 여러 agent가 다루면서 충돌할 위험이 더 크다. 한 명의 유진에 skills를 분리하면 사용자 경험과 권한 경계가 단순하고, 나중에 특정 skill의 독립 agent 분리가 필요한지 실제 사용 증거로 판단할 수 있다.

### Hermes가 직접 편집하면 더 빠르지 않은가?

빠르지만 provider 응답, stale context, memory 오류가 즉시 편집 손상으로 이어질 수 있다. 기존 EditorCommandPort와 명시적 사용자 적용을 유지하면 속도 손실은 작고 복구 가능성은 크게 높다.

### 이전 Task 22 전체 감사를 다시 해야 하지 않는가?

Task 22는 이미 editor/output release audit을 통과했다. 전체를 다시 반복하면 비용만 커진다. 대신 당시 제외됐고 이번 작업이 실제로 접촉하는 Hermes, gateway, conversation, network, memory 경계를 Phase 0에서 집중 감사한다.

### Mem0에 프로젝트 정보를 넣으면 더 똑똑하지 않은가?

단기 응답은 좋아질 수 있지만 오래된 revision과 잘못된 승인 상태가 기억으로 남아 편집 사실과 충돌한다. 프로젝트 상태는 매번 VideoBox에서 읽고, Mem0에는 장기 선호만 보관한다.
