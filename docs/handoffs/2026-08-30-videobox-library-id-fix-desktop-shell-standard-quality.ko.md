# 2026-08-30 인계 — 자료실 id 목록 노출 수정, Tauri 데스크톱 셸 착수(빌드 막힘), 표준 화질 추가

## 이번 세션에서 실제로 한 일

### 1. AI 영상 생성 실물 검증 — 오류 없음 (owner 요청 "실제로 만들어보자")

이전 세션에서 붙인 화면(빠른 미리보기 화질 선택·취소 버튼·자료실 등록·새로고침
복귀)을 실제 브라우저에서 눌러가며 검증했다.

- **빠른 미리보기**: scene 2에서 6.1초 만에 완성, `library_asset_id` 정상 등록.
- **취소 버튼**: scene 3에서 고화질 실행 후 취소 → ComfyUI `/history`로
  `execution_interrupted`(KSampler 노드) 직접 확인 — 실제로 GPU 작업이 멈췄다.
  다른 이미지 생성 작업은 건드리지 않았다.
- **새로고침 복귀**: scene 4에서 고화질 시작 직후 새로고침 → "이어서 확인하는
  중이에요…"가 정확히 뜨고 폴링이 이어졌다.

세 가지 모두 실물 검증 완료, 결함 없음.

### 2. 알려진 격차 수정 — 목록 조회의 `library_asset_id`가 항상 null이던 문제 (커밋 `0f7cafa12`)

`GET .../scene-videos`(목록)가 `library_asset_id`·`gif_asset_id`·
`gif_library_asset_id`를 항상 `None`으로 돌려주고 있었다 — 만드는 순간의
응답에만 값이 있었다. 새로고침하면 "자료실에도 저장했어요"가 사라져 보이는
문제였다.

**고친 방식**: `scene_video_service.py`가 생성 직후 이 값들을 scene 자산
자체의 메타데이터에도 `store.update_asset_metadata`로 같이 적어 두고,
`scene_videos.py`의 `_as_result`가 그 메타데이터에서 값을 읽어 온다. 실제
`LocalProjectStore`로 검증하는 새 테스트(`test_the_list_view_still_shows_the_library_id_after_a_refresh`)
추가. 브라우저에서 표준 화질로 새로 만든 장면으로 실물 확인 완료 — 새로
만든 자산은 목록에서도 `library_asset_id`가 보이고, 이 수정 전에 만들어진
옛 자산은 여전히 null(소급 반영 없음, 의도된 동작).

### 3. 표준 화질 단계 추가 — 미리보기와 고화질 사이 (owner 요청 "AI 영상 생성 단축 검토", 커밋 `80647b8b8`)

미리보기(12초)와 고화질(18~20분) 사이에 아무것도 없어서, 완성에 가까운
화질이 필요한데 20분을 못 기다리는 경우 고를 자리가 없었다.

**실측(RTX 5090, 2026-08-30)**:
- 960x540·49프레임·14스텝 — 약 34초.
- **1280x720·65프레임·16스텝 — 약 139~140초(2분 19~20초).** 두 번 실측(격리
  테스트 1회, 실제 화면을 통한 종단 실행 1회)으로 확인. 후자는 자료실 등록도
  같이 성공.

**정한 값: 1280x720·65프레임·16스텝, "표준 (약 3분)".** `SceneVideoService`·
API 모델(`Literal["preview", "standard", "full"]`)·`api.ts`·`SceneImageStudio.tsx`의
화질 select에 전부 반영. 새 테스트 4건(서비스 2건 + API 1건 + 기존 확장)
추가, 브라우저에서 실제로 표준 화질을 골라 140.4초 만에 완성·자료실 등록까지
확인했다.

### 4. 설치형 데스크톱 셸(Tauri) 착수 — 빌드가 막혀 있다 (owner 실시간 승인, 커밋 `80647b8b8`·`579f83bc`)

owner가 대화창에서 "1,2번 진행"(설치형 검토 + AI 영상 단축 검토)을 명시적으로
지시해 `docs/decisions/2026-08-30-installed-desktop-shell-tauri.ko.md`에
승인 기록을 남기고 착수했다.

**확인한 것**: CapCut이 설치형인 이유(파일시스템 직접 접근·GPU 하드웨어
인코딩·탭 생명주기 무관 처리)는 VideoBox에 그대로 적용되지 않는다 — VideoBox의
실제 렌더링·AI 생성은 이미 owner 로컬 머신에서 서버 쪽(FFmpeg·ComfyUI)으로
100% 로컬로 돈다. 브라우저 탭은 제어판일 뿐이다. 그래서 설치형 전환이 주는
것은 CapCut의 실제 이유가 아니라 앱 아이콘·독 노출·주소창 없는 창 정도다.

**만든 것**: `apps/desktop/`(기존 빈 placeholder 디렉터리 재사용, 재사용
게이트 원칙) 아래 Tauri 뼈대 — `package.json`·`src-tauri/tauri.conf.json`
(`http://127.0.0.1:5173`을 가리키는 창)·`Cargo.toml`·`main.rs`. Electron이
아니라 Tauri를 고른 이유: VideoBox가 1인용 로컬 도구라 여러 OS Chromium
통일성이 필요 없고, Electron의 ~150MB Chromium 번들이 낭비다.

**실제로 빌드는 못 했다.** Rust(rustup)와 Visual Studio Build Tools(C++
워크로드)를 winget으로 설치했고 MSVC 링커까지는 통과했지만, **Windows 11
Smart App Control**(`SmartAppControlState: On`)이 새로 컴파일된 서명 안 된
`build-script-build.exe`를 차단한다(`os error 4551`). 이 기능은 한 번 끄면
OS 재설치 없이는 되돌리기 어려운 시스템 보안 설정이라 **owner 확인 없이
끄지 않았다** — `apps/desktop/README.md`에 owner가 고를 수 있는 세 가지 길을
적어 뒀다(개별 항목 허용 / Smart App Control 전체 끄기 / 별도 서명 파이프라인).

**따라서 이 셸은 아직 owner 화면에서 실제로 눌러 본 적이 없다** —
`CLAUDE.md` §4 기준으로 완료가 아니다. owner가 Smart App Control 문제를
해결한 뒤에야 실제 빌드·검증이 가능하다.

### 5. SaaS 전환 관련 질문 답변 (구현 없음)

owner가 "나중에 SaaS로 만들면 이 설치형에 로그인 정보를 붙이면 되냐"고 물어서
답만 했다: 셸 자체는 그냥 지정된 주소를 보여주는 껍데기라 로그인 화면이든
뭐든 그 주소가 보여주는 대로 따라간다. 진짜 무게가 실리는 건 셸이 아니라
백엔드가 다중 사용자·계정·과금을 지원하게 만드는 것이고, 그건 `CLAUDE.md`
§6이 별도 승인 필요 항목으로 못박아 둔 것이라 이번엔 손대지 않았다.

### 6. 코드리뷰 — 8각도 병렬 검토, 확실한 결함 3건 즉시 수정 (owner 요청 "코드리뷰 갭검증 역방향 동작검증 커밋 푸쉬")

`0f7cafa12`~`4862e29d`(오늘 밤 7개 커밋, push 전) 전체를 대상으로 8개 각도
(정확성 3·재사용·간결화·효율·고도·CLAUDE.md 준수)로 병렬 코드리뷰를 진행했다.
10건이 검증을 통과했고, 그중 확실한(CONFIRMED) 결함 3건은 바로 고쳤다.

**바로 고친 것:**

1. **`update_asset_metadata` 실패가 성공한 생성물을 지워 버리던 결함**
   (`scene_video_service.py`) — 자료실 id를 목록에도 보이게 하려고 생성
   직후 자산 메타데이터를 다시 쓰는 호출(위 2번 항목)이 `_ingest_into_library`와
   달리 자기 실패를 삼키지 않았다. 이 호출 하나가 실패하면(예: 일시적 DB
   쓰기 오류) 바깥 `except Exception`이 방금 20분 걸려 만든 자산까지 보상
   삭제(compensate)해 버렸다 — 세 곳(직접 읽기, efficiency 각도, 제거된
   동작 감사 각도)에서 독립적으로 잡아낸 결함이다. `_ingest_into_library`와
   같은 try/except로 감쌌다. 회귀 테스트
   (`test_a_broken_metadata_patch_does_not_lose_the_project_asset_either`)를
   추가해 수정 전 실패·수정 후 통과를 직접 확인했다.
2. **`VIDEOBOX_VIDEO_STEPS`/길이 환경변수가 조용히 죽어 있던 것**
   (`comfyui_video_generation.py`) — 화질 단계(preview/standard/full)가
   생기면서 실제 생성은 `self.config.steps`가 아니라
   `SceneVideoRequest.steps`(단계별 고정값)를 쓰는데, 문서·`compose.yaml`은
   여전히 이 환경변수가 화질을 조정한다고 말하고 있었다. 재설계 대신
   `VideoGenerationConfig`·`compose.yaml`에 "이제 실제 생성에 아무 영향이
   없다"고 명시하는 쪽을 택했다 — 화질 단계 체계와 개념이 부딪히는
   (어느 단계를 조정할지 모호한) 낡은 단일 환경변수를 억지로 되살리는 것보다
   정직하게 죽었다고 적는 게 맞다고 판단했다.
3. **provider Protocol 선언이 실제 호출 계약과 어긋나 있던 것**
   (`visual_generation.py`) — `SceneVideoProvider.generate_video`가 여전히
   `(self, request)`만 선언하고 있었는데, 실제 호출부(`scene_video_service.py`)와
   구현체(`ComfyUIVideoGenerationProvider`)는 이미 `on_submitted`·`cancel_event`
   키워드 인자를 쓴다. Protocol은 런타임에 강제되지 않아 지금 당장 뭔가
   깨진 건 아니지만, 이 선언만 보고 새 provider를 짜면 취소 기능을 걸 때
   `TypeError`가 난다. 선언을 실제 계약에 맞춰 갱신했다.

**추가로 고친 것 (낮은 위험, 빠른 수정):**

4. `get_scene_video_job`·`cancel_scene_video`가 잠금 밖에서 같은 job dict
   참조를 여러 번 나눠 읽던 것 — `_run_job`의 원자적 `job.update(...)`과
   경합하면 "성공했는데 결과는 없음" 같은 앞뒤 안 맞는 조합을 돌려줄 수
   있었다(영향은 적다 — 폴링이 2초마다 다시 도니 다음 요청에서 바로잡힌다).
   `cancel_scene_video`는 상태 확인과 취소 이벤트 켜기가 잠금 밖에서 따로
   일어나 이미 끝난 작업에 조용히 이벤트만 켜고 409도 안 뜨는 경합도 있었다.
   `_snapshot_job` 헬퍼로 통일해 확인·복사를 한 번의 잠금 안에서 하도록 고쳤다.

**owner 요청으로 이어서 고친 것("기록만 하고 넘어간 것들도 마저 고쳐줘"):**

5. **`_ingest_into_library`의 error_code 미기록.** `LibraryIngestService.ingest_batch`가
   이미 쓰는 `type(error).__name__` 관례를 그대로 따라 `_ingest_into_library`가
   `(library_asset_id, error_code)` 튜플을 돌려주게 바꿨다. `SceneVideoResult`·
   `apps/web/src/api.ts`·`_as_result`(목록 조회)에 `library_ingest_error`·
   `gif_library_ingest_error`를 새로 실어, 자료실 등록이 왜 안 됐는지 이제
   asset 메타데이터·API 응답에서 확인할 수 있다. 회귀 테스트 갱신.
6. **폴링 루프 중복.** 유튜브 학습(`VoiceTtsSettings.tsx`)과 AI 영상 생성
   (`SceneImageStudio.tsx`)이 거의 같은 폴링 루프를 각자 따로 짜 놓고
   있었다. `apps/web/src/lib/pollJob.ts`로 공통 루프(`pollJobUntilTerminal`)를
   뽑았다 — 두 자리의 유일한 실제 차이(확인 순서)는 `delayFirst` 옵션 하나로
   남겨 뒀다. 전용 단위 테스트(`pollJob.test.ts`) 5건 추가.
7. **화질 3단계 리터럴 4곳 중복.** `scene_video_service.py`에 `SceneVideoQuality`
   타입 별칭과 `_QUALITY_PRESETS` 표(딕셔너리) 하나로 모았다 — if/elif/else
   가지와 9개 흩어진 상수를 없앴다. `services/api/.../models.py`는 이
   타입을 그대로 가져다 쓰고, `apps/web/src/api.ts`도 `SceneVideoQuality`
   타입 하나로 모아 `SceneImageStudio.tsx`가 재사용한다. 넷째 화질이
   생기면 이제 표 한 줄만 늘리면 된다. `tsc -b` 통과 확인.
8. **`_cancel_prompt`의 TOCTOU 경합 — 절반만 고쳤다.** `/queue` 스냅샷과
   `/interrupt` 사이의 진짜 경합(다른 작업을 잘못 멈출 가능성)은 ComfyUI가
   prompt_id별 실행 상태를 실시간으로 알려주는 방법(websocket `executing`
   이벤트 등)으로 바꿔야 하는 큰 작업이라 이번에도 손대지 않았다. 대신 그
   틈에서 **가장 아까운 경우**(취소를 요청한 바로 그 순간 이 작업이 이미
   자연히 끝나 버린 경우, 즉 자기 자신의 성공한 결과를 취소로 버리는 것)는
   막았다 — 취소 처리 직후 `/history`를 한 번 더 확인해서 실제로 결과가
   나와 있으면 그걸 그대로 돌려준다. 회귀 테스트 추가.
9. **job 상태 영속화 — 이번에도 안 했다(의도적).** 백엔드 프로세스가
   재시작되면 진행 중이던 job이 사라지는 문제 자체는 그대로다. 이유:
   실제 코드(`api.ts`의 `request()`)를 다시 읽어 확인해 보니, 재시작으로
   job을 잃었을 때 화면은 이미 **안전하게** 실패한다 — 404가 그대로
   `ApiRequestError`로 던져지고 `pollSceneVideoJob`의 catch가
   "진행 상황을 확인하지 못했어요. 잠시 뒤 다시 눌러 주세요."를 보여주며
   깨끗이 끝난다(무한 대기·크래시·거짓 성공 없음). 진짜 고치려면
   `LocalProjectStore`(가장 민감하고 넓게 쓰이는 파일)에 새 테이블·스키마
   마이그레이션을 넣어야 하는 큰 작업인데, 실제로 발생하는 경우(20분짜리
   생성 도중 컨테이너가 재시작되는 것)는 드문 운영 사고이고 지금도 안전하게
   실패하고 있어서, 이 시각에 그 파일을 건드리는 위험이 얻는 이득보다 크다고
   판단했다. **범위 밖으로 남긴다 — owner가 원하면 별도 세션에서 신중하게.**

**검증**: 회귀 테스트 추가 뒤 관련 스위트(`test_scene_video_service.py`,
`test_api_scene_videos.py`, `test_comfyui_video_generation_provider.py`,
`test_video_generation_config.py`) 41 passed, 프론트 신규 테스트
(`pollJob.test.ts`) 5 passed. 잠금 로직을 고친 취소 버튼은 컨테이너 재빌드
후 실제 ComfyUI로 다시 검증(scene 4, 고화질 실행 → 취소 → `/history`에서
`execution_interrupted` 확인, "취소했어요." 정상 표시). 전체 백엔드 pytest
결과는 아래 검증 상태 참고.

## 검증 상태

- 백엔드 전체 pytest 1차(코드리뷰 최초 수정 반영): **4175 passed, 56 skipped,
  1 failed**(`0:37:39`). 실패 1건은
  `test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`
  — 이 세션이 건드리지 않은 파일이고, 격리 재실행에서도 2/2 재현돼 그때는
  기존 결함으로 판단했다.
- 백엔드 전체 pytest 2차(위 5~8번 이어서 고친 것 반영, 최종):
  **4177 passed, 56 skipped, 0 failed**(`0:34:57`). **`test_owner_ready_script.py`가
  이번엔 통과했다** — 시스템 부하에 민감한 기존 타이밍 결함이었다는 판단을
  뒷받침한다(이 세션이 그 파일을 건드린 적은 없다).
- 프론트 전체 vitest: **98 files passed, 1369 passed, 0 failed**(`pollJob.test.ts`
  5건 포함).
- 표준 화질·자료실 id 수정·error_code 기록·화질 preset 통합·취소 경합 완화,
  전부 컨테이너 재빌드 후 실제 브라우저·ComfyUI로 종단 검증 완료(추정 아님):
  - scene 4에서 미리보기 재생성 → 성공, `library_asset_id` 채워짐,
    `library_ingest_error: null` 정상 확인(목록 조회에도 그대로 남음).
  - 재빌드 직후 첫 두 번의 시도는 `scene_video_generation_blocked`로
    실패했다 — 컨테이너 재시작 직후 host.docker.internal 네트워킹이
    안정되기 전의 일시적 현상으로 판단(같은 코드 경로를 컨테이너 안에서
    직접 다시 호출해 즉시 성공했고, 몇 초 뒤 화면에서도 그대로 성공했다 —
    코드 회귀가 아니다).
  - `tsc -b` 통과(화질 타입 통합이 컴파일 오류를 만들지 않음).
- 취소 버튼(잠금 로직 재작성, 이번엔 안 건드림): 1차 검증에서 scene 4
  고화질 실행 → 취소 → ComfyUI `/history`에서 `execution_interrupted` 직접
  확인, 화면에 "취소했어요." 정상 표시.
- Tauri 데스크톱 셸: 설정 파일만 있고 빌드·실행 미검증(위 4번 참고, 오늘 밤
  추가 진전 없음).

## 커밋

- `0f7cafa12` — fix: keep AI scene-video library ids visible after a page refresh
- `80647b8b8` — feat: add a standard-quality tier for AI scene video (Tauri 뼈대 포함 —
  파일 스테이징이 겹쳐 한 커밋에 같이 들어갔다, 내용은 서로 무관)
- `579f83bc` — docs: record why the Tauri desktop shell build is blocked tonight
- `4862e29d` — docs: hand off tonight's session
- `0009e3db3` — fix: don't lose a finished AI video over a metadata patch, and fix job-read races
- `424bf8758` — fix: finish the deferred code-review items — error tracking, shared poller, quality presets, cancel-race

전부 push 완료(owner 요청 "커밋 푸쉬", 이어서 "기록만 하고 넘어간 것들도 마저 고쳐줘").
**컨테이너도 이 커밋 기준으로 재빌드·재시작 완료** — `scripts/owner-ready.ps1
-Mode Start -Rebuild` 실행 후 `docker exec ... SCENE_VIDEO_QUALITIES` 직접
조회로 최신 코드가 실제로 돌고 있음을 확인했다.

## 다음 세션에서 할 일 (우선순위 순)

1. **owner가 Smart App Control 문제를 어떻게 풀지 결정.** 결정 나면 그때
   `npm run tauri dev`/`build`로 실제 빌드·화면 검증을 이어간다.
2. **옛 AI 영상 자산의 `library_asset_id`가 여전히 null인 것** — 이번 수정
   전에 만들어진 자산들(`asset_92d486e20847`, `asset_6ebe1226d94f` 등)은
   소급 반영되지 않는다. 문제로 지적되면 그때 마이그레이션을 논의한다(지금은
   조용히 넘어감 — 개수가 적고 재생성이 쉽다).
3. **job 상태 영속화만 의도적으로 남겨 뒀다.** 코드리뷰에서 "기록만 하고
   넘어간 것" 5건 중 4건(error_code 기록·폴링 루프 공유·화질 preset 표
   통합·취소 경합의 절반)은 이번에 마저 고쳤다. 나머지 하나(백엔드 재시작
   시 job 상태가 통째로 사라지는 것)는 지금도 안전하게(무한 대기·거짓
   성공 없이) 실패하고 있고, 고치려면 `LocalProjectStore`(가장 민감하고
   넓게 쓰이는 파일)에 스키마 마이그레이션이 필요한 큰 작업이라 이 시각에
   손대는 위험이 이득보다 크다고 판단해 남겨 뒀다. owner가 원하면 별도
   세션에서 신중하게.
4. **`_cancel_prompt`의 TOCTOU 경합 — 절반만 고쳤다.** 취소 요청과 거의
   동시에 다른 작업이 시작되면 그 작업을 잘못 멈출 가능성 자체는 아직
   남아 있다(websocket으로 실행 상태를 실시간으로 받아야 진짜 고침). "취소
   요청 순간 자기 자신이 이미 끝나 버린 경우"만 이번에 막았다.

## 다음 세션 시작 시 확인만 하면 된다

```bash
cd .worktrees/videobox-container-compatibility
git log --oneline -10
git status --short
```

현재(이 문서 작성 시점) 기준 작업 트리는 깨끗하고(`output/`는 이 세션이
만든 게 아닌 무관한 산출물), `424bf8758`까지 전부 push·컨테이너 배포
완료다.

## 2026-08-30 이어진 세션 — job 상태 영속화 완료, 자율 루프 착수·두 우선순위 막힘

owner가 일요일 휴일에 승인을 위임하고 2분 간격 `/loop` 자율 개발을 지시했다
(cron job `f8e1c98a`, 세션 종료 시 사라짐, 7일 뒤 자동 만료).

### 1. job 상태 영속화 — 완료 (위 "다음 세션 할 일 3번")

새 스키마 없이 기존 재사용 게이트로 풀었다: `JobType.SCENE_VIDEO_GENERATION`
한 줄을 `jobs.py`에 추가하니 `recover_orphaned_in_process_jobs`(재시작 시
멈춘 job을 실패로 정리하는 기존 장치, `main.py`가 시작할 때마다 이미
모든 프로젝트에 돌리는 것)가 새 JobType도 자동으로 덮었다(`_IN_PROCESS_JOB_TYPES`가
`JobType` 전체에서 동적으로 계산되는 구조라서). `scene_videos.py`는 시작 시
`store.create_job`, 완료 시 `store.update_job`으로 DB에도 기록하고, 조회
시 메모리(`_jobs`)에 없으면 DB로 폴백 — 완성된 결과는 중복 저장하지 않고
`output_ref`가 가리키는 scene 자산 메타데이터에서 `_as_result`로 재구성한다.
새 테스트 3건(재시작 스트랜드 job 복구, 메모리 소실 후에도 결과 재현,
메모리 소실 job은 취소 시 404 아닌 409) 추가, scene-video 테스트 14건·
job 복구/대시보드/재시도 스위트 8건·프론트 전체 1369건 통과.

### 2. CLAUDE.md 정리 — 완료

낡은 SSOT 표 항목 2개 삭제(둘 다 이미 마감·비authoritative였던 문서를
가리킴), 완전히 대체된 결정 기록 3건을 역사 기록으로 압축, 08-30
Tauri 승인이 반영 안 돼 있던 "설치형 보류/미승인" 문구 2곳을 정정,
새 결정(`2026-08-30-capcut-button-level-parity.ko.md`,
`2026-08-30-installed-desktop-shell-tauri.ko.md`) 색인 추가. 7,956자/239줄
(한도 8,000자/260줄), `test_handoff_entry_point.py` 5건 통과.

### 3. 백엔드 전체 pytest — 1차 실행에서 내 실수로 오염, 2차 재실행 중

1차 실행(4176 passed / 56 skipped / 4 failed, 52:39) 도중 프론트 전체
vitest를 동시에 돌려 버렸다 — 이 저장소에 이미 있던 "전체 pytest는 무거운
작업과 겹치면 안 된다"는 규정을 놓쳤다. 실패 4건을 격리 재실행하니 3건은
바로 통과(오염이 원인인 거짓 실패), 1건(`test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`)은
격리해도 2/2 재현되지만 이 세션이 건드리지 않은 파일이고 어젯밤 세션에서도
같은 방식으로 재현돼 "기존 결함, 세션 무관"으로 판단된 이력이 있다 — 이번에도
같은 판단. 정확한 최종 기록을 위해 겹침 없이 2차 전체 실행을 다시 배경에서
돌렸다. **2차 결과(겹침 없음, 정확한 최종 기록): 4180 passed, 56 skipped,
0 failed(0:35:31)** — 평소 소요 시간과 일치, 1차의 4건 실패는 전부 내 오염이
원인이었음을 확인. `job` 상태 영속화 새 테스트 3건이 그대로 반영돼
4177 → 4180.

### 4. 자율 루프의 두 헤드라인 우선순위 — 둘 다 오늘 밤은 착수 보류(추측 대신 정직하게 막힘 기록)

**TOCTOU 취소 경합 나머지 절반** (`comfyui_video_generation.py`의
`_cancel_prompt`) — 진짜 고치려면 ComfyUI websocket의 `executing` 이벤트로
실시간 실행 상태를 받아야 한다. 확인한 것:
- 이 저장소 `.venv`에 websocket 클라이언트 라이브러리가 **없다**
  (`websockets`·`websocket-client` 둘 다 `ModuleNotFoundError`). 새 의존성
  추가가 필요하다.
- `ComfyUIHTTPTransport`(`comfyui_image_generation.py`)는 보안 경계로
  `_ALLOWED_COMFYUI_HOSTS`·`_COMFYUI_PORT`(8188)만 허용하는 host 검증을
  자체 구현해 뒀다 — 새 websocket 연결도 정확히 같은 허용 목록을 따라야
  SSRF류 구멍을 만들지 않는다.
- **owner 컴퓨터의 ComfyUI가 지금 안 켜져 있다**(일요일, owner 부재) — 이
  provider는 이미 실제 GPU로 검증된 적이 있는 코드라서(08-30 취소 실측),
  websocket 계층을 추가하고 mock으로만 테스트한 뒤 "완료"라고 부르면
  `CLAUDE.md` §4를 어기는 것이다. **그래서 오늘 밤은 코드를 짜지 않고
  막힘만 기록한다** — 실제 ComfyUI가 켜져 있을 때(owner가 있거나, 다음
  세션에서 직접 켜고) 다시 시작한다.

**캡컷 버튼 단위 벤치마킹** (`2026-08-30-capcut-button-level-parity.ko.md`) —
착수 전 저장소를 다 뒤졌지만 **owner가 보여준 캡컷 캡처 이미지가 파일로
어디에도 저장돼 있지 않다**(`docs/decisions/` 등 어디에도 `.png`/`.jpg` 없음,
채팅에서만 보여준 것). 채팅 요약 문구만 보고 버튼 크기·배치를 기억으로
재구성하면 **추측**이지 벤치마킹이 아니다 — 틀리면 owner가 다시 다 고쳐야
한다. **그래서 이 항목도 오늘 밤은 착수하지 않는다.** 다음 세션에서 owner가
캡처 파일을 저장소에 남겨 주면(`docs/decisions/assets/` 같은 자리) 그때
정확하게 시작한다.

**루프가 이어서 하는 것**: 위 두 헤드라인이 막혀 있으므로, 2차 pytest가
끝나는 대로 `docs/handoffs/2026-08-29-...capcut-dark-theme-handoff.ko.md`의
"참고만 하고 안 고친 것" 목록(장면 찾기 로직 3중 중복, 내보내기 팝업 상태
조회 중복 호출, 접근성 겹침 등) 중 **먼저 실물로 재현을 확인한 뒤** 확실한
것만 고친다 — 옛 메모를 확인 없이 믿지 않는다(`[[videobox-measure-before-guessing]]`).

### 5. 위 목록 중 두 건 실물 확인·수정 완료 (커밋 `78f4cf36`, `3dd495d2`)

컨테이너를 띄우고 `/projects/my-project/output` 화면을 브라우저 JS로 직접
재본 결과, 아래 두 건은 옛 메모 그대로 재현됐다 — 그 자리에서 고쳤다.

1. **`<h1>` 두 개·`aria-live` 두 개 중복 — 확인 완료, 수정함.**
   `document.querySelectorAll('h1')`로 실측: `["영상 검토", "완성본과
   CapCut 초안"]` 두 개, `aria-live` 두 개. 원인: `ReviewAndOutputPage`가
   `TimelineReviewSections`(자기 `<h1>`·`aria-live` 보유) 아래 `OutputsPage`를
   `reviewInline`으로 붙이는데, `OutputsPage`는 그 값을 "검토 화면 열기"
   링크를 숨기는 데만 쓰고 자기 `<h1>`·`aria-live`는 그대로 냈다.
   `reviewInline`일 때 `<h1>`→`<h2>`로 내리고 `aria-live`를 비우도록 고침.
   재빌드 후 재확인: `<h1>` 1개, `aria-live` 1개. 회귀 테스트 추가
   (`ReviewAndOutputPage.test.tsx`), 프론트 전체 1371 passed.
2. **내보내기 팝업 상태 조회 중복 — "두 번"이 아니라 매번 재동기화 때마다.**
   `read_network_requests`로 실측: 한 화면 로드에 `/api/capcut/handoff-diagnostics`가
   2번 나감. 원인: `OutputsPage`의 재조회 effect가 `[refresh, shared]`에
   걸려 있어(의도적 — `shared`가 늦게 채워지면 다시 그린다) `shared`가
   채워질 때마다 `refresh({reuseShared: true})`가 다시 도는데, 이때
   `getCapcutHandoffDiagnostics()`만 캐시 없이 매번 새로 불렀다(다른
   필드들은 전부 `sharedRead`/`options` 캐시가 있었음). CapCut 상태는
   검토 승인 여부와 무관하므로 `reuseShared` 재동기화일 때는 마지막 값을
   재사용하도록 캐시 추가(명시적 새로고침·프로젝트 전환 시엔 그대로
   새로 부름). 새 탭으로 깨끗하게 재확인: 1번으로 감소. 회귀 테스트 추가,
   프론트 전체 재확인 통과.

### 6. "장면 찾기 로직 3중 중복" — 찾아서 확인, 하나로 모음 (커밋 `96ca976a`)

`EditorWorkbench.tsx` 안에서 찾았다 -- 요청받은 장면으로 포커스 이동
(266~277행), 현재 선택 장면 찾기(356~361행), 내보내기 팝업에서 장면
클릭(669~673행) 세 곳이 전부 같은 5줄("내레이션 트랙 우선, 없으면 자막")을
손으로 반복하고 있었다. **다만 08-29 메모와 달리, 지금은 세 곳 다 규칙이
있었다** — 그 사이 누군가 이미 세 곳을 맞춰 놓은 것으로 보인다(낡은 메모를
확인 없이 믿지 않는 원칙대로 먼저 실측함). 그래도 손으로 세 벌 두는 것
자체가 위험(다음에 하나만 고치고 나머지를 잊는 것)이라 `findNarrationOrCaptionBySegment`
헬퍼 하나로 모았다 -- 순수 추출이라 동작 변화 없음. 프론트 전체 1371
passed(변화 없음), `tsc -b` 통과, 재빌드 후 브라우저에서 내보내기 팝업 →
검토본 다시 만들기 → 장면 "편집하기" 클릭까지 실제로 확인(팝업이 닫히고
재생 위치가 옮겨감).

**루프 2차 반복 총정리**: 이번 반복에서 항목 3(낮은 위험 후속)에서 확실한
결함·중복 3건을 실물로 확인하고 전부 고쳤다(`78f4cf36`·`3dd495d2`·`96ca976a`).
항목 1(TOCTOU)·2(캡컷 버튼 벤치마킹)는 여전히 각각 ComfyUI 실행·캡처 파일
대기 중, 착수 안 함.

### 7. 낮은 위험 후속 항목 소진 — `docs/handoffs/` 전체를 더 넓게 훑음, 루프 정지

`2026-08-24`~`2026-08-27` 인계 문서까지 전부 확인했다. 남은 항목들:

- **`2026-08-25` 계열의 "화면 생산 코드가 안 부르는 API 22개" 분류** — 여러
  인계에 반복 등장하지만, 각 문서 스스로 "대표님이 화면에 붙일지/지울지/
  그대로 둘지 결정해야 한다"고 명시한다. 삭제는 되돌리기 번거롭고
  잘못 지우면 아직 안 쓴 게 아니라 못 쓰게 만드는 것이라, 제품 판단 없이
  혼자 정하지 않는다. 이 수치는 5일 전 것이라 오늘 밤 작업(scene-video,
  job 영속화 등)으로 이미 낡았을 가능성도 있다.
- **`2026-08-26` AI 대화 편집(conversational editing/proposal preview)의
  "마감 리뷰 P1(미해결)"** — 실측으로 확인: **이미 고쳐져 있었다.**
  `local_pipeline.py:559`의 `get_proposal_preview_status`(GET/폴링 경로)가
  이미 `recover_inherited_proposal_preview_claims`·`recover_stale_proposal_preview_claims`를
  "pending/running일 때마다" 부르고 있다 — 그 자리 주석이 정확히 이 P1이
  요구한 이유("API 프로세스가 재시작되거나 워커 스레드가 죽어도 이 두 자리만이
  되살릴 수 있으므로 start뿐 아니라 매 non-terminal 읽기에서도 돈다")를
  그대로 적고 있다. 언제 고쳐졌는지는 이 세션에서 못 찾았지만(핸드오프
  교차 참조 없음), 코드는 확실하다.
  같은 인계의 "아직 하지 않은 것"(프론트 API 연결, pre-apply mutation 0
  E2E, approved-asset 검증, clarification 표시, 실제 QA) 6개 항목은 **새
  UI 흐름을 처음부터 설계해야 하는 기능 구현**이지 낮은 위험 버그 수정이
  아니다 — 08-27 이후 어느 인계에도 이 기능이 다시 언급되지 않아 우선순위가
  바뀌었을 가능성이 있다. 대표님 재확인 없이 손대지 않는다.

**결론: 오늘 밤 안전하게 진행할 낮은 위험 항목이 바닥났다.** 세 우선순위
전부(TOCTOU=ComfyUI 필요, 캡컷 버튼=캡처 필요, 낮은 위험 후속=소진) 막혀
있어 2분 간격 루프(`f8e1c98a`)를 여기서 멈춘다 — 할 일이 없는데 계속
돌리면 없는 일을 만들어내는 위험(범위 이탈)이 실제 이득보다 크다.
다음 세션(또는 대표님이 캡처·ComfyUI·API 22개 판단 중 하나를 주면 그때)이
이어간다.

## 2026-08-30 세 번째 이어진 세션 — 대표님이 막힘 세 개를 전부 풀어 줌

owner가 "① 내가 ComfyUI 킬 수 있다 ② 캡컷 자료는 지난 세션 로그에 있을
것이다 ③ AI 대화 편집은 끝까지 완성해야 한다"고 실시간으로 세 막힘을
직접 해소했다.

### 1. 캡컷 캡처 3장 복구 — 파일로는 안 남아 있었다는 게 사실이었다

git 전체 이력(`git log --all`)엔 정말 없었다. 대신 `.claude/projects/`의
과거 세션 JSONL 로그(사람이 채팅에 직접 첨부한 이미지)를 뒤져 정확히
일치하는 대화(2026-08-29T07:08·07:13, "지금 첫번쨰 사진이 캣컵 들어가자
마다 사진이야" 등 결정 문서에 인용된 문장과 토씨까지 같음)를 찾아 이미지
3장을 복구했다. `docs/decisions/assets/`에 저장하고 `2026-08-29`·`2026-08-30`
결정 문서에 참조를 남겼다.

**`git add`가 이 파일들만 두 번 막혔다가, 시간이 지난 뒤 재시도하니 통과했다**
— 일시적 차단이었던 것으로 보인다(원인 특정 못함). 커밋 `bdb6bd3b`로
푸시 완료. 우회 시도 없이 owner에게 상황을 먼저 알린 뒤 재시도로 풀린
사례로 남긴다.

### 2. AI 대화 편집(conversational editing) — Task 4 확실한 결함 2건 수정 (커밋 `151b222c1`)

`docs/superpowers/plans/2026-08-26-ai-conversational-editing-release-gaps.md`
Task 4를 실제 코드와 대조해 보니 Task 3(팝업이 후보 결과 영상을 보여주는
것)은 **이미 완료**돼 있었다(08-27 커밋 `e6f16060b` 등, 그날 인계 문서
제목엔 안 드러났을 뿐). Task 4에서 확실한 결함 두 개를 찾아 고쳤다:

1. **모호한 요청에 유진이 실제로 물은 말이 화면에 한 번도 안 보였다.**
   `director_proposals.py`가 proposal이 없을 때 `reply_text`를 사용자가
   방금 쓴 문장(`body.instruction`)으로 덮어쓰고 있었다 — 유진의 실제
   되물음은 버려졌다. `YujinEditingResult`에 `reply_text` 필드를 추가하고
   adapter 두 자리에서 채워 넣었다. **`rejected`(우리 쪽 검증이 막은
   경우)는 일부러 안 건드렸다** — 그때 모델의 reply_text는 "성공했다"는
   전제로 쓰였을 수 있어(예: 승인 안 된 자산인데 "음악을 골랐어요") 보여주면
   오해를 만든다. Task 4가 원래 범위를 clarification으로만 좁힌 이유이기도
   하다.
2. **`apply_media`가 요구하는 `asset_id`를 모델이 알 방법이 없었다.**
   검증 쪽(`_validate_current_targets`)은 이미 승인된 자산 목록과 대조하고
   있었는데, 프롬프트(`_editing_prompt`)는 그 목록을 한 번도 모델에게
   보여주지 않았다 — B-roll·음악·효과음 교체는 설계상 지원 동작인데
   실제로는 한 번도 성공할 수 없는 상태였다. 프롬프트에 승인된 자산
   (id, type) 목록(없으면 그 사실 자체)을 추가했다.

새 테스트 4건 추가(`test_yujin_editing_proposal_adapter.py`,
`test_api_media_director.py`, `test_yujin_editing_command_evaluation.py`
각각), 관련 스위트 83 passed.

**남은 Task 4 조각**: 실제 로컬 LLM으로 GPU 켜 놓고 candidate → preview MP4
→ apply → undo/redo → 검토 승인 → final MP4까지 끝까지 밟는 owned fixture
QA는 이번에도 안 했다 — LM Studio 쪽 실측까지 하기엔 이번 반복 시간이
부족했다. 다음 반복이 이어갈 것.

### 3. TOCTOU 취소 경합 나머지 절반 — 진짜 고침, 실물 검증 완료 (커밋 `b9c71dca`)

owner가 ComfyUI 데스크톱 버전을 직접 켰다(`127.0.0.1:8188` 응답 확인).
`websockets==17.1`을 `requirements-runtime.txt`·`requirements-container.txt`에
추가하고(pip install 자체는 관리자 승인 없이 끝남), `comfyui_video_generation.py`에
`ComfyUIExecutionTracker`를 새로 짰다 — ComfyUI websocket(`/ws`)의
`executing` 이벤트를 실시간으로 받아 "지금 실제로 실행 중인 prompt_id"를
안다. `_cancel_prompt`가 이제 `/queue` 스냅샷(요청 시점의 사진, 시차 있음)
대신 이 실시간 값을 믿는다 — 트래커가 한 번도 이벤트를 못 받았으면(연결
실패 등) 예전 `/queue` 판정으로 조용히 폴백한다(퇴행 방지).

**기존 시험 10건 전부 무변화로 통과**(트래커 미설정이 기본값이라 단위
시험이 진짜 소켓을 열지 않는다 -- `execution_tracker_factory=None` 기본값의
역할). 새 시험 8건 추가: 가짜 트래커로 "스냅샷은 우리 job이라는데 트래커는
남의 job이 실행 중이라고 함 → interrupt 안 부름"이 이 수정의 핵심
검증이다. `ComfyUIExecutionTracker` 자체도 가짜 websocket 연결로 4건
(prompt_id 반영, node=null 시 해제, 무관한 메시지 무시, 연결 실패 시 조용한
폴백) 검증.

**실물 검증(추정 아님)**: 컨테이너 재빌드(`websockets` 실제 설치 확인 —
`docker exec ... python -c "import websockets"` → `17.1 present`) 후
`my-project`에서 실제로:
- preview 화질 생성 1건 정상 성공(8.1초, 자료실 등록까지 확인) — 트래커
  배선이 정상 경로를 안 깨뜨림.
- standard 화질 생성 1건을 8초 뒤 취소 → `scene_video_cancelled`로 정상
  실패 → ComfyUI `/history` 직접 조회로 그 prompt_id가 `execution_interrupted`인
  것 확인. 기존에 검증됐던 취소 동작이 새 코드 경로로도 그대로 됨을 확인.
- 웹소켓 자체 연결도 별도로 직접 확인(`ws://127.0.0.1:8188/ws` 연결 성공,
  최초 `status` 메시지 수신).

**아직 실물로 못 잰 것**: 두 작업이 동시에 실행 중일 때 진짜로 경합이
발생하는 상황(다른 prompt를 잘못 멈추는 경우)은 재현하지 못했다 — 실제
GPU에서 두 영상을 동시에 정확한 타이밍으로 충돌시키기가 지금 시간 안에
어렵다. 이 부분의 정확성은 가짜 트래커를 쓴 단위 시험(위 8건)이 결정론적으로
보장한다 — 실물 검증은 "새 경로가 정상 케이스를 깨뜨리지 않는다"까지다.

**커밋·푸시 완료** — 전체 백엔드 pytest 최종 결과: **4191 passed, 56
skipped, 1 failed**(`test_start_hermes_yujin_script.py`의 8초 타임아웃
경계 시험, 격리 재실행 3/3 통과로 이 세션 무관한 기존 타이밍 결함 확인).
커밋 `b9c71dca`.

## 2026-08-30 네 번째 이어진 세션 — 캡컷 버튼 단위 벤치마킹 1~3단계 완료

owner가 "결국은 다 바꿀 건데 어떤 걸 먼저 하는 게 나아?"에 구조부터
먼저 하는 게 낫다는 답과 함께 "제대로 확실하게 짚어가며 진행"을 지시,
이어서 왼쪽 진행 후 "오른쪽 패널도 이어서 상시 노출로 바꿔줘"까지 세
단계를 이 세션에서 전부 끝냈다. 상세 경위·판단 근거는
`docs/decisions/2026-08-30-capcut-button-level-parity.ko.md`에 단계별로
기록돼 있다 — 여기서는 요약만 남긴다.

- **1단계(커밋 `d5fd80120`)**: 편집 동작(되돌리기·나누기·붙이기 등)을
  상단 도구줄에서 타임라인 바로 위 줄로 옮겼다 — 캡컷 실제 위치와 대조해
  확인.
- **2단계(커밋 `56511ce`)**: 왼쪽 패널 안에 있던 콘텐츠 탭(미디어·오디오·
  자막·전환)을 패널 밖, 편집기 맨 위로 승격했다. `EditorAssetBrowser`를
  controlled 컴포넌트로 바꿔 패널 내용 로직은 재사용하고 탭 버튼만
  옮겼다. TDZ 크래시(함수 선언 순서)와 서랍-모드 접기 회귀를 각각 겪고
  고쳤다 — 자세한 원인은 결정 문서 100~104행.
- **3단계(커밋 `1fa85e2a5`)**: 오른쪽 "세부 정보" 패널은 탭이 하나뿐이라
  승격할 게 없어서, 자기 단추로 닫을 수 있던 것만 없앴다(`openRightPane`
  추가). 서랍 모드 열기·닫기는 그대로 둠.

각 단계마다 재빌드 후 브라우저에서 실제로 확인했고, 3단계 종료 시점
프런트엔드 전체 시험 1,371개 통과. 전부 커밋·푸시 완료.

**남아 있는 화면**: 결정 문서 §"화면(컴포넌트)마다 개별 진행" 원칙대로,
편집기 상단·좌우 패널 다음으로 어느 화면(첫 화면, 검토 화면 등)부터
버튼 단위 대조를 이어갈지는 아직 owner 우선순위를 안 물어봤다.

## 2026-08-30 다섯 번째 이어진 세션 — 세 우선순위 동시 진행

owner "어차피 모두다 해야되는거니까 진행해. 그리고 마지막은 내가
승인할테니까 너가 진행해줘" 지시로 위 세 우선순위를 순서대로 밟았다.

### 1. Tauri 데스크톱 셸 빌드 — 실제로 시도, 구조적으로 막혀 있음을 확인

`npm run tauri build` 실제 실행. 이전 세션의 `os error 4551`(빌드
스크립트 실행 파일 차단)과 달리 이번엔 ~120개 crate를 컴파일하는 데까지
진행됐다가 `zerofrom_derive` 프록시-매크로 dll을 못 찾는다는 오류로
실패. Windows 이벤트 뷰어(`Microsoft-Windows-CodeIntegrity/Operational`,
event id 3077/3033/3118)를 직접 조회해 원인을 확인 — **Smart App
Control이 `rustc.exe`가 방금 컴파일한 서명 안 된 proc-macro dll을 매번
개별적으로 차단하고 있었다.** 이전에 알려진 "빌드 스크립트 실행 파일
하나"가 아니라 **컴파일되는 dll마다** 걸리는 구조적 차단이라, "허용
항목 지정"으로는 Rust 빌드 하나에 수십 번 반복해야 해서 현실적이지
않다는 것이 이번에 새로 확인된 사실이다.

**owner에게 알릴 것**: 승인 버튼 한 번 누르는 방식이 아니다. Smart App
Control 자체를 끄거나(되돌리기 어려움), Windows 보안 설정에서 항목별
검토 방식을 다시 확인하거나, 서명된 빌드 파이프라인을 구성하는 것 중
하나를 owner가 직접 골라야 한다 — 시스템 보안 설정 변경은 승인을
받아도 직접 하지 않는다는 원칙(`CLAUDE.md`)에 따라 진행하지 않았다.
`apps/desktop/README.md`는 이미 이 내용을 담고 있어 추가 수정 없음.

### 2. AI 대화 편집 Task 4 마지막 조각 — 실제로 끝까지 밟았고, 결함 1건 발견·수정 (커밋 `fa8afe07`)

LM Studio(`qwen/qwen3.6-35b-a3b`, `127.0.0.1:1234`)가 이미 떠 있는 것을
확인하고 실제 브라우저로 전체 경로를 밟았다.

- **발견한 결함**: "B-roll 색감을 따뜻하게 바꿔줘"처럼 허용 intent
  밖의 요청에 모델이 `proposal: null`은 정확히 두면서도, `reply_text`는
  프롬프트 예시 문장의 성공 어투("만들었어요")를 그대로 베껴 편집이
  이미 된 것처럼 답했다. 이 문구가 화면에 그대로 보인다
  (`interpret_yujin_editing_request`의 clarification 분기) — owner가
  실제로는 아무 일도 안 일어났는데 됐다고 믿게 만드는 결함이었다.
- **고친 것**: `_editing_prompt`에 proposal이 없을 때의 예시 문장과
  "성공했다고 쓰지 마라"는 명시적 지시를 추가. 재빌드 후 같은 요청을
  다시 보내 실제로 "지금 대화 편집으로는 색감 보정을 지원하지 않아요"로
  바뀐 것을 확인했다(모델이 프롬프트의 실패-예시 문장을 거의 그대로
  베꼈다는 점은 감수 사항으로 남긴다 — few-shot 예시의 흔한 한계).
- **끝까지 밟은 경로**: "이 장면을 2배 빠르게 해줘" → 편집안 생성
  (`set_scene_speed`, status: ready) → "편집안 보기" 다이얼로그 →
  "이 구간 미리보기"로 실제 MP4 렌더 확인 → "이 편집안 적용" → 타임라인이
  실제로 5.00초→2.50초로 바뀜 확인 → Ctrl 없이 화면의 "실행 취소"로
  되돌림(5.00초로 복귀) → "다시 실행"으로 재적용(2.50초로 복귀) →
  (이 프로젝트는 `timeline_build` job이 한 번도 없어 검토 화면이 못 열려서
  `My Project`로 옮겨) 검토 승인 → 자막 만들기 → 완성본 만들기 → 완성본
  실패(`stale_output_asset: subtitle freshness changed`, 자막을 먼저
  만들기 전이라 발생한 정상적인 방어 동작이었음, 순서를 바꿔 재시도) →
  최종 MP4 생성 성공(15.072초, 재생 확인).
- 관련 backend 시험 84개 통과, 백엔드 전체 pytest 4193 passed·56
  skipped·0 failed(단독 실행). 커밋·푸시 완료.

### 3. 캡컷 버튼 단위 벤치마킹 4단계 착수 — 첫 화면, 시스템 버그 발견·수정 (커밋 `9378c5c0`)

`/projects` 화면의 "+ 새 프로젝트 만들기"를 캡컷 첫 화면의 큰 CTA
배너와 대조하다가, 이 버튼의 CSS가 이미 `min-height: 5rem`·
`border-radius: var(--vb-radius-md)`를 지정하고 있는데도 실제로는
35px·모서리 0px로 렌더링되는 것을 발견. `getComputedStyle`·
`document.styleSheets` 직접 조회로 원인 확인 —

1. `--radius-2xl`이라는, **정의된 적 없는 변수**를 참조하는 규칙이
   `product-shell.css`·`footage.css` 두 곳에 있었다(반지름 척도를
   셋으로 줄인 2026-08-27 정리에서 빠뜨린 옛 이름). 정의 안 된 `var()`는
   선언을 무효로 만들어 초기값(0)으로 떨어진다 — **이 화면 전체의
   default·outline 버튼이 전부** 모서리 없이 각지게 그려지고 있었다.
2. 속성 선택자를 쓴 전역 버튼 규칙(`min-height:32px`)이 특정도가 더
   높아 `.vb-catalog-create`의 `min-height: 5rem`을 조용히 눌러 왔다.

두 CSS 파일 수정 + 깨진 값을 "정답"으로 박아 둔 시험 1건 수정. 재빌드
후 실측: "+ 새 프로젝트 만들기" 80px·모서리 10px로 확인, 옆 "격자로
보기" 버튼은 높이 35px 그대로에 모서리만 10px로 고쳐짐(다른 버튼
크기는 안 건드림). 프런트엔드 전체 1,371 통과.

**남은 것**: 첫 화면의 나머지 버튼(퀵스타트 카드, 검색·보기전환·보관함
줄)은 대조 전. 보기전환 버튼은 2026-08-22에 이미 캡컷과 대조해 정한
자리라 재승인 없이 덮어쓰지 않는다.

## 다음 우선순위 (이 다섯 번째 이어진 세션 종료 시점)

1. **Tauri 데스크톱 셸 — owner 결정 필요.** Smart App Control 처리
   방식(끄기/항목별 예외/서명 파이프라인) 중 무엇을 고를지 owner에게
   먼저 물어본다. 결정 전에는 빌드를 다시 시도하지 않는다.
2. **캡컷 버튼 단위 벤치마킹 — 첫 화면 나머지, 또는 다음 화면.** 퀵스타트
   카드·검색줄을 마저 볼지, 검토 화면 등 다른 화면으로 넘어갈지 owner
   우선순위 확인.
3. AI 대화 편집 Task 4는 이번 세션으로 완료 — 추가 조각 없음.

## 다음 세션 시작 프롬프트

```
CLAUDE.md와 docs/handoffs/2026-08-30-videobox-library-id-fix-desktop-shell-standard-quality.ko.md를
먼저 읽어. 이번 세션까지 job 상태 영속화, ComfyUI 취소 TOCTOU 수정, AI
대화 편집 결함 2건 + Task 4 종단 QA 완료, 캡컷 버튼 단위 벤치마킹
1~4단계(편집 동작 위치, 왼쪽 콘텐츠 탭 승격, 오른쪽 패널 상시 노출,
첫 화면 CTA 버튼 + 전역 CSS 버그 수정)까지 전부 끝났고 push까지 완료된
상태야. Tauri 데스크톱 셸은 Smart App Control이 구조적으로 막고 있다는
게 확인돼(컴파일되는 dll마다 개별 차단) owner 결정이 필요한 상태로
남아 있어. 다음 우선순위는 (1) Tauri 빌드는 owner가 Smart App Control을
어떻게 처리할지 정할 때까지 보류, (2) 캡컷 버튼 단위 벤치마킹을 첫
화면 나머지 버튼으로 이어갈지 다른 화면으로 넘어갈지 owner에게 확인
순서로 진행해. 다른 지시가 없으면 이 순서대로 진행 여부를 먼저 물어봐.
```
