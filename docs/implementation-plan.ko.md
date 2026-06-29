# VideoBox 실행용 구현 계획서

## 1. 목적

이 문서는 VideoBox를 실제로 구현하기 위한 실행 계획서다.

목표는:

- 범위를 고정하고
- 구현 순서를 분명히 하고
- 개발 중 흔들림을 줄이며
- MVP와 이후 단계의 경계를 명확히 하는 것

## 2. 현재 구현 전략

구현 방향은 다음과 같이 확정한다.

- 로컬 우선 구현
- SaaS 확장 가능 구조
- 직접 풀 편집기 대신 CapCut export 중심
- 자동 최종본보다 자동 초안 생성 우선
- 나레이션 + 참고 문서 + B-roll 추천 흐름을 첫 구현 대상으로 선택

## 3. 첫 구현 대상

첫 구현 대상은 `설명형/나레이션 기반 자동 초안 생성기`다.

입력:

- 녹음 파일
- 참고 문서 또는 스크립트
- 사용자 B-roll 자산
- 사용자 본인 목소리 샘플

출력:

- 세그먼트 분석 결과
- 자동 자막
- 본인 목소리 기반 TTS 대체 오디오
- B-roll 추천
- 음악 추천
- 설명형 비주얼 계획
- timeline JSON
- 1차 playable local preview artifact
- CapCut export 결과

## 4. MVP 범위

### 포함

- 프로젝트 생성
- 로컬 파일 ingest
- STT
- 세그먼트/장면 분리
- 반복 take / 무음 / 재시작 탐지
- 본인 목소리 기반 제한적 TTS 대체 생성
- B-roll 자산 메타데이터 기반 검색
- 문장/장면별 B-roll 추천
- 기본 음악 추천
- 간단한 설명형 오버레이 계획
- timeline JSON 생성
- preview 렌더
- CapCut export
- review용 기본 화면

### 제외

- 풀 자체 편집기
- 실시간 멀티트랙 편집 UI
- 결제/계정 체계 전체
- 멀티유저 협업
- 클라우드 렌더 팜
- 고급 생성형 애니메이션
- 완전 자동 최종본 보장

## 5. 마일스톤

### Milestone 0. 계획 고정

목표:

- 제품 계획서 확정
- 구현 계획서 확정
- 아키텍처 계획 확정
- BrollBox 재사용 범위 확정

완료 기준:

- 개발 시작 전 기준 문서가 준비됨

### Milestone 1. 코어 뼈대

목표:

- 폴더 구조 생성
- domain models 정의
- timeline schema 정의
- provider interfaces 정의
- storage abstraction 정의
- local job model 정의

완료 기준:

- 새 제품의 코어 경계가 코드로 분리되어 있음

### Milestone 2. 입력과 분석

목표:

- 로컬 미디어 ingest
- 녹음 파일 STT
- 세그먼트/장면 분리
- 반복 take / 무음 / 재시작 탐지
- TTS 입력 샘플 관리

완료 기준:

- 입력 오디오에서 세그먼트 레코드와 분석 결과 생성 가능

### Milestone 3. 추천 엔진

목표:

- B-roll 자산 인덱싱
- 문장/장면별 B-roll 추천
- 기본 음악 추천
- 설명형 비주얼 계획
- TTS 대체 가능 구간 추천

완료 기준:

- 세그먼트 단위로 후보 추천과 점수 산출 가능

### Milestone 4. 편집 초안 생성

목표:

- rough cut planning
- timeline JSON 생성
- review flags 생성

완료 기준:

- 자동 초안의 구조화 결과가 생성됨

### Milestone 5. 출력

목표:

- preview 렌더
- 자막 파일 생성
- CapCut export

완료 기준:

- 실제 검수 가능한 결과물이 출력됨

### Milestone 6. 얇은 review UI

목표:

- 세그먼트 검수
- 후보 교체
- 검수 플래그 확인

완료 기준:

- 사용자가 초안을 보고 최소 수정 판단을 할 수 있음

## 6. 권장 개발 순서

1. 문서 고정
2. 프로젝트 구조 생성
3. domain models / timeline schema / provider interfaces 구현
4. local storage adapter / local job runner 구현
5. STT + 세그먼트 분석 구현
6. B-roll 인덱싱 및 추천 구현
7. 음악 추천 구현
8. 설명형 비주얼 계획 구현
9. timeline builder 구현
10. TTS provider 연결
11. preview renderer 구현
12. CapCut export adapter 구현
13. review UI 구현

## 7. 기술 선택 초안

- 언어: Python 우선
- 영상 처리: FFmpeg
- 전사: WhisperX 또는 대체 STT provider
- LLM: 로컬 Qwen 우선 + Gemini multi-key fallback + 선택적 OpenAI provider
- TTS: 사용자 본인 목소리 기반 TTS provider
- 비전/자산 분석: OpenCV + 자산 메타데이터 인덱싱
- 데이터 저장: 로컬 DB 우선
- UI: React + TypeScript 기반 로컬 우선 web review dashboard
- export 대상: CapCut

## 8. BrollBox 재사용 방침

재사용 우선순위:

1. CapCut export
2. auto cut
3. transcribe/alignment 아이디어
4. script matching 구조
5. shorts 추출 흐름

원칙:

- 전체 구조 복제 금지
- execution 로직만 선별 이식
- Google Sheets/Drive 구조는 버림
- provider 하드코딩 제거
- TTS는 별도 provider로 제한 범위 구현

## 8.1 재사용/OSS 반영 게이트

이 항목은 특정 milestone에서 한 번만 확인하는 참고사항이 아니다.
앞으로 모든 구현 goal에 계속 적용하는 상위 규칙이다.

각 구현 작업은 시작 전에 아래를 먼저 판단해야 한다.

1. 이번 작업과 관련된 기존 내부 소스 또는 외부 OSS가 이미 있는가
2. 있으면 `adopt as-is`, `partial port`, `rewrite`, `exclude` 중 어디에 해당하는가
3. 이번 작업 범위에서 실제로 반영할 재사용 단위는 무엇인가
4. 이번 작업에서 의도적으로 제외하는 재사용 후보는 무엇이며 이유는 무엇인가
5. 현재 작업이 repo 경계를 오염시키지 않는가

판단 기준:

- `소스 복제`보다 `경계 유지`를 우선한다
- `통째 복사`보다 `선별 이식`을 우선한다
- `UI 구조`, `Google Sheets/Drive 결합`, `provider 직접 호출 하드코딩`은 반입 금지다
- 재사용 판단은 기능 설명이 아니라 실제 코드 반영 단위까지 내려와야 한다

## 8.2 각 Goal 프롬프트 필수 체크

앞으로 모든 구현 goal 프롬프트에는 아래 체크를 포함하는 것을 기본값으로 한다.

- 관련 BrollBox/기존 내부 코드/외부 OSS 재사용 후보를 먼저 검토할 것
- 각 후보를 `adopt as-is`, `partial port`, `rewrite`, `exclude`로 분류할 것
- 이번 goal에서 실제 반영할 재사용 범위를 명시할 것
- 반입 금지 규칙과 경계 유지 원칙을 지킬 것
- 테스트로 재사용 반영과 구조 보존을 함께 증명할 것

특히 우선 검토 대상은 아래 순서를 기본으로 삼는다.

1. `execution/export_capcut.py`
2. `execution/auto_cut.py`
3. `execution/transcribe_audio.py`의 alignment 흐름
4. `execution/match_script.py`의 scene split 흐름
5. `execution/search_broll.py`의 scoring 축

## 8.3 구현 완료 시 적용 여부 보고

각 구현 작업이 끝나면 완료 보고에 아래를 반드시 포함한다.

- 이번 작업에서 확인한 재사용 후보
- 실제 반영한 항목과 반영 방식
- 이번 범위에서 제외한 항목과 제외 이유
- 경계 보존 여부
- 테스트와 리뷰로 무엇을 검증했는지

짧게라도 이 항목을 남겨야, 개발 중간에 재사용 원칙이 잊히거나 다른 방향으로 새는 일을 줄일 수 있다.

## 9. 리스크

### 9.1 자동 추천 품질

위험:

- B-roll 추천이 문맥에 안 맞을 수 있음

대응:

- 추천 점수와 검수 플래그 제공

### 9.2 STT 및 정렬 품질

위험:

- 발음이 안 좋거나 재녹음이 섞인 경우 정렬이 흔들릴 수 있음
- 본인 목소리 TTS 품질이 문장 길이와 억양에 따라 흔들릴 수 있음

대응:

- ambiguous 구간을 자동 삭제하지 않고 review 대상으로 보냄
- TTS도 자동 전면 대체하지 않고 review 기반 후보로만 적용

### 9.3 CapCut export 의존

위험:

- CapCut 구조 변경 가능성

대응:

- exporter를 별도 adapter로 격리

### 9.4 범위 폭발

위험:

- 자체 편집기, SaaS, 생성형 그래픽까지 동시에 욕심낼 수 있음

대응:

- 첫 구현은 나레이션 기반 초안 생성기로 고정

## 10. 예상 개발 기간

가정:

- 1인 중심 개발
- 직접 편집기 제외
- CapCut export 중심
- 첫 장르는 나레이션/설명형 영상

### 기술 검증 프로토타입

- 예상: 3~5주

포함:

- STT
- 세그먼트 분석
- 제한적 TTS 실험
- B-roll 추천 기본형
- timeline JSON
- preview 또는 export 일부

### MVP

- 예상: 2~4개월

포함:

- 코어 구조
- ingest
- 추천
- preview
- CapCut export
- review UI 기본형

### 실사용 v1

- 예상: 4~7개월

포함:

- 긴 영상 안정화
- 자산 재사용성 향상
- shortform 후보 개선
- 오류 처리와 운영성 강화

## 11. 착수 전 확인 사항

- 계획 문서 3종 확정
- 재사용 감사 문서 확정
- 첫 장르 확정
- provider 전략 확정
- 로컬 파일/프로젝트 저장 전략 확정
- 본인 목소리 TTS 허용 범위 확정

## 12. 다음 실제 작업

문서 확정 후 첫 코드 작업은 아래 순서로 진행한다.

1. 실제 폴더 구조 생성
2. domain models 작성
3. timeline schema 작성
4. provider interfaces 작성
5. local storage adapter 작성
6. local job runner 작성

이 단계가 끝난 뒤에야 기능 구현으로 들어간다.
