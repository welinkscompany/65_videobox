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

승인된 시각 결정은 현재 두 건이다. 둘 다 사용자가 명시 승인했고 재승인 없이 바꾸지 않는다.

- `docs/decisions/creator-workspace-visual-approval.ko.md` (2026-07-17, 홈·인터뷰·편집기 팔레트)
- `docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md` (2026-07-22, 편집 작업판 5개 viewport)

## 2.1 제품 범위 경계

`docs/implementation-plan.ko.md` §4와 §8.4가 고정한 경계다. 이걸 모르고 UI를 비판하거나 확장하지 않는다.

- VideoBox는 **설명형 영상용 경량 후편집기**다. 풀 NLE를 직접 구현하지 않는다.
- MVP 제외: 풀 자체 편집기, 실시간 멀티트랙 편집 UI, 고급 모션그래픽, 색보정, 오디오 믹싱 콘솔,
  자유 키프레임, 완전 자동 최종본 보장, 결제·멀티유저.
- 편집기 범위는 §8.4의 14개 조작으로 고정: 컷 유지/삭제, 컷 경계 조정, 세그먼트 병합/분리,
  자막 텍스트/타이밍, B-roll 교체, 배경 교체, 설명 자산 삽입, 음악, 효과음, review flag,
  원본/자동/수정 비교, 수정 이력, 부분 재생성.
- 이 경계를 넘는 요구가 오면 먼저 계획서와의 충돌을 사용자에게 알리고 결정을 받는다.

세부 운영 규정의 authoritative 본문은 `docs/development-fast-path.ko.md`에 유지한다.
이 파일은 그것을 대체하지 않고 진입점 역할을 한다.

## 3. 개발 환경

### 위치와 브랜치

- 활성 worktree: `.worktrees/videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility` (이름의 `codex/` 접두사는 과거 흔적이며 의미 없음)
- main 브랜치는 컨테이너 마이그레이션 계획 문서만 있는 뒤처진 상태다. 실제 개발선은 위 worktree다.

### 기본 구현 루프

`docs/development-fast-path.ko.md` §1의 고정 순서다.

`plan reconcile → RED → minimal GREEN → focused verification → broader verification`

- 새 UI를 만들기 전에 기존 흐름을 재사용할 수 있는지 먼저 본다.
- RED/GREEN 단계에서는 정확히 테스트 1개만 돌린다. broader는 Task가 닫힐 때만.
- `approval-output hardening / preflight contract` 계열 작업에는
  `scripts/dev-fast-path.ps1 -Mode status`로 현재 gate를 먼저 확인한다.
  그 외 slice에 이 helper를 억지로 맞추지 않는다.

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

`§10.9`에 따라 아래를 전달한다. 고정 서식이 아니라 내용 요건이다.
해당 없으면 적지 않는다. 대화형 턴에 보고서 형식을 억지로 씌우지 않는다.

- 이번 턴에 실제로 한 일 (쉬운 말)
- 수행한 검증과, 검증하지 못한 채 남은 것
- 커밋·푸시 여부. 하지 않았으면 이유
- 막힌 지점이나 사용자 결정이 필요한 사항 (있을 때만)

구현 작업을 닫을 때는 `docs/implementation-plan.ko.md` §8.3에 따라 아래도 함께 남긴다.
재사용 원칙이 잊히거나 방향이 새는 것을 막기 위한 항목이다.

- 확인한 재사용 후보
- 실제 반영한 항목과 반영 방식
- 이번 범위에서 제외한 항목과 제외 이유
- 경계 보존 여부
- 테스트와 리뷰로 검증한 것

다음 세션용 복사-붙여넣기 프롬프트는 남기지 않는다.
인계가 필요하면 `docs/handoffs/` 문서로 남긴다.

진행률은 매 턴 보고하지 않는다. Task를 실제로 열거나 닫을 때, 또는 사용자가 물을 때만 보고하며
`§10.8`의 계산 규정을 따른다. 모수가 정의되지 않았으면 수치를 지어내지 않는다.

## 7. 사용자 커뮤니케이션

- 기본적으로 존댓말을 유지한다.
- 쉬운 말로 요약하되 기술적으로 중요한 경계와 리스크는 숨기지 않는다.
- dashboard에 노출되는 문구는 `§10.13` creator-language 규정을 따른다.
  개발·시스템 내부 용어(`provider`, `runtime`, `job`, `revision`, `pipeline` 등)를 사용자 화면에 쓰지 않는다.
