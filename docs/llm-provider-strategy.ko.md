# VideoBox LLM Provider 전략

## 1. 목적

이 문서는 VideoBox에서 사용할 LLM, TTS, 비주얼 생성 provider의 실제 운영 전략을 고정하기 위한 문서다.

핵심 목적:

- 어떤 모델을 기본으로 쓸지
- 어떤 모델을 fallback으로 쓸지
- 어떤 작업은 로컬로 처리할지
- 어떤 외부 연동은 실험 기능으로만 둘지

## 2. 결론 요약

VideoBox의 기본 AI 라우팅은 아래처럼 고정한다.

- `primary`: 로컬 LLM `Qwen 3 35B`
- `fallback-1`: `Gemini` multi-key pool
- `fallback-2`: 선택적 `OpenAI` provider
- `optional visual provider`: `ComfyUI`

핵심 원칙:

- 기본은 `local-first`
- 반복적이고 구조화 가능한 작업은 `Qwen` 우선
- Gemini는 `클라우드 fallback + 보조 처리`
- OpenAI는 `핵심 필수 경로가 아니라 선택적 provider`
- ComfyUI는 `편집 엔진 핵심이 아니라 optional visual generation`

## 3. 왜 이렇게 가는가

### 3.1 로컬 Qwen 3 35B를 기본으로 두는 이유

- 사용자의 하드웨어가 충분히 강력하다
- 반복적인 구조화 작업을 외부 과금 없이 처리할 수 있다
- 비용 예측이 쉽다
- 나중에 SaaS 확장 시에도 `local provider`와 `remote provider` 경계를 유지하기 좋다

### 3.2 Gemini를 1차 클라우드 fallback으로 두는 이유

- 비용 부담이 OpenAI보다 낮다
- 다중 키 풀 구조를 만들면 무료/저비용 구간에서 운영 여지가 있다
- scene planning, 키워드 확장, 보조 분류 같은 작업에 적합하다

### 3.3 OpenAI를 필수 주력으로 두지 않는 이유

- API 비용 부담이 크다
- ChatGPT 구독을 일반 API 비용 대체로 믿고 설계하면 위험하다
- 비공식 Codex/OAuth 경로는 실험 기능으로는 가능해도 핵심 제품 경로로 쓰기엔 불안정하다

### 3.4 ComfyUI를 핵심 경로로 두지 않는 이유

- 이미지/영상 생성은 편집 초안 생성보다 범위가 크다
- 품질 일관성, 라이선스, 렌더 시간 리스크가 있다
- 초기에 핵심은 `추천과 편집 초안`이지 `생성형 미디어 제작`이 아니다

## 4. Provider 계층 구조

VideoBox는 아래 경계를 유지한다.

- `LLMProvider`
- `LLMTaskRouter`
- `TTSProvider`
- `VisualGenerationProvider`
- `No-LLM fallback path`

중요 원칙:

- `core-engine` 안에 특정 모델 SDK 호출을 직접 박지 않는다
- 모든 외부 모델 호출은 provider interface 뒤에서만 수행한다
- 같은 작업이라도 `local -> gemini -> openai` 순으로 fallback 가능해야 한다

## 5. 작업별 라우팅 정책

### 5.1 로컬 Qwen 3 35B 우선 작업

- 대본 장면 분리 초안
- 추천 이유 요약
- B-roll 검색 키워드 확장
- 세그먼트 설명 요약
- 규칙 기반 결과를 JSON 구조로 정리
- 반복적인 schema validation 보조

이런 작업은 품질보다 `대량 처리`, `반복`, `구조화`가 중요하다.

### 5.2 Gemini 우선 fallback 작업

- 로컬 장면 분리 결과가 불안정한 경우
- 로컬 키워드 확장 결과가 빈약한 경우
- operator용 설명 문구 보조
- 비교 후보 생성
- 보조 rerank

### 5.3 OpenAI 선택적 사용 작업

- 사람 검수가 많이 드는 애매한 정렬 판단
- 매우 중요한 최종 설명 문구 품질 보정
- 로컬/Gemini 결과가 모두 불안정할 때의 마지막 fallback

이 경로는 `비필수`로 둔다.

### 5.4 ComfyUI 선택 작업

- 설명형 카드용 보조 이미지 생성
- 스크립트 기반 삽화 초안
- 썸네일 실험
- operator 검토용 시각화 시안

이 경로는 `optional`이다.

## 6. Gemini key pool 정책

## 결정

- UI 입력 허용 한도: `최대 10개`
- 실제 기본 active pool: `3~4개`

즉, 구조는 10개까지 확장 가능하게 만들되 실제 기본 운영은 3~4개 키 기준으로 최적화한다.

### 6.1 key 상태 모델

- `active`
- `cooldown`
- `disabled`
- `invalid`

### 6.2 자동 로테이션 조건

- `429`
- `RESOURCE_EXHAUSTED`
- quota 초과
- 연속적인 5xx
- 연결 timeout 반복

### 6.3 운영 규칙

- 실패한 키는 일정 시간 `cooldown`
- 일정 횟수 이상 실패하면 `disabled`
- 사용자는 대시보드에서 키 추가/수정/비활성화 가능
- 키별 마지막 사용 시각, 최근 오류, 현재 상태를 보여준다

## 7. Gemini 모델 선택 기준

현재 기준 추천 모델 역할은 아래처럼 고정한다.

- `default_model = gemini-2.5-flash`
- `cheap_model = gemini-2.5-flash-lite`
- `high_quality_model = gemini-2.5-pro` 또는 동급 상위 모델

### 역할 분리

#### `gemini-2.5-flash`

- 기본 fallback
- 속도/비용/품질 균형
- 장면 분리, 요약, 키워드 확장

#### `gemini-2.5-flash-lite`

- 아주 단순한 반복 구조화
- 짧은 JSON 생성
- 저비용 후보 생성

#### `gemini-2.5-pro`

- 정말 필요한 고난도 판단만
- 기본 경로로 두지 않음

## 8. OpenAI 정책

### 공식 지원

- `BYOK (Bring Your Own Key)`만 공식 지원 경로로 간주

### 비공식/실험 경로

- ChatGPT/Codex OAuth 기반 비공식 프록시 경로는 `experimental`로만 둔다
- 기본 provider로 가정하지 않는다
- 언제든 꺼도 전체 파이프라인이 유지되어야 한다

즉, OpenAI는 아래 둘을 구분한다.

- `official_openai_provider`
- `experimental_codex_oauth_provider`

두 구현은 절대 같은 신뢰도로 취급하지 않는다.

## 9. TTS 정책

TTS는 `사용자 본인 목소리 기반 제한적 대체`만 허용한다.

원칙:

- 전면 자동 대체 금지
- `tts_replacement` recommendation으로만 제안
- review 승인 후 적용
- voice cloning studio로 범위 확장 금지

Voicebox는 참고 가능하지만:

- 소스 전체 vendoring 금지
- provider boundary 뒤에서만 제한적으로 연동

## 10. ComfyUI 정책

ComfyUI는 다음 원칙으로 쓴다.

- 기본 편집 파이프라인 필수 경로가 아님
- visual generation provider로만 연결
- 생성 결과는 자동 적용보다 `review asset`으로 먼저 저장
- B-roll 대체 핵심 엔진으로 사용하지 않음

## 11. 실패 시 fallback 순서

기본 fallback 순서는 아래다.

1. `Qwen 3 35B`
2. `Gemini active key pool`
3. `OpenAI BYOK provider` 또는 선택적 experimental provider
4. 그래도 실패하면 `rule-based fallback` 또는 `manual review required`

중요한 건 `LLM 실패 = 파이프라인 전체 실패`가 되면 안 된다는 점이다.

## 12. 구현 규칙

Phase 8 이후 구현 시 아래를 지켜야 한다.

1. `LLMTaskRouter`가 task type별로 provider를 선택한다
2. provider별 timeout/retry/cooldown 규칙을 분리한다
3. 특정 Gemini 키나 특정 모델명을 core business logic에 하드코딩하지 않는다
4. provider 오류는 job/event/log로 추적 가능해야 한다
5. operator가 대시보드에서 key pool 상태를 볼 수 있어야 한다
6. OpenAI 실험 provider는 kill switch가 있어야 한다

## 13. 최종 결론

VideoBox의 AI provider 전략은 다음 한 문장으로 고정한다.

`기본은 로컬 Qwen, 클라우드 fallback은 Gemini multi-key pool, OpenAI는 선택적 provider, ComfyUI는 optional visual provider로 분리한다.`

이렇게 해야:

- 비용을 통제할 수 있고
- 로컬 우선 구조를 지킬 수 있으며
- 모델 교체와 SaaS 확장도 더 쉬워진다
