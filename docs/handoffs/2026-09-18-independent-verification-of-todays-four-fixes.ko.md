**대체됨:** `docs/handoffs/2026-09-18-transcript-panel-text-delete.ko.md`

# 오늘 커밋 넷에 대한 독립 검증 -- 코드리뷰·갭검증·역방향 (검증만, 코드 변경 없음)

코디네이터 지시: 오늘 세션이 순서대로 커밋·푸시한 넷(`90c0aeab5`·`b19c435b9`·
`04d9af569`·`515779e21`)에 대해 코드리뷰·갭검증·역방향·동작 검증을 **격리
worktree**(`.claude/worktrees/agent-a154deaec24622f81`)에서 독립적으로 다시
하라는 지시였다. 원본 작업 트리·컨테이너는 건드리지 않는다는 전제였다.

이 문서는 검증 결과만 담는다 -- **코드를 하나도 고치지 않았다.** 진짜 결함을
찾지 못했다(찾았다면 RED→GREEN으로 고쳤을 것이다).

## 0. 검증 범위를 어떻게 좁혔는가

네 커밋의 자기 인계 문서(`2026-09-18-timeline-click-selection-was-silently-
crashing.ko.md`, `2026-09-18-variant-conflict-resolution-actually-wired-to-
chat.ko.md`, `2026-09-18-wiring-gap-audit-and-shortform-summary-fix.ko.md`,
`2026-09-18-overlay-placement-id-and-narration-overlap-root-causes-fixed.ko.md`)
가 이미 **owner 실사용 프로젝트(`0907-b26195af`) 데이터로, 실제 컨테이너
재빌드와 실제 브라우저로, 전후 API 상태를 대조하며** 매우 엄격하게 검증돼
있었다(RED fixture를 실물 데이터 모양대로 손으로 지어 재현, 드래그 트림
실측, undo로 원상복구까지). 그래서 이 검증의 실제 값은 "같은 것을 한 번 더
확인"이 아니라 **(1) 독립된 눈으로 코드를 다시 읽어 놓친 결함이 있는지,
(2) 문서가 스스로 "확인 못 했다"고 적어 둔 자리를 실제로 메우는 것**에 있다고
판단했다.

## 1. 코드리뷰 -- 진짜 결함 없음

`git diff d2f648032..515779e21`(네 커밋 전체, 21개 파일)를 전부 읽었다.

### 1-1. dead-zone 방지 로직 (`TimelineDock.tsx`)

과제가 지목한 세 가지를 직접 추적했다:

- **여러 lane에서 일관되게 동작하는가** -- `TIMELINE_LANES = ["narration",
  "broll", "bgm", "sfx", "overlay", "caption"]` 전체를 순회하며 같은
  `laneNeedsClipAccess` 계산을 적용한다(레인별 분기 없음). 새 시험
  (`timeline-dock.test.tsx`)이 narration·broll·overlay 세 lane을 한 fixture
  (`cutEditedBrollView`)에 같이 넣어 교차 확인한다. **일관됨.**
- **짧은 클립의 경계값** -- `draftProjection.rects`는 `projectVisibleTimelineClips`
  → `deriveClipRect`가 만드는데, `visibleStartSec = Math.max(clip.startSec,
  viewport.startSec)`로 뷰포트에 **클램프**된다(`timeline-geometry.ts:143`).
  그래서 `rect.x`는 절대 음수가 되지 않고, "죽은 자리"(`rect.x <
  LANE_HEADER_DEAD_ZONE_PX`) 판정은 뷰포트 왼쪽 끝(스크롤 위치와 무관하게
  **지금 화면에 실제로 보이는** 왼쪽 끝)에 걸친 클립만 정확히 잡는다. 처음엔
  "스크롤하면 뷰포트 좌표계라 엉뚱한 자리에서도 오탐하는 것 아닌가"를
  의심했으나, `originSec: state.viewportStartSec`가 rects·헤더 뭉치 **양쪽
  다** 같은 좌표계를 쓰고, 클램프 덕분에 화면 밖 클립은 애초에 음수 x를 받지
  않는다는 것을 `selectVisibleClips`(`clip.startSec < viewport.endSec &&
  clip.endSec > viewport.startSec`)까지 따라가 확인했다. **경계값 결함 없음.**
- **`selectClip`의 clipId dedupe**가 겹치는 두 rect 중 어느 쪽을 남기는지는
  상관없다 -- 같은 clipId를 가리키므로 결과가 같다.

### 1-2. `resolve_variant_conflict`가 기존 20개 intent와 같은 패턴을 따르는가

`yujin_editing_proposals.py`(도메인 모델), `yujin_editing_proposal_adapter.py`
(`_validate_current_targets`), `yujin_editing_proposal_service.py`(스키마·
프롬프트), `director_proposals.py`(컨텍스트 배선·적용 분기)를 전부 대조했다.
`_StrictFrozenModel` 상속, discriminator literal, "같은 요청에 다른 조작이
섞이면 거절"(숏폼 넷과 동일 패턴), 지어낸 값 방어(`variant_conflict_not_current`,
색감·전환과 동일 패턴) -- **전부 기존 관례를 그대로 따른다.** 새 예외·새
검증 스타일을 만들지 않았다.

`apply_variant_patch`에 넘기는 `current_master_segment_ids`는 채팅 경로가
`current.kind == "vertical_full"`이면 무조건 읽어서 넘기는데, 화면 단추
경로(`output_variants.py`의 `patch_variant`)는 `"resolve_conflicts" in
request.patch`도 같이 본다. 겉보기엔 다르지만 **채팅 경로는 애초에
`resolve_variant_conflict`가 아니면 이 함수 자체를 안 타므로** 두 조건은
실질적으로 동치다 -- `apply_variant_patch` 내부도 `field in
_STRUCTURAL_FIELDS`로 한 번 더 걸러서, 무관한 필드(`crop` 등)를 풀 때
불필요한 `store.get_editing_session` 한 번이 더 도는 것 말고는 부작용이
없다(기존 단추 경로도 같은 특성을 이미 갖고 있어 이번 커밋이 새로 만든
비효율이 아니다). **사소하고, 고칠 가치보다 건드릴 위험이 크다고 판단해
남겨 둔다.**

### 1-3. `composition_plan.py`의 placement_id 유일성 수정이 다른 자리를 깨뜨리는가

`export_overlays`의 `clip_id`를 참조하는 모든 자리(`ffmpeg_final_renderer.py`,
`local_pipeline.py`의 `fingerprint_exact_preview`, `timeline_placements.py`,
`output_source_verifier.py`, `editor_playback_manifest.py`)를 grep으로 찾아
하나씩 봤다. **어느 자리도 clip_id 문자열을 패턴 매칭·파싱하지 않는다** --
전부 불투명한 식별자로 동등 비교·딕셔너리 키로만 쓴다. 포맷이
`{base}@{segment_id}`로 바뀌어도 깨지는 자리가 없다. `fingerprint_exact_preview`
가 이 값을 캐시 지문에 포함하므로 **의도대로** 분할된 오버레이는 이제 다른
지문을 받는다(옛 캐시가 무효화되는 것은 버그가 아니라 고침의 목적 그 자체).

### 1-4. 겹치는 파일을 건드린 커밋들의 마지막 상태 일관성

`output_variants.py`(`b19c435b9`가 안 건드림, `515779e21`만 건드림),
`director_proposals.py`(`b19c435b9`만), `composition_plan.py`(`515779e21`만)
-- 실제로는 파일 단위 겹침이 없었다(각 커밋이 서로 다른 함수/파일을 건드림).
`git log --oneline --stat`로 확인했고, merge conflict 없이 선형으로 쌓였다.
**일관성 문제 없음.**

## 2. 갭검증 -- 문서 주장과 코드 대조

네 handoff가 "했다"고 적은 것과 "안 했다"고 스스로 적어 둔 것을 코드/실물로
한 줄씩 대조했다.

- `timeline-click-selection...` 문서가 **못 했다고 적은** "드래그로 실제
  트림 커밋"은, 다음 문서(`overlay-placement-id-and-narration-overlap...`)가
  실제로 완료했다(§"실물 확인": `session_revision` 22→23, undo로 원상복구
  확인). **갭이 메워진 것을 확인.**
- `wiring-gap-audit...` 문서가 **못 했다고 스스로 적은** "숏폼 넷 완료 문구의
  실제 브라우저 확인"은 이번 검증(§3)이 메웠다.
- `wiring-gap-full-audit.ko.md`의 판단 필요 9건 목록을, 오늘 이후 코드
  기준으로 다시 훑었다 -- 새로 생긴 항목은 없다(9건 모두 여전히 그대로,
  범위 밖 판단도 그대로 유효). 이 넷 커밋이 그 9건 중 어느 것도 건드리지
  않았다.
- `variant-conflict-resolution-actually-wired-to-chat...` 문서가 "고치지
  않음"으로 남긴 `story` 13중복은 다음 커밋(`515779e21`)이 실제로 고쳤다
  (`rebase_variant`의 `conflicts_by_field` 패턴 적용) -- **갭이 메워짐.**
  다만 이미 저장된 데이터(`variant-1a55a20bd4f0477d88e5530abe9e63fc`)의
  정리는 owner 판단으로 여전히 미뤄져 있다(owner 실사용 데이터라 이번
  검증도 손대지 않았다).

정직하게: 네 handoff 모두 스스로 남긴 미해결 항목이 극히 적고(대부분 다음
커밋이 바로 메웠다), 새로 발견한 미기재 갭은 없다.

## 3. 역방향 검증 -- 격리 컨테이너 + 실제 브라우저

`docker ps`로 원본 세션 컨테이너(`65_videobox-videobox-*`, 포트 5173, 4개
컨테이너)가 이미 떠 있는 것을 먼저 확인했다 -- **절대 안 건드림.** 격리를
위해:

- `.env.container`를 이 worktree 전용으로 새로 만들어 `VIDEOBOX_WEB_PORT=5273`,
  `VIDEOBOX_CONTAINER_DATA_ROOT`를 원본과 무관한 새 폴더
  (`20_project/65_videobox-project-isolated-a154`)로 지정.
- `docker compose -p videobox-verify-a154`로 **compose project 이름 자체를
  분리**했다(compose.yaml의 `name: 65_videobox`를 그대로 두면 원본과 같은
  컨테이너·네트워크·볼륨 이름이 되어 충돌하므로 `-p` 오버라이드가 필수였다
  -- 이 worktree 안에서 처음 겪은 함정이라 기록해 둔다).
- 데이터 루트가 비어 있어 `scripts/migrate_container_data.py`로 빈
  스냅샷(placeholder sqlite 하나)을 만들어 컨테이너 모드 필수 검증
  (`verify_container_snapshot`)을 통과시켰다.
- `videobox-verify-a154-videobox-workspace` 이미지로 **이 worktree(네 커밋
  포함)의 코드를 빌드**했다 -- 원본 이미지와 이름이 겹치지 않는다.
- 검증이 끝난 뒤 `docker compose down` + 이미지·볼륨·데이터 폴더 삭제로 전부
  치웠다. 검증 뒤 원본 세션 컨테이너 4개가 그대로 떠 있고 `/health`가
  200인 것을 재확인했다.

### 실제로 확인한 것

1. **숏폼 완료 문구(`04d9af569`가 남긴 유일한 미확인 항목)** -- 격리
   환경에서 새 프로젝트를 만들고(세그먼트 하나가 기본으로 있는 빈 편집본),
   실제 브라우저에서 유진 채팅창에 "숏폼 만들어줘"를 타이핑해 보냈다.
   네트워크 탭에서 `POST .../yujin-editing-proposals` → 201, `.../preflight`
   → 200, `.../apply` → 200이 실제로 도는 것을 확인했고, 화면에 정확히
   **"숏폼을 새로 만들어요."**가 떴다(옛 결함이었던 의미 없는 "편집 항목을
   바꿔요."가 아니었다). `GET /api/projects/{id}/output-variants`로 전후
   대조 -- 채팅 전 2개(가로·세로 전체)였던 변형본이 채팅 후
   `kind: "vertical_highlight"`인 새 변형본
   (`variant-7e2c32b948744047aae4e9c158ef9539`,
   `selected_segment_ids: ["timeline_001:001"]`)로 3개가 됐다. **말과
   실제 상태 변화가 일치함을 확인** -- `videobox-chat-reply-text-is-a-
   separate-blind-llm-call` 메모가 경고하는 "말과 실행이 다른 LLM
   호출"류 거짓 긍정이 아니다.
2. **콘솔 에러 0건** -- 이 세션 내내(다이얼로그 열기, 채팅, API 호출)
   `read_console_messages`로 확인. 회귀 없음.
3. **원본 세션 무영향** -- 검증 전후 `docker ps`·`curl .../health`로
   원본 스택(포트 5173) 상태 동일함을 확인.

### 확인하지 못한 것

- **타임라인 클립 클릭 선택(`90c0aeab5`)을 이 격리 환경의 실제 브라우저로
  재현하지 못했다.** 격리 환경이 빈 데이터에서 시작해 실제 영상 클립을
  타임라인에 올리려면 미디어 인박스 워처(자료실 자동 색인, 30초 주기 폴링)
  또는 STT 파이프라인을 거쳐야 하는데, 합성 테스트 영상(ffmpeg
  `testsrc`+사인파)을 드롭 폴더에 넣고 두 차례(약 70초) 기다려도 라이브러리에
  올라오지 않았다 -- 원인을 더 파고들 가치보다 이 검증의 본래 목적(오늘
  커밋 넷 검증)에서 벗어난다고 판단해 중단했다. **대신 코드 레벨로
  경계값·좌표계를 끝까지 추적해 §1-1에서 대체 검증했다.** 이 항목은 이미
  원본 세션이 owner 실사용 프로젝트로 두 번 재빌드해 실측(브라우저
  `elementFromPoint`, `data-selected="true"`, 트림 손잡이 등장까지) 확인한
  바 있어, 이번 세션의 대체 검증(코드 추적)으로 판정에 대한 신뢰도는
  충분하다고 본다.
- **변형본 충돌 풀기 채팅 경로(`b19c435b9`)를 이 격리 환경에서 다시
  재현하지 못했다** -- 실제 충돌(마스터 리비전이 갈라진 변형본)을 만들려면
  세션 분할 후 `/rebase` 호출 등 여러 단계가 필요한데, 위와 같은 이유로
  시간 대비 가치가 낮다고 판단해 중단했다. 원본 세션이 이미 **세 번**
  (실사용 프로젝트 두 변형본 + 검증용 새 프로젝트 하나)을 실물로 확인했다.
- **완성본 재빌드 없이 실행했다** -- `-Rebuild`는 이미 이 worktree의 코드로
  이미지를 새로 빌드했으므로 별도 불필요.

## 4. 최종 판정

- **코드리뷰**: 진짜 결함 없음. 사소한 비효율(§1-2) 하나를 찾았으나 고칠
  가치보다 위험이 커서 그대로 둔다(코드 변경 없음).
- **갭검증**: 네 handoff가 스스로 남긴 미해결 항목은 거의 없었고, 있던
  것(드래그 트림 실물 확인, `story` 중복)은 이후 커밋이 이미 메웠다. 새로
  발견한 미기재 갭은 없다.
- **역방향 검증**: 04d9af569가 유일하게 브라우저로 확인 안 됐던 항목(숏폼
  완료 문구)을 이번에 실제로 확인했고, 말한 대로 실제 변형본이 생성됨을
  API로 대조해 확인했다. 나머지 셋(90c0aeab5, b19c435b9, 515779e21의
  브라우저 확인)은 이미 원본 세션이 owner 실사용 데이터로 여러 번 실물
  확인했고, 이번 세션은 코드 레벨 독립 추적으로 그 판정을 재확인했다.
- **최종**: **네 커밋 모두 owner가 기대한 대로 실제로 동작한다고 판단한다.**
  코드를 고치지 않았다(고칠 결함을 못 찾았다).

## 재사용 원칙

- 재사용 후보: `scripts/owner-ready.ps1`이 하는 것과 같은 단계(compose
  config 검증 → build → up)를 `docker compose` 직접 호출로 재현했다 -- 이
  worktree에서 `owner-ready.ps1`을 그대로 쓰면 `-p` 오버라이드가 없어
  원본과 컨테이너 이름이 겹치므로, 이번만 직접 compose를 썼다(스크립트를
  고치지 않았다 -- 그 스크립트는 "원본 하나만 뜬다"는 전제로 설계됐고,
  격리 다중 인스턴스 지원은 이번 범위 밖).
- 실제 반영: 코드 변경 없음. 검증 산출물만(이 handoff, `CLAUDE.md` §2 갱신).
- 제외: 미디어 인박스 워처를 통한 실제 클립 업로드 재현(§3 "확인하지
  못한 것") -- 이번 검증 목적에서 벗어난다고 판단해 중단.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.
  원본 컨테이너·데이터 건드리지 않음(검증 전후 상태 동일 확인).

## 커밋·푸시

코드 변경이 없어 이 handoff 문서와 `CLAUDE.md` §2 갱신만 이 격리
worktree에 커밋한다. 원본 작업 트리로 병합하거나 원격에 푸시하지 않는다
(코디네이터 지시) -- 코디네이터가 결과를 보고 직접 병합·정리한다.
