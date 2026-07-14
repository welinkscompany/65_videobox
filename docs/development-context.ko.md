# VideoBox 개발 컨텍스트

> 이 문서는 현재 브랜치의 작업 맥락과 우선순위를 요약하는 보조 컨텍스트 문서다. 현재 authoritative 상태/next slice 판단은 `docs/development-status-2026-06-29.ko.md`의 `## 235`와 `docs/implementation-plan.ko.md`의 `## 22`를 기준으로 본다. 최신 재개 절차는 `docs/handoffs/2026-07-14-local-media-director-plan-closeout.ko.md`에 있다.

## 폴더 역할

- 개발 폴더: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`
  - VideoBox 프로그램 자체를 개발하는 소스 코드 및 개발 워크스페이스다.
  - 코드, 아키텍처 노트, 구현 문서, 테스트, 개발 도구 관련 내용은 이 폴더에 둔다.

- 프로젝트 폴더: `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`
  - 프로그램이 만들어진 뒤 실제 운영하면서 사용하는 프로젝트 폴더다.
  - 생성된 결과물, 작업 데이터, 런타임 산출물, 사용자용 결과물은 이 폴더에 둔다.

## 작업 원칙

- 개발용 소스 파일과 운영용 프로젝트 산출물을 섞지 않는다.
- 개발 폴더는 제품을 만드는 워크스페이스로 취급한다.
- 프로젝트 폴더는 프로그램이 만들어내는 자산과 결과물을 운영하는 워크스페이스로 취급한다.

## 현재 결정

- 위 두 폴더는 의도적으로 분리된 구조이며, 나중에 명시적인 아키텍처 결정이 나오지 않는 한 계속 분리해서 유지한다.
- VideoBox는 더 이상 `자동 초안 생성기 + 얇은 review UI` 수준으로만 보지 않는다.
- 현재 기준 제품 방향은 `자동 초안 생성기 + 설명형 영상용 경량 후편집기 + 필요 시 CapCut handoff`다.
- 다만 풀 편집기, 고급 모션그래픽, 복잡한 오디오 믹싱, 색보정 전체, 자유 키프레임은 현재 범위에 넣지 않는다.
- 오픈소스 편집기 반입은 지금 즉시가 아니라, 편집 도메인 모델과 수정 API가 먼저 고정된 뒤에 검토하는 것으로 본다.
- 현재 다음 구현 우선순위는 `Local Media Director Slice 1 Task 1: local-only runtime 경계와 deterministic test guard`다.
- 승인 설계는 `docs/superpowers/specs/2026-07-14-local-media-director-design.md`, 실행 계획은 `docs/superpowers/plans/2026-07-14-local-media-director-implementation.md`다.
- 계획은 3개 순차 slice와 18개 TDD Task로 구성되며 production 구현은 시작 전이다.
- 현재 코드의 Gemini 자동 fallback, 외부 HTTP(S) runtime 허용, text-only Qwen adapter를 구현 완료로 오해하지 않는다.
- 마지막 기록된 broader baseline은 `docs/development-status-2026-06-29.ko.md` §234의 backend `801 passed`, frontend `105 passed`, production build 성공이다. 이는 이번 문서-only closeout에서 새로 실행한 결과가 아니므로 다음 production 변경 완료 주장에는 fresh 검증을 다시 사용한다.
