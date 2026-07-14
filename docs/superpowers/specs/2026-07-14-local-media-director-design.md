# Local Media Director Design

**Date:** 2026-07-14  
**Status:** approved; implementation plan created
**Scope:** VideoBox의 로컬 B-roll 자동 태깅·검색·추천, BGM/SFX 추천, 대화형 AI 디렉터와 수동 편집의 통합

## 1. 결정과 목표

VideoBox는 Gemini를 기본 또는 자동 fallback으로 사용하지 않는다. 로컬 LM Studio만 기본 AI 경로로 사용한다. 현재 개발 PC smoke에서는 `qwen/qwen3.6-35b-a3b`가 vision capability를, `text-embedding-bge-m3`가 embedding capability를 제공함을 확인했지만, 배포/실행 시에는 이 모델명을 가정하지 않는다. 시작 전 capability preflight가 모델 key/variant, `vision`, structured JSON, embedding 가용성, loaded state, 허용 context/profile을 확인해 현재 실행 profile을 고정한다.

사용자는 검색어를 생각하지 않아도 된다. 대본을 붙여넣거나 파일로 입력하면 VideoBox가 구간별 의도·분위기·전환을 해석하고, 로컬 자산에서 B-roll, BGM, SFX 후보를 제안한다. 사용자는 미리보기와 근거를 확인한 뒤에만 후보를 편집 초안에 적용한다.

자동 추천은 수동 편집을 대체하지 않는다. 같은 편집기에서 직접 자산을 고르고 구간에 배치하거나, AI에게 자연어로 기존 선택을 교체·제거·조정하도록 요청할 수 있다.

## 2. 사용자 제작 흐름

1. 사용자가 프로젝트를 만들고 대본을 입력한다. 나레이션은 즉시 입력하거나 이후에 추가할 수 있다. 대본이 없는 경우에도 `수동 편집`으로 진입할 수 있지만 script-first 자동 proposal은 만들지 않는다.
2. 사용자가 B-roll 폴더/파일을 가져오면 비동기 로컬 분석 job이 생성된다. 분석 중에도 기존 편집 작업은 가능하다.
3. FFmpeg가 duration, codec, aspect ratio, representative frames, scene boundaries를 추출한다. 긴 영상은 장면 경계 기준의 분석 단위로 나뉘지만 원본 파일은 변경하지 않는다.
4. capability preflight가 선택한 LM Studio Vision model이 대표 프레임을 읽어 구조화 태그·설명·신뢰도·검수 필요 여부를 JSON Schema로 반환한다. 선택된 local embedding model은 태그/설명/대본 구간을 임베딩해 로컬 의미 검색을 제공한다.
5. AI 디렉터는 대본 구간과 활성 편집 구간을 문맥으로 B-roll/BGM/SFX 추천 묶음을 만든다. 각 후보에는 미리보기, 적용 범위, 추천 근거, 점수, 라이선스/가용성 상태가 있어야 한다.
6. 사용자가 카드에서 개별 적용 또는 묶음 적용을 누를 때만 editing session의 candidate timeline을 변경한다. 적용 전에는 add/replace/remove placement, loop/trim/crop, BGM gain/ducking, SRT/caption 영향이 표시된 preflight diff를 보여준다. `B-roll만 적용`, `B-03만 교체`, `전체 6개 변경 적용`처럼 scope를 좁힐 수 있고, 한 번의 적용은 하나의 atomic mutation이다. 모든 기존 review/approval/output gate는 유지한다.
7. 사용자는 대화로 “B-roll 3번을 사람 없는 장면으로 바꿔줘”, “음악 2번 볼륨을 낮춰줘”, “효과음 5번을 삭제해줘”처럼 변경을 요청한다. AI는 수정 후보만 제시하고 명시적 적용 전에는 상태를 변경하지 않는다. 대본이 수정되면 영향 구간 proposal만 stale로 표시하고 refresh를 제안하며, 기존 placement를 자동 변경하지 않는다.

## 3. AI 디렉터 UX

### 3.1 화면 배치

- Desktop: 편집기 우측에 기본 폭 360–420px의 고정 가능한 `AI 디렉터` 패널을 둔다. 패널은 접을 수 있다. 패널 상단 context bar는 현재 segment/timecode, 선택 placement, active proposal revision, `draft`/`applied` 상태를 항상 보여준다.
- 편집기 중앙의 영상 미리보기와 하단 타임라인은 대화 중에도 유지한다.
- 추천을 열면 타임라인 바로 위에 비교 트레이가 나타난다. B-roll은 썸네일/짧은 preview, BGM/SFX는 재생 가능한 audio preview를 제공한다.
- Mobile/narrow viewport: AI 디렉터는 unsent draft를 보존하는 modal bottom sheet로 전환한다. Escape/back/close, focus trap, timeline으로의 복귀가 필요하다. 비교 트레이는 하나씩 전체 폭 carousel로 보이며 `비교`, `교체`, `적용` 행동을 카드 안에서 수행한다.

### 3.2 대화와 제안의 분리

- 대화 메시지, AI 응답, 후보 묶음, 사용자 적용 결정은 project-scoped 기록으로 영속한다.
- AI 응답은 자연어와 machine-readable proposal을 함께 가진다.
- proposal에는 immutable proposal id, base editing-session revision, asset-index revision, expiry, target segment ids, 매체별 후보, 각 후보의 stable id, visible reference code, reason, score, preview URI, proposed controls가 포함된다.
- 대화는 편집 변경 그 자체가 아니며 undo 대상이 아니다. proposal 적용/해제/수동 편집만 undo 대상이다.

### 3.3 Interaction states, preview, accessibility

AI 디렉터의 상태는 `script_required`, `idle`, `analysis_running`, `proposal_ready`, `applying`, `blocked`, `error`로 명시한다. `blocked`는 LM Studio 모델/자원 미가동처럼 사용자가 복구할 수 있는 상태이고, `error`는 재시도 가능한 실제 실행 오류다. 파일별/scene별 분석 진행률, 추정 대기열 위치, 취소/재시도, 저품질 tag 경고와 수동 tag 편집 진입을 제공한다.

B-roll preview는 선택 scene window의 정확한 in/out, loop/trim/crop을 사용한다. audio preview는 자동 재생하지 않고, 새 preview를 시작하면 이전 preview를 중지하며, 현재 narration 문맥에서 solo/mute와 normalized audition을 제공한다. 모든 preview control에는 asset reference/timecode label, keyboard operation, visible focus, screen-reader live status가 필요하다. 상태는 색상만으로 구분하지 않으며 reduced motion을 존중한다.

### 3.4 Manual editor parity and ranking control

편집기에는 `AI 디렉터`와 `수동` entry를 제공하되 route를 분리하지 않는다. 수동 사용자는 selected range/playhead에 add/replace할 수 있고, B-roll은 drag/drop 또는 action button, BGM/SFX는 범위/controls를 명시해 배치한다. 라이브러리는 type, aspect, duration, analyzed/review-needed, favorite filter를 제공한다.

추천 카드에는 간결한 reason chips와 diversity group을 표시한다. 사용자는 project-scoped `pin`, `제외 asset`, `제외 creator/tag`를 지정할 수 있다. 후보가 부족할 때만 `왜 이 후보뿐인가`를 제공한다. favorite/recent usage는 반복 패널티를 이기지 못한다.

## 4. 자산 인텔리전스

### 4.1 B-roll

태그 schema는 다음 레이어를 가진다: 장소, 행동, 시간대, 날씨, 인물/물체, 감정, 분위기, 주제 연결, 장면, 색감/톤, 촬영 방식, 계절, 국가/지역. 추가 기술 메타데이터는 duration, resolution, aspect ratio, codec, scene windows, thumbnail URI다.

분석은 현재 generic job과 구분된 durable `MEDIA_ANALYSIS` job/entity를 사용하며 상태 `queued`, `running`, `succeeded`, `needs_review`, `blocked`, `failed`, `cancelled`를 가진다. 결과 태그가 최소 레이어/태그 품질 규칙을 통과하지 않거나 JSON schema를 통과하지 못하면 `needs_review`로 저장한다. 낮은 품질 결과를 자동 추천의 상위 후보로 올리지 않는다.

`VisionProvider.analyze_images`와 `EmbeddingProvider.embed`는 기존 text-only local provider와 별도 adapter다. LM Studio OpenAI-compatible image payload 및 embeddings endpoint를 사용하며, local preflight는 loopback `127.0.0.1:1234`만 허용하고 redirect를 따르지 않는다. 각 요청에는 timeout과 size limit이 있다.

기본 실행 예산은 VLM concurrency `1`, source clip당 representative frame 최대 `6`, frame long edge `768px`, encoded image 최대 `1.5MiB`, FFmpeg 단계 `60초`, VLM 단계 `120초`, embedding 단계 `15초`, retry 최대 `2회`(5초/30초 backoff)다. Qwen 35B Q4가 긴 context로 이미 로드된 현재 PC profile에서는 병렬 VLM 처리나 전체 영상을 한 요청으로 보내지 않는다. 자원 부족/모델 미가동은 `blocked`로, JSON/실행 오류는 `failed`로 구분한다. 취소는 FFmpeg frame stage와 VLM stage 사이에서 cooperative하게 확인하며 늦게 도착한 결과는 저장하지 않는다.

추천된 scene window의 in/out 및 crop/loop/trim controls는 editing-session mutation에 그대로 기록한다. preview, FFmpeg final renderer, real CapCut draft adapter는 같은 controls를 소비해야 하며, export 단계가 임의로 다른 구간을 재선택하거나 재trim해서는 안 된다.

### 4.2 음악과 효과음

- BGM은 전체 또는 명시된 범위에 대한 mood, energy, genre, vocal presence, recommended use, duration, license metadata를 가진다.
- SFX는 action/event, intensity, mood, duration, recommended use, license metadata를 가진다.
- Starter Media Pack의 verified asset 계약은 유지한다. global verified/indexed asset은 recommendation 후보로 보일 수 있지만, timeline에는 apply transaction 안에서 재검증·materialize된 project-local asset만 적용할 수 있다. materialize 실패는 candidate timeline을 변경하지 않는다.
- user-owned B-roll은 `rights=unknown`이 기본이다. 기본 정책은 local draft/export를 막지 않되 output 화면에 저작권 확인 warning을 보이는 것이다. Starter Pack의 verified license 상태와 혼동하지 않는다.
- asset 없는 가상 추천은 적용 후보가 될 수 없다. output 직전 renderer/CapCut은 project-local path, asset content SHA-256, media revision을 재검증하고 stale이면 re-materialize 또는 명시적 복구를 요구하며 조용히 대체하지 않는다.

### 4.3 검색과 ranking

각 candidate score는 다음의 가중 조합으로 생성한다: 대본 구간 의미 유사도, 구조 태그 일치도, duration/aspect ratio 적합도, 사용자의 명시 조건, favorite/recent-use 보정, 중복/반복 패널티, availability/license eligibility. BGE-M3가 unavailable일 때는 normalized Korean tags/synonyms와 lexical matching으로 degrade하며, deterministic tie-break(asset stable id)를 사용한다.

점수는 설명 가능한 근거로 반환한다. raw embedding score만 UI에 노출하지 않는다.

## 5. 번호와 직접 편집

번호는 매체 종류와 scope를 구분한다.

- 후보 카드: active proposal revision 범위의 `P12-B-03`, `P12-M-02`, `P12-S-05`
- 실제 timeline 배치: `B-03`, `M-02`, `S-05`
- SFX에는 적용 시간도 함께 표시한다. 예: `S-05 · 00:38–00:39`.
- visible 번호는 화면 순서에 맞춰 보이지만, 모든 대화 명령은 immutable asset/placement/proposal id로 해석한다. `B-03`는 timeline placement, `P12-B-03`는 proposal candidate다. 먼저 currently open proposal scope를 해석하고 둘 이상이 매칭되면 disambiguation card를 보여준다. 화면 재정렬 또는 동일 asset의 복수 placement 때문에 잘못된 자산을 변경하면 안 된다.

수동 모드에서 사용자는 라이브러리를 검색·미리보기·선택해 특정 구간에 B-roll/BGM/SFX를 직접 배치한다. 자동 추천, 수동 선택, 대화형 수정은 동일한 editing-session mutation 모델을 사용한다.

## 6. Undo/Redo

- 최근 10개의 성공한 사용자 action transaction을 project에 영속한다. proposal bundle apply가 여러 asset을 바꾸어도 하나의 Ctrl+Z action이다.
- 지원 범위: B-roll/BGM/SFX 적용, 교체, 해제, controls 변경, 대화 proposal 묶음 적용, caption/overlay 변경.
- UI는 named history(`B-03 교체`, `추천 묶음 적용`)와 undo/redo 버튼, `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`/`Ctrl/Cmd+Y` shortcut을 제공한다. text input/IME composition 중에는 shortcut을 가로채지 않는다.
- 새 mutation은 redo stack을 비운다. stale revision conflict 또는 이미 없는 asset을 복원하려는 경우 atomic하게 실패하고 현재 session은 손상시키지 않으며, disabled reason/restore action을 보여준다.
- undo/redo 또는 새 mutation은 affected review/approval/output freshness를 무효화한다. 과거 MP4/CapCut draft는 history로 보존하되 current timeline output처럼 표시하지 않는다.
- 대화 로그와 분석 결과는 삭제하지 않는다.

## 7. 로컬 전용과 오류 복구

- Vision/text/embedding 요청은 LM Studio `http://127.0.0.1:1234` loopback allowlist만 사용한다. Gemini/외부 AI provider로 fallback하지 않는다.
- 모델 미로드/서버 미가동/timeout/schema invalid는 외부로 전송하지 않는다. UI는 정확한 원인과 `LM Studio 시작`, `분석 재시도`, `수동 태그` 복구 행동을 제시한다.
- 분석 cache key는 original content SHA-256, frame/scene extractor version, FFmpeg version, model key/variant/quantization, prompt/schema version으로 구성한다. 결과는 frame/scene provenance와 selectable in/out window를 저장한다. source hash/revision이 달라지면 tags, embeddings, previews, proposals를 stale 처리한다. derived frame/preview는 project analysis cache에 저장하고 asset delete 즉시 제거하며 stale cache는 30일 후 prune한다. source disappearance는 asset unavailable로 표시하고 새 proposal/apply를 막지만 기존 history는 보존한다.
- job은 idempotency key, durable attempt/error/next_retry를 가지며 restart 뒤 orphan running job을 안전하게 queued로 복구한다. retry는 capped exponential backoff이고 cancel은 idempotent하며 partial tag를 commit하지 않는다.
- 입력 영상과 프레임은 project-local 처리 범위를 벗어나 전송하지 않는다.

## 8. 검증 계약

1. deterministic fake vision/text/embedding providers와 HTTP/socket guard로 모든 normal unit/API/E2E test가 localhost LM Studio에 연결하지 않음을 보장한다.
2. 별도 opt-in local integration smoke가 capability/model profile을 확인한 뒤 현재 LM Studio Vision → JSON schema tags → BGE-M3 search → proposal을 실행한다. capability가 없으면 skip하며 CI 기본 경로에서는 실행하지 않는다.
3. async test는 sleep 없이 deterministic queue/fake clock을 사용한다. B-roll ingest/analysis, script-first proposal, candidate preview, explicit apply, B/M/S numbered natural-language target resolution, manual placement, persistent 10-step undo/redo, refresh recovery, failed-analysis recovery를 RED-first contract/E2E test로 고정한다.
4. RED regression은 duplicate job, cancel-late-result, retry/restart, cache invalidation, materialize failure, source mutation after proposal, renderer/CapCut hash mismatch, atomic proposal-bundle undo/redo, stale proposal rejection, keyboard/IME shortcut guard를 포함한다.
5. 실제 local media library에서 B-roll/BGM/SFX를 materialize해 candidate timeline → SRT → FFmpeg MP4 → real CapCut draft를 확인한다.
6. full Python 3.12 backend, frontend tests/build, real pack verifier, long-form Korean smoke는 기존 기준으로 계속 green이어야 한다.

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
