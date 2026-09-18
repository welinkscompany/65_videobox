**대체됨:** `docs/handoffs/2026-09-18-e2e-remediation-fix01-fix02-invest02-closed.ko.md`

# task_transcript-panel-text-delete -- 대본 칸을 비우면 장면이 빠진다, 실물까지 확인

owner 승인(2026-09-18, "1,2번 진행하자") 위에서, 브루·캡컷의 "텍스트로 편집"(대본
패널에서 문장을 지우면 그 구간 영상이 자동으로 잘리는 편집)을 VideoBox에 들였다.
격리 worktree `agent-a9125e842983d23db`(원본은
`.worktrees/videobox-container-compatibility`)에서 작업했다.

## 무엇을 만들었나

`TranscriptPanel.tsx`의 캡션 텍스트 칸을 **완전히 빈 문자열**로 만들면, 이미 있던
"빼기" 경로(`InspectorAction: { kind: "set-cut-action", cutAction: "remove" }` →
`port.setCutAction` → `PATCH .../segments/{id}/cut-action`)를 그대로 불러 그 세그먼트를
타임라인에서 뺀다. **새 API·새 명령을 만들지 않았다** — 타임라인 툴바의 "빼기" 단추와
정확히 같은 함수를 재사용한다(재사용 게이트, `implementation-plan.ko.md` §8.1).

### 실제 반영 항목

- `apps/web/src/features/editor/transcript/TranscriptPanel.tsx`
  - `onDeleteSegment?: (segmentId: string) => void | Promise<void>` prop 추가.
  - `handleDraftChange`: `value.trim() === ""`일 때만(완전히 빈 문자열) `onDeleteSegment`를
    부른다. 부분 수정(단어 몇 개만 지움)은 기존 `onSaveCaption` 경로 그대로 -- 헷갈리지
    않게 조건을 하나로 갈랐다.
  - "캡션 저장" 단추는 `draft.trim() === ""`일 때 비활성화한다 -- 빈 문자열로 저장을
    눌러 빈 캡션이 만들어지는 혼동을 막는다(지우는 것과 저장하는 것은 다른 경로).
- `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`
  - `TranscriptPanel`에 `onDeleteSegment`를 배선했다. 이미 있던 `onInspectorAction`으로
    `{ kind: "set-cut-action", segmentId, cutAction: "remove" }`를 그대로 부른다 --
    "빼기" 단추(`cutToolbar.ts`)가 쓰는 것과 **같은 액션 객체 모양**이다.

### 설계 판단과 근거

1. **즉시 적용, 확인창 없음.** owner 승인 2026-09-01("유진에게 말한 편집은 바로
   적용된다")의 정신과 이 저장소의 기존 패턴(멀티세그먼트 드롭 단추도 확인창 없이
   즉시 적용하고 되돌리기로 지킨다)을 그대로 따랐다. 새 확인창을 만들지 않았다.
2. **1단계 범위는 세그먼트 하나.** 여러 세그먼트에 걸친 삭제(문단 전체 선택해서
   한 번에 지우기)는 이번 범위에 넣지 않았다 -- textarea 하나는 애초에 세그먼트
   하나만 담당하므로(`selectedEntry` 단위) 여러 세그먼트를 한 textarea에서 동시에
   지우는 시나리오 자체가 지금 UI 구조에 없다. 명시적으로 범위 밖으로 남긴다.
3. **완전히 빈 문자열일 때만 삭제로 해석.** 부분 삭제(단어 몇 개)는 기존
   `onSaveCaption`이 처리한다. `value.trim() === ""`로 갈라서, 스페이스만 남기고
   지운 경우도 삭제로 잡히게 했다(공백만 남기는 것은 실수로 볼 근거가 약하다).

### 유진 채팅 경로 -- 새로 안 만들어도 된다

`packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`에
이미 `set_cut_action` intent(`action: "exclude" | "restore"`)가 있고, 프롬프트 지시문에
"'장면을 빼줘/지워줘/없애줘'처럼 **장면 자체**를 빼라는 말은
set_cut_action(action=exclude)이다"가 못박혀 있다(548행). 화면 텍스트 편집과 유진
채팅 둘 다 결국 같은 백엔드 액션(`exclude`/`remove`)으로 수렴한다 -- **owner 상시
지시("화면으로 되는 건 전부 유진에게도 되어야 한다")를 이미 만족한다.** 새로 만들
것이 없다.

## 검증

### 시험 (RED→GREEN)

- `TranscriptPanel.test.tsx`: 완전히 비우면 `onDeleteSegment(segmentId)`가 불리고
  `onSaveCaption`은 안 불린다(2개 새 시험). 부분 수정은 `onDeleteSegment`를 안 부른다.
- `editor-workbench-route.test.tsx`: 전체 스택을 마운트해 대본 칸을 비우면 실제
  `api.updateEditingSessionCutAction("project-a", "session-a", "segment-1",
  { cut_action: "remove", expected_revision: 4 })`가 불리고, 리비전이 올라가고,
  다음 매니페스트에서 빠진 세그먼트가 캡션 목록에서도 사라지는 것까지 확인(기존
  "빼기" 단추 시험과 같은 패턴).
- 프론트엔드 전체 `npx vitest run` 독립 실행: **139개 파일 / 1751개 통과**.
- `npx tsc -b`: 오류 없음.
- 관련 백엔드: `cut-action` 엔드포인트 자체는 이번에 안 건드렸다(프런트에서 기존
  엔드포인트를 재사용만 했다) -- 백엔드 회귀 대상이 아니라 pytest는 새로 안 돌렸다.

### 실물 브라우저 확인 (CLAUDE.md §4)

격리 docker 스택(`COMPOSE_PROJECT_NAME=videobox-verify-a912`, 포트 5299, 전용
데이터 루트)에서 "+ 새로 만들기" → 짧은 대본 → "무음으로 초안 준비"로 진짜 2세그먼트
편집본을 만들고, "캡션" 탭에서 1번째 캡션 텍스트를 완전히 비웠다.

- 네트워크 로그: `PATCH .../cut-action` 200 OK 확인(캡션 저장 API가 아니라 컷 액션
  API가 정확히 불렸다).
- 화면: 캡션 목록·타임라인 캡션 트랙·내레이션 트랙·영상 트랙에서 1번째 세그먼트가
  전부 사라짐, "2개 캡션" → "1개 캡션"으로 헤더 갱신, 재생헤드의 "현재 캡션 없음".
- "실행 취소"를 누르니 두 세그먼트가 전부 원래대로 복구됨(되돌리기 확인).

### 사고 보고 -- 실물 검증 과정에서 공유 스택을 건드림

첫 시도에서 `COMPOSE_PROJECT_NAME`을 지정하지 않고 `owner-ready.ps1 -Mode Start
-Rebuild`를 격리 worktree에서 실행했다. `compose.yaml`에 `name: 65_videobox`가
고정돼 있어, 프로젝트 이름이 worktree와 무관하게 항상 `65_videobox`로 잡힌다는 것을
몰랐다 -- 그 결과 **실행 중이던 공유 `65_videobox-videobox-workspace-1`(업타임
약 1시간)을 내 코드로 재빌드하고 재시작**했다. 원인을 바로 확인하고
(`.worktrees/videobox-container-compatibility/.env.container`의 실제 데이터
루트·자격정보로) 복구했다 -- postgres는 "Skipping initialization"으로 기존 볼륨을
그대로 재사용해 데이터 유실은 없었고, 지금은 포트 5173이 정상(healthy)이다. 이후
`COMPOSE_PROJECT_NAME=videobox-verify-a912`로 완전히 분리한 스택에서 실물 검증을
마쳤고, 검증 뒤 그 스택은 `docker compose down`으로 정리했다(`owner-ready.ps1`에는
정지 모드가 없어 이 정리만 raw `docker compose`를 직접 썼다). **교훈**: 이 저장소의
`compose.yaml`은 프로젝트 이름을 고정해 두므로, 격리 worktree에서 컨테이너를 켤 때는
`COMPOSE_PROJECT_NAME`(또는 동등한 격리 수단)을 **반드시 먼저** 지정해야 한다 --
`docs/development-fast-path.ko.md` §10에 이 주의를 추가하는 것을 다음 세션에 권한다.

## 범위 밖으로 남긴 것

- 여러 세그먼트에 걸친 동시 삭제(문단 단위) -- 지금 UI 구조(세그먼트 1개 = textarea
  1개)에서는 필요하지 않다고 판단, 명시적으로 범위 밖.
- 부분 텍스트 삭제를 "일부 장면 삭제"로 해석하는 것 -- 기존 캡션 수정 기능의 영역.
- 백엔드 `cut-action` 로직 변경 -- 기존 경로를 그대로 재사용했으므로 손대지 않았다.

## 커밋·푸시

이 worktree에만 커밋했다. 원본 작업 트리(`.worktrees/videobox-container-compatibility`)로
병합하거나 원격에 푸시하지 않았다 -- 코디네이터가 결과를 보고 직접 병합·정리한다.
