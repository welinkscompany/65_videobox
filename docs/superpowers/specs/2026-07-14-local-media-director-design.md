# Local Media Director Design

**Date:** 2026-07-14  
**Status:** proposed for user review  
**Scope:** VideoBox의 로컬 B-roll 자동 태깅·검색·추천, BGM/SFX 추천, 대화형 AI 디렉터와 수동 편집의 통합

## 1. 결정과 목표

VideoBox는 Gemini를 기본 또는 자동 fallback으로 사용하지 않는다. 로컬 LM Studio에 이미 로드된 `qwen/qwen3.6-35b-a3b` vision model과 `text-embedding-bge-m3` embedding model만을 기본 AI 경로로 사용한다.

사용자는 검색어를 생각하지 않아도 된다. 대본을 붙여넣거나 파일로 입력하면 VideoBox가 구간별 의도·분위기·전환을 해석하고, 로컬 자산에서 B-roll, BGM, SFX 후보를 제안한다. 사용자는 미리보기와 근거를 확인한 뒤에만 후보를 편집 초안에 적용한다.

자동 추천은 수동 편집을 대체하지 않는다. 같은 편집기에서 직접 자산을 고르고 구간에 배치하거나, AI에게 자연어로 기존 선택을 교체·제거·조정하도록 요청할 수 있다.

## 2. 사용자 제작 흐름

1. 사용자가 프로젝트를 만들고 대본을 입력한다. 나레이션은 즉시 입력하거나 이후에 추가할 수 있다.
2. 사용자가 B-roll 폴더/파일을 가져오면 비동기 로컬 분석 job이 생성된다. 분석 중에도 기존 편집 작업은 가능하다.
3. FFmpeg가 duration, codec, aspect ratio, representative frames, scene boundaries를 추출한다. 긴 영상은 장면 경계 기준의 분석 단위로 나뉘지만 원본 파일은 변경하지 않는다.
4. Qwen3.6 Vision이 대표 프레임을 읽어 구조화 태그·설명·신뢰도·검수 필요 여부를 JSON Schema로 반환한다. BGE-M3는 태그/설명/대본 구간을 임베딩해 로컬 의미 검색을 제공한다.
5. AI 디렉터는 대본 구간과 활성 편집 구간을 문맥으로 B-roll/BGM/SFX 추천 묶음을 만든다. 각 후보에는 미리보기, 적용 범위, 추천 근거, 점수, 라이선스/가용성 상태가 있어야 한다.
6. 사용자가 카드에서 개별 적용 또는 묶음 적용을 누를 때만 editing session의 candidate timeline을 변경한다. 모든 기존 review/approval/output gate는 유지한다.
7. 사용자는 대화로 “B-roll 3번을 사람 없는 장면으로 바꿔줘”, “음악 2번 볼륨을 낮춰줘”, “효과음 5번을 삭제해줘”처럼 변경을 요청한다. AI는 수정 후보만 제시하고 명시적 적용 전에는 상태를 변경하지 않는다.

## 3. AI 디렉터 UX

### 3.1 화면 배치

- Desktop: 편집기 우측에 기본 폭 360–420px의 고정 가능한 `AI 디렉터` 패널을 둔다. 패널은 접을 수 있다.
- 편집기 중앙의 영상 미리보기와 하단 타임라인은 대화 중에도 유지한다.
- 추천을 열면 타임라인 바로 위에 비교 트레이가 나타난다. B-roll은 썸네일/짧은 preview, BGM/SFX는 재생 가능한 audio preview를 제공한다.
- Mobile/narrow viewport: AI 디렉터는 하단 sheet로 전환하고, 비교 트레이는 한 후보씩 전체 폭으로 표시한다.

### 3.2 대화와 제안의 분리

- 대화 메시지, AI 응답, 후보 묶음, 사용자 적용 결정은 project-scoped 기록으로 영속한다.
- AI 응답은 자연어와 machine-readable proposal을 함께 가진다.
- proposal에는 target segment ids, 매체별 후보, 각 후보의 stable id, visible reference code, reason, score, preview URI, proposed controls가 포함된다.
- 대화는 편집 변경 그 자체가 아니며 undo 대상이 아니다. proposal 적용/해제/수동 편집만 undo 대상이다.

## 4. 자산 인텔리전스

### 4.1 B-roll

태그 schema는 다음 레이어를 가진다: 장소, 행동, 시간대, 날씨, 인물/물체, 감정, 분위기, 주제 연결, 장면, 색감/톤, 촬영 방식, 계절, 국가/지역. 추가 기술 메타데이터는 duration, resolution, aspect ratio, codec, scene windows, thumbnail URI다.

분석 job은 상태 `queued`, `running`, `succeeded`, `needs_review`, `failed`, `cancelled`를 가진다. 결과 태그가 최소 레이어/태그 품질 규칙을 통과하지 않거나 JSON schema를 통과하지 못하면 `needs_review`로 저장한다. 낮은 품질 결과를 자동 추천의 상위 후보로 올리지 않는다.

### 4.2 음악과 효과음

- BGM은 전체 또는 명시된 범위에 대한 mood, energy, genre, vocal presence, recommended use, duration, license metadata를 가진다.
- SFX는 action/event, intensity, mood, duration, recommended use, license metadata를 가진다.
- Starter Media Pack의 verified asset 계약은 유지한다. materialize된 project-local asset만 timeline에 적용할 수 있다.
- 추천은 실제로 선택 가능한 verified/materialized 상태만 제시한다. asset 없는 가상 추천은 적용 후보가 될 수 없다.

### 4.3 검색과 ranking

각 candidate score는 다음의 가중 조합으로 생성한다: 대본 구간 의미 유사도, 구조 태그 일치도, duration/aspect ratio 적합도, 사용자의 명시 조건, favorite/recent-use 보정, 중복/반복 패널티, availability/license eligibility.

점수는 설명 가능한 근거로 반환한다. raw embedding score만 UI에 노출하지 않는다.

## 5. 번호와 직접 편집

번호는 매체 종류와 scope를 구분한다.

- 후보 카드: `B-roll 1`, `음악 2`, `효과음 5`
- 실제 timeline 배치: `B-03`, `M-02`, `S-05`
- SFX에는 적용 시간도 함께 표시한다. 예: `S-05 · 00:38–00:39`.
- visible 번호는 화면 순서에 맞춰 보이지만, 모든 대화 명령은 immutable asset/placement/proposal id로 해석한다. 화면 재정렬 때문에 잘못된 자산을 변경하면 안 된다.

수동 모드에서 사용자는 라이브러리를 검색·미리보기·선택해 특정 구간에 B-roll/BGM/SFX를 직접 배치한다. 자동 추천, 수동 선택, 대화형 수정은 동일한 editing-session mutation 모델을 사용한다.

## 6. Undo/Redo

- 최근 10개의 성공한 editing-session mutation을 project에 영속한다.
- 지원 범위: B-roll/BGM/SFX 적용, 교체, 해제, controls 변경, 대화 proposal 묶음 적용, caption/overlay 변경.
- UI는 undo/redo 버튼과 `Ctrl+Z`, `Ctrl+Shift+Z`/`Ctrl+Y` shortcut을 제공한다.
- 새 mutation은 redo stack을 비운다. stale revision conflict 또는 이미 없는 asset을 복원하려는 경우 안전하게 실패하고 현재 session은 손상시키지 않는다.
- 대화 로그와 분석 결과는 삭제하지 않는다.

## 7. 로컬 전용과 오류 복구

- Vision/text/embedding 요청은 LM Studio `http://127.0.0.1:1234`만 사용한다. Gemini/외부 AI provider로 fallback하지 않는다.
- 모델 미로드/서버 미가동/timeout/schema invalid는 외부로 전송하지 않는다. UI는 정확한 원인과 `LM Studio 시작`, `분석 재시도`, `수동 태그` 복구 행동을 제시한다.
- 분석 결과는 source fingerprint와 model id/prompt version을 저장한다. 동일 source와 동일 analyzer version은 캐시를 재사용한다.
- 입력 영상과 프레임은 project-local 처리 범위를 벗어나 전송하지 않는다.

## 8. 검증 계약

1. deterministic fake vision/text/embedding providers로 모든 unit/API/E2E test가 localhost LM Studio에 연결하지 않는다.
2. 별도 opt-in local integration smoke가 현재 LM Studio의 Qwen3.6 Vision으로 대표 프레임 → JSON schema tags → BGE-M3 search → proposal을 확인한다.
3. B-roll ingest/analysis, script-first proposal, candidate preview, explicit apply, B/M/S numbered natural-language target resolution, manual placement, persistent 10-step undo/redo, refresh recovery, failed-analysis recovery를 RED-first contract/E2E test로 고정한다.
4. 실제 local media library에서 B-roll/BGM/SFX를 materialize해 candidate timeline → SRT → FFmpeg MP4 → real CapCut draft를 확인한다.
5. full Python 3.12 backend, frontend tests/build, real pack verifier, long-form Korean smoke는 기존 기준으로 계속 green이어야 한다.

## 9. 비목표

- AI가 사용자 승인 없이 final timeline을 변경하거나 export를 실행하는 기능
- Gemini 또는 외부 cloud AI 자동 fallback
- 원본 B-roll 파일의 파괴적 rename/split/edit
- 자산이 없는 음악/SFX 가상 후보를 timeline에 적용하는 기능
- 현재 단계에서 별도 full nonlinear editor를 새로 만드는 작업

## 10. 단계 분해

이 범위는 하나의 큰 기능이므로 다음 세 implementation slice로 나눈다.

1. **Local media intelligence foundation:** LM Studio Qwen Vision/BGE adapters, asset analysis jobs, metadata schema/index, B-roll batch analysis/review.
2. **Script-first proposal engine:** 대본 구간 intent, B-roll/BGM/SFX ranking/proposals, preview/materialization, explicit apply, local failure recovery.
3. **Director workspace:** 우측 AI panel, proposal cards/numbering, manual editor integration, persistent conversation, 10-step undo/redo, responsive UI and full output E2E.

각 slice는 독립적으로 TDD와 full regression을 거쳐 commit/push 한다. 다음 slice는 직전 slice의 actual provider smoke와 review를 통과한 뒤에 시작한다.
