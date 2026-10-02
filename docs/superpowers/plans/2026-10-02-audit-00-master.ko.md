# 2026-10-02 점검 후속 — 실행 총괄 (먼저 읽는 문서)

> **For agentic workers:** 이 문서는 세 상세 계획서의 **순서·경계·멈춤 규칙**이다. 구현은
> 각 계획서를 superpowers:subagent-driven-development로 Task 하나씩 진행한다.
> 실행 모델은 **Claude Sonnet**. 이 문서와 각 계획서의 Global Constraints가 모든 Task에 걸린다.

**Spec:** `docs/superpowers/2026-10-02-audit-follow-up-plan.ko.md` (요약판) +
`docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md` (owner 결정·경계)

## 1. 실행 순서 (바꾸지 않는다)

| 순서 | 계획서 | Task 수 | 왜 이 순서인가 |
|---|---|---|---|
| 1 | `2026-10-02-audit-a-security-tools-rename.ko.md` | 11 (0~10) · 약 5~6.5시간 | 비밀값 유출(Task 0)이 가장 급하다. 이름 바꾸기 라우트를 묶음 F가 쓴다. 다리 토큰은 더빙(묶음 E) 실측 전에 끝나 있어야 두 번 고치지 않는다 |
| 2 | `2026-10-02-audit-bf-yujin-capabilities.ko.md` | 23 (+조건부 23) · 약 22~35시간 | 가장 크다. `YujinPanel`·`OutputsPage`를 G보다 먼저 바꾼다 |
| 3 | `2026-10-02-audit-g-screen-improvements.ko.md` | 18 (0~17) · 약 8~9시간 | 같은 두 파일을 마지막에 다듬는다. 앵커를 **문자열로** 찾게 쓰여 있어 앞 계획 뒤에도 따라간다 |

**계획서끼리 병렬로 돌리지 않는다.** 아래 파일을 여럿이 같이 고친다:
`apps/web/src/features/editor/workbench/YujinPanel.tsx`(B–F·G), `apps/web/src/app/OutputsPage.tsx`(B–F·G),
`services/api/src/videobox_api/routers/library_assets.py`(A·B–F), `apps/web/src/api.ts`(A·B–F),
`apps/web/src/task22-parity-owners.test.ts`(셋 다), `docs/oss/editor-ui-source-map.json`(A·G — ProductShell 해시).

## 2. Task를 시작할 때마다 (Sonnet 실행자 공통)

1. `git status --short`가 깨끗한지, `git log -1`이 앞 Task 커밋인지 본다. 아니면 멈추고 보고.
2. Task의 **Files**를 열어 앵커(줄 번호가 아니라 인용된 옛 코드 문자열)를 찾는다. 줄 번호는 앞 계획이
   들어오면 밀린다 — **문자열이 그대로 있으면 진행, 문자열이 없으면 멈추고 보고**(짐작해서 고치지 않는다).
3. RED 시험이 **실패하는 것을 실제로 보고** 나서 구현한다. 처음부터 통과하면 멈추고 보고.
4. 시험 명령: 백엔드 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>::<시험>`,
   웹 `cd apps/web && npx vitest run <파일>`(저장소 루트에서 돌리면 jsdom이 깨진다).

## 3. 멈춤 규칙 (이 때는 진행하지 말고 owner에게 보고)

- 컨테이너는 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`로만 다룬다. 이것이 실패하면 멈춘다.
- **푸시가 도구 권한으로 막히면 우회하지 않는다.** owner에게 다음을 요청한다:
  `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`
  (또는 허용 규칙 `Bash(git push origin main)` 추가). 강제 푸시는 금지.
- 유진 지연 중앙값이 기준선의 **1.5배**를 넘으면 B–F 계획서의 선택 Task(두 단계 고르기)를 검토 대상으로 올리고 멈춘다.
- 같은 땜질을 두 번 하게 되면 멈춘다(원인이 다른 데 있다).
- 이미 알려진 실패 둘은 이번 변경 탓이 아니다(세션 전 커밋에서도 실패 — 2026-10-01 인계):
  `editor-workbench.test.tsx` "gives the material dock back …", `test_owner_ready_script.py::test_smoke_timeout…`.
  e2e `release-gates` "dock drag" 성능 관문은 기계 부하로 흔들린다 — G 계획서의 재측정 Task 전까지는
  **세션 전 커밋과 번갈아 재서** 같은 범위면 무관으로 본다.

## 4. owner 결정이 필요해 **건너뛰는** 것

| 항목 | 위치 | owner에게 물을 것 |
|---|---|---|
| 비밀값 교체 | A Task 0 | ".env.container가 예전 이미지 층에 남아 있습니다. DB 비밀번호·게이트웨이 토큰을 새로 바꿀까요?" |
| 유진이 자산 권리(출처) 적기 | B–F Task 21(F6) | "출처는 업로드 승인을 막는 안전장치입니다. 유진이 대표님 말을 듣고 적게 할까요, 화면에서만 적게 둘까요?" |
| 장면 영상 생성(약 20분 GPU) | B–F Task 21(F8) | "유진에게 장면 영상 만들기를 열까요? 한 번에 약 20분 걸립니다." |
| e2e 스냅샷 그림 갱신 | G | 바뀐 화면 그림 비교를 owner가 보고 승인 |

## 5. 총괄 검토에서 확인·보완한 것 (2026-10-02)

- 세 계획서마다 다른 검토자가 실제 코드와 앵커를 대조하고 직접 고쳤다(A 약 30곳, B–F 약 40곳, G 15곳 이상).
- 계획 A Task 0: `.env.container`가 이미지에 구워지던 비밀값 유출 + 이미지에 실린 윈도우용 `.venv-chatterbox`(1.9GB). 혼자 먼저 실행할 수 있다.
- 계획 A Task 9: 분위기 태그에 문장 조각이 섞이는 **서버 쪽 원인**(화면 필터는 방어 겹으로 남김).
- 계획 B–F Task 4: 같은 편집안을 두 번 적용하면 미리보기 링크·업로드 승인 요청이 두 번 생기던 위험 → 조건부 UPDATE로 한 번만, MCP 재시도는 `editing_proposal_needs_refresh`일 때만.
- 계획 B–F Task 6: 유진 적용기가 `caption_style` 같은 세션 맨 위 값을 버리던 **기존 결함**.
- 계획 B–F Task 7 Step 0: 편집 판단 프롬프트의 옛 "검토용 후보만 만든다" 문장.
- 계획 G Task 0: 흔들리던 e2e 성능 관문 재측정 + 92를 박아 둔 단위 시험(main에서 이미 실패) 수리.
- 계획 G Task 12~15: 자료실 썸네일이 요청마다 원본 전체를 sha256하던 느림, 편집기 중복 요청,
  검토본 장면 0개(전사 표에서 장면을 읽는 구조), 문구가 바뀐 e2e 재실행.

## 6. 끝의 끝

세 계획서가 모두 닫히면: 백엔드 전체 pytest를 **단독으로**(약 50분), 웹 전체 vitest, `npm run build`,
e2e 48건, 컨테이너 재빌드 후 브라우저로 1440×900·375 폭 확인. 인계 문서
`docs/handoffs/2026-10-0X-…ko.md`를 새로 쓰고 CLAUDE.md §2 "최신 세션 인계" 줄을 옮긴다(시험이 지킨다).
