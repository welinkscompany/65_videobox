# VideoBox Task 19 editor asset browser closeout

## 완료 내용

- 편집기 왼쪽 dock에 project-local B-roll과 Starter Pack BGM/SFX를 위한 callback-only 자산 브라우저를 추가했다. 검색·유형 필터·선택 구간·명시적 적용·권리/검수/오디오 상태를 표시한다.
- 카드는 API 호출, 저장, native player를 소유하지 않는다. project B-roll과 library asset truth는 Route가 각각 독립적으로 읽고, 카드 projection은 stable card ID와 library materialization ID를 보존한다.
- B-roll video/audio/image은 각각 video/audio/정지 image audition으로 정확히 표시한다. image는 두 번째 player가 아니라 기존 PreviewStage 안의 단일 비재생 surface이며, image/audio/video 모두 local URL guard를 통과해야 한다.
- B-roll은 현재 revision의 command port로 직접 적용한다. BGM/SFX는 materialize 성공 뒤에만 같은 port로 적용한다. materialize 실패와 A→B route 전환 뒤 늦은 materialize 완료는 media command를 0회로 유지하고 manifest refresh fence를 사용한다.
- 자산 목록 로드 실패는 브라우저 안내만 표시하며 편집기, 대본, timeline, exact preview를 막지 않는다.

## 검증

- TDD RED→GREEN: projection, browser, one-stage preview, route materialize/apply 순서로 수행했다. final focused frontend는 `6 files / 62 tests passed`였다.
- frontend full: `50 files / 490 tests passed`.
- production build 성공. 기존 500 kB chunk warning만 남았다.
- Editor UI OSS provenance PowerShell verifier 성공, `git diff --check` 성공.
- independent spec/quality review, final gap, source-to-runtime reverse review의 Critical/Important는 0이다. route→projector→callback browser→PreviewStage/EditorCommandPort 경로를 다시 추적했다.
- 전체 Python regression은 실행하거나 통과로 주장하지 않았다. full frontend의 기존 React `act(...)`, jsdom navigation, ErrorBoundary stderr는 비실패 테스트 출력이다.

## 범위와 provenance

- `opencut-classic` pinned SHA `cf5e79e919144200294fb9fed22a222592a0aeea`는 기존 source map의 MIT partial-port reference로만 확인했다. Task 19는 upstream source copy, dependency, runtime import를 추가하지 않았으므로 source map/NOTICE materialization 변경이 없다.
- voice replacement, image-overlay apply, Director/Eugene recommendation, favourite/recent/pin/exclude, ingest, drag/drop, automatic apply, provider/Hermes/Mem0은 범위 밖으로 유지했다.
- 보호 대상 `?? .tmp-final-fence-debug/`는 기존 범위 밖 잔재로 보존했으며 stage/remove하지 않았다.
- 사용자 지시대로 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다. Task 9 사람/환경 acceptance와 CapCut Desktop 실증은 별도다.

## 커밋과 다음 goal

- Task 19 commits: `6a17df0`, `6491b5e`, `127d000`, `abb2309`, `0d7e138`, `7a6892f`.
- next goal은 Task 20 persistent Eugene conversation, inline recommendation, typed Inspector의 별도 written spec 및 사용자 승인이다. Task 19 경계의 asset truth·one preview owner·revision fence를 재사용하되, 새 provider/runtime 작업은 추가 승인 없이는 시작하지 않는다.
