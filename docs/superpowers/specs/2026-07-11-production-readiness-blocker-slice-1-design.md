# VideoBox Production-Readiness Blocker Slice 1 설계

- 기준 HEAD: `dd03143`
- 작성일: 2026-07-11
- 상태: 구현 전 승인 설계

## 1. 목적

이 작업은 현재 VideoBox를 내부 데모 수준에서 실제 유튜브 제작에 사용할 수 있는 최소 production-readiness 수준으로 올리는 첫 blocker slice다. 범위는 새 사용자의 첫 프로젝트 생성부터 편집 결과의 SRT, 최종 MP4, CapCut draft 일관성까지다.

기존 경량 편집기와 provider 경계는 유지하고, 풀 NLE 기능이나 새로운 클라우드 인프라는 추가하지 않는다.

## 2. 확인된 기준 상태

현재 HEAD에서 다음 문제가 확인됐다.

1. 웹 첫 화면은 프로젝트가 없을 때 안내만 표시하고 프로젝트 생성, narration ingest, script ingest로 이어지지 않는다.
2. music recommendation에 실제 asset이 없어도 synthetic `music/suggested` URI가 timeline에 들어갈 수 있다.
3. final render 또는 CapCut 생성 실패 응답의 artifact는 nullable인데 frontend contract와 화면은 non-null로 가정한다.
4. caption partial regeneration의 수정 문구가 candidate timeline에는 존재해도 subtitle/final output이 별도 segment 저장소를 다시 읽어 원문으로 돌아갈 수 있다.
5. 짧은 B-roll 또는 TTS 소스가 clip duration보다 짧을 때 final output이 조기 종료되거나 미디어가 비는 구간이 생길 수 있다.
6. partial regeneration이 생성하는 `export_overlays`가 FFmpeg final renderer와 real CapCut draft adapter에서 소비되지 않는다.
7. backend API tests의 기본 `create_app` 경로가 localhost LLM runtime을 사용할 수 있어 회귀 테스트가 비결정적이다.

## 3. 선택한 접근법

각 blocker를 계약 우선 수직 슬라이스로 처리한다.

1. 문제를 재현하는 E2E 또는 contract test를 추가하고 단독 실행에서 RED를 확인한다.
2. 해당 계약을 만족하는 최소 production code를 구현한다.
3. 관련 focused suite를 GREEN으로 만든다.
4. 여섯 범위가 모두 연결된 뒤 frontend/backend 전체 회귀와 10분 smoke를 실행한다.

계층별 일괄 수정은 중간 contract drift를 숨길 수 있고, 증상별 patch는 동일 데이터를 여러 출력 경로가 다르게 해석하는 현재 문제를 유지할 수 있으므로 선택하지 않는다.

## 4. 기능 설계

### 4.1 빈 첫 화면 온보딩

웹 API client에 project create, narration upload, script upload 함수를 추가한다. 빈 상태 화면은 다음 상태 머신을 사용한다.

`empty -> creating project -> ingesting optional inputs -> project ready`

- 프로젝트 이름은 필수다.
- narration과 script는 둘 다 선택 사항이며 어느 한쪽부터 ingest할 수 있다.
- 생성 성공 직후 새 프로젝트를 선택하고 dashboard 데이터를 다시 읽는다.
- 업로드 일부가 실패하면 생성된 프로젝트를 숨기지 않고 성공/실패 항목을 구분해 재시도할 수 있게 한다.
- 새로고침 후 서버의 project 목록을 다시 읽어 생성된 프로젝트를 계속 선택할 수 있어야 한다.
- 요청 실패는 사용자가 이해할 수 있는 한글 오류와 재시도 동작으로 표시한다.

### 4.2 실제 music asset 없는 추천

music recommendation은 추천 metadata와 playable asset을 구분한다.

- `selected_asset_id`와 해석 가능한 local `storage_uri`가 모두 유효한 경우에만 BGM timeline clip을 만든다.
- 추천 문구, mood, score만 있고 asset이 없으면 추천 결과는 보존하지만 timeline에는 BGM clip을 만들지 않는다.
- timeline builder는 synthetic `music/suggested` URI를 만들지 않는다.
- legacy timeline read는 유지하되 새 build 경로에서 invalid BGM source를 생성하지 않는다.
- final renderer도 존재하지 않는 BGM 파일을 조용히 무시하지 않고, timeline에 명시된 실제 asset이 사라졌다면 actionable render error를 반환한다.

### 4.3 nullable artifact와 UI 오류 격리

final render와 CapCut draft 응답은 다음 의미를 가진다.

- 성공: `status=succeeded`, artifact non-null
- 실패: `status=failed`, artifact null, error detail non-empty
- 진행 중: 기존 job contract 유지

Frontend TypeScript type을 이 contract와 일치시키고 artifact를 사용하기 전 discriminated status를 검사한다. 실패한 작업은 파일 링크 대신 오류 카드와 재시도 버튼을 표시한다.

React root에는 ErrorBoundary를 둔다. 예상하지 못한 render exception이 발생해도 전체 빈 화면 대신 복구 안내와 dashboard 다시 불러오기 동작을 제공한다. ErrorBoundary는 API 실패를 대체하지 않고 마지막 UI 격리선으로만 사용한다.

### 4.4 caption partial regeneration SSOT

partial regeneration이 만든 candidate timeline의 segment snapshot을 해당 output의 effective caption SSOT로 사용한다.

- 수정된 `caption_text`, `start_ms`, `end_ms`를 candidate timeline segment에 영속화한다.
- subtitle render는 timeline snapshot을 우선 읽고, segment snapshot이 없는 legacy timeline만 기존 DB segment를 fallback으로 읽는다.
- FFmpeg final과 CapCut draft는 동일한 SRT 또는 동일 effective segment collection을 소비한다.
- 저장 후 process 재시작이나 UI 새로고침이 있어도 candidate timeline을 기준으로 동일한 수정 caption이 나온다.
- 원본 transcript/segment를 파괴적으로 덮어쓰지 않아 원본/수정 비교 기능을 보존한다.

### 4.5 clip duration 정규화

timeline clip duration을 출력 계약으로 사용한다.

- B-roll video가 짧으면 loop하고 clip end에서 trim한다.
- still image는 clip duration 동안 유지한다.
- B-roll video가 길면 필요한 구간만 trim한다.
- TTS replacement audio가 짧으면 발화를 반복하지 않고 silence pad한 뒤 clip end에서 trim한다.
- TTS replacement audio가 길면 clip end에서 trim한다.
- 최종 mux는 짧은 보조 track 때문에 narration/timeline보다 먼저 끝나지 않는다.
- renderer helper가 source probe 결과와 clip duration을 받아 명시적인 normalization filter/input option을 만든다.

### 4.6 export overlays 반영

candidate timeline의 `export_overlays`를 canonical overlay collection으로 정규화하고 두 exporter가 같은 collection을 소비한다.

- text/card overlay: FFmpeg에서는 text/card filter, CapCut에서는 실제 text material/track으로 생성한다.
- local image/table-image overlay: FFmpeg에서는 image overlay, CapCut에서는 실제 image material/track으로 생성한다.
- 위치, 시작 시각, 지속 시간, 표시 문구 또는 source URI를 보존한다.
- 현재 canonical schema 밖의 overlay type은 조용히 누락하지 않는다. API artifact에는 warning을 남기고, 필수 필드가 잘못된 overlay는 명시적 validation/render error로 처리한다.
- CapCut contract test는 manifest 모양만 검사하지 않고 real adapter가 생성한 draft JSON/material collection에 overlay가 존재함을 확인한다.

## 5. 데이터 흐름

1. 사용자가 project를 만들고 narration/script를 ingest한다.
2. deterministic provider가 transcript/segment/recommendation을 만든다.
3. timeline builder는 실제 asset이 있는 추천만 media track에 적용한다.
4. editing session partial regeneration은 effective segment와 canonical overlay를 포함한 candidate timeline을 저장한다.
5. subtitle renderer가 candidate timeline segment에서 SRT를 만든다.
6. FFmpeg final renderer와 CapCut adapter가 같은 timeline, SRT, overlay contract를 소비한다.
7. output job은 성공 artifact 또는 nullable failure artifact/error detail을 반환한다.
8. UI는 status를 기준으로 성공 결과나 복구 가능한 오류를 표시한다.

## 6. 테스트 설계

### 6.1 RED 계약

각 범위는 기존 구현에서 실패하는 아래 테스트로 시작한다.

1. 프로젝트가 0개인 UI에서 create + narration/script ingest 후 새로고침해도 프로젝트가 보인다.
2. selected music asset이 없는 recommendation으로 만든 timeline에 BGM clip이 없다.
3. final/CapCut failure artifact가 null이어도 화면이 crash하지 않고 오류/재시도를 표시하며, 강제 render exception은 ErrorBoundary가 격리한다.
4. caption partial regeneration 후 subtitle API, final render input, CapCut subtitle이 모두 수정 문구를 포함한다.
5. 짧은 B-roll/TTS fixture로 렌더한 결과 duration이 timeline duration과 허용 오차 안에서 일치한다.
6. overlay가 포함된 timeline의 FFmpeg output frame과 real CapCut draft material에 overlay가 존재한다.
7. 기본 test app factory를 사용해도 localhost LLM endpoint를 호출하지 않는다.

### 6.2 회귀 범위

- frontend: 기존 75개 전체와 신규 실패/복구/새로고침/ErrorBoundary E2E 또는 component tests
- backend: 기존 605개 전체와 신규 contract/render/export tests
- 실행 Python: repository `.venv`의 Python 3.12
- frontend production build
- 테스트 중 localhost LLM request가 발생하지 않았다는 spy/forbidden transport assertion

기존 숫자는 기준선이다. 최종 보고에는 신규 테스트를 포함한 실제 수와 실패/skip 여부를 적는다.

## 7. 실제 10분 한국어 smoke

600초 분량의 실제 한국어 narration media fixture 하나를 사용한다. LLM, STT, TTS 결과만 deterministic provider로 고정하고 파일 ingest, 저장, editing session, subtitle, FFmpeg final rendering은 production 경로를 사용한다.

검증 항목은 다음과 같다.

- narration/script ingest 성공
- partial caption 수정 후 재시작/재조회에도 수정 문구 유지
- SRT에 수정된 한국어 문구 포함
- 짧은 B-roll이 전체 clip 범위에 존재
- overlay가 지정 구간의 추출 frame에 보임
- MP4 duration이 600초 timeline과 허용 오차 안에서 일치
- final artifact가 실제로 존재하고 `ffprobe`가 읽을 수 있음

저사양에서도 실행 가능하도록 해상도와 bitrate는 낮추되 duration과 production FFmpeg code path는 축소하지 않는다.

## 8. 오류 처리와 관측성

- backend output failure는 job status, stable error code, 사용자용 message, nullable artifact를 함께 보존한다.
- frontend는 네트워크 실패, backend job 실패, 예상하지 못한 React render 실패를 구분한다.
- overlay validation failure와 missing media source는 output job log/error detail에서 대상 clip/overlay ID를 식별할 수 있어야 한다.
- 자동 복구가 데이터 손실을 만들 수 있는 경우에는 실패를 노출하고 사용자가 재시도하게 한다.

## 9. 재사용 판단

- 기존 storage/project ingest API: `adopt as-is`, frontend 연결만 추가한다.
- 기존 timeline/recommendation normalization: `partial port`, synthetic BGM 생성 경로만 계약에 맞게 좁힌다.
- 기존 FFmpeg renderer와 PyCapCut adapter: `partial port`, duration/overlay 지원 helper를 추가한다.
- 외부 풀 편집기 또는 별도 렌더 프레임워크: `exclude`, 현재 경계를 넓히고 회귀 위험을 높이므로 이번 slice에 반입하지 않는다.
- BrollBox 전체 복제: `exclude`, 기존 VideoBox renderer/exporter 경계를 유지한다.

## 10. 범위 제외

- 풀 timeline editor 또는 keyframe UI
- 음악 asset 검색/다운로드 서비스 신규 구축
- cloud render farm
- 실제 Whisper/XTTS/LLM 품질 벤치마크
- CapCut의 모든 overlay/effect type 지원
- 이번 여섯 blocker와 무관한 구조 리팩터링

## 11. 완료 기준

다음이 모두 충족될 때만 이 slice를 완료로 본다.

1. 여섯 blocker 각각의 RED 증거와 GREEN 회귀 증거가 있다.
2. test `create_app`이 localhost LLM을 호출하지 않는다.
3. frontend 전체, production build, backend 전체가 통과한다.
4. 실제 10분 한국어 sample의 ingest→edit→SRT→MP4 smoke가 통과한다.
5. git diff/status를 검토하고 불필요한 파일이 없다.
6. implementation plan과 development status SSOT가 현재 HEAD 기준 상태와 누적 진행률을 반영한다.
7. 코드리뷰에서 확인된 blocker가 모두 해결됐다.
8. 논리적으로 닫힌 커밋을 만들고 push 여부를 명시한다.
