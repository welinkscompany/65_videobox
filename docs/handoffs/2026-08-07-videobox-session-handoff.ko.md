# 2026-08-07 세션 핸드오프 — 계획서 Task 1~21 전부 완료

## 이 세션에서 한 일 (전부 커밋·푸시 완료, worktree clean)

`codex/videobox-container-compatibility` 브랜치, 원격과 동기화 상태.

| 커밋 | 내용 |
|---|---|
| `f26d88bf5` | feat: 유진 채팅 UI를 로컬 우선 대화 경로에 연결 (Task 13/14) |
| `9c5ffd33c` | docs: 계획서에 Task 13/14 closeout 기록 |
| `a3a4c201f` | fix: 로컬 런타임 model_name을 환경변수로 해석 |
| `bf4d9e6f6` | docs: model_name 고침 closeout 기록 |
| `f92f4ef30` | docs: 루프 세션 핸드오프 (중간 지점) |
| `295ebe721` | feat: 미디어 인박스 워치 사이클 수동 실행 스크립트 + 실제 Drive 첫 이동(9개) |
| `a6b2215dc` | docs: F-7 이미 해결됨으로 정정 |
| `bb299a135` | docs: 컨테이너 네트워크 경로는 옵션 2(현행 유지)로 owner 결정 기록 |
| `605518b8d` | feat: Task 18 마무리 — 반복 워처 루프 + 라이브러리→project 복사 API |

## 계획서 상태

`docs/superpowers/plans/2026-08-05-videobox-owner-usable-recovery.md`의 Task 1~21이
**전부 완료**됐다. 이번 세션에서 닫은 것:

- **Task 13/14**: 유진 채팅을 로컬 동기 엔드포인트로 재배선. `HermesRunService`/
  capability-token 코드는 안 건드림. 옛 SSE 테스트 15개를 새 흐름에 맞게 재작성
- **Task 18**: 실제 Drive 폴더에서 첫 실이동(owner 참관, 영상 9개), 이어서 반복 워처
  루프(`run_inbox_watcher_loop`, `VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED` opt-in, 기본 꺼짐)와
  라이브러리→project 복사 API(`POST /api/projects/{id}/media-inbox/import`,
  `GET /api/media-inbox/assets`)까지 완성. **프론트 UI는 아직 없다** — 라이브러리 파일을
  고르는 화면이 다음 후보
- **모델명 환경변수화**: `LocalOpenAICompatibleRuntimeConfig.model_name` 기본값
  (`qwen3-35b`)과 실제 로드 모델(`qwen/qwen3.6-35b-a3b`) 불일치를
  `resolve_local_runtime_config()` + `VIDEOBOX_LOCAL_MODEL_NAME`로 해결
- **컨테이너→호스트 LM Studio 네트워크 경로**: owner가 옵션 2(호스트 네이티브 유지,
  코드 변경 없음)로 결정, `architecture-plan.ko.md` §11 권고와 일치
- **F-7(중복 액션 노출)**: 재확인 결과 이전 세션에 이미 해결·테스트로 고정돼 있었다.
  추가 변경 없음

## 이번 세션에서 잡은 실제 결함 (코드리뷰)

`import_media_inbox_asset_to_project()`의 `filename` 파라미터에 경로 탐색(`../`) 방어가
없어 `library_root` 밖 임의 파일을 프로젝트로 복사할 수 있는 결함이 있었다. 구분자
포함 시 거부하도록 고치고 회귀 테스트를 추가했다(라이브러리는 항상 flat이라 정당한
파일명에 구분자가 올 일이 없다).

## 세션 인프라 관련 발견

Browser 미리보기 도구(`preview_start`)로 `api` 서버를 띄우면 worktree가 아니라
**메인 브랜치 체크아웃 경로**(`D:\...\65_videobox`, 컨테이너 마이그레이션 계획 문서만
있는 뒤처진 브랜치)에서 실행된다. 실제 개발선(`codex/videobox-container-compatibility`
worktree)의 최신 코드를 역방향 검증하려면 `.venv/Scripts/python.exe scripts/run_api.py`를
worktree 경로에서 **직접 Bash로 백그라운드 실행**해야 한다. 다음 세션에서 API 서버로
실측할 때 이 함정을 기억할 것.

## 남은 것

계획서(Task 1~21) 자체에는 더 없다. 자연스러운 다음 후보:

1. **라이브러리→project 복사 프론트 UI** — 백엔드 API는 이번에 완성했지만, 라이브러리에
   쌓인 파일을 고르는 화면이 없다. 지금은 API를 직접 호출해야 프로젝트에 반입된다
2. `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`의 나머지
   항목은 대부분 이미 해결됐거나(F-6, F-7처럼) owner의 결정 자체가 필요한 사안(D-1
   오렌지 팔레트 재승인 등)이라 별도 지시가 있을 때 착수

owner에게 "몇 % 남았는지" 질문을 받았을 때 답한 내용: 프로젝트 문서 어디에도 전체
프로그램 단위의 "N개 중 M개" 카운트가 정의돼 있지 않다(계획서는 §4 기능 목록 +
§5 마일스톤으로만 MVP 범위를 정의). 의도적으로 안 만든 큰 덩어리는 외부 AI(GPT 등)
연동(§23, Hermes 게이트웨이·capability signer·OAuth) — 로컬 AI로 충분하다고 판단해
보류한 것이지 미완성이 아니다. 정확한 %가 필요하면 기준(예: §4 기능 목록 중 실제
동작 비율)을 정해 실측으로 계산해야 한다.
