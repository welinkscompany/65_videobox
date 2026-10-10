# VideoBox 최상위 개발 지침

이 파일이 이 저장소의 **최상위 지침**이다. 어느 AI 코딩 도구를 쓰든 이 파일이 먼저다.
동의가 목표가 아니다. 가장 논리적이고 현실적인 해결책을 찾는 것이 목표다.

세부는 여기 두지 않는다. 이 파일은 **판단에 필요한 것만** 담고, 운영 세부는
`docs/development-fast-path.ko.md` `## 10`(규정)과 `## 11`(명령·주소)에 있다.

## 색인 — 무엇이 어디 있고 언제 읽히나

이 파일은 **매번 알아야 하는 것만** 담는다(2026-10-09 W1428, 루이스 대표님 지시로 AK 하네스를 옮김).
옮긴 글은 한 줄도 버리지 않고 원문 그대로 아래 파일로 갔다. 절 번호(§0~§8)는 그대로 남아 있어
코드·문서 주석의 「CLAUDE.md §N」은 여기서 시작해 이 표를 따라가면 된다.

| 주제 | 있는 곳 | 언제 읽히나 |
|---|---|---|
| §2 지금 유효한 결정(제품 방향·번역기·팔레트·Tauri·모션·안 만드는 것) | `.claude/rules/current-decisions.md` | **항상** |
| §3 개발 환경(메인 체크아웃·worktree·venv·owner-ready·`.env.container`) | `.claude/rules/dev-environment.md` | **항상** |
| §3 조각마다 하는 검증 넷(갭·역방향·동작·배선) | `.claude/rules/verification-four.md` | **항상** |
| §3 재사용 게이트·기본 구현 루프 | `.claude/rules/reuse-gate-and-loop.md` | `apps/` `services/` `packages/` `scripts/` `tests/` `docker/` `config/` 작업 때 자동 |
| §5 보호 경계 | `.claude/rules/protected-boundaries.md` | **항상** |
| §6 Mem0 제거·유진 기억·§10.14 남은 조항 | `.claude/rules/yujin-memory.md` | 유진·기억·compose·`docs/decisions/` 작업 때 자동 |
| §7 턴 종료 보고 내용 요건 | `.claude/rules/turn-end-report.md` | **항상** |
| 훅(무엇이 언제 막나) | `.claude/hooks-README.md`, 값은 `.claude/harness-policy.json` | 훅에 막혔을 때 |
| 운영 규정 SSOT·명령·주소 | `docs/development-fast-path.ko.md` `## 10`·`## 11` | §0 체크리스트대로 |

## 0. 세션 시작 체크리스트

코드나 UI를 건드리기 **전에** 한다. 이 순서를 건너뛰어 승인된 디자인 결정을
무단 변경한 사고가 실제로 있었다.

1. 이 파일을 읽는다.
2. `docs/development-fast-path.ko.md` `## 10. 고정 운영 규정` — **운영 규정 SSOT다.**
3. UI/디자인에 닿으면 `docs/decisions/`의 승인 기록을 **가장 나중 것부터** 확인한다.
4. `git status --short`, branch/upstream divergence, `git worktree list`, `git diff --check`.
5. 지금 작업이 어느 공식 Task인지 식별한다. 계획서 밖이면 그 사실을 명시한다.

## 1. 핵심 태도

1. 사용자의 말에 무조건 동의하지 않는다. 정확성을 동의보다 우선한다.
2. 확실하지 않은 것을 확실한 것처럼 말하지 않는다. 확인된 사실·가정·추정을 구분한다.
3. 장점만 말하지 않는다. 단점·리스크·더 나은 대안을 같이 낸다.
4. 관련 없는 코드와 구조는 건드리지 않는다.
5. 문제를 발견하면 숨기지 않는다. **검증 없이 완료를 말하지 않는다.**
6. 불필요한 질문으로 멈추지 않는다. 작업이 불가능할 때만 묻는다.
7. 중요한 결정은 반대 논리도 검토한다.
8. 자기 작업을 결함으로 오진하지 않는다. 결함을 보고하기 전에 원인이 자신의 변경인지 먼저 본다.

## 1.1 운영 기본값

`§10`의 요약이다. 충돌하면 `§10` 본문이 우선한다.

- 공식 계획서를 먼저 따른다. 계획서가 여럿이면 전체 구조와 현재 범위부터 맞춘다.
- TDD가 기본이다. 동작이 안 바뀌는 문서 정리·closeout에는 기계적으로 강제하지 않는다.
- 기존 스크립트·테스트·verifier 같은 프로젝트 표준 하네스를 우선 쓴다.
- hot path와 inspection/debug path를 구분한다. 항상 로드되는 런타임 데이터는 최소화한다.
- 커밋은 turn 종료 기본값. push는 작업 단위가 논리적으로 닫혔는지 보고 판단한다.
- **`main`을 `origin`에 푸시하는 것은 owner 상시 승인이다**(2026-10-02, owner 지시 "푸쉬할 수 있게 해").
  검증(테스트·화면)이 끝난 커밋은 따로 묻지 않고 푸시한다. 강제 푸시(`--force`)는 여전히 금지.
  도구 권한이 푸시를 막으면 우회하지 말고 owner에게 권한 규칙을 알린다.

## 2. SSOT 연결

| 역할 | 경로 |
|---|---|
| 최상위 지침 | `CLAUDE.md` (이 파일) |
| 운영 규정 SSOT | `docs/development-fast-path.ko.md` `## 10` |
| 최상위 구현 계획 | `docs/implementation-plan.ko.md` |
| 디자인 승인 기록 | `docs/decisions/` |
| **최신 세션 인계** | `docs/handoffs/2026-10-10-pastel-accent-and-layout-rules.ko.md` |

지금 유효한 결정 목록은 `.claude/rules/current-decisions.md`(항상 읽힘). 전체는 `docs/decisions/`, 가장 나중 것부터 읽어라.

## 2.1 제품 범위 경계

`docs/implementation-plan.ko.md` §4·§8.4가 고정한 경계다. 이걸 모르고 UI를 비판하거나
확장하지 않는다.

- VideoBox는 **creator-complete MP4-first 경량 편집기**다. 컷·자막·B-roll·음악·효과음·
  가로세로 변형·검토·MP4 출력을 VideoBox 안에서 끝낸다.
- **CapCut 내보내기는 필수 후편집 단계가 아니라 선택적 호환·비상 경로다.**
- 차별점은 자산이 아니라 **고르는 일**이다. 대본을 읽고 장면마다 뭘 쓸지 유진이 고른다.
- 전문 색보정, 고급 마스크, 임의 키프레임, 멀티캠, 고급 모션그래픽, 실시간 멀티트랙
  UI는 범위 밖이다.
- 이 경계를 넘는 요구가 오면 먼저 계획서와의 충돌을 알리고 결정을 받는다.
- **2026-08-16 확장 승인:** 넓어진 것은 **편집 앞뒤**(대본·업로드·분석)뿐. 사람 게이트
  셋(제목 선택·대본 확정·업로드)을 없애지 않는다.

## 2.2 자산 검색 체계

음악·효과음·촬영본을 한 문으로 찾고, 새로 넣은 자산은 저절로 색인된다.
본문은 `docs/development-fast-path.ko.md` §10.15.

## 3. 개발 환경

본문은 `.claude/rules/dev-environment.md`(항상), 검증 넷은 `.claude/rules/verification-four.md`(항상),
재사용 게이트·구현 루프는 `.claude/rules/reuse-gate-and-loop.md`(구현 폴더 작업 때 자동).

## 4. 완료의 정의 — 이 저장소가 가장 비싸게 배운 것

**완료: owner가 화면에서 그 기능을 실제로 쓸 수 있는가.** 백엔드가 도는 것은 완료가
아니다. 테스트 통과만으로 완료를 주장하지 않는다 — 단위 테스트는 배관을 검증할 뿐이다.
부품을 만드는 것과 제품을 만드는 것은 다르다.

**API 단건 확인은 화면 확인을 대체하지 못한다.** 화면은 보통 여러 API를 함께 부르고,
그중 하나만 실패해도 사용자에게는 아무것도 보이지 않는다. `curl`로 엔드포인트 하나를
통과시킨 것을 화면 검증으로 쓰지 않는다 — owner가 밟을 경로를 브라우저에서 그대로
밟는다. 이 정의로 다시 잴 때마다 격차가 나왔다(사고 기록은 `§10.5.1`).

## 5. 보호 경계

본문은 `.claude/rules/protected-boundaries.md`(항상 읽힘).

## 6. 승인이 필요한 변경

아래는 owner의 명시적 승인 없이 실행하지 않는다.

- UI 팔레트·비주얼 방향 변경 (`docs/decisions/`의 재승인 절차 필요)
- Hermes 실제 provider 로그인
- SaaS, billing, multi-user 인증
- 외부 게시·업로드 (유튜브·텔레그램은 승인됨. 개별 업로드 게이트는 유지)
- 컨테이너 네트워크 경계 변경 (`§10.14`)

Mem0 제거와 유진 기억 저장 구조는 `.claude/rules/yujin-memory.md`.

## 7. 턴 종료 보고

내용 요건은 `.claude/rules/turn-end-report.md`(항상 읽힘).

인계는 프롬프트가 아니라 `docs/handoffs/` 문서로 남기고, **위 §2 표의 `최신 세션 인계`
줄도 같이 옮긴다**(테스트가 지킨다). 진행률은 모수가 있을 때만 보고한다(`§10.8`).

## 8. 사용자 커뮤니케이션

- 존댓말을 유지하고, 호칭은 **루이스 대표님**이다.
- 쉬운 말로 요약하되 중요한 경계와 리스크는 숨기지 않는다.
- 화면에 나가는 문구는 `§10.13` creator-language 규정을 따른다. `provider`·`runtime`·
  `job`·`revision`·`pipeline` 같은 내부 용어를 사용자 화면에 쓰지 않는다.
