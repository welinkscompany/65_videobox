# VideoBox 2026-08-25 E2E 복구·재배포 인계

## 실제로 한 일

- 현재 승인 화면을 예전 명칭·배치로 되돌리지 않고 E2E 계약을 복구했습니다. 대상은
  편집기 `소재`·`세부 정보`, 넓은 화면의 도크 폭 조건, 접힌 전체 메뉴, 라이브러리
  사이드바 필터, 시작 선택 화면, 미리보기 시간 표기, TTS 접근성 이름입니다.
- 그 과정에서 접힌 전체 메뉴가 `Escape`로 닫히지 않는 실제 조작 결함을 발견해
  `TopBar.tsx`에서 메뉴와 프로젝트 전환 목록을 Escape로 닫도록 고쳤습니다.
- 코드리뷰 지적에 따라 URL 자체는 제외하되 실제 `aria-label`·`aria-labelledby`·이미지
  대체 텍스트에는 내부 식별자가 나오지 않는지 시험으로 확인합니다.
- 개발 기록은 `docs/development-status-2026-06-29.ko.md` 끝의
  `개발 기록 — 2026-08-25 전역 이동·E2E 계약 복구와 로컬 재배포`에 남겼습니다.

## 검증 근거

- `apps/web`에서 `npx vitest run --silent` — 96 파일, 1,282 통과.
- `apps/web`에서 `npx tsc --noEmit` — 통과.
- `apps/web`에서 `npx playwright test --reporter=line` — 47 통과.
- 공식 재빌드: `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory` 실행.
  이후 `http://127.0.0.1:5173/health`는 `status: ok`, 저장소 `postgres`를 반환했고,
  `/api/projects`는 실제 프로젝트 15개를 반환했습니다.

## 검증했지만 못 끝낸 것

- `apps/web/src/api.ts`의 화면 생산 코드에서 이름으로 닿지 않는 API 22개는
  `화면에 붙일 것 / 지울 것 / 그대로 둘 것`을 대표님이 결정해야 합니다. 구현이나
  삭제는 하지 않았습니다.
- 외부 게시·업로드·provider/live 환경은 실행하지 않았습니다.
- `output/`은 사용자가 보존한 미추적 산출물입니다. 커밋·푸시하지 않았습니다.

## 목요일에 화면으로 확인해야 할 것

- 실제 대표님 프로젝트에서 상단 경로, 작은 이전 버튼, 조밀한 보조 버튼과 툴팁의
  찾기 쉬움·방해 정도를 확인합니다.
- 긴 프로젝트 이름과 좁은 화면에서 현재 위치가 충분히 읽히는지 확인합니다.
- 승인된 팔레트·배치가 실제 화면에서 의도치 않게 달라지지 않았는지 확인합니다.
  자동시험·DOM·컨테이너 응답은 이 사람 수용 확인을 대체하지 않습니다.

## 커밋·푸시·배포

- 최신 코드 커밋: `68e3ddec3 수정: 현재 화면 계약에 맞춘 E2E와 메뉴 닫기`.
- 원격 푸시: `origin/codex/videobox-container-compatibility`에 `68e3ddec3`까지 완료.
- 로컬 컨테이너 배포: 공식 재빌드·기동 뒤 `/health` 200 확인. 외부 운영 배포나
  게시·업로드는 하지 않았습니다.

## 다음 세션 한 줄 프롬프트

`D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility 에서 CLAUDE.md와 docs/handoffs/2026-08-25-videobox-e2e-closeout-deployment-handoff.ko.md를 먼저 읽고, git 상태·원격 동기화·5173 /health를 확인한 뒤 API 22개를 화면 연결/삭제/유지로 분류하는 문서 작업부터 이어서 진행해줘.`
