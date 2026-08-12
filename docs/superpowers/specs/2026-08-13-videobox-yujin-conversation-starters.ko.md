# VideoBox 유진 대화 스타터 설계

## 상태

- 사용자 승인: 2026-08-13
- 범위: 편집기 Right Dock의 대화 빈 상태 UX
- 제외: Hermes provider/configuration, agent gateway, proposal backend, editor mutation

## 목표

유진 대화가 아직 시작되지 않은 편집기에서 사용자가 자연어 요청을 쉽게 시작할 수 있도록 한다. 대화 스타터는 기존 VideoBox 디자인 시스템과 풋티지 화면의 컴팩트 칩 패턴을 따르며, 선택 즉시 외부 효과를 발생시키지 않는다.

## 사용자 흐름

1. 사용자가 편집기 Right Dock의 빈 유진 대화 영역을 본다.
2. `무엇을 도와드릴까요?` 안내와 컴팩트 스타터 칩 4개를 확인한다.
3. 칩을 클릭한다.
4. 기존 요청 입력창에 해당 문장이 채워지고 입력창으로 포커스가 이동한다.
5. 사용자가 문장을 검토·수정한 뒤 `요청 보내기`를 명시적으로 누른다.
6. 그때만 기존 `onSendMessage` 경로를 통해 대화를 전송한다.

스타터 클릭 자체는 메시지 생성, Hermes 호출, 제안 생성, 미디어 적용, timeline mutation을 수행하지 않는다.

## 화면 설계

빈 대화 상태에서 다음 구조를 사용한다.

- 제목: `무엇을 도와드릴까요?`
- 보조 문구: `스타터를 누르면 요청 문장이 입력창에 채워져요.`
- 칩:
  - `이 장면에 어울리는 B-roll 추천해 줘`
  - `현재 편집 흐름 점검해 줘`
  - `자막을 더 간결하게 다듬어 줘`
  - `세로 영상용으로 바꿀 부분 찾아 줘`

칩은 Right Dock의 제한된 폭에서 줄바꿈되는 컴팩트 버튼으로 표현한다. 기존 `유진에게 추천받기` 버튼은 자동 제안 생성이라는 별도 흐름이므로 유지한다. 대화 스타터와 자동 제안 CTA를 하나의 동작으로 합치지 않는다.

## 표시·상태 규칙

- `messages.length === 0`, `proposal` 없음, 대화가 시작되지 않은 상태에서만 표시한다.
- 기존 대화 메시지 또는 proposal이 있으면 빈 상태 스타터를 표시하지 않는다.
- `composerDisabled`가 true이면 칩도 비활성화한다.
- 오류·unavailable 상태에서도 기존 복구 문구와 수동 편집 경로를 우선하며, 스타터가 자동 재시도를 의미하지 않도록 한다.
- 칩은 `button type="button"`과 명확한 accessible name을 사용한다.

## 구현 경계

- `RightDock` 내부의 정적 starter 정의와 controlled draft 업데이트만 추가한다.
- 기존 `draft`, `onDraftChange`, `onSendMessage` 계약을 재사용한다. 새 API prop이나 backend route는 추가하지 않는다.
- 입력창 ref를 사용해 스타터 선택 후 입력창에 포커스를 준다.
- 스타터 클릭 시 `onSendMessage`, `onStart`, `onApplyProposal`, `onManualEdit`를 호출하지 않는다.
- 기존 `EditorCommandPort`, proposal approval, Hermes SSE/run lifecycle에는 변경을 가하지 않는다.
- 스타일은 `apps/web/src/styles/editor-workbench.css`의 기존 토큰과 Right Dock 구조를 사용한다. 새로운 색상 체계나 독립적인 디자인 언어를 만들지 않는다.

## 검증 계획

Right Dock 단위 테스트에 다음을 추가한다.

1. 빈 대화 상태에서 4개 starter가 표시된다.
2. starter 클릭이 정확한 문장을 `onDraftChange`로 전달한다.
3. starter 클릭이 `onSendMessage` 또는 기존 자동 제안 경로를 호출하지 않는다.
4. 클릭 후 요청 입력창이 포커스를 가진다.
5. 기존 메시지 또는 proposal이 있으면 starter가 표시되지 않는다.
6. `composerDisabled` 상태에서는 starter가 비활성화된다.

관련 기존 Right Dock/editor workbench 테스트, frontend build, `git diff --check`를 실행한다. 실제 Hermes live chat과 owner acceptance는 이 UI slice의 자동 검증 범위가 아니며 별도 gate로 기록한다.

## 접근성·안전 검토

- 입력창을 직접 조작하는 보조 UI이므로 mutation 권한을 새로 만들지 않는다.
- 버튼 키보드 조작은 native button semantics에 맡긴다.
- 포커스 이동은 사용자가 선택한 요청을 즉시 검토할 수 있게 하지만 자동 전송은 하지 않는다.
- 내부 source ID, proposal ID, filesystem path, shell 지시는 starter 문구에 포함하지 않는다.
- 스타터 문구가 변경되어도 최종 실행은 기존 명시적 전송·제안 preview·approval 경로를 통과한다.

## 결정 근거

컴팩트 칩은 Right Dock의 가로 폭과 기존 풋티지 스타터 패턴을 동시에 만족한다. 목적별 카드보다 세로 공간을 적게 차지하고, 대표 제안 + 목록보다 특정 작업으로 사용자를 과도하게 유도하지 않는다. 입력만 채우는 동작은 대화 내용을 사용자가 검토할 수 있고, Hermes가 비구성 상태일 때도 불필요한 실패 요청을 발생시키지 않는다.
