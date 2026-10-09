# 훅 안내 — VideoBox

이 저장소의 훅은 두 갈래다.

- **VideoBox 자기 훅 셋**(2026-08-20·09-19부터): 본문이 이 저장소 `scripts/` 안에 있다.
  이음매 가드 라우터(`scripts/guard_router.py`)와 worktree 동기화 점검. 설명 SSOT는
  `docs/development-fast-path.ko.md` §10.18.
- **공용 하네스 훅 다섯**(2026-10-09 W1428, 루이스 대표님 지시로 AK 하네스를 옮김): 본문은
  `D:/AI_Workspace_louis_office_50/10_workspace/_reference/harness/hooks/` 한 곳에 있고, 이 저장소는
  호출(`.claude/settings.json`)과 값(`.claude/harness-policy.json`)만 갖는다. 훅 로직을 고치려면 공용
  폴더에서 고치고 거기 테스트(`python -m pytest tests`)를 돌린다. 이 저장소에 복사본을 만들지 않는다.

공용 훅은 읽다 실패하면 **통과**한다(한 줄 경고) — 고장 난 가드가 일을 다 막으면 꺼 버리게 되기 때문이다.
VideoBox 자기 훅은 못 돌린 것을 `안 돌아감`으로 보고하고 `통과`로도 `실패`로도 바꾸지 않는다(§10.18).

| 훅 | 언제 | 막는 것 | 규칙이 사는 곳 | 테스트 |
|---|---|---|---|---|
| `scripts/guard_router.py --hook post-tool-use` (자기 훅) | PostToolUse `Edit` `Write` — 상태 문구 「방금 고친 파일을 지키는 장치 확인」 | 방금 저장한 파일에 걸린 **빠른**(실측 10초 이하) 이음매 가드만 그 자리에서 돌린다. 실패하면 `decision: block` 으로 실패 내용을 돌려준다. 통과면 조용하다. 느린 가드는 여기서 안 돈다 | `scripts/guard_router.py` 의 `GUARDS` 표(경로 → 지키는 테스트), fast-path §10.18 | `tests/test_guard_router_table.py` |
| `scripts/guard_router.py --hook stop` (자기 훅) | Stop — 상태 문구 「이번에 바뀐 파일 전체를 지키는 장치 확인」(최대 30분) | 이번에 바뀐 파일 전체(작업 트리 + base 이후 커밋)에 걸린 가드를 **느린 것까지** 한 번 돌린다(예: `editor-ui-provenance`, `owner-ready-script`). 실패면 턴을 막는다. 화면에 닿는 파일을 고쳤으면 "화면에서 밟아 보라"는 **사실만** 알리고, 제품 코드만 고치고 인계 문서가 없으면 인계 알림을 낸다 | 같은 표, CLAUDE.md §4·§7 | `tests/test_guard_router_table.py`, `tests/test_handoff_freshness_guard.py` |
| `scripts/session-start-worktree-sync-check.sh` (자기 훅) | SessionStart — 「worktree 동기화 상태 확인」 | 안 막음. 각 worktree 를 main 에 병합됨(정리 후보) / 고유 커밋 있음(검토 후보) / 작업 중(손대지 말 것)으로 나눠 알려 준다. 삭제·병합은 하지 않는다 | fast-path §10.18·§10.21 | 없음(읽기 전용 셸) |
| `shell_guard.py` (공용) | PreToolUse `Bash` `PowerShell` `Read` | ① `python -`(stdin 으로 프로그램 읽기, 셸이 멈춤) ② 이름으로 프로세스 죽이기(`taskkill /IM`, `pkill`, `killall`, `Stop-Process -Name`) ③ `.env*` 읽기(`.env.container` 포함; `cat`·`Get-Content`·Read 도구; `.env.container.example` 은 통과) ④ `-p 65_videobox` 없는 `docker compose down/stop/rm/kill`, 소유 목록 밖 컨테이너(`ak-system-*`, `louis-personal-*`, `openmic-*`, `86_global-blog-20wp-*` …)의 `docker stop/rm/kill/restart`, 읽을 수 없는 대상(`$(docker ps -q)`), `docker prune` | `harness-policy.json` → `shell` (`65_videobox`, `65_videobox-*`, `videobox-hermes-yujin`) | 공용 `tests/test_shell_guard.py` |
| `finish_first_guard.py` (공용) | PreToolUse `Agent`, `Bash`/`PowerShell`(`git worktree add` 일 때만) | 72시간 멈춘 갈래(`.claude/worktrees/*`)가 있는데 새 Agent·새 worktree 를 시작하는 것, 열린 갈래 3개 이상에서 새 worktree 를 여는 것. 읽기 전용 에이전트(Explore·Plan …), `묶음:` 표시, 멈춘 갈래 이름을 적은 재개, `parked` 목록(`hopeful-pasteur-64b08e`)은 통과 | `harness-policy.json` → `finish_first`, CLAUDE.md §3·fast-path §10.21 | 공용 `tests/test_finish_first_guard.py` |
| `model_choice_guard.py` (공용) | PreToolUse `Agent` | `model` 없이 서브에이전트 띄우기, `opus`·`sonnet`·`haiku` 밖의 값(버전 박힌 ID 포함), 버전 박힌 `model:` 을 가진 `.claude/agents/*.md` 정의 | `harness-policy.json` → `model` | 공용 `tests/test_model_choice_guard.py` |
| `merge_checklist.py` (공용) | PostToolUse `Bash`/`PowerShell`(`git merge` 직후, 브랜치 `harness-`·`claude/`·`agent-`·`worktree-`) | 안 막음. 바뀐 파일에 맞는 검증 명령(가드 라우터 `--changed --speed all`, `.venv` pytest, `npx tsc --noEmit`, `npx vitest run`, `npm run test:e2e`, real-flow, 인계·문서 계약 테스트, 출처 해시 테스트, compose 계약 테스트)을 Claude 에게 알려 준다 | `harness-policy.json` → `merge` | 공용 `tests/test_merge_checklist.py` |
| `answer_style_guard.py` (공용) | Stop | 칭찬·이유 없는 동의로 시작한 답, 의견을 물었는데 추천도 반대 논리도 없는 답 — 한 번 되돌려 다시 쓰게 함 | `harness-policy.json` → `answer_style` (한국어 문구 목록, 되돌림 사유는 CLAUDE.md §1 핵심 태도 1·2·3·7) | 공용 `tests/test_answer_style_guard.py` |

## 각 훅이 못 잡는 것

- **guard_router (PostToolUse·Stop)**: **화면에서 실제로 밟아 봤는가**는 모른다(§10.18 — 라이브러리 전면 차단과 자막 배경색 죽음은 화면에서만 나왔다). 표에 없는 경로를 고친 것(표가 안 지키는 자리), `.venv` 가 없는 worktree(→ `안 돌아감`, `VIDEOBOX_GUARD_PYTHON` 으로 지정), Bash 로 바꾼 파일(PostToolUse 는 `Edit`/`Write` 만 본다 — Stop 이 잡는다). `.claude/rules/*.md` 는 아직 표에 없다(CLAUDE.md 만 `handoff-entry-point`·`documentation-contract` 로 간다).
- **session-start 점검**: 막지 않는다. `.claude/worktrees/` 안에 있지만 git 에 등록되지 않은 폴더(예: 옛 `agent-*` 폴더 셋)는 보지 않는다.
- **shell_guard**: 실행 시점에 만들어지는 명령(`eval`, docker 를 부르는 스크립트 파일 — `scripts/owner-ready.ps1` 안의 compose 도 여기 해당), `kill $(pgrep node)`, 세 단 넘는 중첩 셸, Read·Bash 가 아닌 도구로 `.env` 를 여는 것(에디터, Grep), 손으로 붙여 넣은 비밀, `docker compose up/restart`. **`-p 65_videobox` 를 밝힌 compose down 과 소유 컨테이너 stop 은 통과한다** — VideoBox 컨테이너를 직접 끄지 말라는 규칙(CLAUDE.md §3 `owner-ready.ps1` 로만)은 이 훅이 아니라 지침이 지킨다.
- **finish_first_guard**: main 에서 바로 한 작업(갈래가 없음 — 이 저장소의 기본 방식), 깨끗하고 main 과 같은 갈래(열린 것으로 안 셈), detached HEAD 갈래, 가짜 `묶음:` 표시, SendMessage 재개, Workflow 안의 `agent()`, `lane_glob` 밖에 만든 갈래.
- **model_choice_guard**: 작업에 안 맞는 모델을 고른 것(고르게만 한다), SendMessage 재개, Workflow 안의 `agent()`.
- **merge_checklist**: 명령이 실제로 돌았는지·초록인지(알려 줄 뿐 검사하지 않음), `git pull`·GitHub 화면 같은 다른 도구의 합침, 접두어 목록에 없는 브랜치, "Already up to date" 인데 reflog 가 옛 merge 인 경우의 오판, rebase·cherry-pick.
- **answer_style_guard**: 이유가 사실인지, 추천이 최선인지(답의 모양만 본다), 목록에 없는 아첨 표현, 같은 턴 앞쪽 메시지에 있는 내용.

## 확인하는 법

- 공용 훅 배선: `python D:/AI_Workspace_louis_office_50/10_workspace/_reference/harness/tests/wiring_check.py .claude/settings.json .`
  (VideoBox 자기 훅 셋은 샘플이 없어 `??? no samples` 로 3건이 찍힌다 — 정상.)
- 자기 훅 표: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_guard_router_table.py`
- 결과 기록: `D:/AI_Workspace_louis_office_50/10_workspace/_reference/harness/REPORT-videobox.md`
