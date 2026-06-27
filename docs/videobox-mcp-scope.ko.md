# VideoBox MCP 범위 정의서

## 1. 목적

이 문서는 VideoBox를 독립 제품으로 유지하면서, 기존 Hermes 에이전트 또는 미래의 다른 에이전트가 VideoBox 기능을 사용할 수 있도록 MCP 경계를 정의하기 위한 문서다.

핵심 목표:

- VideoBox 본체를 Hermes에 직접 묶지 않는다
- VideoBox는 독립 편집 엔진으로 유지한다
- Hermes는 MCP를 통해 VideoBox 기능을 호출한다
- 로컬 단독 사용과 에이전트 사용을 모두 가능하게 한다

## 2. 상위 원칙

### 2.1 제품 본체와 에이전트를 분리한다

VideoBox는 편집 엔진이다.
Hermes는 오케스트레이션 에이전트다.

이 둘은 역할이 다르다.

- VideoBox: 입력을 받아 전사, 추천, 초안 생성, export를 수행
- Hermes: 사용자의 의도를 해석하고 적절한 순서로 VideoBox 기능을 호출

### 2.2 VideoBox는 독립 실행 가능해야 한다

Hermes가 없어도 다음이 가능해야 한다.

- 프로젝트 생성
- 자산 등록
- 전사 실행
- 추천 실행
- preview 생성
- CapCut export

즉, Hermes는 필수 런타임이 아니라 외부 호출자다.

### 2.3 MCP는 제어면(control plane)이다

MCP는 실제 무거운 영상 처리를 직접 수행하는 계층이 아니다.
MCP는 VideoBox 엔진에게 작업을 요청하고 상태를 조회하는 계층이다.

즉:

- heavy processing = VideoBox core / worker
- orchestration + tool invocation = MCP layer

### 2.4 장기적으로는 다른 에이전트도 붙을 수 있어야 한다

VideoBox MCP는 Hermes 전용이 아니라 일반적인 tool surface가 되어야 한다.

## 3. 권장 구조

```text
Hermes Agent
-> VideoBox MCP
-> VideoBox API / Job Layer
-> VideoBox Core Engine
-> Local Storage / Media Files / Export
```

## 4. 책임 분리

### 4.1 Hermes가 맡는 일

- 사용자의 작업 목표 해석
- 어떤 프로젝트를 만들지 판단
- 어떤 입력이 필요한지 수집
- 어떤 순서로 VideoBox 기능을 호출할지 결정
- 결과 요약과 다음 행동 제안

### 4.2 VideoBox MCP가 맡는 일

- tool 목록 제공
- VideoBox API 호출 래핑
- 입력값 검증
- job 시작/상태 조회/결과 반환

### 4.3 VideoBox Core가 맡는 일

- STT
- 세그먼트 분리
- TTS 대체 생성
- B-roll 추천
- 음악 추천
- timeline 생성
- preview 렌더
- CapCut export

## 5. MCP로 노출할 1차 도구 목록

첫 구현에서 MCP로 노출할 도구는 아래 정도가 적절하다.

### 프로젝트

- `create_project`
- `list_projects`
- `get_project`

### 자산 / 입력

- `register_narration_audio`
- `register_script_document`
- `register_broll_asset`
- `register_voice_sample`
- `list_project_assets`

### 분석

- `start_transcription`
- `get_transcription_result`
- `start_segment_analysis`
- `get_segment_analysis`

### 추천

- `start_broll_recommendation`
- `get_broll_recommendation`
- `start_music_recommendation`
- `get_music_recommendation`
- `start_tts_replacement_recommendation`
- `get_tts_replacement_recommendation`

### 편집 결과

- `build_timeline`
- `get_timeline`
- `render_preview`
- `get_preview_status`
- `export_capcut`
- `get_export_status`

## 6. 1차 MCP에서 굳이 넣지 않을 것

아래는 1차 MCP 도구로 넣지 않는 것이 좋다.

- 미세한 타임라인 수동 편집 도구
- 실시간 프레임 단위 조작
- 대량 배치 운영 도구
- 권한/결제/조직 관리
- 범용 음성 클로닝 스튜디오 기능

이유:

- 첫 구현의 핵심 도구 surface가 흐려진다
- 에이전트 호출이 너무 복잡해진다

## 7. TTS 관련 MCP 정책

TTS는 아래 범위로 제한한다.

- 사용자 본인 목소리 샘플만 등록 가능
- 일부 나레이션 구간 대체용으로만 사용
- 자동 전면 대체 금지
- review 기반 적용

따라서 MCP에서도 다음 정도만 허용한다.

- `register_voice_sample`
- `start_tts_replacement_recommendation`
- `get_tts_replacement_recommendation`

그리고 `apply_tts_to_entire_project` 같은 도구는 만들지 않는다.

## 8. API와 MCP의 관계

MCP는 가능하면 VideoBox API를 직접 감싼다.

즉:

- Core engine을 MCP가 직접 import해서 뒤섞지 않는다
- MCP -> API -> Core / Job Layer 구조를 선호한다

이유:

- 로컬 단독 사용과 에이전트 사용이 같은 API를 공유할 수 있다
- 테스트가 쉬워진다
- 나중에 원격 실행 구조로 바꿀 수 있다

## 9. 상태 조회 방식

무거운 작업은 즉시 완료보다 job 기반으로 노출한다.

예:

- `start_transcription`
- `get_transcription_result`

예:

- `render_preview`
- `get_preview_status`

이 구조가 필요한 이유:

- WhisperX
- 추천 계산
- preview 렌더
- CapCut export

같은 작업은 시간이 걸리기 때문이다.

## 10. 결과물 반환 원칙

MCP는 가능하면 큰 바이너리 파일 자체를 들고 다니지 않는다.

반환 대상 예시:

- `project_id`
- `job_id`
- `timeline_id`
- `preview_uri`
- `export_uri`
- 요약 메타데이터

즉 실제 파일은 VideoBox 저장소/프로젝트 폴더에 두고, MCP는 참조값을 반환하는 방식이 좋다.

## 11. Hermes 연동 방식

기존 Hermes는 다음 방식으로 붙는 것이 적절하다.

1. 사용자가 목표 설명
2. Hermes가 필요한 입력을 정리
3. Hermes가 VideoBox MCP 도구 호출
4. VideoBox가 결과 생성
5. Hermes가 결과 요약 및 다음 액션 제안

예:

- 프로젝트 생성
- 나레이션 등록
- 스크립트 등록
- 전사 실행
- B-roll 추천 실행
- timeline 생성
- preview 또는 CapCut export 요청

## 12. 장점

이 구조의 장점은 명확하다.

- VideoBox를 독립 제품으로 유지 가능
- Hermes가 이미 있어도 재사용 가능
- 다른 에이전트 연결도 가능
- 로컬 단독 사용과 에이전트 사용이 충돌하지 않음
- SaaS 확장 시에도 API/MCP 경계를 재사용 가능

## 13. 리스크

### 13.1 MCP를 너무 크게 만들 위험

대응:

- 1차는 coarse-grained tools만 제공

### 13.2 Core와 MCP가 뒤섞일 위험

대응:

- MCP는 API를 감싸는 계층으로 유지

### 13.3 에이전트가 과도하게 세부 기능을 직접 제어하려는 위험

대응:

- timeline 세부 수정은 MCP보다 review UI에 맡긴다

## 14. 결론

VideoBox는 Hermes 내부 기능으로 만들지 않는다.
VideoBox는 독립 편집 엔진으로 만들고, Hermes는 MCP를 통해 VideoBox를 사용하는 외부 오케스트레이터로 둔다.

이것이 가장 재사용성이 높고, 가장 덜 얽히며, 지금의 제품 방향과도 가장 잘 맞는다.
