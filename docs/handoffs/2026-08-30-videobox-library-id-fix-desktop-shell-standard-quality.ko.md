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

**기록만 하고 이번엔 안 고친 것(범위가 크거나 위험 대비 이득이 낮음):**

- `_cancel_prompt`의 `/queue` 스냅샷과 `/interrupt` 사이 TOCTOU 경합 — 두
  작업이 거의 동시에 걸려 있을 때 취소가 다른(관련 없는) 작업을 멈출 수
  있다. 실제로 이런 타이밍이 나려면 두 작업이 정확히 그 순간에 겹쳐야 해서
  드물지만, ComfyUI가 prompt_id별 실행 상태를 실시간으로 알려주는 방법
  (websocket `executing` 이벤트 등)으로 바꾸는 게 진짜 고침이라 오늘 밤엔
  손대지 않았다.
- job 상태가 백엔드 프로세스 안 메모리에만 있어서, 프론트가 방금 받은
  새로고침 복귀 능력(3번 항목)과 내구성이 어긋난다 — 백엔드가 재시작되면
  진행 중이던 job이 통째로 사라진다. 자산 저장소처럼 영속화하는 게 진짜
  고침이라 큰 작업이다.
- 화질 3단계가 4개 파일(`scene_video_service.py`·`models.py`·`api.ts`)에
  각각 손으로 맞춘 리터럴로 중복돼 있다 — 넷째 단계가 생기면 하나라도
  빠뜨리면 컴파일 오류 없이 조용히 어긋난다. 단일 preset 표로 합치는 게
  진짜 고침이지만 지금 범위 밖.
- `_ingest_into_library`가 `LibraryIngestService.ingest_batch`가 이미 갖고
  있는 "실패해도 계속 진행 + error_code 기록" 패턴을 손으로 다시 짜면서
  error_code 기록만 놓쳤다 — 실패 자체는 이미 안전하게 삼키므로 급하지 않다.
- 유튜브 학습 poller와 이 파일의 `pollSceneVideoJob`이 거의 같은
  polling 루프를 두 파일에 따로 짜 놓았다 — 공유 헬퍼로 뽑는 게 정리지만
  기능에는 영향 없다.

**검증**: 회귀 테스트 추가 뒤 관련 스위트(`test_scene_video_service.py`,
`test_api_scene_videos.py`, `test_comfyui_video_generation_provider.py`,
`test_video_generation_config.py`) 40 passed. 잠금 로직을 고친 취소 버튼은
컨테이너 재빌드 후 실제 ComfyUI로 다시 검증(scene 4, 고화질 실행 →
취소 → `/history`에서 `execution_interrupted` 확인, "취소했어요." 정상
표시). 전체 백엔드 pytest 결과는 아래 검증 상태 참고.

## 검증 상태

- 백엔드 전체 pytest(코드리뷰 수정 반영, 최종): **4175 passed, 56 skipped,
  1 failed**(`0:37:39`). 실패 1건은
  `test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`
  — 이 세션이 건드리지 않은 파일이고, 격리 재실행에서도 2/2 재현돼(전체
  스위트 부하와 무관) 오늘 밤 변경과 무관한 기존 결함으로 판단했다. PowerShell
  자식 프로세스를 1초 안에 죽이는지 보는 시험인데, 이 머신에 밤새 떠 있는
  무관한 docker 컨테이너 18개 이상(다른 프로젝트들)이 시스템 부하를 계속
  주고 있어 타이밍에 민감한 것으로 보인다 — 직접 원인 조사는 이번 세션
  범위 밖으로 남긴다.
- 프론트 전체 vitest: **97 files passed, 1364 passed, 0 failed**(코드리뷰
  수정은 프론트 파일을 건드리지 않아 재확인 안 함).
- 표준 화질·자료실 id 수정 둘 다 컨테이너 재빌드 후 실제 브라우저에서
  종단 검증 완료(추정 아님).
- 코드리뷰 수정 관련 스위트(4개 파일) 재확인: **40 passed, 0 failed**.
- 취소 버튼(잠금 로직 재작성): 컨테이너 재빌드 후 scene 4에서 고화질 실행 →
  취소 → ComfyUI `/history`에서 `execution_interrupted` 직접 확인, 화면에
  "취소했어요." 정상 표시, 목록 조회도 그대로 정상.
- Tauri 데스크톱 셸: 설정 파일만 있고 빌드·실행 미검증(위 4번 참고).

## 커밋

- `0f7cafa12` — fix: keep AI scene-video library ids visible after a page refresh
- `80647b8b8` — feat: add a standard-quality tier for AI scene video (Tauri 뼈대 포함 —
  파일 스테이징이 겹쳐 한 커밋에 같이 들어갔다, 내용은 서로 무관)
- `579f83bc` — docs: record why the Tauri desktop shell build is blocked tonight
- `4862e29d` — docs: hand off tonight's session
- (다음) 코드리뷰 결함 3+1건 수정 — 위 6번 항목

전부 push 완료(owner 요청 "커밋 푸쉬").

## 다음 세션에서 할 일 (우선순위 순)

1. **owner가 Smart App Control 문제를 어떻게 풀지 결정.** 결정 나면 그때
   `npm run tauri dev`/`build`로 실제 빌드·화면 검증을 이어간다.
2. **옛 AI 영상 자산의 `library_asset_id`가 여전히 null인 것** — 이번 수정
   전에 만들어진 자산들(`asset_92d486e20847`, `asset_6ebe1226d94f` 등)은
   소급 반영되지 않는다. 문제로 지적되면 그때 마이그레이션을 논의한다(지금은
   조용히 넘어감 — 개수가 적고 재생성이 쉽다).
3. **코드리뷰에서 기록만 하고 넘어간 5건**(위 6번 항목 "기록만 하고 이번엔
   안 고친 것") — 여유 있을 때 우선순위대로: (a) `_cancel_prompt`의 TOCTOU
   경합, (b) job 상태 영속화, (c) 화질 3단계 리터럴 4곳 중복, (d)
   `_ingest_into_library`의 error_code 미기록, (e) 폴링 루프 중복.
