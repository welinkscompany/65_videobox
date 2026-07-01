# VideoBox SaaS 확장 설계 노트

## 제품 방향

VideoBox는 초기에는 로컬 우선 애플리케이션으로 구현하되, 나중에 SaaS 기반 모델로 확장할 때 전체를 갈아엎지 않도록 코어 엔진, 데이터 모델, 작업 모델, provider 인터페이스를 SaaS 확장 가능 구조로 설계한다.

이 말은 지금 SaaS 기능을 전부 구현한다는 뜻이 아니다.
핵심은 엔진과 데이터 경계에 로컬 전용 가정을 박아 넣지 않는다는 뜻이다.

## 설계 원칙

- 구현 우선순위: 로컬 우선
- 아키텍처 우선순위: SaaS 확장 가능
- 코어 엔진은 로컬 데스크톱 실행과 미래의 클라우드 워커 실행에서 재사용 가능해야 한다
- 스토리지, 인증, provider 자격 증명, 배포 방식은 코어 엔진 바깥 레이어에 둔다

## 기존 계획서에 반영해야 할 수정 포인트

### 1. 코어 엔진과 앱 껍데기를 분리한다

아래 항목은 UI, 인증, 결제, 배포와 분리해야 한다.

- 미디어 ingest
- 전사
- speech cleanup 분석
- 장면 및 토픽 분석
- 편집 의도 처리
- B-roll 매칭
- rough cut planning
- 시각 보조 계획
- 오디오 계획
- timeline 생성
- preview 계획
- CapCut export
- shortform 추출

엔진은 구조화된 입력을 받아 구조화된 출력을 내보내야 한다.
특정 데스크톱 UI나 직접적인 클라우드 서비스에 의존하면 안 된다.

### 2. 경로 중심 사고 대신 식별자 중심 사고로 바꾼다

다음 같은 레코드 식별자를 우선으로 둔다.

- `project_id`
- `asset_id`
- `job_id`
- `timeline_id`
- `provider_id`

경로는 여전히 필요하지만, 주 식별자가 아니라 스토리지 메타데이터로 붙여야 한다.
그래야 나중에 로컬 디스크 경로를 클라우드 object URI로 바꾸기 쉽다.

### 3. 스토리지 추상화를 도입한다

엔진은 모든 자산이 영원히 로컬 파일시스템에만 있다고 가정하면 안 된다.

권장 개념:

- `storage_provider`
- `asset_uri`
- `preview_uri`
- `export_uri`
- `storage_kind` 예: `local`, `network`, `object`

초기 로컬 빌드에서는 이 값들이 전부 로컬 파일에 매핑되어도 괜찮다.

### 4. 오래 걸리는 작업은 job으로 다룬다

다음 작업을 job으로 정식 모델링한다.

- ingest job
- transcription job
- analysis job
- preview render job
- export job

권장 상태값:

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

이 구조는 로컬 실행에도 도움이 되고, 나중에 클라우드 워커로 넘길 때도 유리하다.

### 5. provider 추상화를 처음부터 넣는다

LLM, STT, TTS는 전부 provider 인터페이스 뒤로 숨긴다.

예시:

- `LLMProvider`
- `STTProvider`
- `TTSProvider`

이렇게 해두면 아래를 모두 대응할 수 있다.

- 사용자 API 키 방식
- 나중의 운영사 managed 방식
- 나중의 로컬 모델 실행 방식

### 6. 사용자 자산과 시스템 자산을 분리한다

데이터 모델에서 아래를 구분해야 한다.

- 사용자 소유 B-roll
- 사용자 프로젝트 입력물
- 시스템 starter 자산
- 라이선스된 기본 자산

이 구분은 나중에 동기화, 접근 제어, 패키징, 비즈니스 규칙에 중요해진다.

### 7. 프로젝트 중심 스키마를 유지한다

각 프로젝트는 아래를 소유해야 한다.

- 미디어 입력물
- 사용 자산
- 편집 의도
- 세그먼트
- timeline 버전
- jobs
- previews
- exports
- shortform 후보

이 구조는 로컬과 SaaS 양쪽으로 확장하기 좋다.

### 8. 인증 전에도 식별 경계를 준비한다

아직 로컬 우선 모드라 해도 다음 같은 필드는 나중을 대비해 호환 가능해야 한다.

- `owner_id`
- `workspace_id`

초기에는 optional이어도 되지만, 스키마 차원에서 자리를 잡아두는 게 좋다.

### 9. 설정 레이어를 분리한다

모든 설정을 한 파일에 섞어 넣지 않는다.

설정 도메인을 나눈다.

- 앱 설정
- 프로젝트 설정
- provider 설정
- 렌더 설정
- 자산 라이브러리 설정

### 10. 하드코딩보다 capability flag를 선호한다

예시:

- `allow_byo_llm`
- `enable_cloud_auth`
- `enable_default_broll_pack`
- `enable_managed_ai`

이렇게 해야 제품이 커질 때 제어 흐름을 크게 다시 쓰지 않아도 된다.

## 지금 만들지 말아야 할 것

아래는 미래 SaaS와는 호환되지만, 첫 구현 단계에서 넣으면 안 된다.

- 결제
- 멀티유저 협업
- 브라우저 기반 풀 편집기
- 클라우드 렌더 팜
- 실시간 동기화
- 완전한 서버 측 프로젝트 저장

이건 확장 레이어이지 MVP 필수 항목이 아니다.

## 권장 MVP 해석

첫 구현 단계는 아래로 좁히는 것이 맞다.

1. 로컬 프로젝트 생성
2. 로컬 미디어 ingest
3. STT 및 세그먼트 분석
4. rough cut planning
5. timeline JSON 생성
6. preview 렌더 출력
7. CapCut export
8. 기본 local-first operator dashboard / lightweight editing UI

위 경계만 잘 지키면 이 MVP도 장기적으로 SaaS 확장 가능한 구조를 유지할 수 있다.
