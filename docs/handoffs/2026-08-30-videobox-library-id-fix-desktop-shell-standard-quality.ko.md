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

## 검증 상태

- 백엔드 전체 pytest: **4175 passed, 56 skipped, 0 failed**(`0:34:24`).
- 프론트 전체 vitest: **97 files passed, 1364 passed, 0 failed**.
- 표준 화질·자료실 id 수정 둘 다 컨테이너 재빌드 후 실제 브라우저에서
  종단 검증 완료(추정 아님).
- Tauri 데스크톱 셸: 설정 파일만 있고 빌드·실행 미검증(위 4번 참고).

## 커밋

- `0f7cafa12` — fix: keep AI scene-video library ids visible after a page refresh
- `80647b8b8` — feat: add a standard-quality tier for AI scene video (Tauri 뼈대 포함 —
  파일 스테이징이 겹쳐 한 커밋에 같이 들어갔다, 내용은 서로 무관)
- `579f83bc` — docs: record why the Tauri desktop shell build is blocked tonight

이 worktree 브랜치에 전부 커밋됨, push는 안 함(요청 없었음).

## 다음 세션에서 할 일 (우선순위 순)

1. **owner가 Smart App Control 문제를 어떻게 풀지 결정.** 결정 나면 그때
   `npm run tauri dev`/`build`로 실제 빌드·화면 검증을 이어간다.
2. **옛 AI 영상 자산의 `library_asset_id`가 여전히 null인 것** — 이번 수정
   전에 만들어진 자산들(`asset_92d486e20847`, `asset_6ebe1226d94f` 등)은
   소급 반영되지 않는다. 문제로 지적되면 그때 마이그레이션을 논의한다(지금은
   조용히 넘어감 — 개수가 적고 재생성이 쉽다).
