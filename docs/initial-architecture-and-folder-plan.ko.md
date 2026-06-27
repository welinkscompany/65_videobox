# VideoBox 초기 아키텍처 및 폴더 계획

## 목표

VideoBox를 로컬 우선 애플리케이션으로 시작하되, SaaS 확장 가능 아키텍처를 가진 구조로 세팅한다.

## 권장 최상위 구조

```text
65_videobox/
  docs/
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
  infra/
    local/
    containers/
  scripts/
  tests/
```

## 영역별 책임

### `apps/desktop`

로컬 우선 운영용 애플리케이션.

역할:

- 프로젝트 생성
- 자산 라이브러리 탐색
- review 워크플로우
- preview 실행
- 로컬 설정 및 provider 키 입력

### `apps/web`

선택적 미래 웹 표면.

첫 구현에 필수는 아니지만, 폴더를 분리해두면 데스크톱 전용 가정이 나머지 구조에 새는 것을 막기 좋다.

### `services/api`

얇은 서비스 레이어.

역할:

- 데스크톱 모드에서 로컬 API 프로세스
- 미래 원격 API 재사용
- 나중의 인증 통합
- 프로젝트/job 조정

편집 지능 자체는 여기에 넣지 않는다.

### `services/worker`

job 실행 레이어.

역할:

- 전사
- 분석
- 렌더
- export

로컬 우선 모드에서는 같은 컴퓨터에서 돌 수 있고, 나중에는 원격 워커로 분리할 수 있다.

### `packages/core-engine`

순수 애플리케이션 로직.

역할:

- ingest 오케스트레이션
- 분석 오케스트레이션
- rough cut planning
- timeline 생성
- shortform 후보 선택

이 패키지는 배포 방식과 무관하게 유지하는 것이 가장 중요하다.

### `packages/domain-models`

공유 모델 정의.

대상:

- project
- asset
- segment
- timeline
- job
- export

### `packages/provider-interfaces`

provider 추상화.

대상:

- LLM providers
- STT providers
- TTS providers

인터페이스는 여기 두고, 실제 provider 바인딩은 별도 위치에 둘 수 있다.

### `packages/storage-abstractions`

스토리지 추상화.

대상:

- 미디어 읽기
- preview 쓰기
- export 위치 조회
- URI 해석

### `packages/timeline-schema`

편집 의사결정의 내부 기준 포맷.

preview, review, rendering, export는 전부 이 공통 스키마를 기준으로 동작해야 한다.

### `packages/capcut-export`

격리된 adapter 레이어.

CapCut 스키마 변경은 여기서 흡수하고, 코어 엔진으로 새지 않게 해야 한다.

### `infra/local`

로컬 셋업 보조 자료.

예:

- ffmpeg 부트스트랩 노트
- 로컬 데이터베이스 셋업
- 로컬 자산 경로 규칙

### `infra/containers`

선택적 재현성과 서비스 패키징을 위한 컨테이너 정의.

초기 반복 개발의 발목을 잡는 필수 요소가 되면 안 된다.

## 권장 데이터 경계

### Project

- `project_id`
- `owner_id`
- `workspace_id`
- `status`
- `settings`

### Asset

- `asset_id`
- `project_id`
- `asset_type`
- `storage_uri`
- `source_kind`
- `metadata`

### Job

- `job_id`
- `project_id`
- `job_type`
- `status`
- `input_ref`
- `output_ref`
- `error_message`

### Timeline

- `timeline_id`
- `project_id`
- `version`
- `output_mode`
- `tracks`

## 컨테이너 권장안

컨테이너는 시작점이 아니라 보조 도구로 다루는 것이 맞다.

### 초기에 컨테이너화해도 되는 것

- API 서비스
- worker 서비스
- 로컬 데이터베이스가 들어갈 경우 그 DB

### 초기에 컨테이너화를 강제하면 안 되는 것

- 데스크톱 파일 접근에 강하게 의존하는 FFmpeg 중심 미디어 워크플로우
- GPU 의존 로컬 모델 실행
- 데스크톱 애플리케이션 전체

### 실무 권장안

초기 개발은 네이티브 로컬 개발로 시작한다.
첫 번째 동작하는 파이프라인이 나온 뒤, 아래 목적이 필요할 때 컨테이너를 추가한다.

- 백엔드 재현성 확보
- worker 격리
- 미래 배포 구조와의 정렬

컨테이너를 너무 일찍 도입하면 영상 툴링, 파일 경로 디버깅, GPU 연동 속도가 오히려 느려질 수 있다.

## 즉시 구현 순서

1. 공유 domain models 정의
2. timeline schema 정의
3. provider interfaces 정의
4. local storage adapter 구현
5. local job runner 구현
6. 첫 ingest to preview 파이프라인 구현
7. CapCut export adapter 추가
8. 얇은 review UI 추가
