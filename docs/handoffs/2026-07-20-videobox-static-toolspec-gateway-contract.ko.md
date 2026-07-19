# VideoBox static ToolSpec Gateway contract 인수인계

**날짜:** 2026-07-20
**상태:** 실제 provider·executor 없는 읽기 전용 ToolSpec/Gateway 정적 계약 완료.

- pinned registry는 `get_project_status` 하나뿐이다. selected-project status revision, strict empty request/result schema, redaction, 1,024 byte/1,000 ms, `read_only_research` phase를 manifest로 고정한다.
- model proposal은 권한이 아니다. exact scalar/empty object, backend-attested context/request, project/revision/phase를 모두 대조하며 static acceptance도 `executor_authorized=false`다.
- private backend-adapter attestation은 ordinary app-contract boundary일 뿐 hostile in-process code나 real capability signer를 대체하지 않는다. Hermes/OAuth/GPT/Qwen/Gemini call, route/UI/DB, mem0, mutation/render/export는 계속 시작하지 않는다.

## 다음 Goal

기존 §23에서 실제 provider 호출 없이 static gateway decision의 audit event/correlation/redaction envelope과 retry/idempotency state contract를 TDD로 고정한다. real signer, Hermes network/OAuth, provider call, DB/API route activation, mutation/render/export은 계속 제외한다.
