# 2026-07-07 output readiness UI closeout

이번 slice의 제품 결정은 `출력 가능 여부를 개요 화면에서 바로 보이게 한다`다.

확인된 사실:

- 백엔드 output gating은 이미 review blocker와 approval 상태를 기준으로 출력 생성을 막고 있었다.
- 기존 웹 UI도 버튼 disable은 있었지만, 사용자가 개요 화면에서 `지금 내보내도 되는지`, `안 되면 무엇을 해야 하는지`를 한눈에 읽는 요약은 부족했다.
- 별도 readiness truth를 새로 만들면 backend gating과 drift가 생길 수 있으므로, 웹 UI는 기존 `reviewSnapshot`과 `timeline`의 blocker/approval 상태만 읽는 표시 계층으로 제한했다.

반영:

- `apps/web/src/App.tsx`
  - 출력 카드에 `내보내기 가능`, `승인 필요`, `내보내기 보류`, `준비 확인 불가` readiness 요약을 추가했다.
  - 보류 상태에서는 검수 표시 수와 대기 추천 수, 다음 행동을 함께 보여준다.
- `apps/web/src/styles.css`
  - readiness banner의 ready/pending/blocked 표시 스타일만 추가했다.
- `apps/web/src/app.test.tsx`
  - blocked / draft / approved 세 상태의 output readiness 문구를 frontend focused test로 고정했다.

검증:

- RED:
  - `npm test -- --run src/app.test.tsx -t "disables preview and export controls until review blockers are cleared|keeps output actions disabled until operator approval even when blockers are clear|surfaces approved output readiness before export generation"` 실패 확인
  - 실패 이유: 새 readiness 문구 없음
- GREEN:
  - 같은 exact test: 3 passed
- focused / build / fast-path:
  - `npm run test:focused` -> 75 passed
  - `npm run build` -> 통과
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` -> 25 passed
  - `./scripts/dev-fast-path.ps1 -Mode output-gating` -> 24 passed

재사용 판단:

- 관련 BrollBox/외부 OSS 반입 후보는 이번 범위에 없음.
- 이번 작업은 output readiness 표시 계층이며 CapCut export adapter, auto cut, STT/alignment, B-roll scoring 로직을 재사용하거나 이식할 성격이 아니다.
- 실제 반영 방식은 기존 VideoBox review/output 상태 계약 재사용이다.

남은 리스크:

- 전체 backend regression `py -m pytest -q`는 이번 turn에서 재시도하지 않았다.
- readiness banner는 backend gating을 대체하지 않는다. 실제 출력 가능 여부의 최종 truth는 기존 output gating API/worker 경계가 유지한다.

다음 추천 goal:

```text
main 최신 기준에서 output readiness UI가 실제 사용자 흐름에서 충분한지 브라우저 smoke로 확인하고,
부족하면 readiness banner의 문구/위치를 최소 조정한다.
검증은 npm run test:focused, npm run build, 필요한 fast-path만 실행한다.
전체 backend regression은 이전 timeout 이력이 있으므로 완료 주장에 포함하지 않는다.
```
