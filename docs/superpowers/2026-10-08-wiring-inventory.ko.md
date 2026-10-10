# 배선 인벤토리 (계획 I Task 0)

- 만든 날: 2026-10-10 (계획 작성은 2026-10-08). 커밋 기준: `bd8bc50f9`(main) 위의 Task 0 커밋.
- 만든 명령: 계획 I Task 0 Step 4의 (a)~(f).
  (a) `cd apps/web && node ../../docs/superpowers/audit-evidence/scan-controls.cjs src`
  (b) `api.ts` 메서드 중 화면 호출 0개 찾기(계획 명령 그대로)
  (c) `grep 'path: "' AppRouter.tsx` + `routeManifest.ts`·`SideNav.tsx`·`TopBar.tsx`
  (d) `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe docs/superpowers/audit-evidence/scan-unrouted.py`
  (e) 유진 명령 이름 grep(계획 명령 그대로)
  (f) 기준선 JSON(`audit-evidence/2026-10-08-design-baseline.json`)에서 `role=tab`·`select` 집계
- 기준선 잰 방식: 계획은 컨테이너(5173)에서 내장 브라우저로 재라고 했지만, 지시에 따라 **진짜 FastAPI + 임시 고정 프로젝트 + Vite 개발 서버 + Chromium**(`npm run test:e2e:real-flow -- design-baseline.spec.mjs`)으로 쟀다. 대표님 실제 데이터는 읽지도 않았다. 대신 **자료실·촬영본이 거의 비어 있어** 그 화면의 컨트롤 수는 계획 표(실제 데이터)와 다르다. 그 화면은 "구조 값"(높이 종류·글꼴·글자 크기 종류)만 비교한다.

## 계획 작성 이후 달라진 것 (착수 확인)

| 항목 | 계획이 쓴 것 | 지금 |
|---|---|---|
| 포인트색 | 주황 `#EA580C` | 파스텔 파랑 `#9EC0F7`(`docs/decisions/2026-10-10-accent-color-blue.ko.md`). 계획 I의 "주황" 표현은 낡았다 → **파랑 기준**으로 읽는다 |
| 계획 H | 먼저 끝내야 함 | Task 0~18 마감(인계 `2026-10-10-editor-core-repair-h.ko.md`), 이 저장소에 반영됨 |
| 계획 G | 아직 0 커밋 | **여전히 0 커밋.** `+ 새로 만들기`는 1120×80 칸 그대로, 설정 섹션은 5개 그대로 → 계획 I Task 7·9는 "G를 안 돌렸을 때" 규칙으로 간다(D5 확인 필요) |
| `dialog.tsx` 닫기 문구 | `Close` | 이미 `닫기`(`615fee8c8`). Task 4에서 그 줄은 건너뜀 |
| 편집기 왼쪽 레일 탭 이름 | 빈칸 | 지금 `role=tab` 13개 모두 이름 있음 |
| 편집기 이유 없는 비활성 | 8개 | 0개 |
| `Toaster` | 어디에도 안 걸림 | `AppRoot.tsx:9`에 걸려 있다(H가 장착) → W-09 부분 해결 |

## 기준선 요약 (1440×900, 가로 넘침 전부 0)

| 화면 | 컨트롤 | 높이 종류(px×개) | Arial 컨트롤 | 컨트롤 글자 크기 | 모서리 | 채운(default) 단추 | 이유 없는 비활성 | 글자 칸 크기 종류 |
|---|---|---|---|---|---|---|---|---|
| `/projects` | 12 | 32×9 · 36×2 · 80×1 | 9 | 14 | 8·6·10 | 2 | 0 | 10·12·14·16·24·40 |
| `/library` | 14 | 32×2 · 36×1 · 40×11 | 3 | 14 (10 ×1) | 8·6 | 0 | 0 | 10 ×12 · 12·14·16 |
| `/library?kind=audio` | 14 | 위와 같음 | 3 | 같음 | 같음 | 0 | 0 | 같음 |
| `/footage` | 24 | 32×22 · 36×2 | 4 | 14 ×18 · 10 ×6 | 10·6·8·0 | 3 | **7** | 10 ×19 · 12·14·16·28 |
| `/voices` | 3 | 32×2 · 36×1 | 3 | 14 | 8·6 | 0 | 0 | 10·12·14·28 |
| `/settings/appearance` | 14 | 32×13 · 36×1 | 4 | 14 | 8·10·6 | 1 | 0 | 10·12·14·40 |
| 편집기 | 138 | 24×20 · 27×3 · 30×15 · 32×78 · 36×15 · 40×6 · 216×1(선택 상자) | **60** | 12 ×82 · 14 ×36 · 13.33 ×20 | 10 ×63 · 8 ×18 · 6 ×10 · **0 ×42** · 999 ×5 | **26** | 0 | 10 ×37 · 12 ×110 · 14 ×57 · 13.33·11.67·16.38·21 |
| `/review` | 8 | 32×7 · 36×1 | 4 | 14 | 8·10 | 1 | 0 | 10·14·28 |

계획 표(2026-10-08, 실제 데이터·H 이전)와 비교: 편집기 컨트롤 192→138(시험 프로젝트가 작음), Arial 66→60, 채운 단추 38→26, 이유 없는 비활성 8→0, 10px 글자 40→37. `/projects`의 `+ 새로 만들기` 80px 칸은 그대로. 굵기는 `/projects`에서 650·700·750이 아직 섞여 있다(650 ×2, 700 ×17, 750 ×1).

## (a) 손잡이 없음 · 이유 없는 비활성 · 이름 없는 아이콘 단추

- 손잡이 없는 단추 **3**개 출력, 그중 진짜는 1개.
  - `features/footage/SceneTimeline.tsx:14` **W-01 그대로**(`data-native-control="footage-playhead"`, 누를 손잡이 없음).
  - `app/ProductShell.tsx:133`, `components/ui/dialog.tsx:119`는 **거짓 양성**: 바깥 `DialogTrigger asChild`/`DialogPrimitive.Close asChild`가 눌림을 받는다. 처리: 그대로 — 이유.
- 조건 비활성인데 이유 없음 **126곳 / 30파일**(계획의 138/33과 다름: 스크립트 규칙의 차이. 새 값 126을 따른다). 많은 순: InspectorControls 19 · FootageOrganizerPage 12 · OutputsPage 11 · YujinPanel 9 · CreationInterview 7 · EditorAssetBrowser 6 · AppRouter 5 · VoiceRecordStart 5 · SceneTimeline 5 · MotionPanel 4 · MediaAnalysisStatusPanel 4 · SourceVideoStart 3. 파일별 전체 줄은 `SCAN_VERBOSE=1`로 다시 돌린다.
- 이름 없는 아이콘 단추 **1**: `components/ui/sidebar.tsx:269` — `<span className="sr-only">Toggle Sidebar</span>`(영어). `SidebarTrigger`를 `sidebar.tsx` 밖에서 쓰는 곳이 없다(grep). 처리: 그대로 — 안 쓰는 부품(영어 문구는 Task 11 정리 후보).

## (b) 화면 호출 0개인 `api` 메서드 (명령 출력 그대로)

`api` 메서드 225개(계획 224). 비시험 소스에서 부르는 곳이 0인 것 **9**(계획과 같음). `tests=`는 그 이름이 나오는 시험 파일 수.

```
cancelHermesRun tests=0
createHermesRun tests=1
getDirectorProposal tests=1
getExport tests=2
getPreview tests=3
listDirectorMessages tests=1
openHermesRunEvents tests=1
prepareDirectorMessage tests=1
retryHermesRun tests=0
```

`getExport`·`getPreview`는 `apps/web/src/app/AppRouter.test.tsx:863-876`이 "부르지 않는다"를 단언한다 = 일부러 남긴 것(그대로 — 그 시험이 이유). 나머지는 W-02 규칙(Task 11)으로 조사. `cancelHermesRun`·`retryHermesRun`은 시험도 0개 → 가장 먼저 없앰 후보.

## (c) 라우트와 메뉴

정의된 경로(`AppRouter.tsx`): `/`(→`/projects`), `/projects/`, `/preview/$token`(공유, 셸 없음), `/library`, `/voices`, `/footage`, `/projects/$projectId/$section`, `/settings/$section`. `routeManifest.ts`의 `globalDestinations` = 프로젝트·자료실·촬영본·내 목소리·설정. 메뉴에서 닿는 곳: `SideNav.tsx` `ITEMS`·`ASSET_ITEMS`, 위 띠 `TopBar.tsx` `STAGES`. **닿지 않는 화면 없음**(계획 W-08과 같음).

## (d) 프런트가 안 부르는 것으로 보이는 백엔드 경로 — 29개 (계획 30)

계획이 적은 `exact-previews/{gid}`는 이제 `api.ts`가 부른다(목록에서 빠짐). 나머지는 같다. 분류는 **잠정**이다 — 이름만으로 "유진·MCP 전용 / 내부 점검 / 화면 약속 / 아무도 안 씀"을 확정할 수 없고(`services`·`packages`의 유진/MCP 파일에서 이 경로 문자열을 직접 쓰는 곳을 못 찾았다), 확정은 Task 11의 몫이다. 지우지 않는다.

| 묶음 | 경로 | 잠정 분류 |
|---|---|---|
| 자산 올리기 | `assets/script-document`, `assets/raw-video`, `jobs/auto-cut-plan`, `jobs/auto-cut-detect` | 화면 약속 후보(만들기 시작 흐름이 쓰는지 Task 11이 확인) |
| 편집판 | `editing-sessions/from-script`, `…/narration-alignment`(+`from-recording`), `…/tracks`(GET/POST/DELETE/PATCH order), `…/segments/{id}/visual-overlay`(PATCH/DELETE) | 화면 약속 후보 / 유진 전용 후보 |
| 분석·추천 작업 | `jobs/segment-analysis`, `jobs/broll-recommendation`, `jobs/music-recommendation`(각 POST+GET) | 내부 작업 후보 |
| 자료실 | `library/ingest-path`, `media-library/install`, `media-library/install-state` | 내부 점검 후보 |
| 출력 | `jobs/preview-render`, `jobs/capcut-export`, `provider-traces`, `jobs/build-timeline` | 내부/선택 경로 후보 |
| 근거 | `media-analysis/{id}/provenance`, `review-snapshots/{job}/recommendations/{id}/reject` | 화면 약속 후보(거절 단추) |
| 내부 | `/internal/live-smoke/…/root-attestation` | 내부 점검(정상) |

## (e) 유진 격차

`yujin_*.py`·`services/api/src/videobox_api/*.py` grep(계획 명령 그대로) 결과 31개 이름: `apply_media apply_overlay apply_tts_candidate create_app create_short_form redo_stack remove_image_overlay remove_media render_calls render_short_form set_caption_font set_caption_layout set_caption_style set_caption_text set_crop set_cut_action set_focal set_image_overlay set_photo_motion set_picture_cleanup set_safe_area set_scene_look set_scene_speed set_scene_transform set_scene_transition set_segment_bounds set_shorts_title set_sound_cleanup set_style set_text undo_stack` (`create_app`·`redo_stack`·`render_calls`·`undo_stack`은 명령이 아니라 함수/상태 이름).

화면에 있고 유진은 아직 못 하는 것(구현하지 않는다. B–F 담당): 장면 나누기 B-Task2 · 앞과 붙이기 B-Task3 · 되돌리기/다시 하기 B-Task4 · 배속 0.25~4 B-Task5 · 트랙 숨기기·소리 끄기 B-Task6 · 완성본 만들기 C-Task9 · 캡컷 초안·미리보기 링크 C-Task10 · 업로드 승인 **요청** C-Task11 · 설명 카드·표·도형 D-Task13 · 자막 모양 D-Task14 · 저장한 포맷 D-Task15 · 자막 번역·언어 E-Task17 · 더빙 E-Task18 · TTS 교체·받아쓰기 캡션·부분 다시 만들기 E-Task19 · 프로젝트 보관 F.

**B–F에 없는 후보**(F-Task21로 넘김): 자료실 이름 바꾸기·즐겨찾기·휴지통, 촬영본 정리(분석 시작·제안 적용·가상 묶음), 모션 만들기, 화면 변형(크기·위치·기울이기·화면 맞춤), 색감·흔들림·노이즈, 소리 크기·서서히, 전환 적용. 명령 목록에 `set_scene_transform`·`set_scene_transition`·`set_scene_look`·`set_sound_cleanup`·`set_picture_cleanup`처럼 **이름이 이미 있는 항목**이 있다 — 그 항목은 "없음"이 아니라 "있는데 배선 확인 필요"로, B–F 첫 Task가 재확인한다(여기서는 확정하지 않는다).

## (f) 탭 · 선택 목록

- `role=tab`: 편집기 13개(미디어·오디오·텍스트·캡션·대본·전환 / 전체·영상·그림 / 화면·소리·속도·보정), 이름 빈칸 0. **설정 화면은 0개**(섹션이 단추 묶음 — W-07 그대로, Task 9).
- 편집기 `select` 4개: 재생 빠르기 · 편집 대상 · 선택 구간 처리 · 영상 화면 맞춤. 편집 대상 선택 상자의 옵션 수는 이 기준선에서 안 쟀다(고정 프로젝트가 작다) → 중복 id 수리 확인은 H 몫.
- `tabpanel` 짝 여부는 이 수집 함수가 안 본다. 편집기 크롬은 계획 L이 Task 10을 대신하므로 그쪽에서 확인.

## 줄별 처리표 (W-01~W-12)

| ID | 상태 | 처리 |
|---|---|---|
| W-01 | 확인됨(`SceneTimeline.tsx:14`) | 없앰 → 꾸밈 `<span aria-hidden="true">`로, `task22-parity-owners` 허용 수 1 감소(Task 11) |
| W-02 | 확인됨(위 9개) | 조사(Task 11). `getExport`·`getPreview`는 그대로 — `AppRouter.test.tsx:863-876` |
| W-03 | 29개, 잠정 분류 | Task 11에서 확정. 지우지 않음 |
| W-04 | 126곳/30파일(계획 138/33) | 편집기 밖 → Task 5, 편집기 → 계획 L(Task 10 대신) |
| W-05 | 일부 해결(`Close`→`닫기`, 영어 자막 모양 이름·백틱 `9ddbef9d7`). `/footage` 내부 id·`−1f`·`+1f`·`fps`·라우터 오류 화면은 이 Task에서 재확인 안 함 | 남은 것: Task 8·11 |
| W-06 | 설정에 `조밀한 화면: 꺼짐` 토글이 아직 있다(기준선 단추 목록) | owner 결정 D3 |
| W-07 | 설정 탭 0개 확인. 편집기 레일 탭 이름은 해결됨 | Task 9, 편집기는 계획 L |
| W-08 | 닿지 않는 화면 없음 | 그대로 — 확인됨 |
| W-09 | `Toaster`가 `AppRoot.tsx:9`에 걸림 → 장착은 끝남 | Task 5는 "화면마다 다른 알림 방식"만 남은 것으로 재확인 |
| W-10 | (e)절 | B–F에 넘김 |
| W-11 | H가 수리 | H에 넘김(완료) |
| W-12 | H가 수리(트랙 단추 클릭 실기 시험 있음) | H에 넘김(완료) |
