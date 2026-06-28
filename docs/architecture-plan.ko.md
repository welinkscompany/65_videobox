# VideoBox 아키텍처 계획서

## 1. 목적

이 문서는 VideoBox의 기술 아키텍처 경계를 명확히 정의하기 위한 기준 문서다.

핵심 목표:

- 로컬 우선 제품으로 빠르게 구현할 수 있어야 한다
- 나중에 SaaS로 확장할 때 코어를 갈아엎지 않아야 한다
- 편집 엔진과 UI, 외부 provider, 스토리지, export 대상을 분리해야 한다

## 2. 아키텍처 원칙

### 2.1 로컬 우선, 구조는 SaaS 확장 가능

초기 구현은 로컬 실행을 전제로 한다.
하지만 아래는 SaaS 확장 가능 구조를 유지해야 한다.

- 코어 엔진
- 데이터 모델
- 작업 모델
- provider 인터페이스
- 스토리지 추상화

### 2.2 내부 기준 포맷은 timeline JSON

모든 편집 의사결정의 내부 기준은 timeline JSON이다.

아래는 timeline JSON을 기준으로 동작해야 한다.

- preview renderer
- review UI
- CapCut exporter
- shortform extractor

### 2.3 코어 엔진은 배포 방식과 분리

코어 엔진은:

- 데스크톱 UI
- 웹 UI
- 클라우드 인증
- 결제
- 특정 provider SDK

와 직접 결합되면 안 된다.

### 2.4 추천과 적용은 분리

초기 아키텍처는 추천 결과와 실제 적용 결과를 분리해 저장해야 한다.

예:

- 추천 B-roll 후보 목록
- 추천 점수
- 선택된 후보
- 자동 적용 여부
- review flag

## 3. 상위 구조

```text
Input Sources
-> Ingest Layer
-> Analysis Layer
-> Recommendation Layer
-> Timeline Builder
-> Preview / Export Layer
-> Review Layer
```

## 4. 계층별 책임

### 4.1 Input Sources

입력 자원:

- 녹음 파일
- 원본 영상
- 참고 문서 / 스크립트
- 사용자 B-roll
- 사용자 본인 목소리 샘플
- 시스템 기본 자산

### 4.2 Ingest Layer

역할:

- 로컬 파일 등록
- 메타데이터 추출
- 자산 식별자 생성
- 프로젝트 연결
- 필요 시 proxy 생성

### 4.3 Analysis Layer

역할:

- STT
- 전사 정렬
- 세그먼트 분리
- 장면 분리
- 반복 take 탐지
- 무음 탐지
- 재시작 구간 탐지
- 원본 영상 자동 컷 전처리

### 4.4 Recommendation Layer

역할:

- B-roll 추천
- 음악 추천
- 설명형 비주얼 추천
- TTS 대체 추천
- shortform 후보 scoring
- confidence 및 review flag 생성

### 4.5 Timeline Builder

역할:

- 세그먼트와 추천 결과를 조합해 timeline JSON 생성
- 자동 적용 규칙 반영
- 검수 필요 항목 표시

### 4.6 Preview / Export Layer

역할:

- playable local preview artifact 렌더
- subtitle 파일 생성
- CapCut export

### 4.7 Review Layer

역할:

- 세그먼트 검수
- 추천 후보 교체
- 검수 플래그 확인
- 최종 export 재실행

## 5. 패키지 구조 기준

```text
apps/
  desktop/
  web/

services/
  api/
  worker/

packages/
  core-engine/
  domain-models/
  provider-interfaces/
  storage-abstractions/
  timeline-schema/
  capcut-export/
```

### `apps/desktop`

- 장기 desktop wrapper 후보
- 현재 주 구현 대상은 아님

### `apps/web`

- 현재 로컬 우선 operator dashboard
- review approval/output workflow의 기본 UI

### `services/api`

- 로컬 API 또는 미래 원격 API
- 프로젝트/job 조정
- 인증 연동 가능 지점

### `services/worker`

- 전사
- 분석
- 렌더
- export

### `packages/core-engine`

- 도메인 흐름 오케스트레이션
- 분석 결과 결합
- rough cut planning
- 추천 결과 조합
- timeline 생성

### `packages/domain-models`

- 공통 레코드 스키마 정의

### `packages/provider-interfaces`

- LLM provider
- STT provider
- TTS provider
- 필요 시 vision provider

### `packages/storage-abstractions`

- 로컬 파일
- 네트워크 경로
- 미래 object storage

### `packages/timeline-schema`

- 내부 편집 기준 구조

### `packages/capcut-export`

- CapCut adapter
- exporter version isolation

## 6. 핵심 데이터 모델

### 6.1 Project

필드 예시:

- `project_id`
- `owner_id`
- `workspace_id`
- `status`
- `settings`
- `created_at`

### 6.2 Asset

필드 예시:

- `asset_id`
- `project_id`
- `asset_type`
- `storage_uri`
- `source_kind`
- `metadata`

자산 종류 예시:

- `raw_video`
- `narration_audio`
- `voice_sample_audio`
- `broll_video`
- `image`
- `bgm`
- `sfx`
- `overlay_template`

### 6.3 Segment

필드 예시:

- `segment_id`
- `project_id`
- `start_sec`
- `end_sec`
- `text`
- `source_type`
- `confidence`
- `cleanup_decision`
- `review_required`

### 6.4 Job

필드 예시:

- `job_id`
- `project_id`
- `job_type`
- `status`
- `input_ref`
- `output_ref`
- `error_message`

상태 예시:

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

### 6.5 Recommendation

필드 예시:

- `recommendation_id`
- `project_id`
- `target_segment_id`
- `recommendation_type`
- `candidate_asset_ids`
- `scores`
- `reason`
- `auto_apply_allowed`
- `review_required`

추천 타입 예시:

- `broll`
- `bgm`
- `overlay`
- `tts_replacement`

### 6.6 Timeline

필드 예시:

- `timeline_id`
- `project_id`
- `version`
- `output_mode`
- `tracks`
- `review_flags`

## 7. Provider 아키텍처

초기부터 provider 추상화를 둔다.

### LLM Provider

역할:

- 장면 분리 보조
- 대본/전사 정렬 보조
- B-roll 키워드 추출
- shortform 후보 reasoning

기본 원칙:

- `LLMTaskRouter` 뒤에서만 호출
- 기본 provider는 로컬 LLM 우선
- 클라우드 provider는 fallback
- 특정 모델명 하드코딩 금지

### STT Provider

역할:

- 녹음 파일 전사
- 단어/문장 타임코드 반환

### TTS Provider

역할:

- 사용자 본인 목소리 기반 나레이션 생성
- 잘못 발음한 구간의 제한적 대체
- 설명형 영상 음성 생성 확장 대비

### Vision Provider

선택적 역할:

- 자산 자동 태깅
- 장면 내용 요약
- B-roll 인덱싱 강화

## 8. Storage 아키텍처

초기에는 로컬 파일 기반이지만, 엔진은 경로 하드코딩을 피해야 한다.

권장 개념:

- `storage_provider`
- `storage_kind`
- `asset_uri`
- `preview_uri`
- `export_uri`

초기 storage kind:

- `local`

미래 확장:

- `network`
- `object`

## 9. Job 아키텍처

오래 걸리는 작업은 모두 job으로 관리한다.

대상:

- ingest
- transcription
- analysis
- recommendation
- preview_render
- export

이렇게 해야:

- 로컬 실행에서도 상태 추적이 가능하고
- 나중에 worker 분리도 쉬워진다

## 10. CapCut 연동 원칙

CapCut은 내부 기준 포맷이 아니다.
CapCut은 export 대상이다.

원칙:

- timeline JSON에서 CapCut payload로 변환
- CapCut 전용 세부 구현은 adapter에 격리
- 코어 엔진은 CapCut 구조를 직접 알지 않음

## 11. 컨테이너 전략

컨테이너는 선택적 도구로만 사용한다.

초기에 컨테이너화 가능:

- API
- worker
- 로컬 DB

초기에 컨테이너화 비권장:

- 데스크톱 앱 전체
- FFmpeg 중심 파일 워크플로우
- GPU 의존 로컬 모델 실행

## 12. BrollBox 재사용 반영 원칙

아래는 새 아키텍처로 이식 가능:

- CapCut export 흐름
- auto cut 로직
- STT/정렬 아이디어
- script matching 흐름
- shorts 추출 흐름

반영 방식:

- 로직은 재사용
- 구조는 재설계
- Google Sheets/Drive 의존은 제거

## 13. 첫 구현에서 아키텍처적으로 꼭 지켜야 할 것

1. domain models를 먼저 정의한다
2. timeline schema를 먼저 고정한다
3. provider 인터페이스 없이 특정 모델 호출을 박지 않는다
4. 로컬 경로를 주 식별자로 쓰지 않는다
5. 추천과 적용 결과를 분리 저장한다
6. CapCut export를 코어에 섞지 않는다
7. TTS는 자동 전면 대체가 아니라 review 기반으로만 적용한다

## 14. 결론

VideoBox의 핵심은 편집기 UI가 아니라 편집 엔진이다.
따라서 아키텍처도 `UI 중심`이 아니라 `분석 -> 추천 -> timeline -> preview/export` 중심으로 설계해야 한다.

이 구조를 지키면:

- 초기 로컬 우선 구현이 가능하고
- 나중에 SaaS 확장도 가능하며
- BrollBox의 유효한 실행 로직도 안전하게 흡수할 수 있다
