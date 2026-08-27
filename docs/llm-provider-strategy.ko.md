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

Hermes Agent 공식 문서는 `hermes model`에서 OpenAI Codex를 선택하면 ChatGPT OAuth device-code login을 지원한다고 명시한다. VideoBox의 첫 Hermes slice는 이 **Hermes 소유** 흐름만 검토·설치 대상으로 삼는다. 근거: <https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/>, <https://hermes-agent.nousresearch.com/docs/user-guide/configuration/>.

**Hermes Agent 버전 pin의 SSOT는 `config/hermes/agent-pin.env`다.** 태그·다이제스트를
여기 적지 않는다 — 2026-08-27에 같은 값이 11개 파일에 흩어져 있다가 어긋날 뻔한 뒤로,
버전 번호는 그 파일 하나에서만 관리하고 나머지는 `tests/test_hermes_agent_pin_consistency.py`가
지킨다. 현재 값을 보려면 그 파일을 열어라.

- Hermes OAuth는 아직 설치·로그인·runtime 검증 전이므로 GPT provider call은 **0**이다.
- credential과 config는 Hermes 전용 state volume에만 두며 VideoBox API/DB, 일반 `.env`, mem0, snapshot, backup, log/trace에는 복사하지 않는다.
- VideoBox가 직접 OpenAI OAuth endpoint, redirect URI, client secret, auth code/refresh token 저장, generic device/PKCE flow, token endpoint를 구현하는 일은 **BLOCKED**다.
- OAuth bootstrap은 창작 요청이나 project data 전송 동의가 아니다. GPT inference를 허용하려면 request별 data-transfer 동의, endpoint/egress allowlist, budget, audit와 별도 사람 gate가 필요하다.

현재 VideoBox에는 OpenAI OAuth endpoint, credential, token, GPT external egress가 없다.

## 5. 외부 연동과 보조 기능

- **ComfyUI는 2026-08-20에 범위 안으로 들어왔다** (owner 승인, `development-fast-path.ko.md` §10.14 조항 2-C).
  대본의 장면에 맞는 그림을 만들어 자산 공백을 채우는 한 경로에만 적용된다.
  이 문서의 이전 판은 "범위 밖"이라고 적고 있었다 -- 두 문서가 서로 다른 말을 하게
  두지 않으려고 여기서 같이 고친다.
  - LLM provider가 아니다. ComfyUI는 OpenAI 모양이 아니라
    (`POST /prompt` 그래프 JSON → `/history` 폴링 → `/view` 회수) 이 문서의 §1~§4가
    말하는 provider 경계와 종류가 다르다. 전용 provider는
    `videobox_provider_interfaces/comfyui_image_generation.py`다.
  - **외부로 나가지 않는다.** 주소는 `http://127.0.0.1:8188` 또는
    `http://host.docker.internal:8188` 둘뿐이고 `ImageGenerationConfig.__post_init__`이
    그 밖의 값을 거절한다. `host.docker.internal`은 도커 호스트, 즉 같은 기계다.
  - 라이선스는 **실행 중에 눈에 보이지 않는 제약**이라 설정이 스스로 말한다
    (`commercial_use_is_unrestricted`). 막지는 않는다 -- owner가 2026-08-21에
    `flux1-dev`로 가기로 하고 라이선스는 본인이 맡는다고 했다.
- SaaS auth/billing, mem0와 VideoBox의 direct OAuth는 현재 runtime 범위 밖이다. Hermes service는 계획 §23의 isolated read-only slice로만 후속 도입한다.
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
