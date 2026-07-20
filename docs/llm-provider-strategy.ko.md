# VideoBox LLM Provider 전략

## 1. 현재 운영 결정

VideoBox의 자동 LLM runtime은 **로컬 Qwen만** 사용한다.

- `primary`: LM Studio loopback의 로컬 Qwen text/vision/embedding provider
- `fallback`: 없음. 로컬 structured generation 실패 시 deterministic/rule-based 결과 또는 사람 검수 필요 상태로 끝낸다.
- `external provider`: 자동 호출하지 않는다.

이 결정은 `docs/implementation-plan.ko.md` §23과 함께 적용한다. core-engine은 provider interface를 유지하지만, 배포된 VideoBox가 외부 provider를 선택하거나 호출하는 근거가 되지 않는다.

## 2. 외부 모델 provider 완전 퇴역 (완료)

VideoBox는 외부 생성 모델 provider를 사용하지 않는다.

- 외부 provider call은 static/runtime 모두 `0`이어야 한다.
- credential key pool, key-management API router, dashboard key-management UI와 provider implementation은 제거한다.
- 기존 프로젝트를 다시 열 때 퇴역 credential table은 삭제하며, credential·schema·module의 read compatibility를 제공하지 않는다.
- 새 key 입력, key rotation, provider fallback, 외부 모델 선택을 다시 추가하지 않는다.

## 3. 로컬 Qwen 경계

로컬 Qwen은 LM Studio의 허용된 loopback endpoint에서만 쓴다.

- 외부 HTTP(S) endpoint와 자동 fallback은 허용하지 않는다.
- text/vision/embedding profile은 실제 local runtime capability와 strict structured result로 검증한다.
- 로컬 모델이 없거나 응답이 invalid이면 외부 provider로 전환하지 않는다.
- 실패 결과는 job/audit에서 local-only failure 또는 deterministic fallback으로 구분한다.

## 4. Hermes 소유 ChatGPT OAuth와 VideoBox direct OAuth 경계

Hermes Agent 공식 문서는 `hermes model`에서 OpenAI Codex를 선택하면 ChatGPT OAuth device-code login을 지원한다고 명시한다. VideoBox의 첫 Hermes slice는 이 **Hermes 소유** 흐름만 검토·설치 대상으로 삼는다. 2026-07-19 기준 source pin은 signed release `v2026.7.7.2` / peeled commit `9de9c25f620ff7f1ce0fd5457d596052d5159596`이다. 근거: <https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/>, <https://hermes-agent.nousresearch.com/docs/user-guide/configuration/>.

- Hermes OAuth는 아직 설치·로그인·runtime 검증 전이므로 GPT provider call은 **0**이다.
- credential과 config는 Hermes 전용 state volume에만 두며 VideoBox API/DB, 일반 `.env`, mem0, snapshot, backup, log/trace에는 복사하지 않는다.
- VideoBox가 직접 OpenAI OAuth endpoint, redirect URI, client secret, auth code/refresh token 저장, generic device/PKCE flow, token endpoint를 구현하는 일은 **BLOCKED**다.
- OAuth bootstrap은 창작 요청이나 project data 전송 동의가 아니다. GPT inference를 허용하려면 request별 data-transfer 동의, endpoint/egress allowlist, budget, audit와 별도 사람 gate가 필요하다.

현재 VideoBox에는 OpenAI OAuth endpoint, credential, token, GPT external egress가 없다.

## 5. 외부 연동과 보조 기능

- ComfyUI, SaaS auth/billing, mem0와 VideoBox의 direct OAuth는 현재 runtime 범위 밖이다. Hermes service는 계획 §23의 isolated read-only slice로만 후속 도입한다.
- TTS/STT와 FFmpeg/CapCut handoff는 각자의 typed provider/handler 경계를 따르며 LLM fallback을 만들지 않는다.
- provider 변경은 공식 계획의 별도 slice, 사람 승인, static/runtime zero-call 검증 없이는 시작하지 않는다.

## 6. 검증 규칙

변경 후 최소한 다음을 확인한다.

1. OpenAPI/public route에 provider credential-management path가 없다.
2. web API client와 화면에 provider credential CRUD가 없다.
3. 신규·기존 project database에 퇴역 credential table이 없다.
4. focused/runtime 검증에서 external provider call은 `0`이다.
5. local-only runtime의 실패는 deterministic fallback 또는 사람 검수로 끝난다.

## 7. 최종 결론

`현재 VideoBox는 로컬 Qwen만 자동 runtime으로 사용한다. 외부 생성 모델 provider의 credential·코드·경로는 제거했으며 호출하지 않는다. Hermes의 공식 ChatGPT OAuth는 전용 container state에서만 후속 검증할 수 있고, VideoBox의 direct OAuth와 GPT 호출은 아직 없다.`
