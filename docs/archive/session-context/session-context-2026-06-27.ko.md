# VideoBox 세션 컨텍스트

> Historical note: 이 문서는 초기 제품 방향/폴더 경계 결정 당시의 중간 저장 기록이다. 현재 authoritative 제품 방향과 next slice 판단은 최신 SSOT 문서를 우선 적용한다: `docs/session-context-2026-07-01-system-hygiene.ko.md`, `docs/development-status-2026-06-29.ko.md`의 `## 17`, `docs/implementation-plan.ko.md`의 2026-07-01 체크포인트.

작성일:

- 2026-06-27

## 1. 폴더 역할

- 개발 폴더: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`
- 프로젝트 폴더: `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`

원칙:

- 개발 폴더는 프로그램 자체를 만드는 워크스페이스다
- 프로젝트 폴더는 실제 운영 결과물과 산출물을 다루는 워크스페이스다

## 2. 제품 방향

VideoBox는 로컬 우선 AI 영상 자동 편집 엔진이다.

핵심 목표:

- 녹음 파일
- 참고 문서/스크립트
- 원본 영상
- B-roll 자산
- 사용자 본인 목소리 샘플

을 받아 자동 편집 초안을 만들고, 최종 수정은 CapCut에서 이어가게 하는 것이다.

## 3. 현재 확정된 핵심 원칙

- 로컬 우선으로 구현한다
- 코어 엔진, 데이터 모델, job 모델, provider 인터페이스는 SaaS 확장 가능 구조로 설계한다
- 내부 기준 포맷은 timeline JSON이다
- 직접 풀 편집기는 만들지 않는다
- CapCut은 내부 기준 포맷이 아니라 export 대상이다
- 자동 최종본보다 자동 초안 생성이 우선이다
- 추천과 자동 적용은 분리한다
- 확신도, 추천 이유, review flag를 남긴다

## 4. 첫 구현 범위

첫 구현은 아래 범위로 고정한다.

1. 로컬 프로젝트 생성
2. 녹음 파일 입력
3. 참고 문서/스크립트 입력
4. 사용자 본인 목소리 샘플 입력
5. B-roll 메타데이터 인덱싱
6. WhisperX 기반 전사
7. 세그먼트 분리
8. 반복 take / 무음 / 재시작 탐지
9. 본인 목소리 기반 제한적 TTS 대체 생성
10. sentence-transformers 기반 텍스트 추천
11. 간단한 B-roll 추천
12. 기본 음악 추천
13. timeline JSON 생성
14. preview 또는 CapCut export
15. 기본 review 대시보드

## 5. TTS 범위

TTS는 기능에 포함한다.

하지만 범위는 다음으로 제한한다.

- 사용자 본인 목소리만 사용
- 나레이션 대체용 TTS만 지원
- 잘못 발음했거나 다시 녹음하기 번거로운 일부 구간만 대체
- 자동 전면 대체 금지
- review 기반 적용

아키텍처 반영 항목:

- `TTSProvider`
- `voice_sample_audio`
- `tts_replacement`

## 6. 기술 선택

현재 기준 기술 선택:

- 대시보드: `React + TypeScript + Vite`
- 로컬 API: `FastAPI`
- 코어 엔진: `Python`
- 전사: `WhisperX`
- 장면 분리 보조: `PySceneDetect`
- 텍스트 의미 검색: `sentence-transformers`
- export: `CapCut adapter`

보류:

- `open_clip`
- `Remotion`
- `Tauri`

## 7. BrollBox 재사용 방침

재사용 가치 높음:

- CapCut export
- auto cut
- transcribe/alignment 아이디어
- script matching 구조
- shorts 추출 흐름

직접 재사용 비추천:

- Streamlit UI
- Google Sheets/Drive 중심 구조
- provider 하드코딩

## 8. 현재 중요한 문서

- `docs/product-plan.ko.md`
- `docs/implementation-plan.ko.md`
- `docs/architecture-plan.ko.md`
- `docs/oss-research-and-scope-cut.ko.md`
- `docs/brollbox-reuse-audit.ko.md`
- `docs/development-context.ko.md`
- `docs/local-storage-strategy.ko.md`
- `docs/videobox-mcp-scope.ko.md`

## 9. 아직 미정인 것

- provider 기본 조합의 상세 선택
- review UI의 첫 화면 구조

## 10. 다음 추천 작업

1. 실제 프로젝트 폴더 구조 생성
2. React 대시보드 뼈대 생성
3. FastAPI 로컬 API 뼈대 생성
4. Python 코어 엔진 패키지 구조 생성
5. SQLite 스키마 초안 생성

## 11. 한 줄 현재 상태

현재 VideoBox는 `본인 목소리 기반 제한적 TTS를 포함한 로컬 우선 자동 편집 초안 생성기`로 방향과 저장 전략이 고정된 상태이며, 다음 단계는 실제 코드 뼈대를 만드는 것이다.
