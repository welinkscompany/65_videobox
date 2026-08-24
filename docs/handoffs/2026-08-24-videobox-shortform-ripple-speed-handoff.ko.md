**대체됨:** `docs/handoffs/2026-08-24-videobox-p1-capcut-caption-fixture-handoff.ko.md`

# VideoBox 숏폼 장면 리플 배속 인계 — 2026-08-24

## 현재 작업선

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch: `codex/videobox-container-compatibility`
- 마지막 HEAD: 다음 세션에서 반드시 `git rev-parse HEAD`로 직접 확인한다.
- upstream divergence(종료 시점): `0 13` (원격에는 push하지 않았다.)

## 실제로 한 일

### 선택 장면 리플 배속을 구현했다

선택한 한 장면에만 `기본(1×) / 1.5배 / 2배`를 적용한다. 선택 장면의 원본
slice는 자르지 않는다. 표시 시간만 `원본 길이 / 배속`으로 줄이고, 뒤 장면은 같은
차이만큼 앞으로 당긴다.

- `set_segment_bounds`와 별도 mutation `set_segment_ripple_playback_rate`를 만들었다.
  따라서 2배속이 대사 뒤 절반을 버리는 trim으로 바뀌지 않는다.
- 세션 revision, output stale 표시, undo/redo history가 기존 한 transaction을 그대로
  사용한다. 허용하지 않은 값(0, 음수, 1.25, 3, NaN)은 저장하지 않는다.
- 공통 `materialize_editing_session_timeline`에서 내레이션·자막·장면 종속 B-roll·SFX·
  overlay의 시간축과 `playback_rate`를 같이 계산한다. 이후 장면은 앞당겨진 위치를
  받는다. 전역 BGM은 빠르게 하지 않고 짧아진 결과 끝에서 멈춘다.
- FFmpeg composition/필터는 내레이션·SFX에 `atempo`, B-roll에 장면 배속과 기존
  B-roll 자체 배속을 곱한 `setpts`를 사용한다.
- CapCut 초안도 같은 materialized clip을 받는다. 실제 초안 JSON 시험에서 2× 장면의
  내레이션과 B-roll이 모두 **표시 2초 / 원본 4초 / speed 2.0**으로 저장됨을 확인했다.
- 편집 화면의 기존 `편집 항목` 안에만 `장면 길이`와 `기본 / 1.5배 / 2배` 단추를
  연결했다. 새 CSS·색·배치 변경은 하지 않았다. 선택 장면과 현재 revision을 API에
  보낸다.

### 발견해서 고친 회귀 두 건

1. 장면에 직접 붙인 B-roll에서 source 범위를 미리 넣어 기존 `in_sec/out_sec` 자르기와
   중복 계산되어 exact preview/final 공통 시험이 실패했다. B-roll 원본 범위 계산은
   기존 CompositionPlan에 맡기고 장면 배속만 곱하도록 고쳤다.
2. 웹 snapshot에 기본 1×를 항상 새 필드로 넣어, 기존 응답 모양을 엄격 비교하던 시험이
   실패했다. 1×는 필드를 생략하고 화면에서 기본값으로 해석하도록 고쳤다.

### 이 작업의 commit

- `0ea2ff102 docs: 숏폼 장면 리플 배속 설계를 고정`
- `de7111ce3 docs: 숏폼 장면 리플 배속 구현 순서를 고정`
- `92a9d3111 feat: 장면 리플 배속을 편집과 렌더 시간축에 반영`
- `720147d41 feat: 선택 장면 배속을 화면과 캡컷 초안에 연결`
- `6c7676bf8 fix: 장면 배속과 B-roll 원본 자르기 충돌을 막음`
- `e60952cea fix: 기본 장면 길이의 기존 스냅샷 모양을 유지`

## 자동 검증 결과

| 검증 | 결과 |
|---|---|
| 리플 배속·기존 B-roll·실제 exact preview focused pytest | 22 passed / warning 1 |
| `.venv\Scripts\python.exe -m pytest -q` 단독 재실행 | **4,046 passed / 56 skipped / warning 1**, 30분 24초 |
| `apps/web` `npx vitest run` | **96 files / 1,267 tests passed** |
| `apps/web` `npx tsc --noEmit` | exit 0, 출력 없음 |
| `git diff --check` | 각 커밋 전 통과 |

백엔드에는 기존 `python_multipart` 폐기 예정 경고 1건이 남았다. 웹 전체 시험도
기존 React `act`, jsdom navigation, dialog description, 의도된 ErrorBoundary 로그를
출력한다. 경고가 없다고 주장하지 않는다.

## 검증했지만 못 끝낸 것

1. 실제 FFmpeg가 리플 배속한 최종 MP4를 재생하여 음성·영상·자막 싱크를 듣고 보는
   사람 확인은 하지 않았다. 자동 시험은 filter graph, materialized 시간축, 기존 실제
   렌더 회귀, CapCut draft JSON까지다.
2. 실제 CapCut 프로그램으로 초안을 열어 voiceover·B-roll의 speed 2.0을 재생해 보지
   않았다. 프로그램 설치·사람 확인이 별도 필요하다.
3. B-roll 자체 배속과 장면 배속의 곱이 0.25–4 범위를 넘는 입력을 화면에서 어떻게
   안내할지는 아직 명시적으로 막지 않았다. 현재 화면은 장면 1/1.5/2만 고르고,
   기존 B-roll control은 별도다. 이 조합의 제품 정책을 대표가 결정하기 전에는
   조용한 자동 보정이나 새로운 배속 범위를 추가하지 마라.
4. `0.5×`, 임의 숫자, 구간 일부 배속, 여러 장면 동시 배속은 이번 범위가 아니다.

## 목요일에 화면으로 확인해야 할 것

1. 편집기에서 장면을 고른 뒤 `편집 항목 → 장면 길이 → 2배`를 설명 없이 찾을 수 있는지
2. 2배를 누른 뒤 선택 장면 길이가 줄고 뒤 장면이 앞으로 붙는지, `기본`으로 되돌리면
   원래 시간축이 돌아오는지
3. 정확 미리보기와 최종 MP4에서 내레이션·자막·영상·효과음이 실제로 함께 빨라지는지,
   BGM 피치가 빨라지지 않는지
4. CapCut 초안을 실제로 열었을 때 voiceover/B-roll 배속과 자막 시간이 VideoBox 결과와
   같은지
5. 기존 승인된 색·배치가 화면에서 바뀌지 않았는지와 루이스 대표님의 사용성 승인

자동 시험 통과는 위 다섯 항목이나 owner acceptance를 대신하지 않는다. 이 세션은
"보기 좋아졌다" 또는 "실제로 들었다"고 판단하지 않았다.

## Claude/Codex 전환 시 해야 할 일

새 도구도 먼저 `CLAUDE.md` §0과 `docs/development-fast-path.ko.md` §10을 읽는다.
그 다음 아래를 직접 확인한다.

```text
git rev-parse HEAD
git status --short
git rev-list --left-right --count @{upstream}...HEAD
git worktree list
git diff --check
```

UI를 건드릴 일이면 최신 `docs/decisions/` 승인 기록을 먼저 읽고, 이 인계와
`docs/superpowers/specs/2026-08-24-videobox-shortform-ripple-speed-design.ko.md`,
`docs/superpowers/plans/2026-08-24-videobox-shortform-ripple-speed.md`를 함께 읽는다.

백엔드 검증은 반드시 `.venv\Scripts\python.exe -m pytest`를 사용한다. 전체 pytest는
다른 장기 작업과 병행하지 않는다. 웹은 `apps/web`에서 `npx vitest run`과
`npx tsc --noEmit`을 쓴다. 화면 확인이 필요하면 컨테이너는
`./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`로만 다루고, 실제
credential과 `.env.container`는 커밋하지 않는다. push·외부 게시·운영 변경은 새 명시
승인 없이는 하지 않는다.
