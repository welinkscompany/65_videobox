# VideoBox Codex 데스크톱 UI 복구 인계

작성일: 2026-08-12  
브랜치: `codex/videobox-container-compatibility`  
최신 소스: `ba4688780`

## 이번 검증에서 고정한 것

- 대시보드: 설명형 문장을 줄이고 `다음 작업`, `다음 할 일`, `초안 있음`, `자산 준비 완료`, `완성본 N개` 키워드 상태로 정리했다. 상태 API 실패 시 새 영상 생성을 유도하지 않고 `상태 확인 실패`와 재시도를 표시한다.
- 사이드바: 아이콘·라벨을 정리하고 접기/펼치기 액션 이름과 아이콘을 상태에 맞게 반전했다. 프로젝트 보관·삭제·복구 실패는 busy와 `role=alert`로 남긴다.
- 자산: 프로젝트 범위 즐겨찾기/최근 사용, 활성 필터 색상, 24개 페이지 제한, 가져오기 응답 유실 재시도 idempotency, 프로젝트 자산 카드 스타일을 고정했다.
- 자체 편집기: 데스크톱 workbench의 미리보기·타임라인·자산 패널이 부모 화면을 밀어내지 않고 내부에 스크롤을 보유한다.
- 검토/출력: `source_session_id`까지 포함한 lineage 검증, stale 검토 재생성 CTA, 출력 카드 4열과 영상 크기 제한, 제품 소유 링크 스타일을 반영했다.

## 검증 증거

- 프론트: Vitest 63개 파일, 875개 통과. Creation readiness 실패 경로(건너뛰기·다시 준비·취소)는 오류를 `role=alert`로 표시하고 재시도 상태를 유지한다.
- 타입/빌드: `npx tsc -b --pretty false`, `npm run build` 통과.
- provenance: `.venv\\Scripts\\python.exe -m pytest tests/test_editor_ui_source_provenance.py` 21개 통과.
- owner-ready 회귀: `.venv\\Scripts\\python.exe -m pytest -q tests/test_owner_ready_script.py` 116개 통과. Smoke timeout은 프로세스 트리 종료 후 후속 검증을 fail-closed로 기록해 bounded failure를 유지한다.
- 백엔드 전체: `.venv\\Scripts\\python.exe -m pytest -q tests` 3321개 통과, 53개 skip, 1개 warning (`00847457f` 기준; 이후 `ba4688780`은 프론트 readiness만 변경).
- 공식 런타임은 `scripts/owner-ready.ps1 -Mode Start -Rebuild -Json` 후 `-Mode Check -Json`으로 갱신했다. VideoBox health 200, branch/upstream·worktree·도구·CapCut pass. Hermes dashboard만 별도 서비스 미기동으로 blocked.

실제 브라우저에서 재빌드된 런타임을 다시 열어 확인한 스크린샷:

`artifacts/qa/desktop-owner-ui-recovery/audit-2026-08-12/`

- `02-media-runtime-final.png`
- `03-editor-runtime-final.png`
- `04-review-runtime-final.png`
- `05-outputs-runtime-final.png`

브라우저 측정 결과: 검토 콘텐츠 폭 약 1009px, 자체 편집기 workbench 폭 약 1124px, 출력 페이지 scrollHeight 968px, 완성본 영상은 카드 안에서 약 182×102px로 제한됐다. 편집기에서 접힌 사이드바를 클릭하면 `data-state=expanded`, 라벨이 `사이드바 접기`로 바뀌는 역방향 동작도 확인했다.

## 아직 owner가 직접 해야 하는 게이트

- QA mutation manifest는 과거 API lane과 UI lane이 섞여 있으므로 실제 브라우저에서 프로젝트 생성→자산 가져오기→분석→편집→검토 승인→SRT/MP4/CapCut 출력을 새로 수행한 증거로 간주하지 않는다.
- 최종 MP4 전체 시청·청취, 자막 타이밍, CapCut Desktop import/open은 owner 확인이 필요하다.
- Home의 완성본 수는 lineage 정책에 따라 역사 개수와 현재 출력 대기 수를 별도 표기할지 다음 제품 결정에서 확정한다.

보호해야 할 기존 runtime QA 프로젝트 `videobox-pc-qa-20260811153350`는 삭제·덮어쓰기하지 않는다.
