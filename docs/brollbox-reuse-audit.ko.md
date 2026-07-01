# BrollBox 재사용 감사 문서

## 목적

기존 `brollbox-master`에서 VideoBox 개발에 재사용할 수 있는 코드, 설계 아이디어, 운영 자산을 선별한다.

핵심 원칙:

- 통째로 복제하지 않는다
- 재사용 가능한 실행 로직만 선별한다
- 새 아키텍처의 경계를 우선한다
- `reuse`, `rewrite`, `discard`로 구분한다

검토 대상 경로:

- `C:\Users\atgro\OneDrive\바탕 화면\개발참고\brollbox-master`

## 전체 판단

BrollBox는 VideoBox의 선행 실험체로서 가치가 높다.
특히 `execution/` 계층에는 재사용 가능한 편집 실행 로직이 많다.

반면 전체 앱 구조는 현재 VideoBox 방향과 맞지 않는다.

이유:

- Streamlit 중심 UI 구조
- Google Sheets/Drive 중심 데이터 구조
- provider 추상화 부재
- 코어 로직과 외부 의존이 강하게 결합된 파일 구조

따라서 VideoBox에서는 `코드 일부 이식 + 구조 재설계`가 맞다.

## 분류 기준

### Reuse

핵심 알고리즘이나 처리 흐름이 유효하고, 구조만 분리하면 새 제품에 바로 살릴 수 있는 대상

### Rewrite

아이디어와 기능은 유효하지만, 현재 구조나 의존성이 새 제품에 맞지 않아 재작성해야 하는 대상

### Discard

새 제품의 핵심 구조와 맞지 않거나 재사용 가치가 낮은 대상

## Reuse 대상

### 1. `execution/export_capcut.py`

판단: `reuse 후보 1순위`

이유:

- CapCut export 흐름이 이미 구체적으로 구현되어 있다
- 오디오 트랙, B-roll 트랙, 자막 트랙, 훅 타이틀, BGM 트랙 구성 방식이 명확하다
- 세로형 출력 대응 아이디어도 포함되어 있다

주의:

- 현재는 `pycapcut`, 환경변수, BrollBox 상수 구조에 결합되어 있다
- VideoBox에서는 `packages/capcut-export` 아래 독립 adapter로 재구성해야 한다

권장 처리:

- 로직과 트랙 설계는 적극 재사용
- API와 데이터 입력 형태는 VideoBox timeline schema 기준으로 재작성

### 2. `execution/auto_cut.py`

판단: `reuse 가치 높음`

이유:

- FFmpeg 기반 자동 컷 분리 로직이 현실적이다
- 장면 변화
- 암전 구간
- 최대 길이 초과 분할
- 너무 짧은 구간 제거
- 너무 어두운 구간 제거
- 정지 화면 제거

이런 다층 기준이 이미 들어가 있다

주의:

- 지금은 단일 파일에 FFmpeg 호출과 규칙이 함께 묶여 있다
- VideoBox에서는 `core-engine`의 raw footage preprocessing 계층으로 옮기는 게 맞다

권장 처리:

- 기준값과 처리 순서는 살린다
- 호출부, 설정, 에러 처리, job 모델 연동은 재작성한다

### 3. `execution/shorts_clip.py`

판단: `부분 재사용`

이유:

- SRT 파싱
- 숏폼 후보 추출 흐름
- FFmpeg 구간 추출
- 단일/다중 구간 합성
- 세로형 변환

이 구조는 VideoBox의 `longform -> shortform` 흐름과 맞는다

주의:

- 모델 호출이 특정 provider에 묶여 있다
- 점수 체계가 아직 템플릿적이다

권장 처리:

- SRT 파싱과 ffmpeg 추출 흐름은 재사용
- 후보 분석과 scoring은 VideoBox 기준으로 재작성

## Rewrite 대상

### 4. `execution/transcribe_audio.py`

판단: `아이디어는 매우 좋지만 재작성 필요`

이유:

- `WhisperX 전사 + 대본 장면 정렬 + 말 잘림 방지`라는 문제 정의가 정확하다
- 실제로 VideoBox의 핵심 기능과 잘 맞는다

재작성해야 하는 이유:

- Gemini 호출이 코드에 직접 박혀 있다
- BrollBox 내부 함수 import에 의존한다
- VideoBox의 provider abstraction, job model, domain model에 맞지 않는다

권장 처리:

- 설계 아이디어를 핵심 참고안으로 채택
- `STTProvider`, `LLMProvider`, `TranscriptAligner` 구조로 다시 설계

### 5. `execution/match_script.py`

판단: `핵심 아이디어 유지, 구조는 재작성`

이유:

- 대본 장면 분리
- 장면별 키워드 추출
- 장면별 B-roll 추천

이 흐름은 VideoBox의 자동 초안 생성에 매우 중요하다

재작성해야 하는 이유:

- Google Sheets 기반 검색 구조에 결합
- Gemini 직접 호출
- 새 제품의 asset index 모델과 맞지 않음

권장 처리:

- `SceneSplitter`
- `SceneKeywordExtractor`
- `BrollMatcher`

이 세 책임으로 분리해서 재구성

### 6. `execution/search_broll.py`

판단: `검색 사고방식은 재사용, 구현은 재작성`

이유:

- 태그 기반 검색
- 필터링
- 점수 계산
- 컨텍스트 검색 fallback

이런 개념은 VideoBox에도 필요하다

재작성해야 하는 이유:

- 시트 컬럼 구조와 강하게 결합
- DataFrame 중심 구현
- provider, storage, asset schema 분리가 없음

권장 처리:

- scoring 로직과 필터 축을 참고
- VideoBox의 asset metadata schema 기준으로 다시 구현

## Discard 대상

### 7. `app.py`, `ui/`

판단: `직접 재사용 비추천`

이유:

- Streamlit 기반 구조가 VideoBox의 장기 구조와 맞지 않는다
- 페이지 구조 자체가 BrollBox의 운영 흐름에 최적화되어 있다
- 지금 필요한 것은 `local-first operator dashboard / lightweight editing UI`이지, BrollBox UI 복제가 아니다

권장 처리:

- UX 아이디어만 참고
- 코드 직접 이식은 하지 않음

### 8. Google Sheets / Drive 중심 운영 방식

판단: `새 제품의 기본 구조로는 부적합`

이유:

- VideoBox는 로컬 우선 구조다
- 사용자 자산과 프로젝트 산출물이 로컬에 있어야 한다
- 나중에 SaaS 확장을 하더라도 storage abstraction 위에 올리는 구조가 더 맞다

권장 처리:

- 초기에는 로컬 DB + 로컬 파일 기반
- 필요 시 나중에 동기화 레이어를 붙임

### 9. `.claude`, memory, 운영용 부수 문서들

판단: `직접 재사용 대상 아님`

이유:

- 운영 기록이나 에이전트 작업용 구조는 VideoBox 제품 구현과 직접 관련이 낮다

권장 처리:

- 참고는 가능
- 제품 코드/설계에 직접 포함하지 않음

## 최종 권장 재사용 우선순위

1. CapCut export 로직
2. 자동 컷 분리 로직
3. WhisperX 전사 및 정렬 아이디어
4. 대본 장면 분리 및 B-roll 매칭 구조
5. 숏폼 추출 흐름
6. 검색/필터/점수화 개념
7. UI는 참고만

## VideoBox 반영 원칙

- BrollBox의 `execution` 계층은 기능 참고와 알고리즘 이식 대상으로 본다
- BrollBox의 `app/ui` 계층은 UI 참고 대상으로만 본다
- Google Sheets/Drive 결합 구조는 버린다
- 특정 모델 호출 하드코딩은 버리고 provider 인터페이스 뒤로 숨긴다
- CapCut export는 새 아키텍처에서 별도 adapter로 격리한다

## 결론

BrollBox는 버릴 프로젝트가 아니라 VideoBox의 중요한 전신이다.
다만 새 제품은 `BrollBox를 복제`하는 게 아니라, `검증된 실행 로직만 추출해 새 아키텍처에 맞게 재구성`해야 한다.
