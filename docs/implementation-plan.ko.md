# VideoBox 실행용 구현 계획서

> 현재 worktree 기준 구현 상태와 next slice 판단은 `## 12. 2026-07-01 현재 구현 체크포인트`와 `## 13. 다음 실제 작업`을 우선 적용한다. 그 외 상위 milestone/범위/순서 섹션은 제품·구현 계획의 기준을 설명하는 문서다.
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
- LLM: 로컬 Qwen 우선 + Gemini multi-key fallback + 선택적 OpenAI provider
- TTS: 사용자 본인 목소리 기반 TTS provider
- 비전/자산 분석: OpenCV + 자산 메타데이터 인덱싱
- 데이터 저장: 로컬 DB 우선
- UI: React + TypeScript 기반 로컬 우선 web review dashboard
- 편집 셸: 오픈소스 편집기 구조를 선별 반입한 React + TypeScript 기반 경량 후편집기
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

현재 기준 아래 범위는 코드와 검증으로 실제 연결되어 있다.

- `editing session` 저장/조회/수정 API
- partial regeneration request contract와 backend job 실행
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

현재 기준 다음 실제 작업은 아래 순서로 재고정한다.

1. review-required 상태에서 subtitle/preview/export gating의 추가 경계와 승인 후 반영 규칙을 세분화
2. TTS replacement approval/output contract에서 stale approval 차단과 approved read-path decision-state surface 이후에도 남아 있는 추가 경계를 선별 보강
3. partial regeneration preflight의 backend read-only/prediction contract와 frontend resume 경계에서 남은 작은 경계를 계속 세분화
4. 그 다음 `local_pipeline`의 partial regeneration / output 경로를 최소 단위로 점진 정리
5. thin editor 범위에서 아직 직접 검증이 약한 남은 고위험 경로를 보강

2026-07-04 최신 누적 메모:

- output operator copy prompt도 non-list stale `tracks[].clips` 값을 실제 clip count처럼 세지 않고 건너뛰어, approved preview/export 경로가 valid track summary prompt surface만 유지하도록 정리했다
- preview renderer도 non-list stale `tracks[].clips` 값을 track summary나 narration source list로 순회하지 않고 건너뛰어, approved preview visible surface가 valid track summary/input만 유지하도록 정리했다
- CapCut export adapter도 non-list stale `tracks[].clips` 값을 voiceover/video/audio segment source처럼 순회하지 않고 건너뛰어, approved export surface가 valid track input만 유지하도록 정리했다
- subtitle render의 timeline segment read-path도 non-list stale `tracks[].clips` 값을 subtitle segment source처럼 순회하지 않고 건너뛰어, approved subtitle output이 valid track input만 기준으로 segment order를 잡도록 정리했다
- review approval의 TTS apply read-path도 stale non-dict `tracks` entry를 target narration track처럼 읽지 않고 건너뛰어, approved narration asset swap이 valid narration track input에만 적용되도록 정리했다
- output operator copy prompt도 `track_type` 없이 남은 stale minimal-dict `tracks` entry를 빈 track summary처럼 노출하지 않고 건너뛰어, approved preview/export 경로가 canonical track summary prompt surface만 유지하도록 정리했다
- output operator copy prompt도 stale non-dict `tracks` entry를 raw track summary 생성 예외로 터뜨리지 않고 건너뛰어, approved preview/export 경로가 valid track summary prompt surface만 유지하도록 정리했다
- output operator copy prompt도 `segment_id` 없이 남은 stale minimal-dict `review_flags` entry를 valid blocker처럼 노출하지 않고 건너뛰어, approved preview/export 경로가 canonical blocker identity를 가진 prompt surface만 유지하도록 정리했다
- output operator copy prompt도 `recommendation_id`나 `target_segment_id` 없이 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation처럼 노출하지 않고 건너뛰어, approved preview/export 경로가 canonical recommendation identity를 가진 prompt surface만 유지하도록 정리했다
- output operator copy prompt도 stale non-dict `pending_recommendations` entry를 raw dict 변환 예외로 터뜨리지 않고 건너뛰어, approved preview/export 경로가 valid recommendation prompt surface만 유지하도록 정리했다
- output operator copy prompt도 stale non-dict `review_flags` entry를 raw dict 변환 예외로 터뜨리지 않고 건너뛰어, approved preview/export 경로가 valid blocker prompt surface만 유지하도록 정리했다
- review snapshot의 blocked persisted operator guidance 재사용도 blocker surface 기반 hidden reuse key로 좁혀, legacy no-key guidance나 다른 blocker를 기준으로 저장된 stale guidance가 현재 `review_flags`/pending blocker truth를 덮어쓰지 않게 정리했다
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
- review guidance prompt의 `pending_recommendations` surface도 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale `recommendation_type`를 canonical lowercase type으로 정리해 operator guidance prompt가 approved/read-path recommendation type 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.target_segment_id` surface도 whitespace stale `target_segment_id`를 trim 기준으로 정리해 operator guidance prompt가 TTS/output read-path의 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `review_flags.code` surface도 legacy `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale code를 canonical lowercase code로 정리해 operator guidance prompt가 review/output gating의 canonical review-flag 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `review_flags.segment_id` surface도 whitespace stale `segment_id`를 trim 기준으로 정리해 operator guidance prompt가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `review_flags.message` surface도 whitespace stale `message`를 trim 기준으로 정리해 operator guidance prompt가 API response 쪽 canonical blocker message 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 message 없는 `review_flags` surface도 canonical default blocker message를 채워 operator guidance prompt가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- heuristic/local review guidance fallback도 message 없는 valid `review_flags`를 generic blocker 문구로 뭉개지 않고 canonical default blocker message를 action item으로 surface해 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- heuristic/local review guidance fallback도 `reason` 없는 valid `pending_recommendations`를 generic blocker 문구로 뭉개지 않고 canonical default blocker message를 action item으로 surface해 review/output gating과 API response 쪽 default blocker reason 기준을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.reason` surface도 whitespace stale `reason`을 trim 기준으로 정리해 operator guidance prompt가 API response 쪽 canonical recommendation reason 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.decision_state` surface도 legacy `" Approved "` 같은 mixed-case stale decision state를 canonical lowercase로 정리해 operator guidance prompt가 API response 쪽 canonical decision-state 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.selected_asset_id` surface도 whitespace stale asset id를 trim 기준으로 정리해 operator guidance prompt가 API response 쪽 canonical selected asset id 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.recommendation_id` surface도 whitespace stale recommendation id를 trim 기준으로 정리해 operator guidance prompt가 approve/output 쪽 canonical recommendation identity 기준과 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.created_at` surface도 whitespace stale created_at 값을 trim 기준으로 정리해 operator guidance prompt가 approve/output 쪽 recommendation metadata truth와 같은 방향을 유지하게 정리했다
- review guidance prompt의 `pending_recommendations.payload.selected_asset_uri` surface도 whitespace stale asset uri를 trim 기준으로 정리해 operator guidance prompt가 TTS approval/output 쪽 canonical selected asset uri 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.recommendation_type` surface도 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale type을 canonical lowercase type으로 정리해 preview/export guidance prompt가 review guidance 및 output truth와 같은 recommendation type 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.target_segment_id` surface도 whitespace stale segment id를 trim 기준으로 정리해 preview/export guidance prompt가 review guidance 및 output truth와 같은 canonical segment id 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.reason` surface도 whitespace stale reason을 trim 기준으로 정리해 preview/export guidance prompt가 review guidance 및 output truth와 같은 canonical recommendation reason 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.selected_asset_id` surface도 whitespace stale asset id를 trim 기준으로 정리해 preview/export guidance prompt가 review guidance 및 TTS/output truth와 같은 canonical selected asset id 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.recommendation_id` surface도 whitespace stale recommendation id를 trim 기준으로 정리해 preview/export guidance prompt가 approve/output 쪽 canonical recommendation identity 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.created_at` surface도 whitespace stale created_at 값을 trim 기준으로 정리해 preview/export guidance prompt가 approve/output 쪽 recommendation metadata truth와 같은 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.payload.selected_asset_uri` surface도 whitespace stale asset uri를 trim 기준으로 정리해 preview/export guidance prompt가 TTS approval/output 쪽 canonical selected asset uri 기준을 유지하게 정리했다
- output operator copy prompt의 `pending_recommendations.decision_state` surface도 legacy `" Approved "` 같은 mixed-case stale decision state를 canonical lowercase로 정리해 preview/export guidance prompt가 approve/read-path 쪽 canonical decision-state 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 `review_flags.code` surface도 legacy `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale code를 canonical lowercase로 정리해 preview/export guidance prompt가 review/output gating의 canonical review-flag 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 `review_flags.segment_id` surface도 whitespace stale `segment_id`를 trim 기준으로 정리해 preview/export guidance prompt가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 `review_flags.message` surface도 whitespace stale `message`를 trim 기준으로 정리해 preview/export guidance prompt가 review/output gating과 API response 쪽 canonical blocker message 기준과 같은 방향을 유지하게 정리했다
- output operator copy prompt의 message 없는 `review_flags` surface도 canonical default blocker message를 채워 preview/export guidance prompt가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다

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
