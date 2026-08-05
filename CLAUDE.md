# VideoBox 최상위 개발 지침

이 파일이 이 저장소의 **최상위 지침**이다.
2026-08-05부로 개발 주체를 Claude Code로 전환했다. `AGENTS.md`는 하위 호환 포인터로만 남긴다.

동의가 목표가 아니다. 가장 논리적이고 현실적인 해결책을 찾는 것이 목표다.

## 0. 세션 시작 체크리스트

코드나 UI를 건드리기 **전에** 반드시 아래를 먼저 수행한다.
이 순서를 건너뛰어 승인된 디자인 결정을 무단 변경한 사고가 실제로 있었다.

1. 이 파일(`CLAUDE.md`)을 읽는다.
2. `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`을 읽는다. **운영 규정 SSOT다.**
3. 작업이 UI/디자인에 닿으면 `docs/decisions/` 아래 승인 기록을 먼저 확인한다.
4. `git status --short`, branch/upstream divergence, `git worktree list`, `git diff --check`를 직접 확인한다.
5. 현재 작업이 어느 공식 Task에 속하는지 식별한다. 계획서 밖이면 그 사실을 명시한다.

## 1. 핵심 태도

1. 사용자의 말에 무조건 동의하지 않는다.
2. 정확성을 동의보다 우선한다.
3. 확실하지 않은 내용은 확실한 것처럼 말하지 않는다.
4. 확인된 사실, 가정, 추정을 구분한다.
5. 장점뿐 아니라 단점과 리스크도 함께 제시한다.
6. 더 나은 대안이 있다면 제안한다.
7. 관련 없는 코드와 구조는 건드리지 않는다.
8. 문제를 발견하면 숨기지 말고 보고한다.
9. 검증 없이 완료되었다고 말하지 않는다.
10. 불필요한 질문으로 작업을 멈추지 않는다.
11. 작업이 불가능한 경우에만 질문한다.
12. 중요한 결정은 반드시 반대 논리도 검토한다.
13. 자기 작업을 결함으로 오진하지 않는다. 결함을 보고하기 전에 그 원인이 자신의 변경인지 먼저 확인한다.

## 2. SSOT 연결

| 역할 | 경로 |
|---|---|
| 최상위 지침 | `CLAUDE.md` (이 파일) |
| 운영 규정 SSOT | `docs/development-fast-path.ko.md` `## 10` |
| 최상위 구현 계획 | `docs/implementation-plan.ko.md` |
| 상태/closeout 로그 | `docs/development-status-2026-06-29.ko.md` |
| 디자인 승인 기록 | `docs/decisions/` |
| 미해결 수정 backlog | `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md` |

세부 운영 규정의 authoritative 본문은 `docs/development-fast-path.ko.md`에 유지한다.
이 파일은 그것을 대체하지 않고 진입점 역할을 한다.

## 3. 개발 환경

### 위치와 브랜치

- 활성 worktree: `.worktrees/videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility` (이름의 `codex/` 접두사는 과거 흔적이며 의미 없음)
- main 브랜치는 컨테이너 마이그레이션 계획 문서만 있는 뒤처진 상태다. 실제 개발선은 위 worktree다.

### 검증 명령

backend 검증은 반드시 프로젝트 루트의 venv를 쓴다. bare `pytest`나 시스템 Python은 근거로 쓰지 않는다.

```bash
.venv/Scripts/python.exe -m pytest -q
```

```bash
npm --prefix apps/web test
```

```bash
npm --prefix apps/web run build
```

프론트엔드 타입 검사:

```bash
npm --prefix apps/web exec tsc -- --noEmit
```

### 로컬 실행

컨테이너 스택은 `scripts/owner-ready.ps1`로 조작한다. 직접 `docker compose`를 치지 않는다.

```powershell
.\scripts\owner-ready.ps1 -Mode Check
```

```powershell
.\scripts\owner-ready.ps1 -Mode Start
```

- VideoBox: `http://127.0.0.1:5173/`
- Hermes 대시보드: `http://127.0.0.1:9119/`
- `.env.container`는 gitignore 대상이다. 실제 credential을 커밋하지 않는다.

개발 서버는 `.claude/launch.json`에 정의돼 있다 (web 5199, api 8000).

### 검증 스크립트

`scripts/` 아래에 verifier가 다수 있다. 새 검증 흐름을 만들기 전에 기존 것을 먼저 찾는다.
예: `verify-editor-ui-system.ps1`, `verify_container_stack.ps1`, `verify-editor-ui-source-provenance.ps1`

## 4. 보호 경계

아래는 열거나 수정하지 않는다.

- `.tmp-final-fence-debug/`
- `.tmp-real-video-dogfood/`
- `apps/web/.tmp-real-video-dogfood/`
- 사용자 원본 영상 샘플 디렉터리 (read-only)
- `artifacts/` 아래 QA 증거는 `preserve-evidence`다. 명시적 분류 근거 없이 삭제하지 않는다.

## 5. 승인이 필요한 변경

아래는 owner의 명시적 승인 없이 실행하지 않는다.

- UI 팔레트·비주얼 방향 변경 (`docs/decisions/creator-workspace-visual-approval.ko.md` 재승인 절차 필요)
- Hermes 실제 provider 로그인, live Mem0
- SaaS, billing, multi-user 인증
- 외부 게시·업로드
- 컨테이너 네트워크 경계 변경 (`§10.14`)

## 6. 턴 종료 보고

`§10.9`에 따라 매 턴 아래를 포함한다. 추천만 한 턴도 동일하다.

- 이번 턴에 실제로 한 작업 (쉬운 말 요약)
- 계획서 기준 진행 범위
- 전체 공식 계획서 기준 누적 진행률과 남은 비율
- 진행률 계산 기준
- 수행한 핵심 검증
- 커밋/푸시 여부와 하지 않았다면 이유
- 다음 추천 Goal 프롬프트

진행률은 이번 턴이 아니라 전체 공식 계획서 기준 누적으로 계산한다.
비공식 조사·분석·메모는 완료율에 포함하지 않고 준비 작업으로 별도 표시한다.

## 7. 사용자 커뮤니케이션

- 기본적으로 존댓말을 유지한다.
- 쉬운 말로 요약하되 기술적으로 중요한 경계와 리스크는 숨기지 않는다.
- dashboard에 노출되는 문구는 `§10.13` creator-language 규정을 따른다.
  개발·시스템 내부 용어(`provider`, `runtime`, `job`, `revision`, `pipeline` 등)를 사용자 화면에 쓰지 않는다.
