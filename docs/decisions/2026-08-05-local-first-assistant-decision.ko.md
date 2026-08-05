# 유진 로컬 우선 전환 결정 기록

- 결정 상태: **approved**
- 결정 시각: 2026-08-05
- 승인자: owner
- 대상 조항: `docs/implementation-plan.ko.md` §23.3A.4 → §23.3B로 개정

## 결정

유진의 1차 대화 route를 **로컬 LLM**으로 바꾼다.
외부 provider(`gpt-5.4`, `gpt-5.4-mini`)는 어댑터 뒤에서 선택 가능한 대안이 되며 기본값이 아니다.

owner 발언: "헤르메스 에이전트는 일단 로컬 llm 을 물려서 동작하게 만들고,
어댑터까지 만들어서 gpt 5.4, 5.4 mini 같은 걸로 쉽게 스위칭 할 수 있게 하자."

## 무엇이 바뀌는가

기존 §23.3A.4는 이렇게 규정했다.

> 유진의 자유 대화·콘셉트/대본 창작·권한/승인 판단·tool selection을 Qwen으로 대체하지 않는다.

이 문장을 로컬 우선 방침으로 대체한다. 로컬 LLM이 유진의 자유 대화를 담당할 수 있다.

## 왜 바꾸는가

기존 제약은 외부 provider가 주 route라는 전제 위에 있었다. 그 전제가 성립하지 않는다.

1. §23.1 egress allowlist gateway가 없어 외부 route를 실행할 수 없다
2. §23.2.6 capability signer도 배포되지 않았다
3. 유진은 어느 경로로도 실제 대화를 해본 적이 없다
4. 로컬 route는 외부 전송이 없어 egress·consent·budget gate 대상이 아니다

즉 로컬이 실제 동작을 가장 먼저 확인할 수 있는 유일한 경로다.

## 무엇을 바꾸지 않는가

아래는 이 결정으로 완화되지 않는다.

- 유진은 DB, filesystem, shell, renderer, CapCut, raw HTTP, credential에 접근하지 않는다
- 편집 mutation은 계속 사람 승인 게이트를 거친다. 대화의 "네"는 승인이 아니다
- 대본·제목·썸네일·추천 영상 생성은 계속 제품 범위 밖이다
- 모델 출력은 untrusted proposal이며 매 tool call마다 권한을 재검사한다
- VideoBox DB가 계속 SSOT다
- provider 전환은 항상 명시적이고 기록된다. 조용한 대체·자동 fallback은 금지다
- 외부 provider 실제 호출은 §23.1 egress gate와 OAuth 로그인이 여전히 선행이다

## 리스크와 완화

| 리스크 | 완화 |
|---|---|
| 로컬 모델의 한국어 창작 품질이 검증되지 않았다 | 실제 대화 후 owner가 직접 판단한다. 품질 미달이면 어댑터로 외부 provider 전환 |
| 로컬 모델이 정형 출력을 안 지킬 수 있다 | JSON Schema와 validator를 필수로 유지한다. 실패는 `blocked` fallback |
| 컨테이너→호스트 경로가 네트워크 경계 변경이다 | `§10.14`에 따라 별도 기록하고, 로컬 loopback 외 대상은 열지 않는다 |

## 구현 계획

`docs/superpowers/plans/2026-08-05-videobox-owner-usable-recovery.md` Slice 5 (Task 12–14).
