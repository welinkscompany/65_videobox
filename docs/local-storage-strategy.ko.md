# VideoBox 로컬 저장 전략

## 1. 목적

이 문서는 VideoBox의 로컬 우선 저장 전략을 확정하기 위한 기준 문서다.

핵심 목표:

- 로컬 우선 구조에 맞는 저장 방식을 결정한다
- SQLite와 파일시스템의 역할을 분리한다
- `project / asset / segment / recommendation / job / timeline / export / voice_sample` 저장 구조를 정의한다
- 개발 폴더와 프로젝트 폴더의 책임 분리를 반영한다
- 나중에 SaaS로 확장 가능하도록 경계를 유지한다

## 2. 최종 결론

VideoBox의 저장 전략은 `SQLite + 파일시스템 하이브리드`로 간다.

즉:

- 구조화된 메타데이터와 상태값은 `SQLite`
- 대용량 미디어와 결과 파일은 `파일시스템`
- timeline, export payload 같은 문서형 산출물은 `JSON 파일 + SQLite 인덱스`

이 구조가 현재 단계에서 가장 현실적이다.

## 3. 왜 PostgreSQL이 아니라 SQLite인가

현재 단계에서 SQLite를 선택하는 이유:

- 로컬 앱 구조와 잘 맞는다
- 사용자가 별도 DB 서버를 관리할 필요가 없다
- 설치/운영 부담이 적다
- 프로젝트, 자산, 세그먼트, 추천, job 상태 저장에 충분하다
- 나중에 PostgreSQL로 이관 가능한 구조로 설계할 수 있다

현재 PostgreSQL을 쓰지 않는 이유:

- 로컬 우선 MVP에는 과하다
- 설정과 운영 복잡도가 커진다
- 지금 제품 가치보다 인프라 관리 비중이 커질 수 있다

따라서 원칙은 다음과 같다.

- `v1 로컬 우선 = SQLite`
- `향후 SaaS/멀티유저 = PostgreSQL 이관 가능하게 설계`

## 4. 폴더 책임 분리

### 개발 폴더

- `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`

용도:

- 소스 코드
- 테스트
- 문서
- 개발용 스크립트
- 로컬 개발 설정

이 폴더에는 실제 운영용 프로젝트 산출물을 저장하지 않는다.

### 프로젝트 폴더

- `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`

용도:

- 실제 프로젝트 데이터
- 입력 미디어
- 생성된 preview
- export 결과
- 로컬 DB 파일
- 캐시/중간 산출물

즉, 운영 중 생성되는 데이터는 전부 이 폴더 아래에 둔다.

## 5. 권장 루트 구조

```text
D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\
  projects\
    <project_id>\
      project.json
      db\
        project.sqlite
      inputs\
        narration\
        raw_video\
        scripts\
        voice_samples\
      assets\
        imported\
        generated\
      analysis\
        transcripts\
        segments\
        recommendations\
      timelines\
      previews\
      exports\
        capcut\
      cache\
      logs\
```

## 6. 저장 계층 역할 분리

### 6.1 SQLite에 저장할 것

SQLite는 검색/조회/상태관리/관계 연결이 필요한 구조화 데이터에 사용한다.

대상:

- project
- asset metadata
- segment
- recommendation
- job
- export record
- timeline index
- voice sample metadata

### 6.2 파일시스템에 저장할 것

파일시스템은 크기가 크거나, 바이너리이거나, 실제 결과물인 항목을 저장한다.

대상:

- 원본 영상
- 녹음 파일
- B-roll 비디오 파일
- 이미지 파일
- 사용자 본인 목소리 샘플 파일
- preview mp4
- generated TTS audio
- subtitle files
- CapCut export payload files

### 6.3 JSON 파일로 저장할 것

문서형 구조이면서 사람이 직접 읽어볼 가치가 있는 산출물은 JSON 파일로 둔다.

대상:

- timeline JSON
- recommendation snapshot
- export payload
- analysis summary

그리고 SQLite에는 이 파일의 위치와 버전 정보만 저장한다.

## 7. 프로젝트별 DB 전략

### 결론

초기에는 `프로젝트별 SQLite 파일`을 사용한다.

예:

- `projects/<project_id>/db/project.sqlite`

이 구조의 장점:

- 프로젝트 이동/백업이 쉽다
- 데이터 경계가 분명하다
- 추후 프로젝트 단위 export/import가 쉬워진다

주의:

- 전역 자산 라이브러리를 붙일 경우 나중에 shared DB를 따로 둘 수 있다

## 8. 공용 자산 라이브러리 전략

### 초기 결정

초기에는 `프로젝트 로컬 자산 우선`으로 간다.

즉:

- 프로젝트에 연결된 B-roll 자산
- 프로젝트에 연결된 voice sample

을 우선 관리한다.

향후 확장:

- 사용자 전역 B-roll 라이브러리
- 시스템 기본 B-roll starter pack
- 전역 voice sample registry

하지만 이 전역 라이브러리는 첫 구현의 필수는 아니다.

## 9. 테이블 역할 정의

아래는 SQLite에 들어갈 최소 테이블 역할 정의다.

### 9.1 `projects`

저장 내용:

- `project_id`
- `name`
- `status`
- `settings_json`
- `created_at`
- `updated_at`

### 9.2 `assets`

저장 내용:

- `asset_id`
- `project_id`
- `asset_type`
- `storage_uri`
- `source_kind`
- `mime_type`
- `duration_sec`
- `metadata_json`
- `created_at`

자산 타입 예시:

- `narration_audio`
- `raw_video`
- `broll_video`
- `image`
- `bgm`
- `sfx`
- `voice_sample_audio`
- `generated_tts_audio`

### 9.3 `segments`

저장 내용:

- `segment_id`
- `project_id`
- `start_sec`
- `end_sec`
- `text`
- `source_asset_id`
- `confidence`
- `cleanup_decision`
- `review_required`
- `metadata_json`

### 9.4 `recommendations`

저장 내용:

- `recommendation_id`
- `project_id`
- `target_segment_id`
- `recommendation_type`
- `selected_asset_id`
- `score`
- `reason`
- `auto_apply_allowed`
- `review_required`
- `payload_json`

추천 타입 예시:

- `broll`
- `bgm`
- `overlay`
- `tts_replacement`

### 9.5 `jobs`

저장 내용:

- `job_id`
- `project_id`
- `job_type`
- `status`
- `input_ref`
- `output_ref`
- `error_message`
- `started_at`
- `finished_at`

job 타입 예시:

- `ingest`
- `transcription`
- `segment_analysis`
- `tts_generation`
- `broll_recommendation`
- `timeline_build`
- `preview_render`
- `capcut_export`

### 9.6 `timelines`

저장 내용:

- `timeline_id`
- `project_id`
- `version`
- `output_mode`
- `file_uri`
- `summary_json`
- `created_at`

실제 timeline 구조는 JSON 파일에 저장한다.

### 9.7 `exports`

저장 내용:

- `export_id`
- `project_id`
- `export_type`
- `file_uri`
- `status`
- `metadata_json`
- `created_at`

### 9.8 `voice_samples`

저장 내용:

- `voice_sample_id`
- `project_id`
- `asset_id`
- `display_name`
- `language`
- `provider_name`
- `consent_note`
- `metadata_json`
- `created_at`

이 테이블은 `voice_sample_audio` asset을 가리키는 메타 테이블이다.

## 10. 파일 네이밍 원칙

원칙:

- 사용자 표시명과 무관하게 내부 식별자는 ID 기준
- 파일명은 가능하면 안정적이고 충돌이 적게
- 실제 표시용 이름은 DB 메타데이터에 둔다

예:

- `inputs/narration/narration_001.wav`
- `inputs/voice_samples/voice_sample_001.wav`
- `analysis/transcripts/transcript_001.json`
- `timelines/timeline_v001.json`
- `previews/preview_v001.mp4`
- `exports/capcut/export_v001/`

## 11. URI 전략

DB에는 가능한 한 절대 경로 문자열 대신 `storage_uri` 개념으로 저장한다.

초기 예시:

- `local://projects/<project_id>/inputs/narration/narration_001.wav`
- `local://projects/<project_id>/timelines/timeline_v001.json`

실제 로컬 파일시스템 경로 해석은 storage adapter가 담당한다.

이유:

- 나중에 네트워크 경로나 object storage로 바꾸기 쉽다
- 코어 엔진이 경로 하드코딩에 묶이지 않는다

## 12. Timeline 저장 전략

timeline은 DB 컬럼에 직접 큰 JSON blob으로 넣지 않는다.

권장 방식:

- 실제 timeline은 JSON 파일 저장
- SQLite에는
  - `timeline_id`
  - `project_id`
  - `version`
  - `output_mode`
  - `file_uri`
  - `summary_json`

만 저장

이유:

- 버전 관리가 쉽다
- 사람이 파일을 열어 디버깅할 수 있다
- CapCut export payload와 나란히 관리하기 좋다

## 13. TTS 저장 전략

### 입력

- 사용자 본인 목소리 샘플은 `voice_sample_audio` asset으로 저장한다

### 출력

- 생성된 TTS 오디오는 `generated_tts_audio` asset으로 저장한다

### 정책

- TTS는 자동 전면 대체하지 않는다
- 일부 세그먼트에 대한 `tts_replacement` 추천으로만 다룬다
- review 승인 후 timeline에 반영한다

## 14. Preview / Export 저장 전략

preview와 export는 실제 결과물 파일이다.

따라서:

- preview mp4는 파일로 저장
- subtitle는 파일로 저장
- CapCut export payload는 파일로 저장
- SQLite에는 결과물 메타데이터와 경로만 저장

## 15. 캐시 전략

캐시는 프로젝트 폴더 아래 `cache/`에 둔다.

예:

- ffmpeg intermediate
- frame thumbnails
- embedding cache
- temporary TTS inference artifacts

정책:

- 캐시는 삭제 가능해야 한다
- 핵심 SSOT는 캐시에 두지 않는다

## 16. SaaS 확장 대비 원칙

현재는 SQLite를 쓰지만, 아래 원칙을 지키면 PostgreSQL로 이관하기 쉽다.

- SQLite 전용 SQL 남발 금지
- DB access layer 분리
- storage adapter 분리
- 대용량 파일은 DB에 넣지 않음
- 파일 참조는 `storage_uri`로 통일

## 17. 최종 저장 원칙

한 줄 요약:

- `DB에는 구조와 상태`
- `파일시스템에는 실제 미디어와 결과물`
- `JSON에는 사람이 읽을 수 있는 편집 산출물`

이 세 층을 유지한다.

## 18. 결론

VideoBox의 로컬 저장 전략은 `프로젝트 폴더 중심 파일시스템 + 프로젝트별 SQLite + 문서형 JSON 산출물` 구조로 확정한다.

이 방식은:

- 로컬 우선 MVP에 가장 적합하고
- 개발/운영 폴더 책임 분리를 지키며
- 나중에 SaaS 확장으로도 이어질 수 있는 가장 현실적인 저장 구조다
