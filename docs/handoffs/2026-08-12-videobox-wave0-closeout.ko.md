# VideoBox Wave 0 closeout

작성일: 2026-08-12  
기준 브랜치: `codex/videobox-container-compatibility`

Wave 0는 프로젝트 우선 진입, 전역 메뉴·프로젝트 단계 분리, truthful workspace summary,
데스크톱 shell 계층과 키워드 문구를 코드와 자동 검증으로 고정했다. 설정 메뉴는 접근 가능한
href에 내부 project ID를 노출하지 않으면서 SPA 이동 시 현재 프로젝트를 query로 보존한다.

## §4–5 갭 표

| 설계 기준 | 증거 | 상태 | 남은 게이트 |
| --- | --- | --- | --- |
| §4 전역 메뉴 4개와 프로젝트 단계 5개 분리 | `ProductShell.test.tsx`, `product-shell.spec.mjs`, route manifest 테스트 | 검증됨 | 실제 owner 브라우저 확인 |
| §4 프로젝트 카드 단일 다음 행동·실패 시 상태 확인 | `AppRouter.test.tsx`, workspace-summary API 테스트 | 검증됨 | 실제 데이터로 owner 확인 |
| §5 viewport 고정·영역 내부 스크롤·데스크톱 최소 1280×800 | `product-shell.css`, shell DOM/E2E geometry 테스트, build | 자동 검증됨 | owner-ready 시각 캡처 미검증 |
| §5 버튼 40px·간격 8/16px·아이콘 접근성 이름 | 제품 CSS, ProductShell DOM 테스트, E2E 접근성 스냅샷 | 부분 검증 | 실제 화면에서 겹침·밀도 확인 |
| §5 설명문보다 작업 키워드 우선·금지 내부 용어 차단 | ProductShell 금지 문구 테스트, voice E2E 접근성 스냅샷 | 검증됨 | 전체 화면 owner 카피 검토 |

## 실행 증거

- canonical frontend focused: route/AppRouter/ProductShell `67 passed`
- ProductShell focused 재검증: `29 passed`
- production build: 성공
- Wave 0 selector/fixture 보정 E2E: editor 5, exact preview, media, review, voice 단독 각 성공
- `git diff --check`: 성공
- 커밋: `0e25375`, `ab75eea`

## 미검증 및 주의

`scripts/owner-ready.ps1`의 Start/Rebuild가 PostgreSQL/workspace health 502로 막혀 실제 owner-ready
브라우저 캡처와 사람의 시각 검증은 수행하지 못했다. 따라서 computed style·DOM·자동 E2E만으로
화면 완료를 주장하지 않는다. 컨테이너가 정상 기동하고 owner가 화면을 열 수 있게 되면 §5의
사이드바 겹침, 버튼 밀도, 내부 스크롤을 1280×800 이상에서 직접 확인하고 이 문서를 갱신해야 한다.

또한 설정 링크의 공개 href는 `/settings/general`로 유지하고, SPA 클릭 핸들러가
`/settings/general?project_id=<현재 프로젝트>`로 이동시킨다. 새로고침·직접 URL에서는
`project_id` 또는 검증된 localStorage fallback을 사용한다.
