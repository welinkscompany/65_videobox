# VideoBox LLM Provider 전략

## 1. 현재 운영 결정

VideoBox의 자동 LLM runtime은 **로컬 Qwen만** 사용한다.

- `primary`: LM Studio loopback의 로컬 Qwen text/vision/embedding provider
- `fallback`: 없음. 로컬 structured generation 실패 시 deterministic/rule-based 결과 또는 사람 검수 필요 상태로 끝낸다.
- `external provider`: 자동 호출하지 않는다.

이 결정은 `docs/implementation-plan.ko.md` §23과 함께 적용한다. core-engine은 provider interface를 유지하지만, 배포된 VideoBox가 외부 provider를 선택하거나 호출하는 근거가 되지 않는다.

## 2. Gemini 격리 (완료)

Gemini는 VideoBox에서 사용하지 않는다.

- Gemini provider call은 static/runtime 모두 `0`이어야 한다.
- Gemini key pool, key-management API router, dashboard key-management UI는 **disabled·unwired**다.
- 과거에 저장된 Gemini key 레코드와 스키마, router/storage/core module은 삭제하지 않는다. migration/read compatibility를 위해 inert 상태로 보존한다.
- legacy router는 `create_app`에 import·등록하지 않으며, web API client와 화면은 Gemini key CRUD를 노출하지 않는다.
- 새 key 입력, key rotation, provider fallback, Gemini 모델 선택을 다시 추가하지 않는다.

## 3. 로컬 Qwen 경계

로컬 Qwen은 LM Studio의 허용된 loopback endpoint에서만 쓴다.

- 외부 HTTP(S) endpoint와 자동 fallback은 허용하지 않는다.
- text/vision/embedding profile은 실제 local runtime capability와 strict structured result로 검증한다.
- 로컬 모델이 없거나 응답이 invalid이면 외부 provider로 전환하지 않는다.
- 실패 결과는 job/audit에서 local-only failure 또는 deterministic fallback으로 구분한다.

## 4. OpenAI 사용자 위임 OAuth (BLOCKED)

Hermes/Yujin을 위한 OpenAI 사용자 위임 OAuth는 아직 구현하지 않았고, 현재 **BLOCKED**다.

- 공식 provider 문서와 현재 약관에서 지원되는 OAuth flow, client type, scope, redirect/verification UX, token 사용 권한을 먼저 증명해야 한다.
- device authorization flow와 authorization-code + PKCE는 동시에 가정하지 않는다. 공식 근거가 확인된 한 방식만 versioned contract로 고정한다.
- 공식 지원 근거가 없거나 entitlement/데이터 전송 권한이 불명확하면 OAuth endpoint, token 저장, GPT provider call을 만들지 않는다.
- OAuth bootstrap은 창작 요청이나 project data 전송 동의가 아니다. 향후 허용되더라도 request별 data-transfer 동의, endpoint pinning, budget, audit가 별도로 필요하다.

현재 VideoBox에는 OpenAI OAuth endpoint, credential, token, external egress가 없다.

## 5. 외부 연동과 보조 기능

- ComfyUI, SaaS auth/billing, Hermes service, mem0는 이 provider 전략의 현재 runtime 범위 밖이다.
- TTS/STT와 FFmpeg/CapCut handoff는 각자의 typed provider/handler 경계를 따르며 LLM fallback을 만들지 않는다.
- provider 변경은 공식 계획의 별도 slice, 사람 승인, static/runtime zero-call 검증 없이는 시작하지 않는다.

## 6. 검증 규칙

변경 후 최소한 다음을 확인한다.

1. OpenAPI/public route에 Gemini key-management path가 없다.
2. web API client와 화면에 Gemini key CRUD가 없다.
3. local-only runtime guard가 Gemini/fallback-capable service를 거부한다.
4. focused/runtime 검증에서 external Gemini provider call은 `0`이다.
5. legacy persisted Gemini data를 삭제하거나 migration compatibility를 깨지 않는다.

## 7. 최종 결론

`현재 VideoBox는 로컬 Qwen만 자동 runtime으로 사용한다. Gemini는 보존된 과거 데이터와 코드만 inert 상태로 남기며 호출하지 않는다. OpenAI 사용자 위임 OAuth는 공식 지원 근거가 확인될 때까지 BLOCKED다.`
