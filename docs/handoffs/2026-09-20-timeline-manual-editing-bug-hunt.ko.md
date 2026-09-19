# 타임라인 수동 편집 실사용 버그 사냥 (2026-09-20)

## 요청과 배경

대표님 지시: "타임라인에서 사람이 직접 편집하는게 오류가 없는지 직접 테스트 해서
오류, 버그 찾아봐" — 실제 프로젝트(`0907-b26195af`, "사진 브이로그 실기 0907")를
브라우저에서 직접 조작하며 분할·트림·삭제·순서변경·실행취소를 밟고, 이어서 유진
채팅·검토(리뷰) 화면까지 확장해서 봤다. 커밋 2건(`151bf9f8`, `34d59bb2e`)이 이미
`main`에 푸시돼 있다.

## 고친 것 (검증 완료, 커밋 `151bf9f8`)

1. **자막 선택 누적 버그** — 장면을 두 번 나누면 생긴 자막들이 전부 최초 조상
   장면의 `segment_id`(대본 정렬·번역용 영구 계보)를 계속 가리켜서, 화면에서
   클립 하나를 고르면 관련 없는 형제 자막 여러 개가 함께 "선택됨"으로 떴다.
   `segment_id`는 그대로 두고(합치기 의미 보존이 목적, 바꾸면 회귀남 —
   `test_merge_keeps_right_semantics_windowed_and_reanchors_legacy_export_overlay`가
   그 계약을 지킨다) **화면 전용 필드 `owning_segment_id`**를 새로 추가해서
   `composition_plan.py`/`editor_playback_manifest.py`/`editorViewModel.ts`/
   `TimelineDock.tsx`에 배선했다.
2. **장면 번호 순서 꼬임** — `TimelineDock.tsx`의 `laneOrdinalByClipId`가 백엔드
   배열 순서 그대로 번호를 매겨서, 분할을 거듭하면 시간순과 어긋났다(예:
   4번째→7번째→5번째). `startSec` 기준 정렬을 추가했다.

두 건 다 RED→GREEN, 백엔드 142건·프런트 570건(무관한 사전 결함 1건 제외) 회귀
없음 확인.

## 버그 아닌 것으로 정정된 것

- **확대 시 클립이 화면 밖으로 나감 / 상단 툴바가 가로로 넘침** — `product-shell.css:11`에
  `@media (min-width:1024px) { [data-vb-desktop-shell] { min-width:1280px; ...} }`가
  **의도적으로** 박혀 있다. 1024~1279px 구간에서 가로 스크롤이 나는 게 설계다.
  1920×1080 등 정상 해상도에서는 전혀 재현 안 됨.
- **"편집할 자리를 찾고 있어요" 문구가 인사말에도 뜸** — 문구 재사용 버그가
  아니라, 모든 메시지가 내용과 무관하게 항상 `answering`+`judging` 두 단계
  LLM 호출을 순서대로 돈다(`EditorWorkbenchRoute.tsx:2066-2073`, 2026-09-01
  승인 결정 "말하면 바로 적용"에 따른 의도된 구조). 다만 **모든 대화 한 번마다
  로컬 LLM을 두 번 부르는 셈**이라 응답 지연의 한 원인이다 — 고칠지는 제품
  판단이 필요해서 손 안 댔다.

## 아직 미해결 (원인 특정, 수정은 다음 세션)

- **최초 진입 시 클립이 2px로 렌더** — 컨테이너 콜드 스타트 직후 딱 한 번만
  재현됐고, 이후 5~6차례 재현 시도 전부 실패. `initialPixelsPerSecond`가
  `viewportWidthPx`/`durationSec`를 잘못된 값으로 한 번만 계산해서 고정되는
  레이스 컨디션으로 추정(`TimelineDock.tsx` 251-265행의 `useReducer` lazy
  initializer, mount 시 한 번만 실행됨). 재현 스크립트가 없어서 다음 세션에서
  콜드 스타트 직후를 노려 다시 잡아야 한다.

## 되돌린 시도 — 검토(리뷰) 화면이 최신 편집을 못 따라가는 버그

**증상**: 장면을 나눈 뒤 "현재 편집본으로 검토본 다시 만들기"를 눌러도 검토
화면(`GET /timelines/{job_id}`)의 장면 경계가 분할 이전 값 그대로였다.

**진짜 원인**: `refresh_review_for_current_edit`
(`packages/storage-abstractions/src/videobox_storage/local_project_store.py`)가
`source_session_revision` 같은 신선도 표시만 갱신하고, 저장된 timeline 문서의
`tracks`는 일부러 안 건드리는 설계다. 렌더 경로는 항상 session과 함께 다시
`materialize_editing_session_timeline`을 부르므로 결과물은 맞지만, 검토
화면은 저장된 값을 그대로 읽는다.

**첫 시도(커밋 `2183eec0`, 이후 되돌림)**: `timeline["tracks"]`를
`materialize_editing_session_timeline`의 결과로 덮어써서 고치려 했다.
**실패 원인**: `composition_plan.py` 240-290행의 `source_tracks =
timeline.get("tracks", [])`가 **원본 소스 길이 계산 기준**(`source_durations`/
`source_bounds`, 트림·리플배속 판단에 쓰임)으로도 이 필드를 읽는다는 걸
놓쳤다 — 단순 "화면 표시용"이 아니었다. 덮어쓰니 broll/overlay 클립의
`overlay_type`/`overlay_payload`가 통째로 빠져서 `playback-manifest`가
422로 죽었다. `git revert`로 되돌리고 재빌드해서 코드는 안전한 상태로
복구했다(`34d59bb2e`).

**부수 피해와 복구**: 되돌리기 전 이 버그 있는 코드가 **실제 프로젝트**
(`0907-b26195af`)의 `timeline_002.json`에 이미 손상된 데이터를 썼다
(`overlay_type` 유실 8건 + 근거 없는 중복 클립 3건). 세션에서 다시 계산한
값으로 8건은 복원, 3건은 삭제해서 복구했고 `playback-manifest`/`timelines`
둘 다 200 확인, 브라우저에서 편집기·검토 화면 정상 렌더 확인했다. 원본은
`timeline_002.json.bak-before-repair`로 남겨 뒀다
(`D:/AI_Workspace_louis_office_50/20_project/65_videobox-project/runtime/projects/0907-b26195af/timelines/`).

**다음에 제대로 고치려면**: `timeline["tracks"]`를 손대지 말고, 검토 화면이
읽는 자리(`GET /timelines/{job_id}` → `orchestrator.get_timeline_job`,
`services/api/src/videobox_api/routers/timeline.py:27`)가 **읽을 때마다
`materialize_editing_session_timeline`을 다시 불러서** 보여주도록 바꿔야
한다 — `editor_playback_manifest.py`의 `build_editor_playback_manifest`가
이미 그 패턴이다. 저장된 `tracks`는 원본 소스 길이 기준으로 그대로 두고,
API 응답 직전에만 최신화한다.

## 백엔드 컨테이너는 소스 볼륨 마운트가 없다

`docker inspect`로 재확인: `65_videobox-videobox-workspace-1`의 마운트는
`runtime`/`drive-sync`/`owner-drop`/`snapshot`/`model_cache`뿐, 저장소
소스(`packages/`, `services/`)는 **이미지에 빌드 시점에 박힌다**. 백엔드
Python 파일을 고치면 `docker restart`가 아니라
`.\scripts\owner-ready.ps1 -Mode Start -Rebuild`로 재빌드해야 반영된다
(PowerShell 실행 정책이 막으면 `powershell -ExecutionPolicy Bypass -File
.\scripts\owner-ready.ps1 ...`). 오늘 이걸 모르고 재시작만 했다가 "고쳤는데
반영이 안 된다"로 한 번 헤맸다.

## 아직 못 한 것

- 숏폼·업로드·렌더(완성본 만들기) 화면은 이번 세션에서 손도 못 댔다.
- 타임라인 안에서도 브롤·캡션·오버레이 트랙은 narration만큼 깊게 안 봤다.
- 유진 로컬 모델이 트리비얼한 인사말에도 이따금 `LOCAL_TIMEOUT`을 내는 것을
  봤다 — `lms unload`+`load -c 32768`로 그 순간은 풀렸지만, 근본 원인(GPU
  경합인지 LM Studio 설정 문제인지)은 못 짚었다.

## 다음 세션 시작 프롬프트

```
검토(리뷰) 화면이 최신 편집을 못 따라가는 버그를 제대로 고쳐줘.
docs/handoffs/2026-09-20-timeline-manual-editing-bug-hunt.ko.md의
"다음에 제대로 고치려면" 절을 읽고, GET /timelines/{job_id}가
저장된 tracks를 그대로 읽는 대신 매번 materialize_editing_session_timeline을
다시 불러서 반환하도록 고쳐줘. timeline["tracks"] 자체는 손대지 마
(composition_plan.py의 source_durations/source_bounds가 그 값을
원본 소스 길이 기준으로 쓴다 — 2026-09-20에 그걸 모르고 덮어썼다가
오버레이가 깨져서 되돌린 적 있다). 고치고 나서 실제 프로젝트
0907-b26195af에서 장면을 나눈 뒤 검토 화면을 브라우저로 직접 밟아서
경계가 맞는지 확인해줘.

이어서 시간 되면: 최초 진입 시 클립이 2px로 렌더되는 버그(콜드 스타트
직후 1회만 재현됨, TimelineDock.tsx의 initialPixelsPerSecond 레이스로
추정)를 콜드 스타트 직후에 노려서 재현하고 고쳐줘. 그리고 숏폼·업로드·
완성본 만들기 화면도 이번엔 브라우저로 직접 밟아서 버그 있는지 봐줘.
```
