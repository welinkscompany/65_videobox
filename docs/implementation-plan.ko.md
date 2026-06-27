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
