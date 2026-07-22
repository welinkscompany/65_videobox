# VideoBox 실행용 구현 계획서

> 현재 worktree 기준 next implementation 판단은 `### 8.4.2 2026-07-17 OSS 앱 셸·편집기 재분석 결정`과 연결된 22-Task 실행 계획을 우선 적용한다. 완료된 Local Media Director 상태는 `## 22`가 authoritative closeout이다. 그 외 상위 milestone/범위/순서 섹션은 제품·구현 계획의 기준을 설명한다.
> 개발 운영 상위 규칙은 저장소 루트 `AGENTS.md`와 `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`을 프로젝트 전역 기본값으로 적용한다. 즉, 이 계획서를 실행할 때의 작업 우선순위, 선택적 TDD/서브에이전트/리뷰 사용, 표준 검증 경로, hot path 구분, 커밋/푸시, 진행률 보고, turn closeout 형식은 해당 규정을 따른다.

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
- 직접 풀 편집기 대신 설명형 영상용 경량 후편집기 + CapCut handoff 중심
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
- 경량 후편집 가능한 draft state
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
- 경량 후편집기
- CapCut export
- review용 기본 화면

### 제외

- 풀 자체 편집기
- 실시간 멀티트랙 편집 UI
- 결제/계정 체계 전체
- 멀티유저 협업
- 클라우드 렌더 팜
- 고급 생성형 애니메이션
- 고급 모션그래픽 편집
- 복잡한 오디오 믹싱 콘솔
- 색보정 툴 전체
- 자유곡선 키프레임 시스템
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

### Milestone 6. 경량 후편집기

목표:

- 세그먼트 검수와 수정
- 컷 유지/삭제 및 경계 미세 조정
- 자막 텍스트/타이밍 수정
- B-roll 후보 교체
- 배경 영상/이미지 교체
- 설명 카드/이미지/표 삽입
- 음악 선택/제거/교체
- 효과음 추천 선택/제거
- 검수 플래그 확인/해제
- 원본/자동/수정 결과 비교
- 수정 이력 저장
- 부분 재생성 실행
- CapCut handoff 전 최종 정리

완료 기준:

- 사용자가 VideoBox 안에서 초안을 직접 다듬고, 설명형 영상 후편집을 끝낸 뒤 export 또는 handoff 할 수 있음

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
13. 경량 후편집 데이터 모델/API 구현
14. 경량 후편집 UI 구현
15. 필요한 경우 CapCut handoff 보강

## 7. 기술 선택 초안

- 언어: Python 우선
- 영상 처리: FFmpeg
- 전사: WhisperX 또는 대체 STT provider
- LLM: LM Studio loopback 기반 로컬 text/vision/embedding provider만 자동 runtime에 사용. Gemini/OpenAI 자동 fallback 금지
- TTS: 사용자 본인 목소리 기반 TTS provider
- 비전/자산 분석: OpenCV + 자산 메타데이터 인덱싱
- 데이터 저장: 로컬 DB 우선
- UI: React + TypeScript 기반 로컬 우선 web review dashboard
- 편집 셸: 오픈소스 편집기 구조를 선별 반입한 React + TypeScript 기반 경량 후편집기
- export 대상: CapCut

### 7.1. 웹 대시보드 표시 언어 기준

- UI 고정 문구: 한글 우선
- UI 문체: 설명문보다 단어 중심 요약
- 상태/작업/검수 코드: 사용자 의미 기준 한글 라벨로 매핑
- 서버 데이터 표시: 화면에서는 한글 표시명 또는 한글 요약 우선
- DB 원본 데이터: 변경하지 않음
- 화면 한글화 대상:
  - 프로젝트명
  - 세그먼트 문장
  - 자산명
  - 파일명
  - 태그
  - 추천 이유
  - 검수 메시지
- 원문 유지 대상:
  - 모델/작업/추천/자산 ID
  - local URI / storage URI
- 자동 번역/요약 위치: DB 저장층이 아니라 웹 UI 표시 계층
- 원문 유지 이유:
  - ID/URI는 추적성 때문에 변형하면 안 된다
- 필요 시 후속 UX:
  - 한글 표시명 우선
  - 원문 보기 보조 토글

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
- TDD를 기본값으로 두되, 문서/상태 정리처럼 코드 동작을 바꾸지 않는 작업은 예외로 분리할 것
- 서브에이전트, code review, gap 검증, 역방향 동작 검증은 고정 의무로 넣지 말고 필요성과 기대 효율이 있을 때만 명시할 것
- closeout에는 계획서 준수 점검, 다음 goal 프롬프트, 진행률/잔여율 추정치를 함께 남길 것
- 추천만 수행한 turn이어도 같은 closeout 규칙을 적용할 것

특히 우선 검토 대상은 아래 순서를 기본으로 삼는다.

1. `execution/export_capcut.py`
2. `execution/auto_cut.py`
3. `execution/transcribe_audio.py`의 alignment 흐름
4. `execution/match_script.py`의 scene split 흐름
5. `execution/search_broll.py`의 scoring 축

## 8.4 경량 후편집기 반영 원칙

경량 후편집기는 이제 선택 사항이 아니라 설명형 영상용 핵심 범위로 본다.
다만 다음 선은 계속 지킨다.

- 풀 NLE를 직접 구현하지 않는다
- 설명형 영상 초안을 빠르게 고치는 데 필요한 편집만 넣는다
- 세그먼트, 자막, 추천 자산, 설명 자산 중심으로 편집 범위를 제한한다
- 고급 모션그래픽, 색보정, 오디오 믹싱, 자유 키프레임은 현재 범위에서 제외한다

현재 편집기 범위는 아래로 고정한다.

- 컷 유지/삭제
- 컷 경계 미세 조정
- 세그먼트 병합/분리
- 자막 텍스트 수정
- 자막 타이밍 미세 조정
- B-roll 교체
- 배경 영상/이미지 교체
- 설명 카드/이미지/표 삽입
- 음악 선택/제거/교체
- 효과음 추천 선택/제거
- review flag 확인/해제
- 원본/자동/수정 비교
- 수정 이력 저장
- 부분 재생성

오픈소스 편집기 반입 시점도 함께 고정한다.

1. 먼저 편집 도메인 모델과 API를 고정한다
2. 그 다음 얇은 자체 검수 UI로 실제 수정 흐름을 검증한다
3. 그 다음 오픈소스 편집기 셸을 `partial port` 또는 `reference` 방식으로 붙인다

즉, 편집기 오픈소스는 `지금 바로 통째 반입`이 아니라 `편집 규칙이 고정된 직후`에 붙이는 것이 원칙이다.

### 8.4.1 OpenCut 및 음성 제작 후속 판단 게이트

- OpenCut은 현재 통째 도입·임베드·제품 의존성 후보가 아니다. 현행판은 재작성 중이고 classic은 archived 상태이므로, VideoBox의 FFmpeg preview·CapCut draft·editing-session SSOT를 대체하지 않는다.
- 향후 timeline patch API와 FFmpeg preview 계약이 안정된 뒤에만 OpenCut을 다시 분석한다. 그때도 기본값은 코드 반입이 아니라 drag/trim, snapping, ripple, waveform, rational time 같은 UX interaction의 독립 재구현이다.
- 재분석 gate는 실제 Editor API/headless 상태, 라이선스·의존성 SBOM, 보안, canonical timeline round-trip, CapCut export 영향, GPU fallback을 포함한다.
- Voice Capture & Narration은 별도 후속 slice다. 브라우저 녹음과 파일 업로드를 narration asset으로 정규화하고, local STT 전사·대본 정렬·자막 생성을 연결한다.
- voice sample 기반 TTS/voice cloning은 전사와 분리한다. 명시적 opt-in, 원본·전사·샘플의 삭제/보관 정책, preview→apply→undo, review/approval gate를 별도 설계·검증하기 전에는 자동 사용하지 않는다.

### 8.4.2 2026-07-17 OSS 앱 셸·편집기 재분석 결정

Local Media Director 18개 Task와 editing-session revision, source provenance, FFmpeg/PyCapCut output gate가 완료됐으므로 §8.4.1의 OpenCut 재분석 gate를 열었다. 이번 결정은 OpenCut을 제품 dependency로 넣는 승인이 아니라, 검증 가능한 화면·상호작용만 VideoBox 경계 안으로 선별 이식하는 승인이다.

- 조사 보고서: `docs/research/2026-07-17-videobox-oss-dashboard-editor-adoption.ko.md`
- 설계서: `docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md`
- 구현 계획서: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`
- 구현 단위: 7개 slice, 22개 실행 Task
- production 구현 상태: Task 11의 두 번째 사용자 시각 승인은 완료했다. 다만 사용자가 고정한 Task 9 사람/환경 acceptance 기준에 따라 공식 누적은 **9/22 Task (40.9%)**, 잔여 **59.1%**를 유지한다.

도입 분류는 다음으로 고정한다.

1. `shadcn/ui`: pinned registry source path와 normalized file SHA를 lock한 source-owned component를 직접 사용한다. live registry 결과를 pinned source로 오인하지 않는다.
2. `shadcn-admin`: sidebar/header/project switcher/settings shell composition만 `partial port`한다.
3. `OpenCut current rewrite`: 실제 editor가 아직 없으므로 editor runtime 후보에서 제외한다.
4. `OpenCut classic`: archived source에서 panel layout, asset tabs, inspector registry, pure timeline/preview geometry만 `partial port` 또는 adapter 방식으로 이식한다.
5. `Opencast Editor`: transcript/subtitle/waveform/cut interaction을 Apache-2.0 attribution과 함께 source-derived behavioral adaptation한다.
6. `Supabase Studio`: 프로젝트 계층, settings IA, mobile navigation을 `reference only`로 사용한다.

OpenCut EditorCore, IndexedDB/OPFS, browser renderer/export, WASM, browser STT와 Opencast Redux/MUI/full snapshot API/player fork/browser waveform decode는 반입하지 않는다. Supabase source도 직접 복사하지 않는다. editing-session, revision, FFmpeg, PyCapCut, output-source verifier는 계속 authoritative하다.

새 shell은 local/cloud capability slot을 갖지만 실제 SaaS auth/team/billing과 Hermes agent/container는 이번 22개 Task에 넣지 않는다. Slice 0 Task 1은 기존 Yujin copy를 closeout하고 project/section 선택, Director 수동 fallback, current/stale preview·output, settings의 legacy baseline을 고정했다. Task 11의 다섯 viewport 시각 prototype은 2026-07-22 사용자 승인을 받았다. Task 14 pure time-scale/geometry/snapping/hit-test, Task 15 read-only UI navigation/performance, Task 16 narration trim/reorder mutation, Task 17 독립 multi-lane placement 편집은 closeout했다. 다음 편집기 goal은 Task 18의 별도 written spec이다. browser source audition은 실제 합성 preview가 아니며, current revision의 정확한 미리보기는 기존 FFmpeg composition path를 재사용한 freshness-bound proxy artifact로 고정한다. caption timing은 현 backend 권한에 맞춰 segment-linked로 제한한다.

## 8.3 구현 완료 시 적용 여부 보고

각 구현 작업이 끝나면 완료 보고에 아래를 반드시 포함한다.

- 이번 작업에서 확인한 재사용 후보
- 실제 반영한 항목과 반영 방식
- 이번 범위에서 제외한 항목과 제외 이유
- 경계 보존 여부
- 테스트와 리뷰로 무엇을 검증했는지

짧게라도 이 항목을 남겨야, 개발 중간에 재사용 원칙이 잊히거나 다른 방향으로 새는 일을 줄일 수 있다.

## 8.5 2026-06-29 현재 구현 상태 점검

확인된 사실:

- 로컬 프로젝트, 자산 등록, job 저장, timeline 저장, review 상태 저장 구조는 이미 코드와 테스트로 검증되어 있다
- transcript alignment, segment analysis, B-roll 추천, 음악 추천, timeline 생성, review approval, subtitle render, preview render, CapCut export 흐름이 이미 연결돼 있다
- 로컬 우선 LLM runtime은 `Local Qwen -> Gemini fallback` 구조로 이미 들어가 있다
- editing session 생성/조회/수정 API와 partial regeneration request contract가 이미 들어가 있다
- 이 구간은 2026-06-29 시점 스냅샷이며, 최신 검증 기준은 아래 2026-07-01 체크포인트를 따른다

현재 기준으로 아직 비어 있는 핵심 범위:

- partial regeneration의 실제 job 실행 연결
- 편집 세션 수정 결과를 timeline 재작성 또는 후속 생성 단계에 반영하는 규칙
- 설명 카드/이미지/표 삽입을 지금보다 세분화한 수정 규칙
- TTS 대체를 편집 세션에서 다루는 planner/provider 연결

정리하면, 지금 단계에서 바로 해야 할 일은 `편집기 UI 반입`이 아니다.
먼저 `편집 상태 모델 + 저장 + 수정 API + 부분 재생성 규칙`을 기반으로 실제 재생성 실행과 timeline 반영 규칙을 고정해야 한다.

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

- 첫 구현은 나레이션 기반 초안 생성기 + 설명형 영상용 경량 후편집기로 고정

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
- 경량 후편집기 설계 일부

### MVP

- 예상: 2~4개월

포함:

- 코어 구조
- ingest
- 추천
- preview
- CapCut export
- 경량 후편집기 기본형

### 실사용 v1

- 예상: 4~7개월

포함:

- 긴 영상 안정화
- 자산 재사용성 향상
- shortform 후보 개선
- 경량 후편집기 안정화
- 오류 처리와 운영성 강화

## 11. 착수 전 확인 사항

- 계획 문서 3종 확정
- 재사용 감사 문서 확정
- 첫 장르 확정
- provider 전략 확정
- 로컬 파일/프로젝트 저장 전략 확정
- 본인 목소리 TTS 허용 범위 확정

## 12. 2026-07-01 현재 구현 체크포인트

### 2026-07-11 production-readiness blocker slice 1 authoritative checkpoint

이번 checkpoint는 `docs/superpowers/plans/2026-07-11-production-readiness-blocker-slice-1.md`의 9개 Task와 여섯 blocker 계약을 기준으로 한다. 2026-07-11 현재 HEAD `f02dde1` 이후 worktree 변경까지 포함한 검증 결과는 아래와 같다.

| blocker | 현재 계약과 증거 |
| --- | --- |
| 빈 첫 화면 | 프로젝트 생성 뒤 narration/script ingest를 독립 실행한다. 하나가 실패해도 생성된 프로젝트와 다른 ingest 성공은 유지하고 실패한 항목만 다시 등록한다. `project-onboarding.test.tsx`가 create/ingest와 failure/retry를 검증한다. |
| assetless BGM | 실물 `selected_asset_id` 없는 mood recommendation은 metadata로만 남고 BGM clip 또는 `music/suggested` URI를 만들지 않는다. |
| nullable output | failed final render/real CapCut draft는 nullable artifact와 error message를 반환하며 UI는 error card, retry, ErrorBoundary로 복구한다. |
| partial caption | partial regeneration candidate의 `caption_segments`가 승인 후 SRT에 쓰이고 final renderer에는 그 timeline의 최신 SRT가 전달된다. |
| short source duration | FFmpeg는 short B-roll을 loop하고 audio를 `apad/trim`한다. real CapCut draft는 B-roll repetition과 project-local persistent WAV silence segment로 source를 늘리지 않고 target window를 채운다. |
| export overlays | FFmpeg는 text 및 image overlay를 실제 frame에 materialize하고, real CapCut draft는 text track과 image video track/material을 가진다. |

검증 증거:

- frontend: `npm test -- --run` 82 passed, `npm run build` 성공. ErrorBoundary intentional throw와 기존 App test의 React `act(...)` warning은 stderr에 남지만 테스트 실패는 아니다.
- backend: `.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider`에서 Python 3.12.10, 621 passed.
- actual Korean smoke: `production-readiness-korean-10m.wav` 600.000초, SHA-256 `a0c7f05a7052be735dce56df38a45ae167a9b24cad122a3c518ef9025701ee0f`; API ingest→edit→partial caption→SRT→FFmpeg MP4 9개 check true (MP4 internal subtitle 및 distinguishable short B-roll loop 포함); final MP4 600.000초, SHA-256 `45e430cae559e94b0b62eb2bf5f8178f74c0472a9fbadebb134ccb9bf9425c79`.

진행률은 이 계획서의 39개 implementation milestone bullet을 재판정한 값이다. 36 완료, 3 부분, 0 미구현으로 판정한다. strict 완료율은 `36 / 39 = 92.3%`, 부분 항목을 0.5로 계산한 weighted 진행률은 `(36 + 3 × 0.5) / 39 = 96.2%`, weighted 잔여율은 `3.8%`다. 부분 3개는 개인 음성 clone 품질, 효과음 추천/선택, 긴 영상의 사람 검수 운영 품질이며 이번 blocker slice의 완료 조건은 아니다.

이하 기존 2026-07-01 체크포인트는 historical reference다.

현재 기준 아래 범위는 코드와 검증으로 실제 연결되어 있다.

- `editing session` 저장/조회/수정 API
- partial regeneration request contract와 backend job 실행
- partial regeneration preflight request contract도 session `segments` 안의 stale non-dict entry를 targeted-segment lookup 후보로 취급하지 않고 건너뛰는 계약
- partial regeneration runtime fallback도 session `segments` 안의 stale non-dict entry를 source-segment fallback 후보로 취급하지 않고 건너뛰는 계약
- thin editor mutation save / clear / remove
- review snapshot -> editing session handoff
- review action family
  - `Approve recommendation`
  - `Reject recommendation`
  - `Mark for manual edit`
- reject explicit decision-state persistence contract
- timeline-local review snapshot truth 보존
- review-action rollback hardening과 warning surface
- review-action rollback도 downstream failure 후 raw persisted timeline shape를 hydrated response shape로 덮어쓰지 않고 pending/applied/review-flag truth를 그대로 복구하는 계약
- pending `tts_replacement` approve 시 target narration track clip `asset_uri`를 승인된 `selected_asset_uri`로 반영하는 계약
- pending `tts_replacement` approve 시 같은 target segment를 가리키는 duplicate narration clip이 있어도 target narration clip 전체의 `asset_uri`를 승인된 `selected_asset_uri`로 동기화하는 계약
- pending `tts_replacement` approve는 `payload.selected_asset_uri`가 비어 있는 stale recommendation shape를 승인 상태로 통과시키지 않고 즉시 거부하는 계약
- pending `tts_replacement` approve는 `target_segment_id`에 대응하는 narration clip이 없는 stale timeline shape도 승인 상태로 통과시키지 않고 즉시 거부하는 계약
- pending `tts_replacement` approve는 persisted narration clip의 `segment_id`에 whitespace가 섞인 stale timeline shape여도 trimmed target segment 기준으로 같은 clip을 매칭해 승인된 `selected_asset_uri`를 반영하는 계약
- pending `tts_replacement` approve는 persisted recommendation의 `recommendation_type`에 whitespace가 섞인 stale shape여도 canonical TTS type 기준으로 narration clip 반영을 계속 수행하는 계약
- pending recommendation approve는 persisted recommendation의 `recommendation_type`에 whitespace가 섞이고 `provider_trace`가 비어 있는 stale shape여도 canonical recommendation type 기준으로 fallback provider trace를 채워 approve response와 persisted applied recommendation trace를 일관되게 유지하는 계약
- review snapshot helper read path도 persisted/applied recommendation의 `recommendation_type`에 whitespace가 섞이고 `provider_trace`가 비어 있는 stale shape여도 canonical recommendation type 기준으로 fallback provider trace를 채워 review snapshot applied recommendation trace를 일관되게 유지하는 계약
- recommendation row read path도 persisted recommendation row의 `recommendation_type`에 whitespace가 섞이고 `provider_trace`가 비어 있는 stale shape여도 canonical recommendation type 기준으로 fallback provider trace를 채워 downstream review/output read truth를 일관되게 유지하는 계약
- recommendation run read path도 saved recommendation run JSON의 top-level `recommendation_type`이 legacy/mixed-case stale shape여도 canonical lowercase type 기준으로 artifact read truth와 returned response surface를 유지해 recommendation result/output build 경로를 끊지 않는 계약
- timeline builder도 approved recommendation의 `recommendation_type`에 whitespace가 섞인 stale shape여도 canonical recommendation type 기준으로 narration/B-roll/BGM clip 반영 분기를 유지해 timeline/output truth를 일관되게 유지하는 계약
- timeline builder도 approved recommendation의 legacy/mixed-case `recommendation_type` shape를 raw casing 그대로 비교하지 않고 canonical lowercase type 기준으로 narration/B-roll/BGM clip 반영 분기를 유지해 timeline/output truth를 일관되게 유지하는 계약
- timeline builder도 approved TTS recommendation의 `target_segment_id`에 whitespace가 섞인 stale shape여도 trimmed segment id 기준으로 narration clip override를 유지하는 계약
- preview renderer도 applied recommendation의 `recommendation_type`에 whitespace가 섞인 stale TTS shape여도 canonical recommendation type 기준으로 selected narration source를 유지하는 계약
- preview renderer도 applied recommendation의 legacy/mixed-case `recommendation_type` TTS shape를 raw casing 그대로 비교하지 않고 canonical lowercase type 기준으로 selected narration source를 유지하는 계약
- preview renderer도 applied TTS recommendation의 `target_segment_id`에 whitespace가 섞인 stale shape여도 trimmed segment id 기준으로 selected narration source를 유지하는 계약
- CapCut export adapter도 applied recommendation의 `recommendation_type`에 whitespace가 섞인 stale TTS shape여도 canonical recommendation type 기준으로 segment-level narration source override를 유지하는 계약
- CapCut export adapter도 applied recommendation의 legacy/mixed-case `recommendation_type` TTS shape를 raw casing 그대로 비교하지 않고 canonical lowercase type 기준으로 segment-level narration source override를 유지하는 계약
- CapCut export adapter도 applied TTS recommendation의 `target_segment_id`에 whitespace가 섞인 stale shape여도 trimmed segment id 기준으로 segment-level narration source override를 유지하는 계약
- CapCut export adapter도 applied recommendation의 `auto_apply_allowed="true"` / `review_required="false"` legacy string false shape를 canonical bool로 해석해 segment-level narration source override를 유지하는 계약
- partial regeneration runtime의 `tts_refresh`도 source timeline `applied_recommendations`에 legacy/mixed-case `recommendation_type` stale approved TTS shape가 남아 있어도 canonical lowercase type 기준으로 기존 recommendation을 교체해 새 manual TTS selection truth를 유지하는 계약
- partial regeneration runtime의 `tts_refresh`도 source timeline `applied_recommendations`의 `target_segment_id`에 whitespace가 섞인 stale approved TTS shape가 남아 있어도 trimmed segment id 기준으로 기존 recommendation을 교체해 새 manual TTS selection truth를 유지하는 계약
- rule-based music recommender도 segment payload의 `review_required="false"` legacy string false shape를 canonical bool로 해석해 실제 review blocker가 없는 segment를 neutral-bed fallback branch로 오판하지 않는 계약
- partial regeneration runtime의 `tts_refresh`도 source timeline `applied_recommendations`에 whitespace가 섞인 stale approved `recommendation_type`이 남아 있어도 canonical recommendation type 기준으로 기존 recommendation을 교체해 새 manual TTS selection truth를 유지하는 계약
- partial regeneration runtime의 `broll_refresh`도 source timeline `applied_recommendations`에 whitespace가 섞인 stale approved `recommendation_type`이 남아 있어도 canonical recommendation type 기준으로 기존 recommendation을 교체해 새 manual B-roll selection truth를 유지하는 계약
- partial regeneration runtime의 `broll_refresh`도 source timeline `applied_recommendations`에 legacy/mixed-case stale approved `recommendation_type`이 남아 있어도 canonical lowercase type 기준으로 기존 recommendation을 교체해 새 manual B-roll selection truth를 유지하는 계약
- partial regeneration runtime의 `broll_refresh`도 source timeline `applied_recommendations`의 `target_segment_id`에 whitespace가 섞인 stale approved B-roll shape가 남아 있어도 trimmed segment id 기준으로 기존 recommendation을 교체해 새 manual B-roll selection truth를 유지하는 계약
- partial regeneration runtime의 `music_refresh`도 source timeline `applied_recommendations`에 whitespace가 섞인 stale approved `recommendation_type`이 남아 있어도 canonical recommendation type 기준으로 기존 recommendation을 교체해 새 manual BGM selection truth를 유지하는 계약
- partial regeneration runtime의 `music_refresh`도 source timeline `applied_recommendations`의 `target_segment_id`에 whitespace가 섞인 stale approved BGM shape가 남아 있어도 trimmed segment id 기준으로 기존 recommendation을 교체해 새 manual BGM selection truth를 유지하는 계약
- pending recommendation approve/reject는 persisted recommendation review flag의 `segment_id`에 whitespace가 섞인 stale timeline shape여도 trimmed target segment 기준으로 같은 flag를 정리해 stale blocker를 남기지 않는 계약
- pending recommendation approve/reject는 persisted recommendation review flag의 `code`에 whitespace가 섞인 stale timeline shape여도 canonical review flag code 기준으로 같은 flag를 정리해 stale blocker를 남기지 않는 계약
- pending recommendation approve/reject는 persisted pending recommendation의 `recommendation_id`에 whitespace가 섞인 stale timeline shape여도 route의 canonical recommendation id 기준으로 같은 recommendation을 선택해 decision mutation을 적용하는 계약
- pending recommendation approve/reject는 persisted `recommendation_decisions`에 whitespace가 섞인 stale key가 남아 있어도 canonical recommendation id key 하나로 정리해 같은 recommendation decision이 중복 key로 남지 않는 계약
- pending recommendation approve/reject는 persisted pending recommendation의 `recommendation_id`에 whitespace가 섞인 stale timeline shape여도 mutation 뒤 persisted `applied_recommendations` surface에는 canonical recommendation id만 남기는 계약
- pending recommendation approve/reject는 persisted pending recommendation의 `target_segment_id`에 whitespace가 섞인 stale timeline shape여도 review flag cleanup이 canonical target segment 기준으로 동작해 stale blocker를 남기지 않는 계약
- pending `tts_replacement` approve 뒤 `applied_recommendations` read path는 `decision_state=approved`와 `recommendation_type=tts_replacement`를 approve 응답, timeline, review snapshot에서 일관되게 유지하는 계약
- recommendation response normalization helper도 legacy/mixed-case `decision_state` shape를 raw casing 그대로 노출하지 않고 canonical lowercase surface로 정리해 approve/timeline/review snapshot read truth를 일관되게 유지하는 계약
- recommendation response normalization helper도 legacy/mixed-case `recommendation_type` shape를 raw casing 그대로 노출하지 않고 canonical lowercase surface로 정리해 approve/timeline/review snapshot/TTS read truth를 일관되게 유지하는 계약
- review flag response normalization helper도 legacy/mixed-case `review_flags.code` shape를 raw casing 그대로 노출하지 않고 canonical lowercase code / trimmed segment / default message surface로 정리해 timeline/review response read truth를 일관되게 유지하는 계약
- pending recommendation approve mutation과 review/timeline read path도 legacy/mixed-case `recommendation_type` shape를 raw casing 그대로 비교하지 않고 canonical lowercase type 기준으로 applied surface / fallback provider trace / review flag cleanup truth를 일관되게 유지하는 계약
- last pending `tts_replacement` approve 뒤에도 다른 segment의 `review_required=true` truth가 남아 있으면 persisted timeline `review_flags`가 synthetic `segment_review_required` blocker를 다시 써서 output gating과 review snapshot truth를 유지하는 계약
- approved timeline이라도 snapshot blocker 컬렉션이 비어 있는 상태에서 segment-level `review_required=true`가 남아 있으면 subtitle / preview / export를 계속 막는 output gating 계약
- approved timeline의 stale non-bool `segment.review_required` shape는 synthetic output blocker로 오판하지 않고 canonical bool/string 값만 review-required blocker로 인정하는 계약
- 위 segment-level `review_required` blocker는 API read path와 review snapshot에서 같은 synthetic flag로 반영돼 review 상태/출력 상태가 서로 어긋나지 않도록 유지하는 계약
- 위 synthetic blocker로 effective review status가 바뀌는 경우 persisted approved `operator_guidance`를 그대로 재사용하지 않고 blocked snapshot 기준 guidance를 다시 계산하는 계약
- unknown dict-shaped `review_flag.code`는 approved timeline output gating blocker로 오판하지 않고 canonical review flag code만 blocker로 유지하는 계약
- approved timeline의 persisted duplicate `review_flags`도 output blocker detail에서 code/segment 기준으로 dedupe되어 같은 blocker가 중복 노출되지 않는 계약
- approved timeline의 persisted duplicate `pending_recommendations`도 output blocker detail에서 recommendation id / target segment / recommendation type 기준으로 dedupe되어 같은 blocker가 중복 노출되지 않는 계약
- approved timeline의 stale mixed-case `pending_recommendations.recommendation_type`도 output blocker detail에서 raw casing을 그대로 노출하지 않고 canonical lowercase type 기준으로 surface를 유지하는 계약
- approved timeline의 stale whitespace `pending_recommendations.recommendation_id` / `target_segment_id`도 output blocker detail에서 raw spacing을 그대로 노출하지 않고 trimmed identity surface를 유지하는 계약
- approved timeline의 stale mixed-case `review_flags.code`도 output blocker 판정과 detail surface에서 raw casing을 그대로 쓰지 않고 canonical lowercase code 기준으로 유지하는 계약
- approved timeline의 persisted `pending_recommendations`에 `decision_state=approved/rejected` stale entry가 남아 있어도 unresolved blocker로 오판하지 않고 API read path / subtitle / preview / export에서 무시하는 계약
- approved timeline의 persisted `pending_recommendations`에 `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like entry가 `decision_state` 없이 남아 있어도 unresolved blocker로 오판하지 않고 subtitle / preview / export에서 무시하는 계약
- timeline build도 recommendation의 `review_required="false"` 같은 legacy string false shape를 review blocker/pending recommendation으로 오판하지 않고 applied recommendation truth를 유지하는 계약
- recommendation 저장 write path도 `review_required="false"` 같은 legacy string false shape를 blocker truth로 굳히지 않고 persisted recommendation / DB row / downstream timeline build에 같은 canonical false를 넘기는 계약
- recommendation read path도 legacy DB text `"false"` shape를 truthy blocker로 오판하지 않고 API read truth / review snapshot / downstream normalization에 같은 canonical false를 넘기는 계약
- editing session 생성 read path도 legacy segment row의 `review_required="false"` shape를 truthy review blocker로 오판하지 않고 session segment / preflight targeted segment에 같은 canonical false를 넘기는 계약
- segment analysis 저장 write path도 incoming segment의 `review_required="false"` shape를 truthy review-required로 굳히지 않고 persisted segment row / editing session / preflight targeted segment에 같은 canonical false를 넘기는 계약
- timeline/review response read path도 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` shape를 truthy recommendation state로 오판하지 않고 API response / review snapshot / partial regeneration result에 같은 canonical false를 넘기는 계약
- review recommendation rollback persistence도 downstream failure 후 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` shape를 truthy DB row로 되돌리지 않고 canonical false로 복구하는 계약
- preview renderer의 TTS applied recommendation read path도 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` shape를 truthy blocker로 오판하지 않고 selected narration source를 유지하는 계약
- review snapshot fallback decision-state 유도도 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` shape를 pending blocker로 오판하지 않고 applied recommendation truth를 유지하는 계약
- review snapshot builder의 direct `timeline_pending_recommendations` override 입력도 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` shape를 pending blocker로 오판하지 않고 applied recommendation truth를 유지하는 계약
- review snapshot builder의 direct `timeline_applied_recommendations` override 입력도 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="true"` shape를 applied recommendation으로 오판하지 않고 pending blocker truth로 재분류하는 계약
- review snapshot API read path도 pending-like legacy recommendation이 stale하게 `applied_recommendations` bucket에 들어 있어도 pending blocker truth와 `review_status=blocked`를 유지하고 duplicate blocker를 만들지 않는 계약
- timeline API read path도 pending-like legacy recommendation이 stale하게 `applied_recommendations` bucket에 들어 있어도 pending blocker truth와 `review_status=blocked`를 유지하고 applied surface를 clean하게 정리하는 계약
- timeline API read path도 unknown / non-blocking `applied_recommendations` stale entry를 canonical supported recommendation type이 아니면 applied surface에 남기지 않고 clean하게 정리하는 계약
- timeline persistence initial review state도 pending-like legacy recommendation이 stale하게 `applied_recommendations` bucket에 들어 있어도 `draft`로 저장하지 않고 `blocked` truth를 유지하는 계약
- timeline persistence initial review state도 unknown / non-blocking `pending_recommendations` shape 하나만으로 `blocked`를 저장하지 않고 canonical blocking pending recommendation이 없으면 `draft` truth를 유지하는 계약
- timeline persistence initial review state도 stale non-list / non-blocking `review_flags` shape 하나만으로 `blocked`를 저장하지 않고 canonical blocking review flag가 없으면 `draft` truth를 유지하는 계약
- timeline persistence initial review state도 mixed-case stale `review_flags.code` blocker가 남아 있으면 canonical lowercase code 기준으로 `blocked` truth를 유지하는 계약
- review snapshot direct helper도 pending override나 blocker flag가 존재하면 persisted approved status를 그대로 우선하지 않고 `review_status=blocked` truth를 유지하는 계약
- review snapshot direct helper도 unknown / non-blocking `timeline_review_flags` shape 하나만으로 persisted approved status를 `blocked`로 다시 뒤집지 않고 canonical blocking review flag가 없으면 approved truth를 유지하는 계약
- review snapshot direct helper도 mixed-case stale `timeline_review_flags.code` blocker를 raw casing 그대로 남기지 않고 canonical lowercase code / trimmed segment / default message surface로 정리하면서 `review_status=blocked` truth를 유지하는 계약
- review snapshot direct helper도 unknown / non-blocking `timeline_pending_recommendations` shape 하나만으로 persisted approved status를 `blocked`로 다시 뒤집지 않고 canonical blocking pending recommendation이 없으면 approved truth를 유지하는 계약
- review snapshot direct helper도 unknown / non-blocking `timeline_pending_recommendations` shape를 `pending_recommendations` surface에 blocker처럼 남기지 않고 canonical blocking pending recommendation만 surface에 유지하는 계약
- review snapshot direct helper도 inline `recommendation_type`가 빠진 direct recommendation 입력이면 persisted recommendation row에서 유일하게 매칭되는 canonical type을 복원해 applied/pending split truth를 유지하는 계약
- review snapshot direct helper도 unknown / non-blocking `timeline_applied_recommendations` stale entry를 canonical supported recommendation type이 아니면 applied surface에 남기지 않고 clean하게 정리하는 계약
- review snapshot helper/store import 경로도 `videobox_core_engine.provider_trace` read 때문에 package-level eager import cycle에 걸리지 않고 direct store/timeline helper tests를 계속 수집할 수 있는 계약
- timeline builder도 unknown / non-blocking recommendation stale entry를 canonical supported recommendation type이 아니면 applied/pending surface와 review flag flow에 반입하지 않고 clean하게 정리하는 계약
- timeline builder의 review snapshot direct dict 입력면도 unknown / non-blocking recommendation stale entry를 canonical supported recommendation type이 아니면 applied/pending surface에 반입하지 않고 clean하게 정리하는 계약
- timeline builder의 review snapshot direct dict 입력면도 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` shape를 pending blocker로 오판하지 않고 applied recommendation truth를 유지하는 계약
- review guidance prompt의 segment attention 계산도 legacy segment payload의 `review_required="false"` shape를 attention-required segment로 오판하지 않고 실제 review-required segment만 포함하는 계약
- partial regeneration preflight는 editing session 내부에 같은 `segment_id`가 중복 저장된 stale shape여도 targeted segment preview에서 first-seen segment를 유지하고 뒤의 stale duplicate가 canonical 값을 덮어쓰지 않는 계약
- partial regeneration preflight targeted-segment helper도 request `segment_ids`에 whitespace가 섞인 stale shape여도 canonical trimmed segment id 기준으로 session segment를 매칭하고 response surface에도 trimmed segment id를 유지하는 계약
- partial regeneration preflight prediction helper도 targeted segment payload의 legacy `review_required="false"` shape를 raw truthiness blocker로 오판하지 않고 canonical false 기준으로 `draft` prediction을 유지하는 계약
- partial regeneration preflight도 source timeline의 `pending_recommendations`에 `decision_state=approved/rejected` stale entry가 남아 있어도 unresolved blocker prediction으로 오판하지 않고 `draft` prediction을 유지하는 계약
- partial regeneration preflight도 source timeline의 `pending_recommendations`에 `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like entry가 `decision_state` 없이 남아 있어도 unresolved blocker prediction으로 오판하지 않고 `draft` prediction을 유지하는 계약
- partial regeneration preflight도 source timeline의 `applied_recommendations`에 `auto_apply_allowed="false"` / `review_required="true"` pending-like legacy entry가 잘못 들어 있어도 unresolved blocker prediction으로 복원해 `blocked` prediction을 유지하는 계약
- partial regeneration preflight도 source timeline의 `pending_recommendations`에 legacy/mixed-case `recommendation_type` blocker가 남아 있어도 canonical lowercase type 기준으로 unresolved blocker prediction을 유지해 `blocked` prediction truth를 잃지 않는 계약
- partial regeneration preflight도 source timeline의 stale mixed-case `review_flags.code` blocker가 남아 있어도 canonical lowercase code 기준으로 unresolved blocker prediction을 유지해 `blocked` prediction truth를 잃지 않는 계약
- partial regeneration runtime의 source segment lookup helper도 persisted source segment row의 `segment_id`에 whitespace가 섞인 stale shape여도 clip/timeline 쪽 canonical trimmed id 기준으로 매칭해 runtime refresh 대상 segment truth를 유지하는 계약
- partial regeneration candidate timeline도 provider-trace audit의 `timeline_id + include_upstream=true` filter에서 source lineage를 잃지 않고 segment analysis / recommendation upstream entry를 같이 보여주는 계약
- partial regeneration candidate timeline의 provider-trace `review_guidance` audit entry도 source job truth를 잃지 않고 `partial_regeneration_job_*`에 연결되는 계약
- partial regeneration candidate timeline의 provider-trace `review_guidance` audit entry도 `partial_regeneration_job_*`의 job type truth를 유지하는 계약
- partial regeneration candidate timeline의 provider-trace `review_guidance_attempt` audit entry도 `partial_regeneration_job_*`의 job type / job id / source job id truth를 유지하는 계약
- partial regeneration candidate timeline의 provider-trace `review_guidance_attempt` audit entry도 `partial_regeneration_job_*`의 `finished_at` truth를 유지하는 계약
- partial regeneration result read path도 applied recommendation의 `provider_trace`가 빠진 legacy shape를 그대로 API validation error로 흘리지 않고 fallback trace를 채운 canonical response로 유지하는 계약
- review snapshot read path도 persisted `operator_guidance`의 `provider_trace`가 빠진 legacy shape를 그대로 API validation error로 흘리지 않고 guidance-specific fallback trace를 채운 canonical response로 유지하는 계약
- partial regeneration candidate timeline의 provider-trace `subtitle_render` audit entry도 persisted subtitle artifact의 `created_at` truth를 유지하는 계약
- partial regeneration candidate timeline의 provider-trace `preview_render` audit entry도 persisted preview artifact의 `created_at` truth를 유지하는 계약
- partial regeneration candidate timeline의 provider-trace `capcut_export` audit entry도 persisted export artifact의 `created_at` truth를 유지하는 계약
- partial regeneration candidate timeline filter도 approval 없이 막힌 failed `preview_render` output job을 source job / candidate timeline truth와 함께 계속 보여주는 계약
- partial regeneration candidate timeline filter도 approval 없이 막힌 failed `capcut_export` output job을 source job / candidate timeline truth와 함께 계속 보여주는 계약
- partial regeneration candidate timeline filter도 approval 없이 막힌 failed `subtitle_render` output job을 source job / candidate timeline truth와 함께 계속 보여주는 계약
- partial regeneration runtime도 preflight와 마찬가지로 nested dict `target_segment_id`가 섞인 stale source `pending_recommendations`를 blocker recommendation으로 복원하지 않고 clean scope rerun result의 `review_status/pending_recommendations/review_flags`를 `draft/[]/[]`로 유지하는 계약
- partial regeneration runtime도 preflight와 마찬가지로 nested dict `segment_id`가 섞인 stale source `review_flags`를 blocker review flag로 복원하지 않고 clean scope rerun result의 `review_status/review_flags/pending_recommendations`를 `draft/[]/[]`로 유지하는 계약
- partial regeneration runtime도 preflight와 마찬가지로 valid source `review_flags.code/segment_id` blocker를 candidate timeline 결과에 복원해 clean scope가 아니면 `review_status=blocked`와 canonical review flag message를 유지하는 계약
- partial regeneration runtime도 preflight와 마찬가지로 mixed-case stale source `review_flags.code` blocker를 candidate timeline 결과에 복원할 때 canonical lowercase code 기준으로 `review_status=blocked`와 review flag surface truth를 유지하는 계약
- partial regeneration runtime도 preflight와 마찬가지로 valid source `pending_recommendations` blocker를 candidate timeline 결과에 복원할 때 missing `provider_trace`를 default fallback trace로 canonicalize해 result API validation error 없이 `review_status=blocked`와 blocker detail을 유지하는 계약
- partial regeneration runtime도 source timeline의 duplicate `pending_recommendations`가 legacy/mixed-case `recommendation_type` 차이만 있는 stale shape여도 canonical lowercase type 기준으로 dedupe해 blocker detail과 `review_status=blocked` truth를 한 번만 유지하는 계약

현재 확인된 검증 기준:

- frontend `src/app.test.tsx` 전체 `66 passed`
- helper `frontend-focused` gate `2 passed`
- review-action backend focused slice `6 passed`
- current-focused helper backend output-gating slice `24 passed`
- current-focused helper backend preflight slice `58 passed`
- current-focused helper frontend preflight slice `25 passed`
- speed-up helper `current-focused-parallel`
  - backend output-gating `24 passed`
  - backend preflight `58 passed`
  - frontend preflight `25 passed`
- Task 2 candidate timeline exact regression `1 passed`
- Task 2 frontend candidate routing exact regression `1 passed`
- Task 2 real-project clean happy-path smoke
  - review snapshot `draft`
  - editing session mutation 1회
  - preflight `draft`
  - partial regeneration candidate `partial_regeneration_job_006`
  - candidate review snapshot 조회 성공
  - candidate approve 성공
  - subtitle / preview / CapCut export 성공
- partial regeneration start response prediction symmetry regressions
  - clean scope start prediction `1 passed`
  - blocked scope start prediction `1 passed`
- partial regeneration candidate provider-trace upstream audit regression
  - `1 passed`
- partial regeneration candidate provider-trace review guidance job lineage regression
  - `1 passed`
- partial regeneration candidate provider-trace review guidance attempt job truth regression
  - `1 passed`
- partial regeneration candidate provider-trace review guidance attempt finished_at regression
  - `1 passed`
- partial regeneration candidate provider-trace subtitle_render created_at regression
  - `1 passed`
- partial regeneration candidate provider-trace preview_render created_at regression
  - `1 passed`
- partial regeneration candidate provider-trace capcut_export created_at regression
  - `1 passed`
- partial regeneration candidate failed preview_render audit filter regression
  - `1 passed`
- partial regeneration candidate failed capcut_export audit filter regression
  - `1 passed`
- partial regeneration candidate failed subtitle_render audit filter regression
  - `1 passed`
- approved timeline stale pending decision-state output gating regression
  - `1 passed`
- output gating legacy applied-like pending recommendation regression
  - `1 passed`
- partial regeneration preflight stale pending decision-state prediction regression
  - `1 passed`
- timeline builder string false recommendation review_required regression
  - `1 passed`
- recommendation store string false review_required regression
  - `1 passed`
- recommendation read path legacy string false regression
  - `1 passed`
- editing session legacy string false segment review_required regression
  - `1 passed`
- segment analysis write path string false segment review_required regression
  - `1 passed`
- timeline API legacy string false pending recommendation response regression
  - `1 passed`
- approve rollback legacy string false recommendation fields regression
  - `1 passed`
- preview renderer string false TTS recommendation review_required regression
  - `1 passed`
- review snapshot fallback legacy string false recommendation decision-state regression
  - `1 passed`
- review snapshot pending override legacy applied-like recommendation regression
  - `1 passed`
- review snapshot applied override legacy pending-like recommendation regression
  - `1 passed`
- review snapshot API misbucketed applied pending-like recommendation regression
  - `1 passed`
- timeline API misbucketed applied pending-like recommendation regression
  - `1 passed`
- timeline persistence misbucketed applied pending-like recommendation regression
  - `1 passed`
- timeline persistence stale non-list review flags initial status regression
  - `1 passed`
- timeline persistence unknown pending recommendation initial status regression
  - `1 passed`
- timeline API unknown applied recommendation surface regression
  - `1 passed`
- review snapshot helper unknown applied recommendation surface regression
  - `1 passed`
- timeline builder unknown applied recommendation surface regression
  - `1 passed`
- timeline builder review snapshot unknown applied recommendation surface regression
  - `1 passed`
- partial regeneration result applied recommendation default provider trace regression
  - `1 passed`
- review snapshot persisted operator guidance default provider trace regression
  - `1 passed`
- review snapshot approve trimmed target narration clip segment id regression
  - `1 passed`
- approve trimmed review flag segment id regression
  - `1 passed`
- approve trimmed review flag code regression
  - `1 passed`
- approve trimmed recommendation id regression
  - `1 passed`
- approve trimmed recommendation decision key regression
  - `1 passed`
- approve trimmed persisted applied recommendation id regression
  - `1 passed`
- approve trimmed target segment id blocker cleanup regression
  - `1 passed`
- approve rollback raw persisted timeline regression
  - `1 passed`
- approve persists remaining segment review-required blocker regression
  - `1 passed`
- review snapshot split without inline recommendation type regression
  - `1 passed`
- review timeline import-cycle collection regression
  - `1 passed`
- review snapshot approve trimmed recommendation type regression
  - `1 passed`
- review snapshot helper persisted-approved pending-override status regression
  - `1 passed`
- review snapshot helper unknown review flag approved-status regression
  - `1 passed`
- review snapshot helper unknown pending recommendation approved-status regression
  - `1 passed`
- review snapshot helper unknown pending recommendation surface regression
  - `1 passed`
- timeline builder review snapshot legacy string false recommendation fields regression
  - `1 passed`
- review guidance string false segment review_required regression
  - `1 passed`
- preflight legacy applied-like pending recommendation prediction regression
  - `1 passed`
- preflight misbucketed applied pending-like recommendation regression
  - `1 passed`
- provider-trace audit focused slice `39 passed`
- helper backend preflight slice `57 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- full backend regression `346 passed`
- frontend build 성공

이 체크포인트 기준으로 review-action placeholder 단계는 이미 지난 상태다.
따라서 이후 작업 우선순위는 review-action 연결 자체가 아니라, 더 상위 출력/편집 흐름 고도화 쪽으로 넘어가야 한다.

## 13. 다음 실제 작업

### 2026-07-11 기준

production-readiness blocker slice 1의 9개 Task는 구현·회귀·600초 smoke·SSOT 갱신까지 완료했다. 다음 goal은 새 기능을 넓히기보다 아래 중 하나를 좁게 선택한다.

1. 실제 사용자 음성 clone TTS 품질과 긴 영상 발화/무음 QA를 별도 provider acceptance 기준으로 고정한다.
2. 효과음 추천·선택·output materialization을 BGM과 같은 real-asset only 계약으로 구현한다.
3. 10분 이상 실제 프로젝트 3건의 수동 CapCut open/edit/export UX 검증을 수행하고 생성 source 경로, overlay layout, Korean typography를 점검한다.

### 2026-07-12 SFX real-asset acceptance 완료

효과음 slice는 실제 등록 asset이 없는 추천을 timeline에 넣지 않고, 편집 세션의 실제 SFX 선택만 partial regeneration에서 `sfx_review_required` 검수 대상으로 만든다. 개별 승인 뒤 candidate partial timeline과 원본 timeline 저장본을 함께 갱신하여 SFX track이 FFmpeg final MP4 및 real CapCut draft에 유지된다. 웹 편집 화면은 효과음 asset ID 저장·해제와 새로고침 복구를 지원한다.

- 검증: frontend 83 passed/build success, backend Python 3.12 632 passed (API 388 + 기타 244 분할 실행), 600초 Korean smoke 12 checks true.
- smoke final MP4 SHA-256: `036bc6ccfbcd5aba814e44aceb9b654f41ead6c9613d9ebfd4eb2dc8f672a93e`.
- 전체 milestone: 39개 중 38 완료, 1 부분. strict 97.4%, partial=0.5 weighted 98.7%, weighted remaining 1.3%.
- 남은 부분은 실제 사용자 녹음 human listening approval과 다중 실제 프로젝트 CapCut UX QA다.

### 2026-07-12 개인 음성 파일 입력 readiness 완료

웹 설정 화면에서 WAV/MP3/M4A/WebM/Ogg/FLAC 음성 파일을 선택해 multipart upload로 등록할 수 있다. 서버는 128 MiB 상한과 1 MiB chunk staging을 적용하고, 등록 뒤 임시 파일을 제거한다. 기존 직접 경로 등록은 호환 경로로 남기며, 최근 등록 voice sample asset은 새로고침 후 목록 API에서 복원되어 TTS candidate 생성에 다시 사용된다. microphone 자동 녹음은 범위 밖이다.

- 검증: frontend 86 passed/build success, backend Python 3.12 633 passed (API 389 + 기타 244 분할 실행), 600초 Korean smoke 13 checks true.
- 전체 milestone: 39개 중 38 완료, 1 부분. strict 97.4%, weighted 98.7%, weighted remaining 1.3%로 유지한다. 실제 사용자 녹음의 human listening approval과 다중 프로젝트 CapCut UX QA는 아직 사람이 수행해야 한다.

### 2026-07-12 개인 음성 TTS 청취 승인 게이트 완료

- 기술 검증을 통과한 `tts_candidate_*`는 SQLite의 `operator_review_status`가 `approved`일 때만 개인 음성 나레이션 대체에 사용할 수 있다. pending/rejected 후보는 기존 나레이션을 유지한다.
- UI에서 재생 후 청취 승인/거부를 저장하며, 새로고침 뒤에도 후보 상태를 다시 읽고 복원한다. 승인 전 후보 선택은 비활성화된다.
- legacy/imported 일반 TTS 교체는 개인 음성 후보가 아니므로 기존 편집 호환성을 유지한다.
- 실제 600초 한국어 smoke에서 `tts_candidate_listening_approved`, SRT, FFmpeg MP4, real CapCut draft 반영을 확인했다.
- 전체 milestone 진행률은 38/39 완료, 1 부분으로 유지한다: strict 97.4%, weighted 98.7%, remaining 1.3%. 남은 것은 실제 사용자가 자신의 음성을 듣고 품질을 판정하는 운영 QA와 다중 실제 프로젝트 CapCut UX QA다.

이하 기존 next-task 목록은 historical reference다.

현재 기준 다음 실제 작업은 아래 순서로 재고정한다.

1. final closeout 본문과 final closeout commit 단위를 authoritative 상태로 유지한다
2. historical 문서와 역할 종료 메모는 기본적으로 historical reference로 유지하고, 명백한 dead artifact가 확인될 때만 별도 삭제 판단을 연다
3. broad 재검증은 마지막 코드 변경 뒤 추가 코드 수정이 없을 때는 기본적으로 재실행하지 않고, 실제 코드 변경이 다시 생길 때만 재판단한다
6. 최종 마감 문서는 최소한 아래 블록을 포함한다
   - 현재 authoritative 상태 요약
   - automatic baseline 요약
   - representative Phase B evidence 요약
   - QA/system verification judgment
   - historical 문서/찌꺼기 정리 판단
   - 남기지 않은 것과 그 이유
   - final commit/push 상태

정리 마감 실행 기준:

- 남은 안정화 slice와 전체 마감 작업의 분리 계획은 `docs/superpowers/plans/2026-07-05-finish-stabilization-and-closeout-plan.ko.md`를 따른다
- 현재 worktree는 `current-focused-parallel green + frontend build green + full backend regression green + representative Phase B evidence 확보`까지 온 상태이므로, 새 stale-shape slice를 더 여는 것보다 `문서 최신화 -> 정리 리팩터링 판단 -> 찌꺼기 파일 정리 -> 최종 closeout` 순서가 우선이다

2026-07-04 최신 누적 메모:

- output operator copy와 review guidance가 각각 들고 있던 `canonical_recommendation_type`, `canonical_decision_state`, `canonical_review_flag_message` helper도 공통 모듈로 묶어, prompt family의 canonical string 규칙이 파일별로 다시 갈라지지 않도록 정리했다
- output operator copy와 review guidance 안에 남아 있던 canonical string helper thin wrapper도 제거해, prompt family가 공통 canonical helper를 바로 참조하도록 정리했다
- output operator copy와 review guidance가 review flag identity / prompt row 정리 로직도 공통 helper로 공유하게 맞춰, valid blocker code와 default blocker message 기준이 파일별로 다시 갈라지지 않도록 정리했다
- output operator copy와 review guidance가 review flag code canonicalizer local helper도 공통 모듈로 다시 모아, mixed-case review flag code 기준이 파일별로 다시 갈라지지 않도록 정리했다
- local pipeline에서 `_normalize_runtime_boolish(...)`를 한 번 더 감싸기만 하던 `review_required` dead wrapper도 제거해, output gating과 partial regeneration read-path이 같은 boolish helper를 직접 공유하도록 정리했다
- preview/output/runtime/TTS apply가 각각 들고 있던 track type canonicalizer와 valid track set도 공통 helper로 다시 모아, mixed-case narration track type과 unknown track type 기준이 파일별로 다시 갈라지지 않도록 정리했다
- prompt/output/runtime/timeline/TTS approval이 각각 들고 있던 recommendation type canonicalizer와 valid recommendation set도 공통 helper로 다시 모아, mixed-case recommendation type과 valid recommendation set 기준이 파일별로 다시 갈라지지 않도록 정리했다
- prompt/output/runtime/review-action이 각각 들고 있던 review-flag code canonicalizer와 valid blocker code set도 공통 helper로 다시 모아, mixed-case review-flag code와 valid blocker code 기준이 파일별로 다시 갈라지지 않도록 정리했다
- preview/output/runtime/review-guidance가 각각 들고 있던 review-status canonicalizer도 공통 helper로 다시 모아, mixed-case review-status surface와 blocked/draft/approved 판단 기준이 파일별로 다시 갈라지지 않도록 정리했다
- preview/review-guidance/runtime이 각각 들고 있던 strict boolish normalization helper도 공통 모듈로 다시 모아, string false와 stale non-bool review_required 해석 기준이 파일별로 다시 갈라지지 않도록 정리했다
- preview/review-action/runtime/timeline이 각각 들고 있던 source-uri trim helper도 공통 모듈로 다시 모아, selected_asset_uri와 narration source surface trim 기준이 파일별로 다시 갈라지지 않도록 정리했다
- prompt/guidance/runtime이 각각 들고 있던 기본 operator review 안내 문구 fallback도 공통 모듈로 다시 모아, default review flag message와 pending recommendation reason 기준이 파일별로 다시 갈라지지 않도록 정리했다
- broader 재검증에서 드러난 nested `target_segment_id` stale pending recommendation runtime 회귀 1개도 복구해, partial regeneration read-path이 string 타입 target identity만 유효한 pending recommendation으로 인정하도록 다시 맞췄다
- broad 회귀 복구 직후 representative Phase B evidence도 다시 수집해, happy-path, frontend operator flow, provider trace failed-output/fallback 근거가 최신 baseline 위에서 모두 green인지 다시 확인했다
- 따라서 현재 worktree의 next step은 추가 cleanup보다 `final closeout 문서화 -> historical 정리 판단 -> 최종 마감 커밋 설계` 쪽이 더 맞다
- final closeout 단계에서는 historical 문서와 역할 종료 메모를 기본적으로 삭제하지 않고, authoritative 포인터에서 밀려난 기록이라는 역할을 먼저 명시하는 쪽을 기본값으로 둔다
- final closeout 본문은 새 cleanup 탐색이 아니라, 이미 확보한 latest automatic baseline + representative evidence를 authoritative 한 장으로 묶는 역할을 맡는다
- final closeout 본문을 실제로 작성한 뒤에는, 남은 일은 새 기능 구현이 아니라 final commit 단위 설계와 historical retention judgment를 마감 순서에 맞게 닫는 쪽으로 더 좁혀진다
- 현재 브랜치에서는 마지막 코드 변경이 `56005dc`에서 끝났고, 그 뒤 커밋은 final closeout 문서화만 다뤘으므로 broad 재검증을 다시 돌릴 직접 사유는 현재 없다
- scoped 정리 점검에서도 즉시 삭제해야 할 임시/실험/찌꺼기 파일 후보는 확인되지 않았으므로, 현재 단계의 required work는 사실상 final closeout과 handoff judgment까지 닫힌 상태로 본다
- remote-synced handoff 메모까지 저장된 현재 시점에서는, 이 구현 계획 기준 required work는 모두 닫힌 상태로 유지한다
- output operator copy와 review guidance가 각각 들고 있던 `VALID_PROMPT_RECOMMENDATION_TYPES`와 `VALID_PROMPT_REVIEW_FLAG_CODES`도 공통 모듈로 묶어, prompt family의 valid-set 기준이 파일별로 다시 갈라지지 않도록 정리했다
- output operator copy와 review guidance가 각각 들고 있던 canonical pending recommendation identity helper도 공통 모듈로 묶어, recommendation_id / target_segment_id / recommendation_type canonical identity 규칙이 파일별로 다시 갈라지지 않도록 정리했다
- output operator copy와 review guidance가 각각 들고 있던 pending recommendation row 정규화 helper를 공통 모듈로 묶어, selected_asset_uri / identity / reason / decision_state canonicalization 규칙이 파일별로 다시 갈라지지 않도록 정리했다
- review guidance prompt 안에서도 pending recommendation row 정규화 중복을 helper 1개로 공통화해, selected_asset_uri / identity / reason / decision_state canonicalization drift 없이 blocked guidance prompt surface를 같은 기준으로 유지하도록 정리했다
- output operator copy prompt 안에서 pending recommendation row 정규화 중복을 helper 1개로 공통화해, selected_asset_uri / identity / reason / decision_state canonicalization drift 없이 prompt surface를 같은 기준으로 유지하도록 정리했다
- partial regeneration/source merge와 output blocker read-path에서 쓰는 pending recommendation dedupe 기준을 `local_pipeline` 내부 helper 1개로 공통화해, mixed-case/trimmed recommendation identity key drift를 줄이되 동작은 바꾸지 않도록 정리했다
- output operator copy prompt도 non-list stale `tracks[].clips` 값을 실제 clip count처럼 세지 않고 건너뛰어, approved preview/export 경로가 valid track summary prompt surface만 유지하도록 정리했다
- preview renderer도 non-list stale `tracks[].clips` 값을 track summary나 narration source list로 순회하지 않고 건너뛰어, approved preview visible surface가 valid track summary/input만 유지하도록 정리했다
- preview renderer도 `tracks[].clips` list 안의 stale non-dict entry를 실제 clip처럼 세거나 narration source surface로 순회하지 않도록 정리해, approved preview visible surface가 canonical clip input만 유지하도록 맞췄다
- CapCut export adapter도 non-list stale `tracks[].clips` 값을 voiceover/video/audio segment source처럼 순회하지 않고 건너뛰어, approved export surface가 valid track input만 유지하도록 정리했다
- CapCut export adapter도 `tracks[].clips` list 안의 stale non-dict entry를 voiceover/video/audio segment source처럼 순회하지 않도록 정리해, approved export surface가 canonical clip input만 기준으로 manifest를 만들게 맞췄다
- subtitle render의 timeline segment read-path도 non-list stale `tracks[].clips` 값을 subtitle segment source처럼 순회하지 않고 건너뛰어, approved subtitle output이 valid track input만 기준으로 segment order를 잡도록 정리했다
- review approval의 TTS apply read-path도 stale non-dict `tracks` entry를 target narration track처럼 읽지 않고 건너뛰어, approved narration asset swap이 valid narration track input에만 적용되도록 정리했다
- review approval의 TTS apply read-path도 stale non-dict `clips` entry를 target narration clip처럼 읽지 않고 건너뛰어, approved narration asset swap이 valid narration clip input에만 적용되도록 정리했다
- review approval decision extraction read-path도 stale non-dict `pending_recommendations` entry를 valid recommendation row처럼 읽지 않고 건너뛰어, approved/rejected recommendation decision 추출이 valid recommendation input에만 적용되도록 정리했다
- review approval decision extraction read-path도 `recommendation_id`만 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation row처럼 승인하지 않고 건너뛰어, approved/rejected recommendation decision 추출이 canonical recommendation identity/type/segment를 가진 input에만 적용되도록 정리했다
- review approval decision extraction read-path도 unknown `recommendation_type`를 가진 stale `pending_recommendations` entry를 valid recommendation row처럼 승인하지 않고 건너뛰어, approved/rejected recommendation decision 추출이 supported recommendation type input에만 적용되도록 정리했다
- review guidance prompt도 stale non-dict `review_flags` entry를 raw dict 변환 예외로 터뜨리지 않고 건너뛰어, blocked review guidance surface가 valid blocker prompt input만 유지하도록 정리했다
- review guidance prompt도 `segment_id` 없이 남은 stale minimal-dict `review_flags` entry를 valid blocker prompt row처럼 노출하지 않고 건너뛰어, blocked review guidance surface가 canonical blocker identity와 supported code를 가진 input만 유지하도록 정리했다
- review guidance prompt도 stale non-dict `pending_recommendations` entry를 raw dict 변환 예외로 터뜨리지 않고 건너뛰어, blocked review guidance surface가 valid recommendation prompt input만 유지하도록 정리했다
- review guidance prompt도 `recommendation_id`만 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation prompt row처럼 노출하지 않고 건너뛰어, blocked review guidance surface가 canonical recommendation identity/type/segment를 가진 input만 유지하도록 정리했다
- output operator copy prompt도 `track_type` 없이 남은 stale minimal-dict `tracks` entry를 빈 track summary처럼 노출하지 않고 건너뛰어, approved preview/export 경로가 canonical track summary prompt surface만 유지하도록 정리했다
- output operator copy prompt도 stale non-dict `tracks` entry를 raw track summary 생성 예외로 터뜨리지 않고 건너뛰어, approved preview/export 경로가 valid track summary prompt surface만 유지하도록 정리했다
- output operator copy prompt도 `segment_id` 없이 남은 stale minimal-dict `review_flags` entry를 valid blocker처럼 노출하지 않고 건너뛰어, approved preview/export 경로가 canonical blocker identity를 가진 prompt surface만 유지하도록 정리했다
- output operator copy prompt도 `recommendation_id`나 `target_segment_id` 없이 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation처럼 노출하지 않고 건너뛰어, approved preview/export 경로가 canonical recommendation identity를 가진 prompt surface만 유지하도록 정리했다
- output operator copy prompt도 stale non-dict `pending_recommendations` entry를 raw dict 변환 예외로 터뜨리지 않고 건너뛰어, approved preview/export 경로가 valid recommendation prompt surface만 유지하도록 정리했다
- output operator copy prompt도 stale non-dict `review_flags` entry를 raw dict 변환 예외로 터뜨리지 않고 건너뛰어, approved preview/export 경로가 valid blocker prompt surface만 유지하도록 정리했다
- review snapshot의 blocked persisted operator guidance 재사용도 blocker surface 기반 hidden reuse key로 좁혀, legacy no-key guidance나 다른 blocker를 기준으로 저장된 stale guidance가 현재 `review_flags`/pending blocker truth를 덮어쓰지 않게 정리했다
- review snapshot의 blocked persisted operator guidance reuse key도 stale unknown/minimal `review_flags`/`pending_recommendations` dict를 blocker truth처럼 키에 섞지 않도록 정리해, 실제 blocker surface가 같은데도 guidance를 불필요하게 다시 생성하는 persistence mismatch를 줄였다
- review snapshot의 blocked persisted operator guidance reuse key도 `decision_state="approved"`이거나 `auto_apply_allowed=true` / `review_required=false`인 stale applied-like `pending_recommendations` entry를 hidden blocker key에 섞지 않도록 정리해, 현재 blocker surface와 무관한 stale pending metadata 때문에 guidance를 불필요하게 다시 생성하지 않게 맞췄다
- review snapshot의 blocked persisted operator guidance reuse key는 stale `review_status="blocked"`만 남고 실제 blocker surface가 비어 있으면 더 이상 빈 blocked key를 만들지 않도록 정리해, blocker가 없는 상태에서 예전 blocked guidance를 재사용하는 경로를 줄였다
- review snapshot의 blocked persisted operator guidance reuse key는 canonical blocker detail이 같은 duplicate `review_flags`/`pending_recommendations` entry를 한 번만 반영하도록 정리해, blocker truth는 같은데 중복 stale entry 때문에 guidance를 불필요하게 다시 생성하지 않게 맞췄다
- review snapshot의 blocked persisted operator guidance reuse key는 message 없는 valid `review_flags`도 canonical default blocker message 기준으로 정리해, API/read-path와 같은 blocker truth인데 raw 빈 message 때문에 guidance를 불필요하게 다시 생성하지 않게 맞췄다
- review snapshot의 blocked persisted operator guidance reuse key는 reason 없는 valid `pending_recommendations`도 canonical default blocker message 기준으로 정리해, API/read-path와 같은 blocker truth인데 raw 빈 reason 때문에 guidance를 불필요하게 다시 생성하지 않게 맞췄다
- review snapshot의 blocked persisted operator guidance persisted reuse key read-path도 legacy `_operator_guidance_reuse_key`에 공백이 섞인 stale 파일 shape를 trim 기준으로 정리해, blocker truth가 같은데 stored key whitespace 때문에 guidance를 불필요하게 다시 생성하지 않게 맞췄다
- recommendation/timeline/review snapshot API response normalization도 `payload.selected_asset_uri`의 whitespace stale shape를 trim 기준으로 정리해, TTS approval/output과 review/output read surface가 canonical selected asset uri 기준을 유지하게 맞췄다
- recommendation/timeline/review snapshot API response normalization도 `recommendation_type` 없는 stale `pending_recommendations`/`applied_recommendations` row를 valid recommendation처럼 surface하지 않고 건너뛰어, review/output read surface가 canonical recommendation identity/type/segment 기준만 유지하게 맞췄다
- preview renderer의 approved TTS narration source surface도 whitespace stale `asset_uri`를 trim 기준으로 정리해, TTS approval/output preview visible surface가 canonical selected narration uri 기준을 유지하게 맞췄다
- CapCut export adapter의 approved TTS voiceover `source_uri` surface도 whitespace stale `asset_uri`를 trim 기준으로 정리해, TTS approval/output export payload surface가 canonical selected narration uri 기준을 유지하게 맞췄다
- CapCut export adapter의 B-roll `source_uri` surface도 whitespace stale `asset_uri`를 trim 기준으로 정리해, export payload surface가 canonical asset uri 기준을 유지하게 맞췄다
- CapCut export adapter의 subtitle `source_uri` surface도 whitespace stale subtitle file uri를 trim 기준으로 정리해, export payload surface가 canonical subtitle uri 기준을 유지하게 맞췄다
- CapCut export adapter의 top-level `subtitle_file_uri` surface도 whitespace stale subtitle file uri를 trim 기준으로 정리해, export payload metadata surface가 canonical subtitle uri 기준을 유지하게 맞췄다
- CapCut export adapter의 overlay `track_name` / `overlay_type` surface도 whitespace stale overlay type을 trim 기준으로 정리해, export payload text-track surface가 canonical overlay type 기준을 유지하게 맞췄다
- CapCut export adapter의 overlay `text` surface도 whitespace stale text를 trim 기준으로 정리해, export payload text-track surface가 canonical overlay copy 기준을 유지하게 맞췄다
- subtitle render의 timeline segment order read-path도 `track_type` 없는 stale minimal-dict `tracks` entry를 실제 subtitle source track처럼 읽지 않도록 정리해, approved subtitle output이 canonical track input만 기준으로 세그먼트 순서를 잡게 맞췄다
- subtitle render의 timeline segment order read-path도 supported set 밖의 stale unknown `track_type`를 subtitle source track처럼 읽지 않도록 정리해, approved subtitle output이 canonical runtime track type만 기준으로 세그먼트 순서를 잡게 맞췄다
- output operator copy prompt의 track summary도 supported set 밖의 stale unknown `track_type`를 valid runtime track summary처럼 노출하지 않도록 정리해, approved preview/export guidance가 canonical runtime track type만 기준으로 요약을 만들게 맞췄다
- preview renderer의 track summary / payload read-path도 supported set 밖의 stale unknown `track_type`를 valid runtime track surface처럼 노출하지 않도록 정리해, approved preview visible surface가 canonical runtime track type만 기준으로 요약을 만들게 맞췄다
- CapCut export adapter의 export payload / track read-path도 supported set 밖의 stale unknown `track_type`를 valid export track surface처럼 노출하지 않도록 정리해, approved export payload가 canonical runtime track type만 기준으로 manifest를 만들게 맞췄다
- partial regeneration `music_refresh`가 whitespace stale source `segment_id`를 가진 segment도 다시 선택하도록 `local_pipeline` source-segment match를 trim 기준으로 맞췄다
- 같은 slice에서 `timeline_builder` dict segment payload도 `segment_id`를 trim해 refreshed recommendation과 segment lookup이 서로 다른 id 기준으로 어긋나지 않게 정리했다
- partial regeneration `overlay_refresh`도 whitespace stale existing overlay `segment_id`를 targeted full refresh 범위에서 정확히 교체하도록 overlay segment match를 trim 기준으로 맞췄다
- partial regeneration `segment_refresh`도 whitespace stale source segment `segment_id`를 trimmed request/session id와 같은 기준으로 맞춰 caption/cut-action rerun이 정확히 적용되게 정리했다
- partial regeneration `segment_refresh`도 stale source `cleanup_decision`을 runtime cut-action canonical 값으로 정리해 caption-only rerun에서도 invalid cut state가 그대로 남지 않게 정리했다
- output gating / output readiness read path도 legacy `review_approvals.status=" APPROVED "` 같은 mixed-case stale shape를 canonical lowercase 승인 상태로 정리해 blocker가 없으면 preview/subtitle/export를 다시 막지 않게 정리했다
- review recommendation approve cleanup도 legacy mixed-case `review_flags.code=" BROLL_REVIEW_REQUIRED "` 같은 stale shape를 canonical lowercase code 기준으로 지워, 마지막 pending recommendation 승인 뒤 output blocker가 잘못 남지 않게 정리했다
- preview renderer의 `review_status` HTML surface도 legacy `" APPROVED "` 같은 mixed-case stale shape를 canonical lowercase 상태로 정리해 visible output surface가 output gating/readiness truth와 같은 기준을 유지하게 정리했다
- output operator copy builder의 prompt `review_status` surface도 legacy `" APPROVED "` 같은 mixed-case stale shape를 canonical lowercase 상태로 정리해 preview/export guidance prompt가 output gating/readiness truth와 같은 기준을 유지하게 정리했다
- heuristic/local review guidance도 legacy `" APPROVED "` 같은 mixed-case stale `review_status`를 canonical lowercase 승인 상태로 정리해 blocker가 없을 때 `승인 대기`가 아니라 approved output guidance truth를 유지하게 정리했다
- review snapshot의 persisted operator guidance 재사용 조건도 legacy `" APPROVED "` 같은 mixed-case stale `review_status`를 canonical lowercase 승인 상태로 비교해, 같은 승인 상태인데도 guidance를 불필요하게 다시 생성하지 않게 정리했다
- timeline builder의 applied recommendation surface도 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale `recommendation_type`를 canonical lowercase type으로 정리해 approved TTS read-path truth와 builder output surface가 같은 기준을 유지하게 정리했다
- preview renderer도 whitespace stale narration clip `segment_id`를 trimmed TTS recommendation과 같은 기준으로 맞춰 approved narration source가 preview에 정확히 반영되게 정리했다
- preview renderer의 narration sources HTML surface도 narration clip `segment_id`를 trim 기준으로 맞춰 approved TTS preview surface가 canonical segment id를 유지하게 정리했다
- CapCut export adapter도 whitespace stale narration clip `segment_id`를 trimmed TTS recommendation과 같은 기준으로 맞춰 approved narration source가 export에 정확히 반영되게 정리했다
- CapCut export adapter의 voiceover segment surface도 narration clip `segment_id`를 trim 기준으로 맞춰 export payload 자체가 canonical segment id를 유지하게 정리했다
- CapCut export adapter의 broll sequential-fill grouping도 `segment_id`를 trim 기준으로 맞춰 padded/raw id가 섞인 같은 세그먼트가 하나의 window로 유지되게 정리했다
- CapCut export adapter도 legacy `" NARRATION "` 같은 mixed-case stale `track_type`를 canonical lowercase track type으로 읽어 approved narration/TTS voiceover track을 놓치지 않게 정리했다
- preview renderer도 legacy `" NARRATION "` 같은 mixed-case stale `track_type`를 canonical lowercase track type으로 읽어 narration sources surface가 비지 않게 정리했다
- preview renderer의 track summary HTML surface도 legacy `" NARRATION "` 같은 mixed-case stale `track_type`를 canonical lowercase track type으로 정리해 visible output surface가 raw stale 값을 그대로 노출하지 않게 정리했다
- review recommendation approval mutation도 legacy `" NARRATION "` 같은 mixed-case stale `track_type`를 canonical lowercase track type으로 읽어 approved TTS narration clip 적용이 실패하지 않게 정리했다
- output operator copy builder의 prompt `track summary` surface도 legacy `" NARRATION "` 같은 mixed-case stale `track_type`를 canonical lowercase track type으로 정리해 preview/export guidance prompt가 preview/output visible surface와 같은 기준을 유지하게 정리했다
- review guidance prompt의 `Segments needing attention` surface도 whitespace stale `segment_id`를 trim 기준으로 정리해 operator guidance prompt가 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `Segments needing attention` 계산도 stale non-dict `segments` entry를 raw `.get(...)` 예외로 터뜨리지 않고 건너뛰어, blocked guidance prompt가 canonical segment input만 기준으로 attention surface를 만들게 정리했다
- review guidance prompt의 `pending_recommendations` surface도 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale `recommendation_type`를 canonical lowercase type으로 정리해 operator guidance prompt가 approved/read-path recommendation type 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.target_segment_id` surface도 whitespace stale `target_segment_id`를 trim 기준으로 정리해 operator guidance prompt가 TTS/output read-path의 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `review_flags.code` surface도 legacy `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale code를 canonical lowercase code로 정리해 operator guidance prompt가 review/output gating의 canonical review-flag 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `review_flags.segment_id` surface도 whitespace stale `segment_id`를 trim 기준으로 정리해 operator guidance prompt가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `review_flags.message` surface도 whitespace stale `message`를 trim 기준으로 정리해 operator guidance prompt가 API response 쪽 canonical blocker message 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 message 없는 `review_flags` surface도 canonical default blocker message를 채워 operator guidance prompt가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- heuristic/local review guidance fallback도 message 없는 valid `review_flags`를 generic blocker 문구로 뭉개지 않고 canonical default blocker message를 action item으로 surface해 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- heuristic/local review guidance fallback도 `reason` 없는 valid `pending_recommendations`를 generic blocker 문구로 뭉개지 않고 canonical default blocker message를 action item으로 surface해 review/output gating과 API response 쪽 default blocker reason 기준을 유지하게 정리했다
- heuristic/local review guidance fallback도 supported set 밖의 stale unknown `pending_recommendations.recommendation_type`를 실제 blocker처럼 취급하지 않도록 정리해, approved guidance truth가 junk pending input 때문에 다시 blocked로 뒤집히지 않게 맞췄다
- review guidance prompt의 `pending_recommendations.reason` surface도 whitespace stale `reason`을 trim 기준으로 정리해 operator guidance prompt가 API response 쪽 canonical recommendation reason 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 reason 없는 valid `pending_recommendations` surface도 canonical default blocker message를 채워 operator guidance prompt가 API response 및 heuristic fallback 쪽 default blocker reason 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.decision_state` surface도 legacy `" Approved "` 같은 mixed-case stale decision state를 canonical lowercase로 정리해 operator guidance prompt가 API response 쪽 canonical decision-state 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.selected_asset_id` surface도 whitespace stale asset id를 trim 기준으로 정리해 operator guidance prompt가 API response 쪽 canonical selected asset id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.recommendation_id` surface도 whitespace stale recommendation id를 trim 기준으로 정리해 operator guidance prompt가 approve/output 쪽 canonical recommendation identity 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.created_at` surface도 whitespace stale created_at 값을 trim 기준으로 정리해 operator guidance prompt가 approve/output 쪽 recommendation metadata truth와 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.payload.selected_asset_uri` surface도 whitespace stale asset uri를 trim 기준으로 정리해 operator guidance prompt가 TTS approval/output 쪽 canonical selected asset uri 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `Pending recommendation count`도 raw stale list 길이가 아니라 filtered canonical pending recommendation surface 기준으로 계산하도록 맞춰, unknown junk recommendation이 blocker count를 부풀리지 않게 정리했다
- heuristic/local review guidance도 `decision_state="approved"`이거나 `auto_apply_allowed=true` / `review_required=false`인 stale applied-like `pending_recommendations` entry를 실제 pending blocker처럼 취급하지 않도록 정리해, approved guidance truth가 output job/read truth와 같은 pending blocker 기준을 유지하게 정리했다
- review guidance / output operator copy의 canonical review-flag allowlist에도 `broll_review_required`를 포함하도록 맞춰, 실제 B-roll blocker가 approved guidance로 잘못 빠지지 않게 정리했다
- timeline summary의 `review_flag_count`도 raw stale list 길이가 아니라 canonical blocking review flag 기준으로 계산하도록 맞춰, unknown junk review flag가 persisted summary blocker count를 부풀리지 않게 정리했다
- timeline summary의 `pending_recommendation_count`도 raw stale list 길이가 아니라 canonical blocking pending recommendation 기준으로 계산하도록 맞춰, unknown junk recommendation이 persisted summary blocker count를 부풀리지 않게 정리했다
- timeline summary의 `track_count`도 raw stale list 길이가 아니라 canonical runtime `track_type` 기준으로 계산하도록 맞춰, unknown junk track이 persisted summary output count를 부풀리지 않게 정리했다
- timeline summary의 `applied_recommendation_count`도 raw stale list 길이가 아니라 canonical runtime recommendation type 기준으로 계산하도록 맞춰, unknown junk applied recommendation이 persisted summary output count를 부풀리지 않게 정리했다
- CapCut export metadata의 `track_count`도 raw stale list 길이가 아니라 canonical runtime `track_type` 기준으로 계산하도록 맞춰, unknown junk track이 persisted export metadata count를 부풀리지 않게 정리했다
- preview summary의 `clip_group_count`도 raw stale list 길이가 아니라 canonical runtime `track_type` 기준으로 계산하도록 맞춰, unknown junk clip group이 persisted preview summary count를 부풀리지 않게 정리했다
- output operator copy prompt의 `pending_recommendations.recommendation_type` surface도 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale type을 canonical lowercase type으로 정리해 preview/export guidance prompt가 review guidance 및 output truth와 같은 recommendation type 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.target_segment_id` surface도 whitespace stale segment id를 trim 기준으로 정리해 preview/export guidance prompt가 review guidance 및 output truth와 같은 canonical segment id 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.reason` surface도 whitespace stale reason을 trim 기준으로 정리해 preview/export guidance prompt가 review guidance 및 output truth와 같은 canonical recommendation reason 기준을 유지하게 정리했다
- output operator copy prompt의 reason 없는 valid `pending_recommendations` surface도 canonical default blocker message를 채워 preview/export guidance prompt가 review guidance 및 output truth와 같은 default blocker reason 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.selected_asset_id` surface도 whitespace stale asset id를 trim 기준으로 정리해 preview/export guidance prompt가 review guidance 및 TTS/output truth와 같은 canonical selected asset id 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.recommendation_id` surface도 whitespace stale recommendation id를 trim 기준으로 정리해 preview/export guidance prompt가 approve/output 쪽 canonical recommendation identity 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.created_at` surface도 whitespace stale created_at 값을 trim 기준으로 정리해 preview/export guidance prompt가 approve/output 쪽 recommendation metadata truth와 같은 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.payload.selected_asset_uri` surface도 whitespace stale asset uri를 trim 기준으로 정리해 preview/export guidance prompt가 TTS approval/output 쪽 canonical selected asset uri 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.decision_state` surface도 legacy `" Approved "` 같은 mixed-case stale decision state를 canonical lowercase로 정리해 preview/export guidance prompt가 approve/read-path 쪽 canonical decision-state 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt도 `decision_state="approved"`이거나 `auto_apply_allowed=true` / `review_required=false`인 stale applied-like `pending_recommendations` entry를 pending blocker surface처럼 노출하지 않도록 정리해, approved output guidance prompt가 output job/read truth와 같은 pending blocker 기준을 유지하게 정리했다
- output operator copy prompt의 `review_flags.code` surface도 legacy `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale code를 canonical lowercase로 정리해 preview/export guidance prompt가 review/output gating의 canonical review-flag 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 `review_flags.segment_id` surface도 whitespace stale `segment_id`를 trim 기준으로 정리해 preview/export guidance prompt가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 `review_flags.message` surface도 whitespace stale `message`를 trim 기준으로 정리해 preview/export guidance prompt가 review/output gating과 API response 쪽 canonical blocker message 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 message 없는 `review_flags` surface도 canonical default blocker message를 채워 preview/export guidance prompt가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- output operator copy prompt의 `track_summary.clip_count` surface도 `tracks[].clips` 안의 stale non-dict entry를 실제 clip처럼 세지 않도록 정리해, approved preview/export guidance가 canonical clip input만 기준으로 summary를 만들게 맞췄다

단, 2026-07-03 기준 `2일 내 1차 데모 완성` 실행 레일은 위 장기 우선순위를 그대로 넓게 다 가져가지 않는다.
즉시 실행 기준은 `docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md`를 따른다.
그 문서 기준 기본 범위는 아래 3개뿐이다.

1. approved TTS persisted truth gap 1개 확인 완료
2. 실제 프로젝트 1개 happy-path smoke 완료
3. evidence / closeout / SSOT freeze 완료

이제 이 2일 실행 레일의 기본 범위는 모두 닫혔다.
다음 실제 작업은 다시 장기 우선순위로 돌아가되, 가장 작은 남은 경계부터 재선정한다.

중요:

- 오픈소스 편집기 셸 반입은 현재도 핵심 우선순위가 아니다
- 대시보드 화이트톤 리디자인은 post-MVP polish로 보류하고, 현재는 기능 완결과 검증 속도를 우선한다
- 저장된 컬러 방향은 `white / gray / light orange` 기반의 밝은 무채색 톤으로 유지하고, 실제 적용은 MVP 사용 피드백 이후 최소 범위로 진행한다
- 후속 적용 순서는 `token/semantic color 정리 -> layout contrast 재점검 -> component skin 최소 치환`으로 제한해, MVP 기능 검증이 끝나기 전에는 실제 UI 리디자인 작업을 시작하지 않는다
- CapCut export와 review/output 계약은 계속 유지한다
- TTS, editing session, review 상태 계약은 서로 따로 놀지 않도록 같은 증거 기준으로 검증해야 한다
- 단, 최종 운영 마감 점검에서는 focused와 representative smoke가 green이어도 broader full backend regression이 red면 운영 완료로 닫지 않는다
- 현재 최신 운영 점검 결과는 `full-suite only red 1개`가 남아 있으므로, 다음 실제 작업은 새 기능 추가가 아니라 그 경계 1개를 좁히는 안정화 복귀다
- 그 blocker를 복구한 뒤 focused와 broader가 모두 다시 green으로 닫혔으므로, 현재 구현 계획 기준 required work는 운영 마감 단계까지 모두 완료된 상태로 본다

## 14. 2026-07-12 personal voice TTS acceptance closeout

- 개인 음성 TTS 후보는 무음, 손상, target duration 불일치를 기술적으로 거부하고 `pending operator review`를 별도 유지한다.
- provider 실패는 generic TTS 자동 대체가 아니라 원본 narration 유지 오류로 처리한다.
- BrollBox `execution/tts_engine.py`는 environment-global 및 gTTS fallback 결합 때문에 `rewrite`, Voicebox는 `reference only`로 확정한다.
- deterministic Korean WAV provider와 실제 FFmpeg/real CapCut adapter를 이용한 600초 smoke가 TTS 후보, timeline approval, SRT, MP4, CapCut draft를 확인한다.

## 15. 2026-07-12 detailed editor upgrade closeout

- `docs/superpowers/plans/2026-07-12-detailed-editor-upgrade-implementation.md`의 Task 1–5를 완료했다. 상세 편집기 계획 진행률은 strict 100%, remaining 0%다.
- Task 5는 BGM/SFX gain/fade/ducking, B-roll crop/fit/loop/pad/trim을 FFmpeg 및 real CapCut draft에 연결하고, missing font/media 차단과 preview/final/CapCut artifact recovery/reload를 추가했다.
- 현재 HEAD 검증: backend Python 3.12 `674 passed`, frontend `96 passed`/build success, `dev-fast-path.ps1 -Mode smoke` 600초 Korean 15 checks true. smoke final MP4 SHA-256은 `448c74034c3981ff7aa5264d12655eba6096b1653261e93d1ffae41a26342f29`다.
- 다음 권장 작업은 새 편집 기능 확대가 아니라 실제 CapCut desktop에서 10분 프로젝트 3건을 열고, B-roll pad와 ducking compatibility warning을 포함한 수동 open/edit/export UX QA를 기록하는 운영 검증이다.

## 16. 2026-07-12 long-form CapCut draft QA closeout

- `loop`, `crop_pad_overlay`, `audio_ducking` 3개 deterministic 600초 fixture가 ingest → editing session → partial regeneration → SRT → styled MP4 → real CapCut `draft_content.json`을 반복 실행한다.
- auto QA는 B-roll loop/crop/pad/trim, image/text overlay, BGM/SFX gain/fade/ducking, 승인 개인 음성 TTS와 persisted ducking warning을 확인한다.
- 실행 명령은 `./scripts/dev-fast-path.ps1 -Mode long-form-capcut-qa`다. 생성 artifact는 `artifacts/long-form-capcut-qa/`에만 두고 Git에는 넣지 않는다.
- 이는 desktop CapCut 사용성 검증이 아니다. manifest의 `desktop_capcut_opened: false`와 같이 명시하며, 실제 CapCut 3건의 open/edit/export QA는 다음 사람 검증으로 남긴다.

## 17. 2026-07-12 CapCut output observability and recovery UX closeout

- real CapCut draft export의 persisted `notes` compatibility warning과 nullable artifact/error_message를 API → frontend type → output panel까지 같은 계약으로 연결했다.
- UI는 artifact 경로와 마지막 성공 artifact를 유지하고, warning을 오류와 분리한 `CapCut에서 후처리 필요` 안내로 표시한다. retry는 failed 상태에서만 노출한다.
- 새로고침 복구, 빈 warning, null artifact, failed API response는 frontend 및 backend contract test로 확인했다.
- 현재 HEAD 검증: Python 3.12 backend `683 passed`, frontend `97 passed`, production build success. 실제 desktop CapCut open/edit/export는 여전히 사람 운영 QA 범위다.

## 18. 2026-07-12 actual CapCut Desktop operating QA closeout

- CapCut Desktop `8.7.0.3685`에서 `loop`, `crop_pad_overlay`, `audio_ducking` 3개 600초 real draft를 실제 open했다. asset track, 10분 timeline, 한국어 caption, overlay, B-roll control surface, BGM/SFX/TTS track이 모두 로드됐다.
- `loop`은 CapCut UI에서 1080P/H.264/MP4/24fps로 실제 export 완료했고 `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Videos\\videobox-qa-loop-20260712.mp4`의 FFprobe duration은 `600.026848` seconds다. 나머지 두 draft는 open/edit/export dialog까지만 확인했다.
- 당시 handoff는 CapCut default project root에 draft folder를 수동 등록해야 했다. 이 제한은 아래 19번 slice에서 해소됐다.

## 19. 2026-07-12 CapCut local-project handoff registration closeout

- VideoBox는 원본 `draft_content.json` artifact를 수정하지 않고, Windows `%LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft\\videobox-<export_id>`에 별도 registered copy를 만든다.
- 지원 탐지는 `%LOCALAPPDATA%\\CapCut\\Apps` 아래의 `CapCut.exe`와 위 local project root가 모두 존재하고 쓰기 가능한 경우로 제한한다. 미설치, project root 미생성, 쓰기 권한 거부는 추측하지 않고 각각 한글 복구 안내를 반환한다.
- 동일 export 재시도는 완전한 등록 copy를 재사용한다. 불완전한 충돌 copy는 새 임시 폴더 copy 후 교체하며, copy 실패 시 임시 폴더를 정리해 원본 artifact를 보존한다.
- CapCut export API는 `handoff.status`, source artifact URI, registered project path, 오류 사유, 등록 시각, reused 여부를 영속화한다. 웹 출력 패널은 `CapCut에 열기 준비`, 등록 경로, 실패 사유, `CapCut 등록 다시 시도`를 새로고침 뒤에도 표시한다.
- 실제 Windows CapCut Desktop에서 `videobox-handoff-loop-20260712`을 검색해 열었다. CapCut detail path는 `C:\\Users\\atgro\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft\\videobox-handoff-loop-20260712`이고, 수동 폴더 복사 없이 10분 타임라인, 한국어 자막, 오디오 트랙이 열렸다. 같은 registration을 두 번 호출해 첫 호출 `reused=False`, 두 번째 호출 `reused=True`도 확인했다.
- 최신 검증: Python 3.12 backend `693 passed`, frontend `99 passed`, production build 성공. artifacts는 Git에 포함하지 않는다.

## 20. 2026-07-13 CapCut handoff diagnostics closeout

- `GET /api/capcut/handoff-diagnostics`는 project/export/source draft를 변경하거나 CapCut을 실행하지 않고 현재 Windows handoff 준비 상태만 반환한다. 권한 검증은 즉시 삭제되는 temporary file probe로 실제 쓰기 가능 여부를 확인한다.
- response는 선택된 최고 버전 `CapCut.exe` 설치 경로와 버전, 예상 local project root, root 존재, 쓰기 권한, `ready`/`failed`, 한글 복구 안내, 검사 시각을 포함한다.
- 웹 출력 패널의 `CapCut 연결 진단` 카드는 설치·프로젝트 경로와 쓰기 상태를 보여주며, failure일 때 `다시 진단`으로 상태를 새로 읽는다. 카드 상태는 page reload 때도 API에서 다시 복구된다.
- live Windows proof: CapCut `8.9.1.3802`, `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Apps\\8.9.1.3802\\CapCut.exe`, `C:\\Users\\atgro\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft`, write access `true`, status `ready`를 확인했다.
- 최신 검증: Python 3.12 backend `698 passed`, frontend `101 passed`, production build 성공. `artifacts/`는 Git에 포함하지 않는다.

## 21. 2026-07-13 long-form CapCut 3/3 final-render operating QA closeout

- CapCut Desktop `8.9.1.3802`에서 `loop`, `crop_pad_overlay`, `audio_ducking` 3개 600초 real draft를 모두 1080P/H.264/MP4/24fps로 실제 local MP4 export 완료했다.
- `loop`: `videobox-qa-loop-20260712.mp4`, `600.026848` seconds, `73,526,175` bytes, SHA-256 `3DF607575BE81F1FD0050F1635B831E1C71D7DB6C7DA45E933D7848C23DF53F8`.
- `crop_pad_overlay`: `videobox-qa-crop-pad-overlay-20260712.mp4`, `600.026848` seconds, `25,452,146` bytes, SHA-256 `839F83D911384B1BE72B8D983DA7AC16E34221CCE505935A0E31F8394187043B`. CapCut timeline에서 Korean caption, image/text overlay, black-pad B-roll track을 확인했다.
- `audio_ducking`: `videobox-qa-audio-ducking-20260712.mp4`, `600.026848` seconds, `73,882,181` bytes, SHA-256 `B23B2D7E7DDC01D3BDD0F49B11126EC80BA8CF90E3349F2DC29BC6AE72EAA11B`. CapCut timeline에서 narration/TTS와 `smoke-bgm.wav`/`smoke-impact.wav` audio track을 확인했다.
- output은 모두 `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Videos\\`에만 두며 VideoBox source artifact 및 Git `artifacts/`는 수정·추가하지 않는다.

## 22. 2026-07-14 Local Media Director implementation plan

- 승인 설계는 `docs/superpowers/specs/2026-07-14-local-media-director-design.md`다.
- 실행 계획은 `docs/superpowers/plans/2026-07-14-local-media-director-implementation.md`다.
- 계획은 18개 TDD Task를 세 순차 slice로 나눈다.
  1. Local media intelligence foundation: LM Studio local-only provider, durable B-roll analysis, 자동 태깅/검수
  2. Script-first proposal engine: narration 없는 provisional script session, B/M/S ranking, preview/materialize, atomic apply
  3. Director workspace: 우측 대화 패널, 수동 편집, B/M/S reference, persistent conversation, 10-step undo/redo, responsive UI
- 구현 시작 전 기준 HEAD는 `8eddb7f`다. Slice 1 Task 1–6과 그 release-blocking remediation, Slice 2 Task 7–12, Slice 3 Task 13–18은 완료됐으며, 전체 계획 기준 18/18 Task(100.0%) 완료·0% 잔여다.
- 구현 계획의 개발 Task는 모두 닫혔다. 다음은 새 기능 Task가 아니라 CapCut Desktop 수동 재생·export 승인, 실제 음성 자연스러움, 배포 전 권리/라이선스 판단의 human acceptance release follow-up이다.
- 기존 `LocalFirstStructuredRuntime`의 Gemini 자동 fallback, 외부 HTTP(S) runtime 허용, text-only Qwen adapter는 승인 설계와 충돌하므로 Slice 1에서 RED test부터 교체한다.
- Codex Sol/Terra/Luna 모델 선택은 개발 에이전트 실행 자원이며 VideoBox 제품 runtime 계약에는 포함하지 않는다.

### Slice 1 Task 1–5 remediation closeout (2026-07-15)

- actual LM Studio media analysis는 strict loopback capability profile로만 opt-in 구성하며, default blocked state와 test-only fake DI seam을 분리한다. model-profile cache identity, durable scene/embedding provenance, active queue position, preview availability, batch partial-failure contract까지 RED-first로 보완했다.
- Task 4의 analysis validity gate는 proposal/apply consumer가 생성되는 Slice 2 Task 8–11에서 연결한다. 이연을 가리기 위한 가짜 apply endpoint는 만들지 않는다.

### Slice 1 Task 6 live gate current evidence — PASS (2026-07-15)

- `87be02e` HEAD의 opt-in smoke가 actual Qwen Vision fixed-schema response, BGE finite embedding, `lm_studio` provider trace(no fallback), restart durable semantic self-match를 통과했다. `@live_lmstudio`+`VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE=1`+exact `127.0.0.1:1234` 외의 일반 회귀는 socket을 열지 않는다.
- native `/api/v1/models`의 loaded instance/vision metadata는 후보 discovery 전용이다. structured JSON은 actual `POST /v1/chat/completions` fixed-schema 성공/strict parse로만 증명했다. exact loopback 7회(native 5, OpenAI runtime 2), external/Gemini 0, profile/variant/sample SHA/trace는 custom Git-excluded success artifact에 저장했다.
- malformed native inventory에 한해서만 이전 strict loaded+native-capabilities inventory를 fallback으로 읽는다. generic `/v1/models` ID나 model name inference는 계속 blocked다. Task 7부터는 이 frozen local-only boundary를 사용한다.

### Slice 2 Task 7 closeout (2026-07-15)

- script-only session은 deterministic segmentation, fixed Korean speech-rate와 최소 2초 provisional timing, durable `timing_source`/alignment-required/source identity를 제공한다. alignment API는 실제 bounds로 교체하고 source ID별 future proposal stale handoff를 보존하지만 Task 8의 proposal domain을 앞당기지 않는다.
- 독립 spec/quality review는 P1/P2 없이 승인했고, reverse runtime review가 찾은 API-level invalid alignment coverage(P2)는 빈 목록·overlap·non-positive bounds 422 E2E로 보완했다. legacy JSON의 absent new fields는 직렬화하지 않는다.
- `ed092d0`에서 focused `66 passed`, final backend full `905 passed, 2 skipped`, frontend `107 passed`/build success와 `git diff --check`를 확인했다. 기존 `python_multipart` deprecation warning 1건은 비차단이다.

### Slice 2 Task 8 closeout (2026-07-15)

- immutable proposal/ranking/persistence를 API/apply 없이 core/store에 한정했다. proposal revision과 asset-index revision은 concurrent-safe하며, music/BGM alias·media-scoped reference code·semantic/lexical fallback provenance를 고정했다.
- narration alignment stale과 asset index mutation은 각각 session/proposal 및 asset/revision을 atomic SQLite transaction으로 처리한다. Task 9가 proposal API와 session/index/expiry preflight를 처음 연결한다. 코드 commit은 `6a5d3ec`이다.

### Slice 2 Task 9 closeout (2026-07-15)

- DirectorProposalService는 SQLite read snapshot으로 script session, assets, analysis, preferences, asset-index revision을 함께 읽어 immutable proposal을 만든다. B-roll은 current source SHA와 succeeded analysis를, BGM/SFX는 source availability와 indexed canonical metadata를 요구한다.
- proposal API는 create/get/preflight/refresh/preferences를 제공하며, preflight는 server-side revision/source/analysis/expiry를 재조회해 `409 stale_proposal`와 immutable diff를 반환한다. proposal lifecycle reason/event는 snapshot JSON과 분리된다. API client도 같은 request contract를 사용한다.
- remediation은 unknown user-owned warning provenance, SHA별 asset ownership, terminal analysis derived-data cleanup, ranking-visible index revision, basename collision, local-only DI fallback rejection을 RED-first로 고정했다. Director route는 provider 호출이 없어 fake Gemini/external HTTP counter 0을 증명한다.
- 코드 commit은 `37252c2`이다.

### Slice 2 Task 10 closeout (2026-07-15)

- ProjectAssetMaterializer는 candidate source→controlled staging→project-local asset의 SHA를 각각 재검증하고, source mutation·post-registration mismatch·unlink failure에는 asset row/file/staging을 보상 정리한다. 동일 project/SHA는 source/right/warning provenance까지 같을 때만 재사용한다.
- candidate preview는 immutable controls와 exact in/out header를 가진 verified temporary snapshot만 스트리밍하며 autoplay, editing-session, timeline mutation을 수행하지 않는다. B-roll은 non-empty applicable analysis, BGM/SFX는 indexed required canonical metadata를 recheck한다.
- independent spec/quality review가 P0/P1/P2 없이 승인했다. focused backend `79 passed`, final backend full `957 passed, 2 skipped`, frontend `108 passed`/build success, `git diff --check`가 통과했다. 코드 commit은 `d1d3f98`이다.

### Local Media Director 중간점검 보완 (2026-07-15)

### Slice 2 Task 11 closeout (2026-07-15)

- proposal apply는 base/session/index/materialized SHA를 단일 SQLite CAS transaction에서 재검증하고 proposal consumption·session write·artifact invalidation을 함께 확정한다. SHA/index race와 DB failure는 session/proposal을 보존하며, apply 전에 등록된 materialized asset은 독립 재사용 자산으로 남긴다.
- proposal과 manual B-roll/BGM/SFX/caption/overlay는 동일 named transaction adapter를 사용한다. undo stack은 10, audit history는 100으로 제한되며 manual mutation도 정확히 한 revision만 전진해 stale CAS를 거부한다.
- review/subtitle/preview/final/CapCut은 durable freshness와 canonical API read를 가진다. stale review는 새 output을 막고 재승인 후에만 복구되며, stale subtitle은 current selector에서 배제된다.
- 검증: focused backend 114 passed, full backend 965 passed/2 skipped, frontend 108 passed/build success. 다음은 Task 12 output hash/revision revalidation과 Slice 2 gate다.

### Slice 2 Task 12 closeout (2026-07-15)

- `OutputSourceStaleError(stale_output_asset)` shared gate는 project-local URI/asset identity, streaming SHA-256, materialized registration revision, current editing-session/timeline/review/subtitle revision을 preview·FFmpeg·PyCapCut에 동일하게 적용한다. direct preview도 SHA 또는 revision-bearing clip이면 verifier store 없이 fail-closed 된다.
- stale old timeline, source mutation, stale review/subtitle, partial regeneration CAS/publish/cleanup failure는 output 전에 차단·보상한다. 실패 publish는 original session revision으로 정확히 복구하고 candidate timeline/review/run을 격리·정리한다. trigger migration도 SQLite 단일 writer transaction으로 직렬화했다.
- real Starter Pack gate는 opt-in(`VIDEOBOX_RUN_REAL_STARTER_PACK_E2E=1`) 상태로 실제 re-materialize→reapply→partial regeneration→reapprove→subtitle regeneration recovery와 external/Gemini call 0을 검증한다. 이 worktree에는 pack이 없어 기본 run은 skip됐다.
- 검증: Task12 focused 147 passed/1 skipped, full backend 978 passed/2 skipped, frontend 108 passed/build success. 다음은 Task 13 persistent conversation과 reference command resolver다.

### Slice 3 Task 13 closeout 및 중간점검 (2026-07-15)

- conversation/message는 SQLite durable truth로 저장하며, message submit은 editing session을 수정하지 않는다. 동일 client message ID는 다른 내용이면 409, 같은 내용이면 이미 확정된 user/assistant exchange를 반환한다.
- local assistant 생성의 동시 재시도는 owner-token claim, heartbeat, finalize fence로 한 번만 실행한다. crash 뒤 stale claim은 회수할 수 있지만 이전 owner는 결과를 확정할 수 없다. local runtime 실패는 `blocked` metadata와 local-only provider trace를 남기고 editing session을 그대로 보존한다.
- resolver는 open proposal 후보와 실제 persisted timeline의 B/M/S override placement를 immutable ID로 구분한다. 숫자만 있는 참조가 둘 이상이면 선택 card용 disambiguation을 반환한다.
- RED는 conversation/resolver 모듈·table 부재와 이후 review P1(typed placement collision, action intent/preflight 부재, history session-scope 우회)을 재현했고 GREEN으로 닫았다. focused `26 passed`, final backend full `996 passed, 2 skipped`, frontend `108 passed`/build success, `git diff --check`를 통과했다. fake Gemini/external provider counter는 0으로 고정했다. 기존 backend multipart warning 및 frontend ErrorBoundary/`act(...)` stderr는 비차단 기존 경고다.
- 중간점검 보완: timeline target은 typed `{segment_id, track_type}`이며, resolved command는 immutable proposal 또는 `{session_id, session_revision}` preflight binding을 가진 action intent를 반환·저장한다. command는 session을 변경하지 않고 Task 15/18의 explicit apply만 atomic mutation/undo를 만든다. unknown/mismatched conversation은 404, in-flight duplicate는 `202 + Retry-After` 계약으로 고정했다. Task 14는 이 intent/conversation DTO의 표시·재시도 client test를, Task 18은 retention/index release audit 및 bootstrap Gemini와 Director 성공 trace의 local-only route-surface 검증을 맡는다. OpenCut/full NLE 및 Voice Capture & Narration은 이 18 Task에 섞지 않고 후속 판단 gate를 유지한다.

### Slice 3 Task 14 closeout (2026-07-16)

- frontend API는 Task 13 conversation create/list/send, typed reference/action-intent/preflight 및 faithful proposal/candidate DTO를 소비한다. `prepareDirectorMessage`는 immutable client message ID/body를 보존해 `202 + Retry-After` 뒤 retry가 이미 확정된 exchange를 받도록 한다.
- pure Director units는 proposal/timeline Korean reference label, explicit stale artifact history(legacy absent `is_current`은 current), action metadata history, IME·editable target을 배제한 Ctrl/Cmd undo/redo를 제공한다. 대화 exchange와 action intent는 apply endpoint나 editing session mutation을 호출하지 않는다.
- quality remediation: 지원하지 않는 proposal apply scope 전송을 제거하고, backend editing-session response가 action_id/label/created_at/reversible/blocked_reason을 보존하도록 contract test를 추가했다.
- 검증: focused frontend `15 passed`, backend contract `9 passed`, full backend `997 passed, 2 skipped`, full frontend `118 passed`/build success, independent spec/quality/final review P1/P2 없음, `git diff --check` 통과. 기존 multipart warning 및 frontend ErrorBoundary/`act(...)` stderr는 비차단 기존 경고다.

- historical note: 이 중간점검의 최초 시점은 HEAD `8b023f5`, Task 1–8/18(44.4%)이었다. 이후 Task 9와 Task 10이 완료됐으므로 현재 truth는 이 섹션 상단의 10/18(55.6%), 다음 Task 11이다.
- 2026-07-15 후속 독립 감사는 Task 9 preflight가 BGM/SFX에 B-roll analysis를 잘못 요구하고, empty B-roll analysis result와 nullable candidate `media_revision`을 허용하며, proposal lifecycle state/event가 원자적이지 않음을 확인했다. Task 10은 materializer 전에 이 세 계약을 RED-first로 고친다. B-roll은 non-empty succeeded analysis+SHA, BGM/SFX는 indexed canonical metadata+SHA로 재검증하고, `media_revision`은 asset registration `created_at`으로 고정한다.
- Task 10은 copy 전후 SHA·staged SHA, per-SHA idempotent lock, cleanup과 source-mutation race, candidate preview까지 닫는다. Task 11은 SQLite authoritative session/sidecar reconciliation·durable output freshness·manual mutation parity를, Task 12는 preview/FFmpeg/CapCut shared stale verifier를 명시했다. Task 13은 idempotent message API와 local-only assistant response contract를 추가했고, Task 18은 Gemini UI뿐 아니라 bootstrap Gemini request 0을 검증한다.
- OpenCut/full NLE와 Voice Capture & Narration은 현재 18 Task 계획에 섞지 않고 별도 후속 판단으로 유지한다.

## 23. Hermes 다음 slice — 기존 Compose 기반 확장 (2026-07-19)

컨테이너 이전은 `codex/videobox-container-compatibility`의 `635a9bb`까지 **완료 (done)** 됐다. Compose project는 `65_videobox`이며, 검증된 immutable `snapshot/`, writable `runtime/`, internal PostgreSQL과 loopback web 경계를 기준선으로 사용한다. Hermes 작업은 새 독립 계획서를 만들지 않고 이 최상위 계획의 다음 slice로 추적한다.

### 23.0 상태 표기와 선행 결정

- `[x] 완료 (done)`: 구현·범위에 맞는 검증·커밋이 끝난 항목이다.
- `[~] 진행 중 (in progress)`: 구현 또는 검증 중이며 완료 주장으로 쓰지 않는다.
- `[ ] 미완료 (pending)`: 아직 시작하지 않았거나, 명시적 gate가 남은 항목이다.
- `[!] BLOCKED`: 외부 사실·권한·승인 근거가 없어 구현을 시작하지 않는 항목이다.
- `[x] 완료 (done)`: Hermes가 올라갈 Compose/PostgreSQL/snapshot/runtime 기준선과 실제 두 장면 current-revision MP4 재생 경로를 고정했다. Task 9 사람/환경 acceptance와 CapCut Desktop evidence의 완료 상태는 이 항목으로 바꾸지 않는다.
- `[~] 진행 중 (in progress, 2026-07-20)`: 외부 생성 모델 provider를 퇴역 중이다. key router·web credential CRUD UI·provider/domain/core module을 삭제하고, 새 project와 다시 여는 기존 SQLite project 모두에서 퇴역 credential table을 제거한다. public provider credential path와 provider transport는 없으며, local-only 실패는 deterministic fallback 또는 사람 검수로 끝난다. 단, 통합 API 파일의 과거 fallback 전용 테스트 삭제와 full backend 재검증은 아직 남아 있다.
- `[x] 완료 (done)`: 2026-07-19 Hermes Agent 공식 문서와 release를 확인했다. 공식 quickstart/configuration은 `hermes model`의 **OpenAI Codex → ChatGPT OAuth device-code login**을 지원한다고 명시한다. 첫 설치는 signed release tag `v2026.7.7.2`의 annotated tag `b7751df34688835a108e0d630f3495fc11f3df79`와 peeled commit `9de9c25f620ff7f1ce0fd5457d596052d5159596`으로 pin한다. 근거: <https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/>, <https://hermes-agent.nousresearch.com/docs/user-guide/configuration/>, <https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.7.2>.
- `[x] 완료 (done)`: `videobox-hermes-agent` pre-auth container를 official amd64 digest `sha256:3db34ce19adfa080736a2a3feb0316dbcccc588faa9afe7fd8ae1c03b4f1a53a`로 기동했다. Compose profile은 `hermes-preauth`이며, `network_mode: none`, host port 없음, VideoBox DB/media/snapshot mount 없음, 전용 scratch `videobox_hermes_preauth_state:/opt/data`, read-only root, `cap_drop: ALL`, `no-new-privileges`, bounded `local` log를 확인했다. 이 scratch volume은 훗날 OAuth state volume과 절대 재사용하지 않는다. official s6 supervisor의 state ownership·supervise lock을 위한 최소 예외로 `CHOWN`, `DAC_OVERRIDE`, `SETGID`, `SETUID`만 다시 더한다. 이 네 capability는 PID 1 supervisor에만 남고 실제 CMD는 UID `10000`/`hermes`, `CapEff=0`으로 실행됨을 runtime에서 확인했다. `hermes --version`은 `v0.18.2 (2026.7.7.2) · upstream 9de9c25f`를 반환했고 scratch state에는 `auth.json`과 `.env`가 없다.
- `[ ] 미완료 (pending)`: 유진 profile, Hermes→VideoBox API 권한중개, egress allowlist gateway, OAuth login, mem0, 편집 mutation은 아직 만들지 않았다. 이 계획의 각 gate를 통과하기 전에는 이 범위를 추가하지 않는다.

이 절은 Hermes 범위에서 `docs/llm-provider-strategy.ko.md`의 과거 외부 fallback보다 우선한다. provider 전략 문서는 현재 local-only 결정으로 갱신됐으며 외부 생성 모델 provider의 credential·key pool·router는 제거했다. 정적 검사와 실제 runtime 모두 external provider call `0`을 유지해야 하며, 외부 fallback 경로를 되살리는 구현은 허용하지 않는다.

### 23.1 [~] 진행 중 (in progress) — Hermes 소유 ChatGPT OAuth·egress 계약

1. **선택한 한 방식:** VideoBox가 OpenAI OAuth endpoint를 구현하는 방식이 아니라, pinned Hermes Agent가 공식 `hermes model`의 `OpenAI Codex` 선택지로 수행하는 ChatGPT **device-code OAuth**를 쓴다. 사용자 로그인은 Hermes container의 interactive setup에서만 수행한다. VideoBox web/API는 redirect URI, client secret, auth code, refresh token을 만들거나 받거나 갱신하지 않는다.
2. **직접 OAuth는 계속 BLOCKED:** OpenAI 일반 API에 대한 VideoBox 자체 사용자 위임 OAuth, authorization-code + PKCE, device flow 재구현, generic token endpoint 호출은 공식 VideoBox contract가 아니므로 구현하지 않는다. Hermes가 소유한 provider credential을 VideoBox DB, 일반 `.env`, mem0, snapshot, backup, log/trace 또는 API response에 복사·전달하지 않는다.
3. OAuth credential과 Hermes config는 pre-auth scratch와 분리된 전용 named state volume에만 둔다. repository에는 secret이 없는 pinned image/source reference와 non-secret allowlist만 둔다. 현재 `hermes-preauth` profile은 network가 없는 preflight-only container이므로 scratch에 auth file이 생성되지 않아야 한다. OAuth profile은 scratch를 mount하지 않으며, egress allowlist gateway가 별도 gate를 통과하기 전에는 `hermes model`을 실행하지 않는다. logout/revoke/expiry/reuse는 Hermes CLI의 공식 동작을 integration test로 확인하고, credential을 열람·export·backup하지 않는다.
4. egress 기본값은 거부다. bootstrap 때만 pinned Hermes 공식 provider flow에 필요한 destination을 명시적으로 allowlist하고, VideoBox project data·media·script·caption·mem0은 그 요청에 포함하지 않는다. OAuth 성공은 창작 요청이나 project data-transfer 동의가 아니며, 향후 GPT inference는 request별 동의·budget·audit와 별도 gate를 통과해야 한다.

### 23.1A [x] 완료 (done) — `65_videobox` workspace container 전환

사용자가 확정한 운영 기준은 **VideoBox 작업 환경을 하나의 `videobox-workspace` 컨테이너에서 실행**하는 것이다. Compose project name `65_videobox`는 이미 실제 runtime의 컨테이너·volume 이름으로 존재하므로 바꾸지 않는다. 이 절은 새 계획서가 아니라 기존 Compose 기준선을 아래처럼 대체한다.

1. `[x] 완료 (done)`: `videobox-api`와 `videobox-web` service를 retire하고, 하나의 `videobox-workspace` image가 Python API, compiled Web static artifact, FFmpeg, Node development toolchain을 함께 가진다. host에는 `127.0.0.1:${VIDEOBOX_WEB_PORT:-5173}:8080` 하나만 노출한다. API는 UID 10001의 `127.0.0.1:8000`만 listen하고, Web proxy는 UID 10002와 scrubbed DB environment로 실행한다. Docker Desktop의 published loopback port 제약으로 workspace는 `videobox-edge`와 internal DB network를 모두 가진다. 이는 Web/API의 Docker-level mount namespace 분리를 포기하는 사용자 승인 workspace tradeoff이며, Windows bind mount permission만으로 Web data 불가를 절대 보장한다고 주장하지 않는다. PID 1은 두 worker를 fork한 직후 `CapPrm`·`CapEff`를 0으로 drop하고, 실제 runtime에서 PID 1·API·Web 모두 capability 0과 `NoNewPrivs=1`을 확인했다.
2. `[x] 완료 (done)`: PostgreSQL은 `65_videobox` 내부 전용 companion service로 유지한다. database volume `65_videobox_videobox_postgres_data`와 current `runtime/`·read-only verified `snapshot/` mount를 그대로 재사용하며, DB port는 host에 열지 않았다. 이는 workspace 한 개에서 개발·운영한다는 기준을 지키면서 DB lifecycle/data integrity를 app process restart와 분리하기 위한 최소 예외다.
3. `[x] 완료 (done)`: workspace는 Docker socket, host bridge, CapCut mount, Hermes OAuth credential volume을 받지 않는다. inspect에서 `Privileged=false`, device 0, Docker socket mount 0을 확인했다. Gemini/OAuth/Hermes provider environment도 workspace에 없으며, `videobox-hermes-agent`의 pre-auth `network_mode: none`·no-VideoBox-data boundary는 유지한다. 실제 Hermes runtime을 workspace process로 합치면 DB/media/process environment 격리가 사라지므로, Agent Gateway·network split gate 전에는 합치지 않는다.
4. `[x] 완료 (done)`: compose contract는 exact project name, service 수(`videobox-workspace`, `videobox-postgres`), loopback-only web port, DB/data/snapshot mount ownership, source-built artifact와 local-only/Gemini-0/OAuth-disabled boundary를 검증한다. 기존 project data에서 workspace health/web UI를 확인했고, `b-roll-smoke-test` current final-render content는 proxy를 통해 `206`, `video/mp4`, Range response로 재생 가능함을 확인했다. internal peer의 direct `:8000` API access는 차단되고 `:8080` proxy health만 통과했다. 그 뒤 legacy API/Web containers를 `remove-orphans`로 정리했다.

### 23.2 [~] 진행 중 (in progress) — 서비스 identity와 VideoBox 권한중개

1. `videobox-hermes-agent`는 internal-only 별도 service로 둔다. VideoBox PostgreSQL, `snapshot/`, `runtime/` media directory, renderer, CapCut/host bridge를 직접 mount·읽기·실행하지 않는다.
2. internal network만으로 권한을 인정하지 않는다. Hermes는 audience=`videobox-api`, operation·project allowlist, expiry·rotation·revocation·replay 방지를 포함한 짧은 수명 service capability로만 VideoBox API를 호출한다.
3. 모든 handler는 최종 `(principal, project_id, operation)`을 검사한다. 초기 `get_project_status`는 명시적으로 선택한 한 project의 allowlisted read model만 반환하며 project list, global job, raw script/caption/media path/voice/transcript/PII를 반환하지 않는다. 단일 local owner MVP만 범위에 넣고 multi-user SaaS auth는 별도 slice다.
4. `[x] 완료 (done)`: `GET /internal/hermes/projects/{project_id}/status`의 conditional read-only contract와 **durable consume/replay ledger**를 구현했다. default VideoBox에는 route가 없고, 명시적으로 주입한 verifier를 `create_app`이 project store에 bind할 때만 strict `HS256` key-id, issuer/principal/audience/operation/project/5분 TTL/JTI를 검사한다. JTI는 `(project_id, jti)` ledger에 원자적으로 consume되어 API restart 뒤에도 replay를 거부하며, persisted revoked JTI도 거부한다. `(project_id, expires_at)` index와 decision commit 뒤 purge로 만료 record를 정리하고, ledger 오류는 raw DB detail 없이 generic `503 hermes_capability_unavailable`으로 fail-closed한다. SQLite restart·two-independent-connection duplicate winner와 별도 임시 PostgreSQL 16 integration의 consume/replay/revoke·expiry purge·two-worker duplicate winner를 검증했다. verifier 단독 unit harness의 process-local replay/revocation은 배포 경로가 아니며, 실제 route에서는 durable callback이 없으면 배포하지 않는다. 반환 field는 `project_id`, `name`, `status`, `updated_at`, `has_editing_session`, `latest_session_revision`뿐이며 `root_storage_uri`, media/script/caption/voice/transcript, project list와 job은 없다.
5. `[x] 완료 (done, static contract only, 2026-07-20)`: canonical Python static authority contract와 Compose extension을 field-by-field로 대조했다. issuer owner는 `gateway-only`, issuance는 `false`, signing secret delivery와 ordinary `/api/*` path는 `forbidden`이며, named future gateway service/network는 현재 Compose에 존재하지 않는다. 기존 `LocalProjectStore.revoke_hermes_capability`는 durable revoke **storage primitive**로만 명시하고, owner-authorized revoke writer는 `not_deployed`로 고정했다. default `create_app`에는 Hermes capability/revoke/issue route가 없고, 기존 conditional status route만 durable `consume_hermes_capability` boundary를 사용한다. Hermes pre-auth는 계속 `network_mode: none`이며 이 계약은 service, route, network, signer 또는 secret을 만들지 않는다.
6. `[ ] 미완료 (pending)`: signer는 아직 어떤 VideoBox API route나 Hermes container에도 배포하지 않는다. owner-authorized revoke writer/source, signing secret delivery·rotation·key lifecycle, gateway audit 및 실제 gateway-only route/network는 아직 없다. Hermes가 self-mint하거나 shared signing key를 받는 설계는 금지한다.

### 23.3 [ ] 미완료 (pending) — 유진 profile, prompt와 업무 영역

첫 slice의 에이전트는 **유진 (Yujin), `yujin-video-director`** 하나로 고정한다. 유진은 대화 요약, 사용자가 명시적으로 선택한 한 project의 상태 설명, action 없는 approval request 제안만 한다. VideoBox는 영상 편집·검수·CapCut 인계에 집중하며, 대본·제목·썸네일·추천 영상의 생성 또는 제안은 현재 제품 범위 밖으로 차단한다. 영상·자막·소리·전환의 근거 없는 품질 주장, DB/SQL, filesystem, shell, renderer, CapCut, raw HTTP, credential, 직접 편집·render·export는 금지한다. 화면 문구는 유진의 짧고 행동 중심적인 안내를 유지한다.

- `[x] 완료 (done, 2026-07-20)`: 실제 provider·tool 실행 없이 `yujin-video-director`의 단일 versioned profile/policy/template/strict four-way response manifest를 literal SHA-256으로 고정했다. immutable registry와 prompt envelope은 `system → developer → task → user` 순서를 고정하고, user text와 선택 project의 allowlisted status는 instruction이 아닌 별도 immutable untrusted data/digest로 보관한다. status/revision의 raw path·sensitive data·instruction·다른 project 식별자를 거부한다. 1,500 ms structured-response timeout 또는 invalid response는 executor 없이 bounded `blocked` fallback으로 끝난다. 응답의 `declared_read_capability`는 실행 요청이 아닌 선언이고 `action=null`, `needs_human_review`, `non_authorizing=true`만 허용한다. 유진은 편집 관련 질문·실행 없는 제안만 할 수 있고 직접 편집 실행은 하지 않는다. 한국어·영어 injection, approval/render/export/CapCut/memory/credential, 대본·제목·썸네일·추천 영상 생성/제안, 다른 project 요청은 blocked이며 제작 요청은 공백·기호·전각 표기 변형도 같은 범위로 정규화해 거부한다. 현재 선택 project ID를 말하는 상태 문의는 허용한다. 이는 profile contract/fixture replay일 뿐 Hermes, OAuth, GPT/Qwen/Gemini call, DB/API route, mem0, 편집·render·export를 추가하거나 활성화하지 않는다.
- `[x] 완료 (done, 2026-07-20)`: 유진 Agent Package v1은 versioned Soul, canonical user preference/consent schema, response-only skill 3개, declaration-only `get_project_status` MCP policy를 profile/tool/workflow/package manifest로 묶는다. memory는 opt-in false·scope none·retention 0이고 MCP 기본값 deny다. filesystem/shell/DB/renderer/CapCut/raw HTTP/mutation MCP와 실제 memory/MCP transport는 허용하지 않는다.

| 역할 | 허용 입력·도구 | 거부 범위 | 사람 gate | 결과 |
|---|---|---|---|---|
| 유진 Project Copilot (첫 slice) | 선택 project ID, allowlisted status read model, 사용자가 입력한 대화 | project list, 원본 미디어·대본·자막, DB/filesystem/shell/renderer/CapCut, mutation | OAuth 연결, 외부 전송 동의 | 구조화된 상태 설명 또는 action 없는 proposal |
| Review/approval coordinator (후속) | immutable proposal과 deterministic preflight 결과 | approval 자체 결정, mutation 실행 | owner의 개별 approval card | 승인·거절 기록 요청 |
| Editing planner (후속) | 승인된 brief와 allowlisted asset metadata | asset/media 원문, 직접 mutation/render/export | project별 변경 approval | deterministic handler에 보낼 draft proposal |

prompt는 system/developer/task/user context 우선순위, template version·manifest hash, structured response schema·size limit·timeout/failure fallback을 가진 versioned registry로 관리한다. project·script·subtitle·asset metadata, mem0, tool result와 사용자 첨부 내용은 모두 **untrusted data**이며 instruction이 아니다. 모델 출력도 untrusted proposal일 뿐이고, policy middleware가 매 tool call마다 다시 권한을 검사한다. 역할 간 memory와 tool 공유는 기본 거부다.

| 사용자 의도 | 유진의 허용 산출물 | Gateway가 허용하는 tool | 금지·처리 |
|---|---|---|---|
| 영상 목표·톤 인터뷰 | 짧은 질문 또는 brief candidate | 선택 project의 status read | 사실·asset 존재를 추정하지 않는다 |
| 현재 상태·자산 문의 | source revision을 포함한 상태 요약 | `get_project_status` 한 개 | 다른 project, raw media/script/caption은 거부한다 |
| 장면·자산·음향 제안 | action 없는 proposal candidate | 첫 slice에서는 없음 | timeline 변경·render·export를 하지 않는다 |
| 대본·제목·썸네일·추천 영상 요청 | `blocked`와 짧은 이유 | 없음 | 영상 편집 전용 제품 범위를 벗어나므로 생성·제안하지 않는다 |
| 편집·export·CapCut 요청 | 별도 UI approval 경로 안내 | 첫 slice에서는 없음 | apply/register/export를 호출하지 않는다 |
| “기억해줘” | memory candidate와 opt-in 설명 | 첫 slice에서는 없음 | mem0 직접 write를 하지 않는다 |
| credential·설정·다른 project 요청 | `blocked`와 짧은 이유 | 없음 | 정보 노출·권한 우회·scope 확대를 거부한다 |

Agent Gateway는 run ownership, context filtering, tool allowlist, idempotency, event/audit를 맡고 창작 판단을 실행으로 확정하지 않는다. deterministic handler는 revision·rights·availability 검사와 정책 실행만 하며 자유 텍스트 지시를 해석하지 않는다. 각 ToolSpec은 `name`, request/result schema, action family, backend-derived project scope, revision precondition, redaction, result byte cap, timeout, idempotency, audit event, allowed run phase를 versioned registry에 가진다. 모델이 반환한 tool name·ID·scope는 권한 근거가 아니며 Gateway가 registry와 capability로 다시 선택·검증한다.

- `[x] 완료 (done, 2026-07-20)`: 첫 static ToolSpec/Gateway contract는 `get_project_status` 하나만 literal manifest SHA-256으로 고정했다. empty strict request, selected-project status 결과 allowlist·redaction, selected-project status revision precondition, 1,024 byte/1,000 ms cap, `read_only_research` phase만 허용한다. model proposal은 exact JSON scalar와 empty object로 정규화한 뒤에도 backend-attested context/request와 대조해야 하며, static acceptance는 항상 `executor_authorized=false`다. backend attestation marker는 hostile in-process code 방어가 아닌 ordinary application-contract boundary이며 실제 signer/API/agent runtime은 계속 미완료다.
- `[x] 완료 (done, 2026-07-20)`: static gateway decision audit/retry는 backend-attested UUIDv4 correlation/idempotency/principal을 hash-bound in-memory state로 묶는다. fixed reason, profile manifest, fixed tool/version, sanitized empty request digest, no-result, principal hash, UTC time만 기록하며 raw model claim·prompt·media·credential은 거부한다. 같은 principal의 retry만 `replayed_nonexecuting`이고 다른 input/principal은 conflict로 비실행 처리한다. 이는 durable ledger/signature가 아닌 nonpersistent app-contract이다.

### 23.3A [~] 진행 중 (in progress) — GPT-5.4 mini profile·로컬 Qwen qualification·안전한 성장

유진의 주 대화/창작 route와 로컬 보조 route는 같은 agent로 위장하거나 자동 fallback하지 않는다. profile·모델·prompt·skill·route 결정은 모두 run ledger에 남기고, provider 변경은 별도 gate로 처리한다.

1. `[x] 완료 (done)`: Hermes 공식 `openai-codex` ChatGPT OAuth route가 curated Codex model 목록에서 `gpt-5.4-mini`를 선택할 수 있음을 공식 provider 문서·모델 코드·release로 다시 확인했다. OpenAI API model page도 GPT-5.4 mini의 tool calling/structured output/400K context를 확인한다. 근거: <https://hermes-agent.nousresearch.com/docs/integrations/providers/>, <https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/models.py>, <https://developers.openai.com/api/docs/models/gpt-5.4-mini>.
2. `[x] 완료 (done)`: local GPU는 RTX 5090 32,607 MiB이고, LM Studio에는 `Qwen3.6 35B A3B` Q4_K_M(vision·tool-use, max context 262,144)이 설치되어 있다. 65,536 context/100% GPU offload estimate는 23.30 GiB, 실제 load는 20.55 GiB로 성공했다. local `/v1/chat/completions`의 JSON Schema title fixture는 reasoning token 0·세 개 title·schema-valid result를 반환했다. 단순 prompt만으로는 reasoning text를 먼저 반환했으므로, plain-text output은 qualification evidence가 아니며 JSON Schema/validator가 필수다.
3. `[ ] 미완료 (pending)`: 실제 Hermes OAuth profile은 `provider=openai-codex`, `model=gpt-5.4-mini`로만 만든다. interactive OAuth model picker에서 정확한 provider/model identifier, pinned Hermes image/version, prompt bundle manifest SHA를 run/audit profile에 고정한다. account entitlement 또는 picker result가 다르면 `BLOCKED`로 끝내며, 일반 `OPENAI_API_KEY`/임의 endpoint/다른 모델로 조용히 대체하지 않는다. device-code login과 외부 GPT call은 23.1 egress allowlist, project text-only consent, request budget/audit gate가 모두 통과하기 전에는 실행하지 않는다.
4. `[~] 진행 중 (in progress)`: Qwen은 named local custom provider로만 등록하고 initial auxiliary slot은 conversation compression·명시된 정형 요약으로 제한한다. title generation과 대본·썸네일·추천 영상 생성은 VideoBox의 현 영상 편집 전용 제품 범위 밖이므로 `disabled`다. 유진의 자유 대화·콘셉트/대본 창작·권한/승인 판단·tool selection을 Qwen으로 대체하지 않는다. conversation compression 결과는 신뢰하지 않는 파생 데이터이며, 원 대화와 VideoBox transcript가 SSOT로 남고 compression은 prompt/tool 권한을 얻지 않는다. video/vision quality, asset tag, keyword expansion, web extract는 각 task의 actual VideoBox fixture benchmark를 통과하기 전 `disabled`다. `[x] 완료 (done, 2026-07-19 현재 확인)`: LM Studio server를 `lms server stop` 뒤 `lms server start --bind 127.0.0.1 --port 1234`로 다시 기동했고 listener가 정확히 `127.0.0.1:1234` 하나임을 확인했다. 그러나 이것은 direct LAN 노출만 닫은 preflight이며 Qwen endpoint를 qualified로 만들거나 Hermes 연결을 허용하지 않는다. initial Qwen profile acceptance threshold의 context 64K 이상, Hermes direct connection 부재와 authenticated·pinned host bridge 경유는 여전히 별도 agent network에서 검증해야 하며, Hermes no-network pre-auth profile에는 연결하지 않는다.
5. `[ ] 미완료 (pending)`: Qwen task state(`disabled`, `shadow_only`, `needs_human_review`, `qualified`, `revoked`)는 각 task별로 독립 관리하며, 화살표 순서가 모든 task의 필수 순차 진행을 뜻하지 않는다. qualification 전에는 해당 task를 `shadow_only` 또는 `needs_human_review`로 유지한다. 한 task의 qualification은 다른 Qwen task, timeline/output, render/export, CapCut 또는 memory 권한으로 확대되지 않는다. 모든 state에서 Qwen은 DB/filesystem/shell/renderer/credential/direct mutation 권한이 없고, Hermes 실패 시 유진으로 위장하지 않는다. routing ledger에는 provider/runtime/model/profile/route reason, context category digest, schema/validator outcome, latency와 token/VRAM budget만 남긴다.
6. `[ ] 미완료 (pending)`: 유진은 반복된 근거를 `skill candidate`로 제안할 수 있으나, 자기 prompt·권한·실행 코드를 자동 활성화/수정하지 않는다. candidate는 fixture replay, injection/security test, quality benchmark, deterministic policy check, 사람 review, immutable version activation을 모두 거쳐야 한다. activation 뒤에도 rollback/revoke owner와 manifest SHA를 ledger에 기록하며, candidate/failed skill은 production route에 영향을 주지 않는다.
7. `[~] 진행 중 (in progress)`: `[x] 완료 (done)`: provider-neutral frozen evaluation core는 corpus/prompt-schema/renderer identity를 case에 고정하고, deep immutable sanitized fixture·strict object/schema allowlist·grounded claim·credential/path/tool/approval data rejection을 검사한다. 어떤 provider도 호출하거나 routing을 mutate하지 않으며, 통과해도 `shadow_only`이고 나머지는 `needs_human_review`다. `[x] 완료 (done, 2026-07-19)`: checked-in Korean shadow corpus는 external SHA-256 pin과 tamper 검증을 거치며, corpus/case/캡처 candidate를 재검증해 schema-valid·grounded·critical policy defect·사람 점수·correction time·95% CI report를 offline으로 기록한다. thresholds 통과도 항상 `needs_human_review`라 route activation 근거가 될 수 없다. `[x] 완료 (done, 2026-07-19)`: synthetic provider capture는 pinned corpus SHA·case/provider/runtime/model·candidate payload digest·opaque 사람 attestation을 함께 묶어 import하고, app-level append-only/tamper-evident hash-chain ledger와 write-once snapshot audit artifact로 보관한다. raw media/path·credential·tool·approval 데이터, capture/attestation replay, record/report 변조·순서 변경은 fail-closed하며, artifact는 이후 정상 append 뒤에도 당시 record snapshot으로 재검증된다. signing key나 external anchor는 아직 없으므로 OS/adversary-proof immutable이라고 주장하지 않으며, 어떤 report도 항상 `needs_human_review`이고 route activation 근거가 될 수 없다. `[ ] 미완료 (pending)`: frozen quality harness는 동일 prompt schema·fixed Korean corpus·sanitized VideoBox fixture·renderer version에서 GPT와 Qwen을 task별 실제 captured output으로 비교한다. schema-valid 98% 이상, grounded claim 95% 이상, critical policy defect 0, 사람 점수 Hermes 대비 -0.5/5 이내, correction time +10% 이내와 95% CI를 기록한다. 통과 전 Qwen은 shadow-only 또는 사람 review이며, 원본 raw media·경로·credential·mem0 원문을 cloud·local prompt에 넣지 않는다. 파생 frame 또는 sanitised approved tag는 해당 task policy와 benchmark가 적절한 gate를 통과한 경우에만 허용할 수 있으며, 일반 허용이 아니다.

### 23.4 [ ] 미완료 (pending) — read-only workflow와 승인 경계

첫 vertical slice 상태 전이는 다음으로 고정한다.

`intake → clarification_needed → brief_candidate → brief_confirmed → read_only_research → proposal_or_approval_request → deterministic_preflight → pending_human_approval → applied | rejected | cancelled | blocked | failed`

- OAuth 연결, 외부 GPT data-transfer, brief 확정, 개별 mutation/render/export/CapCut은 각각 별도 사람 gate다.
- 채팅의 “네”는 approval이 아니다. approval card는 project/conversation/run/proposal/action hash, base revision, change summary, rights blocker, prompt/skill version, expiry를 immutable하게 묶는다.
- reject·expire·stale·권한 부족은 side effect `0`으로 끝낸다. `applied`는 이 slice 범위 밖이며, 첫 slice에서 proposal은 durable하지만 action 없는 기록이다.
- retry는 idempotency key, duplicate winner, timeout/backoff/circuit breaker를 사용한다. API/GPT/mem0 장애와 token revoke/expiry, partial tool failure, restart/recovery는 수동 편집과 프로젝트 truth를 손상시키지 않고 명시적인 blocked/offline 상태로 보인다.
- `[x] 완료 (done, 2026-07-20)`: first read-only workflow의 declarative transition, immutable static proposal/approval-card/preflight를 고정했다. chat 긍정 문구는 승인 신호가 아니며 card는 built-in prompt/no-skill manifest, project/conversation/run/proposal scope, base revision, change summary, rights blocker, expiry를 digest-bound로 묶는다. reject·expire·stale·권한 부족 및 recorded approval 모두 side effect 0·nonexecuting이며 pending→applied는 이 slice에서 거부한다.
- `[x] 완료 (done, 2026-07-19)`: 실제 provider 호출 전의 offline synthetic evidence intake contract를 구현했다. 이는 real owner authentication/consent issuance·provider gateway가 아니라 fixture-only preparation이다. immutable grant는 opaque owner/grant ref, pinned corpus SHA, exact synthetic provider/runtime, scope, UTC expiry와 capture/token/latency budget을 묶고, preflight는 side effect `0`로 stable allow/deny를 낸다. accept는 journal·OS advisory lock 아래 전용 accepted-intake evidence sink와 redacted tamper-evident intake audit을 one-to-one으로 복구한다. marked intake sink의 mutation은 gateway의 private in-process writer capability만 허용하며, 외부에는 read verification만 보인다. 이 경계는 hostile in-process code 보안이 아니라 ordinary application code의 bypass 방지 contract다. 일반 parent evidence ledger는 pre-gate/offline test evidence일 뿐 intake grant/audit/budget를 우회하거나 intake sink를 막지 않는다. 정상 writable 경로의 accepted/denied는 `offline_evidence_only` audit으로 남고 route를 활성화하지 않는다. audit/lock I/O 불가는 audit을 억지로 만들지 않고 non-authorizing fail-closed로 끝난다. raw capture/credential/path/media와 plain owner/grant ref는 audit에 넣지 않는다. crash/interruption 뒤 retry는 journaled prepared time·grant binding을 재검증해 audit/evidence pair만 복구하며, 새 provider 실행이나 expiry 우회가 아니다. 실제 identity issuer, consent UI, retention/size cap, network gateway와 provider call은 계속 미완료다.

### 23.5 [ ] 미완료 (pending) — mem0와 기록 보존

mem0는 유진의 선택적 보조기억이다. tenant/project namespace, opt-in, TTL·retention·size cap, encryption, retrieval provenance, 사용자 clear-memory/delete/forget 경로를 둔다. token, approval, VideoBox project/editing/asset/conversation SSOT, hidden instruction은 저장·검색·복원하지 않는다. mem0 장애는 대화를 막지 않고 장기 기억 없이 계속하며 audit에만 기록한다.

VideoBox typed audit handler는 actor/principal, project, correlation ID, prompt/skill version hash, 허용 tool, sanitised argument/result digest, proposal/approval decision, 시간을 append-only ledger에 남긴다. secret, raw prompt, media, OAuth token은 audit에 남기지 않는다. retention/export/redaction와 incident/recovery runbook, restart restore drill의 acceptance도 이 slice의 산출물이다.

### 23.6 [ ] 미완료 (pending) — 검증·release gate

다음 항목을 모두 통과해야 read-only Hermes slice를 완료 (done)로 표시한다.

1. OAuth contract와 bootstrap/logout/revoke/expiry/reuse 실패가 23.1 선택 방식대로 동작하며 secret이 log·snapshot·mem0에 없다.
2. Compose inspect에서 Hermes에 DB/media/snapshot mount가 없고, approved network와 egress allowlist 외 연결이 없다.
3. API integration에서 unauthenticated, expired capability, cross-project, allowlist 밖 tool, injected instruction, poisoned mem0, rate/cost limit 요청이 fail-closed한다.
4. 프로젝트 status read model field allowlist, prompt-injection, structured-output size/timeout, audit redaction·complete correlation, restart/idempotent duplicate/recovery를 focused와 runtime으로 검증한다.
5. 외부 생성 모델 provider credential·key pool·router·transport가 static·runtime 모두 없고, OAuth/GPT endpoint도 user consent·budget·audit 없이 호출되지 않는다.
6. 코드리뷰, 계획 gap 검증, source→runtime 역방향 검증, focused/full relevant tests, production build를 다시 수행하고 논리적으로 닫힌 단위만 commit/push한다.

승인 기반 editing mutation, CapCut/host bridge, multi-agent fan-out, SaaS auth/billing, 대규모 UI framework는 위 gate 뒤 별도 slice다. 다중 에이전트가 필요해도 Gateway가 child scope·allowed tools·budget·deadline·audit correlation을 소유하며, child는 독립 DB/media/OAuth/mem0 권한을 받지 않는다.
