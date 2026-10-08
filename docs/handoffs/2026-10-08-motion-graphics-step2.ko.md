# 설명 모션 2단계 — 모션 다리(8202)·템플릿 셋·편집기 `모션 만들기` (2026-10-08)

**이어받는 문서:** `2026-10-08-audit-bundle-a-security-tools-rename.ko.md`
계획서: `docs/superpowers/plans/2026-10-08-motion-graphics-step2.ko.md`
결정 기록: `docs/decisions/2026-10-08-motion-graphics-with-hyperframes.ko.md`
작업 장부: `.superpowers/sdd/2026-10-08-motion-graphics-step2.ko/progress.md`
(Task별 보고서 `task-N-report.md`, `task-8a-report.md`, `task-8b-report.md`가 같은 폴더에 있다.)

작업은 메인 체크아웃에서 직접 했다(CLAUDE.md §3). 커밋 범위는 `9ceff6a4a..` 이후 Task 0~8.

## 한 일

| Task | 내용 |
|---|---|
| 0 | 출발 점검(읽기만) — 앵커·도구·포트 |
| 1 | 템플릿 셋(막대 비교·금액 카운터·단계 목록)과 하이퍼프레임 **0.8.140** 고정, `npm ci --ignore-scripts` (`..c2ae9c02c`) |
| 2 | 모션 다리(8202) — 템플릿만 그리고, 한 번에 하나, 시간 상한, 네트워크 0건 (`..20ea843dc`, 고침 2회 `2cf405a8b`·`aa399d9b4`) |
| 3 | 템플릿 목록·엄격한 변수 검사·다리 부르는 쪽·자료실 등록 서비스 (`..f608184db`, 고침 1회) |
| 4 | 자료실 `모션 만들기` API와 compose 다리 주소 (`..5176aa63c`) |
| 5 | `owner-ready`가 모션 다리를 켜고, 처음 준비는 숨은 창에서 따로 (`..d59f2fc59`) |
| 6 | 편집기 `모션` 팝업(`MotionPanel`) — 적어서 만들고 이 프로젝트로 가져온다 (`..ee88302e6`) |
| 7 | 실측만(코드 없음) — 아래 표 |
| 8 | 실물로 닫기. Part A에서 **실결함 1건**을 찾아 고침 3커밋(`6e6309012`·`6799f952b`·`8eb1502b0`), Part B에서 재빌드·재확인·전체 시험·문서 |

## 실측 값

### Task 7 (호스트 직접, 하이퍼프레임 0.8.140, 네트워크 언급 전부 0)

| 항목 | 시간(초) | 크기(바이트) | 비고 |
|---|---|---|---|
| 6초 bar_compare 5회 | 11.44~12.16 | 368947 | 다섯 개 md5 동일(`6a8d9607…`) = 이 기계에서 결정적 |
| 30초 bar_compare mp4 | 13.81 | 552769 | h264 1920x1080 30fps, 30.000000초 |
| 30초 money_counter mp4 | 14.28 | 1167059 | 같음 |
| 30초 step_list mp4 | 13.86 | 583587 | 같음 |
| 30초 bar_compare 겹(overlay) webm | 47.27 | 867239 | vp9 1920x1080 |
| 동시 요청 | 200 / 10.76초 + 409 / 0.0028초 | | 둘째는 기다리지 않고 즉시 거절 |

Task 2 실렌더 9개(템플릿 3 x full·overlay·longest, 6초): 8.9~13.7초. 겹 mp4는 전부 yuv420p, 겹 webm은 알파 있음(모서리 알파 0, 카드 알파 220). Task 5 owner-ready Start는 준비 중인 가짜 prepare를 붙잡아 둔 채 돌려줬다(시작이 준비를 안 기다린다).

### Task 8 Part A (실제 컨테이너, 화면 경로)

- 3초 클립 셋을 자료실에서 받아 ffprobe: 전부 `h264, yuv420p, 1920x1080, 30/1, 3.000000초`. 프레임을 눈으로 봤다: 한글 또렷, `1,280만 / 860만 / 430만`, `₩12,345,678`, 단계 셋 글 맞음, 판 밖으로 나간 글 없음.
- 화면에서 만든 시간: 막대 비교 약 수 초~, 금액 카운터 36.7초(기계 부하 중), 단계 목록 14.1초.
- 프로젝트의 정확 미리보기(exact-preview) 길로 1.33초 장면을 그렸다: 1.2초 프레임이 모션 전체 화면이고, 가장 큰 막대 줄 화소 `(252,174,31)` = 주황(R>200, G 140~200, B<80) 통과.
- 30초 클립(막대·단계): 1초는 인트로 도중, 15초와 29초 프레임이 **화소까지 같다** = 인트로 뒤 마지막 모양을 붙잡고 있다(아래 안 한 것 참조). 겹 webm은 `-c:v libvpx-vp9`로 읽으면 `yuva420p`, 모서리 알파 0, 막대 알파 255.
- 팝업 폭 375: 팝업 343폭, 가로 넘침 없음, 팔레트 다크 그대로.

### Task 8 Part B (재빌드한 컨테이너)

- `owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild` 전부 `PASS`, `모션 다리가 이미 준비돼 있습니다`(다리는 Part A 고침 뒤 12:27에 이미 새 코드로 떠 있었다). 8202 리스너는 하나, 명령줄이 이 저장소의 `scripts\host_motion_service.py`, 토큰 없는 `/diagnostics`는 401. 템플릿 목록 `['bar_compare','money_counter','step_list']`.
- **화면 API 경로**: `POST /api/library/motions`(금액 카운터 3초 full, 금액은 정수) → 201, **왕복 10.0초**(다리 elapsed 9.66초). 같은 자산을 프로젝트 `0907-b26195af`에 가져오니(`materialize` 201) 프로젝트 자산 `metadata.title`에 자료실 파일 이름이 실렸다(고침의 결과).
- **화면(내장 브라우저, 단계 목록 `8b 재빌드 확인`)**: 누르자 단추가 `만드는 중… 1분 안쪽으로 걸려요`로 잠겼다. 만드는 동안 Esc와 팝업 바깥 누르기를 해 봤고 팝업이 그대로 열려 있었다(캡처 `8b-busy-lock-after-esc-and-outside-click.jpg`). 끝나자 `다 만들었어요. 이 프로젝트 영상 목록에 넣어 뒀으니 장면을 고르고 적용을 눌러 쓰세요.`, Esc로 닫히고, 영상 목록 카드가 `8b-재빌드확인`·`8b-재빌드-확인`으로 **이름을 단다**(Part A 때는 `자료 N`). 이 화면 경로의 렌더 시간은 정확히 재지 못했다(화면 도구로 보는 것이라 초 단위 기록이 없음) — 같은 단계의 API 왕복이 10초다. 내장 브라우저는 화면을 안 그리는 때가 있어(저장소 메모) 글자 모양·애니메이션은 이 경로로 판단하지 않았다.

### 전체 시험 (혼자 돌림)

- 파이썬(`--ignore=tests/test_mcp_server.py`): **5561 통과, 56 건너뜀, 1 xfail, 실패 2** (45분14초).
  - `test_handoff_entry_point::test_entry_map_points_at_the_newest_handoff` — 이 문서보다 먼저 CLAUDE.md를 옮겨서 난 일시 실패. 이 문서를 만든 뒤 통과해야 한다(아래 확인).
  - `test_response_model_extra_forbid_ratchet::test_response_models_without_extra_forbid_do_not_grow` — **이 계획 때문이다.** 모션 응답 모델 셋(`MotionResponse`, `MotionTemplateResponse`, `MotionTemplateListResponse`)에 `extra="forbid"`가 없어 기준선 97 → 100. 알려진 흔들리는 시험이 아니다.
  - 알려진 `smoke_timeout`은 이번엔 통과.
- vitest: **146개 파일 / 1830건 전부 통과**(알려진 흔들리는 시험도 이번엔 통과).
- 빌드: 성공(500kB 넘는 청크 경고는 기존).
- e2e(playwright): **48건 전부 통과**(포트 4173 점거자 없음). `workbench dock drag has fixed warmup`(부하에 흔들리는 성능 문): 따로 혼자 5번 → **4번 통과, 1번 실패**(실패 메시지는 못 남겼다). 기계에 남의 python 3.14 프로세스 둘이 계속 CPU를 쓰고 있어(대표님 쪽, 안 껐다) 부하 약 45%였다. 이 계획이 건드린 영역(편집기 자료 칸)과 도크 끌기의 연결은 못 찾았지만 증명하진 않았다.

## 실제로 찾은 결함 — 숨은 창으로 켠 다리에서 렌더가 180초 멈춘다

- **증상**: 화면 `모션 만들기`가 180초 뒤 504(`motion_took_too_long`). 다리 안의 node가 CPU 1.7초만 쓰고 가만히 서 있고, 크롬(chrome-headless-shell)·ffmpeg는 뜨지도 않았다.
- **원인(재서 확인)**: `run_bounded()`가 `Popen`에 `stdin=`을 안 줬다. `owner-ready`가 다리를 숨은 창(`Start-Process -WindowStyle Hidden`, 출력 리다이렉트)으로 켜면 자식이 닫히지 않는 stdin을 물려받고 node가 기다린다. 같은 다리를 평범한 셸에서 켜면 11초, 숨은 창으로 켜면 180초 상한까지 간다. `stdin=DEVNULL`만 더한 래퍼는 같은 숨은 창에서 10.4초.
- **왜 시험이 놓쳤나**: 단위 시험은 `Popen`을 가짜로 바꾸거나 평범한 스폰이라 stdin이 열려 있어도 안 걸렸다. Task 7 실측은 Git Bash에서 다리를 띄웠다(키보드 stdin이 있는 환경). 제품이 실제로 쓰는 "숨은 창 + 리다이렉트"로 켠 것은 Part A가 처음이었다. 교훈: 호스트 다리를 시험하려면 **owner-ready가 켜는 방식 그대로** 켜서 한 번 밟는다.
- **고침(`6e6309012`)**: `stdin=subprocess.DEVNULL`. `prepare-motion.ps1`의 자식(npm ci, browser ensure)도 같은 위험이라 빈 임시 파일을 `-RedirectStandardInput`으로 준다. 시험 둘: Popen kwargs 시험, 그리고 stdin이 열린 파이프인 부모 아래서 stdin을 읽는 자식을 실제로 스폰하는 시험(수정 전 둘 다 실패). 실물: 숨은 창으로 켠 다리에서 렌더 10.5초.
- 같이 고친 것(`6e6309012`, `6799f952b`): prepare 기록(transcript)은 잠금을 얻은 뒤에만, 잠금 catch가 `UnauthorizedAccessException`도 처리, `layout`이 falsy(0/False/[]/{}/"")면 400(`layout is None`일 때만 full), 만드는 동안 팝업 닫기 막기(Esc·바깥·닫기 단추), 단계 줄이 칸을 채움, **자료실에서 가져온 영상 카드가 이름을 단다**. 마지막은 모션만이 아니라 **모든 자료실 사용자 자산 가져오기**에 적용된다(`materialize_user_library_asset`이 파일 이름에서 확장자를 뗀 것을 `metadata.title`로 싣는다. 이름이 없으면 옛 동작 그대로). 시험 `tests/test_library_materialize_carries_title.py`. 전체 시험에서 라이브러리·자료실 쪽 회귀는 나오지 않았다.
- 클라이언트 280초 상한(`8eb1502b0`): 요청이 280초 넘게 답이 없으면 스스로 놓여나 팝업을 닫을 수 있다.

### 마감 직전 고침 — 응답 모델 기준선 시험

위 전체 시험의 빨간 시험 하나(모션 응답 모델 셋이 `extra="forbid"` 없음, 기준선 97 → 100)를 같은 날 고쳤다. 세 모델에 `ConfigDict(extra="forbid")`를 달았고 기준선은 올리지 않았다. 확인: ratchet·`test_api_motions`·`test_api_infographics`·`test_handoff_entry_point`·editor-ui provenance = 60 통과. `models.py`가 바뀌어 컨테이너를 한 번 더 `-Rebuild`(전부 PASS)한 뒤 화면 경로 `POST /api/library/motions` 금액 카운터 3초 → 201, 왕복 11.9초. 이 고침 뒤 전체 pytest를 처음부터 다시 돌리지는 않았다(바뀐 것은 응답 모델 설정 셋뿐, 관련 시험만 확인). 위 "결정 필요" 1번은 해결됐다.

## 안 한 것·남은 것 (정직하게)

1. **투명 겹(overlay)은 이 계획 Task 9가 하는 것인데 안 했다.** 화면에서는 `layout: full`만 연다(API도 `Literal["full"]`). 완성본 렌더러가 투명 webm의 알파를 아직 못 읽는다(기본 디코더는 알파를 `yuv420p`로 보고하고 `libvpx-vp9`로 읽어야 `yuva420p`). 겹 webm 파일 자체는 알파가 맞게 만들어진다(Task 7·Part A 실측).
2. **유진 연결은 3단계다(plan B–F 뒤).** 화면에 연 기능이라 유진 배선이 빠진 상태다(CLAUDE.md "화면에 열면 유진도 같이"). 세 겹이 필요하다: (1) 의도 — `yujin_editing_proposals.py`에 `MakeMotionOperation(segment_id, template, variables, duration_sec)`, 변수 검사는 `parse_motion_variables`를 그대로, (2) 적용기 — `MotionService.make` → `materialize` → `update_segment_broll_override`(전체 화면), 되돌리기는 기존 B-roll 되돌리기, 오래 걸려서 기다림 표시(작업+폴링) 재사용, (3) 프로필 안내문 — "숫자 장면에 막대 비교·금액 카운터·단계 목록 중 하나를 **제안**하고 숫자는 대본에 있는 것만 쓴다"(사람 게이트 유지). 공유 파일(`YujinPanel`·`OutputsPage`·`library_assets.py`·`api.ts`)을 plan B–F가 고치므로 그 뒤에 한다.
3. **30초 클립은 인트로 뒤 마지막 모양을 붙잡고 있다.** 막대·단계 템플릿은 15초와 29초 프레임이 화소까지 같았다. 의도된 동작처럼 보이지만 이를 말하는 설계 문장은 못 찾았고, **의도인지는 미검증**이다. 금액 카운터는 15초와 29초가 작은 칸(624,560)–(656,592)에서만 다르다(원인 모름).
4. **카운터·단계 클립은 장면에 적용해 렌더하지 않았다.** 막대 비교만 장면에 적용해 정확 미리보기로 그렸다. **완성본(final render)은 안 돌렸다** — 사람 게이트(검토 승인)가 필요하고 대표님 실제 프로젝트를 바꾸기 때문이다. 그래서 "완성본 mp4에서 모션 프레임이 그대로 나온다"는 직접 확인하지 않았다.
5. **장면(1.33초)보다 긴 모션(3초 최소)이면 사용자는 앞부분만 본다**(막대가 자라는 중). 기본 길이 정책과 안내는 정하지 않았다.
6. **처음 준비(npm 설치·브라우저 약 270MB 받기) 경로는 가짜로만 시험했다.** 실제 엔진 캐시는 건드리지 않았다.
7. **팝업을 만드는 도중 닫는 경험**: 지금은 만드는 동안 닫히지 않는다(고침). 다만 한 번 닫혔다 열면 빈 새 폼이 보이고 "만드는 중" 표시가 없던 관찰(Part A (d))은 고친 뒤 건강한 경우로 다시 밟지 않았다.
8. 옛 export overlay 경로(`-loop 1`), 세로(9:16) 템플릿, 30초 넘는 클립(상한), 캡컷 내보내기에서 모션 클립 확인은 하지 않았다.
9. **이월한 사소한 것들(장부 `minor (deferred)`)**:
   - T1: 거절 목록이 프로토콜 상대 `url(//` 등 일부를 놓친다(보강함), `template.js`의 null bars는 API가 막는다.
   - T2: `allowlist`에 SystemDrive/ProgramData/USERNAME 없음(크롬이 안 뜨면 재확인), 413은 단위 시험만, `prepare-motion.ps1`을 PS5.1 `Start-Process` ExitCode null 위험은 고침으로 해소.
   - T3: `float(reply.get('elapsed_sec') or 0.0)`가 숫자 아닌 값이면 ValueError.
   - T4: `_http_error`의 예기치 않은 예외 detail 확인, `MotionCreateRequest.variables` 크기 상한 없음(문 앞), detail이 문자열이거나 객체.
   - T5: start-motion 리다이렉트가 8201과 같은 방식(출력 파이프를 받는 호출자는 다리가 사는 동안 대기할 수 있음).
   - T6: 막대 값 칸이 `-5/1e3/0x10`을 화면에서 받는다(서버가 거절), 기다림 문구가 정적.
10. **대표님이 치울 수 있는 실물 찌꺼기(내가 지우지 않았다)**:
    - 자료실 시험 항목 5개: `user_219eab55fb4941e8b03d644a8db1f0ee`, `user_b0936e707b9c4fbbb976a200295d153f`, `user_613a800236d64bc9825ad738c4f3d5c1`, `user_db281152a19e4c6aaa0134776b1b59a1`(Part A), `user_e3f7c4a25226486baf9ab3753f3dc4c0`(Part B API 확인), `user_b9354c54ae27438dab1dc1e00b664288`(마감 직전 재확인), 그리고 Part B 화면 확인으로 만든 `8b 재빌드 확인` 항목 하나(자료실에서 제목으로 찾는다).
    - 프로젝트 `0907-b26195af`(사진 브이로그 실기 0907): 프로젝트 자산 3개(Part A) + Part B의 `asset_29e668e2ddbf` 및 화면 확인 자산 1개, 그리고 장면 `timeline_001:001`에 **B-roll 대체(막대 비교 `asset_f0c0ca611b44`)**가 걸려 있다. 실제 영상으로 쓰실 프로젝트면 이 대체를 되돌리고 자산을 빼야 한다.
    - 남의 python 3.14 프로세스 둘(PID 50708·47840)이 오늘 02:40에 시작해 몇 시간째 CPU를 쓰고 있다(우리 세션이 띄운 것 아님, 안 껐다).

## 내가 내린 판단 (장부 `Ruling:` 전부)

| 판단 | 틀렸을 때 비용 |
|---|---|
| 처음 엔진 준비(npm + 크롬 약 400MB)는 자동·백그라운드·시간 상한, `Start`는 안 기다린다. owner가 "설치해서 써라"고 했다 | 예상 못한 400MB 다운로드가 한 번 일어난다 |
| 다리가 `--variables` 대신 `data.js`를 직접 쓴다(스파이크에서 `--variables`를 안 재 봤다) | 결정 문서의 말과 구현이 다르다. 기능에는 영향 없음 |
| 30초 상한·9:16 템플릿 없음·GSAP 없음(저장소 반입은 owner 승인 필요) — 계획 그대로 | 긴 영상·세로·고급 이징이 필요하면 후속 작업 |
| Task 9(투명 겹)은 대표님이 겹 사용을 명시했으므로 Task 0~8 다음에 포함하기로 했다 | 약 2.5시간 낭비 가능. **결과적으로 이 인계에서는 안 했다** |
| 유진 모션 연결(3단계)은 plan B–F 뒤에 한다(공유 파일 충돌) | 그동안 유진은 모션을 못 쓴다 |
| 중단 규칙은 마스터 문서 §3과 같다. 흔들리는 시험: editor-workbench 도크, owner_ready smoke_timeout, 부하에 흔들리는 e2e·vitest(단독 재실행) | 진짜 회귀를 흔들리는 시험으로 오진할 수 있다 |

## 재사용 게이트 (§8.3)

- **재사용(adopt/partial port)**: 그림 다리의 판단/껍데기 분리·`_Handler` 모양, 다리 문지기(`host_bridge_guard`)·공유 토큰·`bridge_request_headers`, `owner-ready`의 다리 블록(전체 이식), `InfographicHostBridge`의 주소 검사(부분 이식), `LibraryIngestService`, `materializeLibraryAsset`, 인포그래픽 패널 CSS.
- **새로 만든 것**: 템플릿 셋, 모션 다리, 변수 검사(`parse_motion_variables`), 준비 스크립트(`prepare-motion.ps1`).
- **뺀 것과 이유**: GSAP(저장소 반입은 owner 승인 필요, 없어도 오프라인으로 된다), `--variables`(스파이크에서 안 재 봤다 — `data.js`로 같은 일을 한다), 리모션(결정 그대로 exclude), open-design 템플릿(프롬프트뿐).
- **경계 보존**: 팔레트·사람 게이트(검토 승인) 그대로. 네트워크는 이 기계 8202 하나가 늘었다(결정 문서 승인). 렌더 중 바깥 접속은 0건(템플릿에 바깥 주소 없음, 죽은 프록시, 시험이 지킨다).

## 결정 필요 (대표님)

1. 위 "대표님이 치울 수 있는 실물 찌꺼기"(자료실 항목·프로젝트 자산·B-roll 대체)를 지울지.
2. 30초 클립이 인트로 뒤 마지막 모양을 붙잡는 동작이 의도에 맞는지.
3. 투명 겹(Task 9)과 유진 연결(3단계)을 언제 할지.
