**대체됨:** docs/handoffs/2026-10-08-motion-graphics-step2.ko.md

# 점검 후속 묶음 A — 다리 토큰·도구 패치·인포그래픽 거절·이름 바꾸기 (2026-10-08)

**이어받는 문서:** `2026-10-01-full-audit-security-copy-wiring.ko.md`
계획서: `docs/superpowers/plans/2026-10-02-audit-a-security-tools-rename.ko.md`
결정 기록: `docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md`
작업 장부: `.superpowers/sdd/2026-10-02-audit-a-security-tools-rename.ko/progress.md`
(Task별 보고서 `task-N-report.md`, `task-10a-report.md`, `task-10b-report.md`가 같은 폴더에 있다.)

작업은 메인 체크아웃에서 직접 했다(CLAUDE.md §3). 커밋 범위는 `f72e801e3..` 이후 Task 0~10.

## 한 일

| Task | 내용 |
|---|---|
| 0 | 이미지에서 `.env.container`·`.venv-chatterbox` 제외 (커밋 `f72e801e3..bb86f519f`) |
| 1 | 도구(npm) 패치 — vite·vitest 등 개발 도구는 패치만 (`bb86f519f..e43a1ef98`) |
| 2 | 호스트 다리 문지기(`host_bridge_guard`): 토큰·Content-Type·Host 검사 (`..3deb7ca42`) |
| 3 | 컨테이너 쪽 다리 호출에 토큰 헤더 (`..b87a969f7`) |
| 4 | `owner-ready`가 `.env.container`에 다리 토큰을 "없을 때만" 쓴다. 원자적 쓰기 (`..7e9da9ea8`, 고침 1회) |
| 5 | 인포그래픽 모델 출력 거절 문지기(스크립트·`on*`·`javascript:` 등) (`..1b3391f19`, 고침 3회) |
| 6 | 자료실 이름 바꾸기 API (`..ccc1ba166`) |
| 7 | 자료실 미리보기 칸 이름 바꾸기 UI (Enter 저장·Esc 취소) (`..49ba5e327`) |
| 8 | 깨진 자료실 이름 일괄 복구 스크립트(미리보기 기본·`--apply`·`--undo`) (`..2b597f86b`, 고침 1회) |
| 9 | 분석 문장 조각이 분위기 태그가 되지 않게 함 (`..ca12a478e`) |

### Task 10 Part A 실측 값 (2026-10-08)

- **다시 짓기**: `owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild` 전부 PASS. 시작 전 8199/8200/8201 포트가 모두 꺼져 있어서 이 한 번에 컨테이너와 다리 셋(voice·capcut·infographic)이 새 소스로 같이 떴다. 옛 다리는 떠 있던 적이 없다. `.env.container`에 `VIDEOBOX_BRIDGE_TOKEN=` 줄 1개, 컨테이너 안은 `token-set`/`env-absent`(비밀 파일 이미지에 없음), `handoff-diagnostics`의 `project_root_exists True`.
- **Step 3**: 토큰 에러 로그 없음. `Start-VideoBox.ps1 -SkipBrowser -Json` → `overall: ready`, voice `pass`.
- **Step 4 다리 표**(토큰 없음/text-plain/잘못된 Host/정상 JSON): 8199 `/synthesize` 401/415/400/400, 8200 `/register` 401/415/400/400, 8201 `/render` 401/415/400/400. voice `/health` 200, capcut `/diagnostics` 토큰 없이 401. 토큰 넣은 실제 `/render`(작은 HTML) 200, PNG 1920x1080.
- **Step 5 화면**:
  - CapCut: `CapCut에 등록` → API 200, 호스트 다리 `/register 200`. 화면에 "이미 등록한 CapCut 정보를 다시 써요". 초안 폴더 14개 그대로(새 폴더 없음).
  - 더빙: 컨테이너 안에서 다리 `/synthesize`를 직접 불러 200, wav 215120바이트·2.24초, 평균 -23.2 dB·최대 -4.7 dB(무음 아님), 54초 걸림.
- **Step 6 깨진 이름**: 미리보기 `고칠 이름 24개`(녹음 2 + 화면 녹화 21 + 완성본 1, 24개 전부 눈으로 확인) → `--apply` `바꿈 24/24`, 되돌림 목록 `artifacts/library-filename-repair/revert-20261007T192145Z.json`(보관). 다시 돌리면 `고칠 이름 0개`. 서버 확인 `2 21 1 0`.
- **Step 7 이름 바꾸기 화면**: 제목이 한글로 보임, 입력칸에 현재 이름이 미리 들어 있음, `a/b`는 저장 버튼 비활성+"이름에 / 나 \ 는 쓸 수 없어요.", Esc로 닫힘, Enter로 저장되어 서버에서 확인, 원래 이름으로 되돌려 서버 확인. 팩 자산에는 이름 바꾸기 버튼이 없다.
- **Step 8 배선 grep**: `check_request(` 3곳, `bridge_request_headers()` 3곳, `renameLibraryAsset(` 1곳(LibraryPreviewPane.tsx), 라우트 `/filename"` 1곳, `filter(isChipTag)` 1곳, `analysis_phrases` 비시험 4곳.
- **분위기 태그 원인(Task 9)**: 분석이 내놓은 문장 조각이 분위기 태그 칸으로 흘러 들어갔다. 새 규칙은 조각이 태그가 되지 않게 막는다.

## 안 한 것·남은 것 (정직하게)

1. **인포그래픽 실모델 생성은 검증 못 했다.** 화면에서 두 번(UTC 19:26:39, 19:29:33) 만들었고 둘 다 `504 infographic_took_too_long`(글 쓰는 LLM 140초 상한). 화면 문구 "너무 오래 걸렸어요. 숫자를 줄이고 다시 해 보세요."는 제대로 나왔다. 따라서 **실모델 출력으로 1920x1080 자산이 나오는지, Task 5 거절 문지기가 실제 출력을 오탐하지 않는지는 미확인**이다. 다리 쪽 렌더만 손으로 쓴 HTML로 확인했다. `infographic_service.py`는 이 묶음에서 안 건드렸으니(마지막 변경 08b875f6c) 느린 로컬 생각 모델 탓으로 보지만, 이전 커밋 비교(bisect)로 증명하지는 않았다. 대표님이 `VIDEOBOX_INFOGRAPHIC_TIMEOUT_SECONDS`를 올릴지 정하신다.
2. **더빙은 화면 경로로 못 밟았다.** 목소리 샘플이 있는 프로젝트(project-318cc020)에 번역된 자막이 없어 더빙 버튼이 안 뜬다. 컨테이너→다리 직접 합성만 확인(위 -23.2 dB).
3. **CapCut 인계는 기존 등록을 재사용**했다(새 초안 폴더 없음). `CapCut 초안 만들기`(새 내보내기)는 일부러 안 눌렀고, CapCut 앱 자체가 그 초안을 여는지는 확인하지 않았다.
4. **Task 5 문지기에 남은 이국적 파서 차이**(Chrome과 파이썬 `HTMLParser`가 다르게 읽는 입력): foster parenting, svg/math 통합 지점, template/frameset, `<?pi>` 가짜 주석. 3번의 고침으로 실제 우회 8건은 막았지만 이 종류는 **알고 둔 것**이다. 구현자의 권고는 **허용 목록(allowlist) 재설계**다(인포그래픽이 쓰는 태그·속성만 통과). 문지기는 로컬 LLM 출력에 대한 겹방어라서 계획 범위 밖으로 두었다. 대표님/다음 묶음이 정한다.
5. **`npm audit --omit=dev`**: 치명 1건이 남아 있다 — `seroval`(≤1.6.2), `@tanstack/react-router`를 통해 들어옴. 이 묶음 이전부터 있던 것이고 범위 밖이라 고치지 않았다. Part B 실측은 아래 "시험 결과".
6. **vite·vitest 경고**: 개발 도구라 패치만 한다는 결정에 따라 전체 `npm audit`에 남아 있는 이름·등급이 있다(위 결정 기록 참조).
7. **`.env.container` 비밀값 교체 여부는 대표님 결정이다.** 옛 이미지 층·빌드 캐시·다른 태그 이미지에 비밀값이 남아 있을 수 있다. 바꿀지, 옛 이미지·빌드 캐시를 지울지 정하신 적이 없어 **하지 않았다**(Task 0 Step 8).
8. **분위기 태그 되채우기는 안 했다.** 새 규칙은 새로 분석하거나 사람이 검토할 때만 적용된다. 이미 저장된 문장 조각 태그는 그대로고 화면 `isChipTag`가 가린다. 새 분석으로 실화면을 재 보지 못했다(분석 한 번에 수 분).
9. **유진 "이름 바꾸기" 의도·적용기·안내문은 묶음 F다**(이 계획 밖). 화면에 연 기능이라 유진 배선이 빠진 상태다(CLAUDE.md "화면에 열면 유진도")는 점을 알고 넘긴다.
10. **깨진 이름이 생긴 원인은 안 고쳤다.** 넣는 쪽 경로를 확인하지 못했다(추정: 윈도우 도구가 multipart 파일 이름을 cp949로 보냄). 복구 스크립트는 이미 들어온 24개만 고쳤고, 같은 일이 다시 생길 수 있다.
11. **디렉터 후보 순위**(`media_ranking.rank_candidates`)는 `analysis_phrases`를 읽지 않는다. 그 길의 자산 모양은 확인하지 않았다.
12. **더빙 401 안내문**("바탕화면 아이콘을 다시 실행")은 토큰이 바뀐 채 옛 다리가 떠 있는 경우는 못 고친다. 그때는 다리를 끄고 다시 켜야 한다. 또 다리 코드가 바뀌면 떠 있는 다리를 손으로 꺼야 한다(`owner-ready`는 포트가 열려 있으면 다시 띄우지 않는다).
13. **이월한 사소한 것들(장부 `minor (deferred)`)**:
    - T0: 브라우저 화면 확인 없이 HTTP 200만 봤다.
    - T1: `CreationInterview` '이전 질문' 시험은 부하에서 흔들린다(단독 재실행 시 통과 확인).
    - T2: `read_env_file_value`는 `OSError`만 잡는다(UTF-16 `.env.container`면 트레이스백, 닫힌 채 실패). 같은 키가 둘이면 첫 줄을 읽는데 compose는 마지막을 읽는다.
    - T3: capcut/infographic 클라이언트에 "토큰 없으면 헤더 없음" 시험이 없다. capcut/infographic 401은 창작자 말 변환이 없다.
    - T4: 토큰 쓰기의 `finally`가 `Replace` 중간 실패 시 `.tmp-*.bak`을 안 지운다(옛 비밀값이 bak에 남을 수 있음). `Replace` 실패 시험 없음. 비-UTF-8 시험이 실패 사유를 단정하지 않는다.
    - T5: `<style>/*<!--*/</style>` 오탐 가능. `_NEVER_NEEDED_TAGS` 끝의 `,}` 서식.
    - T6: `max_length`가 strip 전에 적용. C1/U+2028 제어문자 미거절. 검증이 pydantic에만 있음(묶음 F에서 재검토). API 수준 builtin 409 시험 없음. `KeyError`→500 경쟁(`set_favorite`과 동일).
    - T7: `saveName`에 바쁨 방지 없음. 저장 실패 뒤 포커스 소실. 새 제목 단정 없음. 선택 바뀔 때 `setRenaming` 경쟁. (화면 확인은 Part A Step 7에서 했다.)
    - T8: `--undo`가 나중의 손 이름 바꾸기를 덮어쓸 수 있음(현재==after 검사 없음). 붙어 있는 악센트 글자 약 1134쌍은 모호(미리보기 우선으로 완화). 드문 cp949 확장 음절 4개 미복구. 되돌림 파일 형식 검사 없음.
    - T9: `recommenders.py:103`의 `.get('analysis_phrases', [])`에 None 방어 없음. 두 번째 분석에서 사용자 태그가 보존되는지 시험이 없다.
14. **Part A 중 일어난 일(영향 없음)**: 이름 바꾸기 확인 중 클릭이 레이아웃 이동으로 `구간 정리하기` 링크에 가서 /footage로 이동했고 거기에 ` 확인`+Enter를 쳤다. 서버를 확인했으니 이름 바꿈·변경은 없었다.

## 내가 내린 판단 (장부 `Ruling:` 전부)

| 판단 | 틀렸을 때 비용 |
|---|---|
| 작업은 worktree가 아니라 main에서 한다 (CLAUDE.md §3) | 없음. 커밋이 작고 되돌릴 수 있다 |
| 비밀값 교체(Task 0 언급, master §4)는 owner 결정이라 구현자에게 시키지 않는다. 옛 이미지도 지우지 않는다 | 대표님이 정하실 때까지 옛 이미지 층에 비밀값이 남는다 |
| Task 2~4 → Task 10 Step 4는 한 번에 이어서 하고, 푸시는 Task 10 뒤에 한다 | (계획 제약) 다리 재시작 사이에 토큰이 안 맞는 구간 |
| Task 5: 계획의 정규식 태그 매처를 속성 수준 `html.parser` 순회로 바꾼다 (리뷰어가 우회 3건 확인) | 코드가 계획보다 크고 오탐이 늘 수 있다(닫힌 쪽으로 실패, 재시도 문구 있음) |
| Task 5 2라운드: 건별 땜질을 멈추고 인포그래픽이 안 쓰는 구조를 통째로 막는다(noscript, `<![`, `--!>`, iframe/object/embed/meta/base/link, style 든 svg/math, 이미지 아닌 `data:`) | 드물게 정상 입력을 거절. 재시도 문구가 있다 |
| Task 5: 3라운드가 깨끗하면 이 계획 안에서 허용 목록으로 재설계하지 않는다. 재설계는 owner/인계로 보류 | 이국적 파서 차이 입력이 문지기를 통과할 수 있다 |
| Task 5 보류: Chrome-대-HTMLParser 차이(foster parenting, svg/math 통합 지점, template/frameset, `<?pi>`)는 진짜지만 미룬다. 문지기는 로컬 LLM 출력에 대한 겹방어다 | 위와 같음 |

## 재사용 게이트 (§8.3)

재사용한 것은 `/favorite` 라우트·`set_favorite` 패턴, `new-hermes-yujin-secrets.ps1`의 "없을 때만·값 안 찍기" 규칙, 다리의 판단/껍데기 분리다. 새로 만든 것은 문지기 하나(`host_bridge_guard`)와 헤더 함수 하나(`bridge_request_headers`)다. 뺀 것은 CSP 주입(측정 스크립트를 막는다)과 시작 스크립트 셋 수정(파이썬 한 곳에서 읽는다)이다. 경계: 팔레트·네트워크 경계·사람 게이트는 그대로다.

## 결정 필요 (대표님)

1. `.env.container` 비밀값 교체 여부.
2. 옛 VideoBox 이미지·빌드 캐시 정리 여부.
3. 인포그래픽 제한 시간(`VIDEOBOX_INFOGRAPHIC_TIMEOUT_SECONDS`)을 올릴지, GPU가 한가할 때 다시 시험할지.
4. Task 5 문지기를 허용 목록으로 재설계할지.
5. `seroval` 치명 경고(`@tanstack/react-router`) 처리 시점.

둘(1·2)은 승인 전에는 하지 않았다.

## 시험 결과 (Part B, 2026-10-08, 혼자 돌림)

- 파이썬 전체(`--ignore=tests/test_mcp_server.py`): **5353 통과, 56 건너뜀, 1 xfail, 실패 0** (41분58초). 알려진 `test_smoke_timeout_kills_the_child_tree...`도 이번엔 통과했다(기계 상태에 따라 흔들리는 시험).
- vitest: **145개 파일 / 1804건 전부 통과**. 알려진 editor-workbench 'gives the material dock back' 시험도 이번엔 통과했다.
- 빌드: 성공(500kB 넘는 청크 경고는 기존).
- `npm audit --omit=dev`: **치명 1건** — `seroval <=1.6.2`(`@tanstack/react-router` 경유). 이 묶음 이전부터 있던 것, 범위 밖이라 고치지 않았다. `npm audit fix`로 고칠 수 있다고 나오지만 의존성 갱신이라 따로 다룬다.
- 로그: 작업 장부 폴더의 `task-10b-pytest.log`, `task-10b-vitest.log`.

## 마감 후 추가 (전체 최종 리뷰 뒤 수정, 2026-10-08)

최종 리뷰가 찾은 것 중 셋을 같은 날 고쳤다(커밋 24029dfa6 · 83aed320f · 2010b9761).

- 인포그래픽 거절기가 `<meta name="viewport" content=…>`까지 막던 문제: `http-equiv`가 있는 meta만 거절한다. 거절되면 재시도 문구가 걸린 구성요소 이름을 알려 준다. 실제 모델 출력으로는 아직 못 재 봤다(위 "안 한 것" 1번 그대로).
- `--undo`가 나중에 손으로 바꾼 이름을 덮어쓰던 문제: 지금 이름이 `after`와 다르면 건너뛰고 알린다(`--force-undo`로 덮어쓰기).
- 화면 이름 바꾸기 검사를 서버 규칙(`.`·`..`·제어 문자·255자)과 맞췄다.

**아직 남은 것 (후속 묶음 몫)**
- 다리가 이미 떠 있는 채로 토큰이 어긋나면 아무것도 알려 주지 않는다. `owner-ready.ps1`이 포트가 열려 있으면 "준비됨"으로 본다. 열려 있는 다리에 토큰으로 한 번 물어 보고 어긋나면 "다리를 껐다 켜세요"를 알려야 한다. 캡컷·인포그래픽 401에는 쉬운 말 안내도 없다.
- 검증(이름 규칙)이 pydantic에만 있다. 묶음 F에서 유진에게 이름 바꾸기를 열기 전에 `rename_asset`(저장소)로 옮긴다.
- 직접 띄운 호스트 API는 토큰을 못 받는다(컨테이너 환경변수만 읽음). `-EnvFile`을 바꾸면 다리가 읽는 파일과 갈라진다.
- 이미 "구간 정리"된 조각은 옛 깨진 이름을 `library_footage_sources.filename`에 복사해 갖고 있다(이름 바꾸기·복구가 거기까지 안 닿는다).
- 읽는 쪽 `videobox_core_engine/mojibake.py` 규칙이 Task 8의 엄격한 규칙과 갈라져 있다(`Àla`→`픩a` 오탐이 읽기 길에는 남음).
- 인포그래픽 거절기를 허용목록(allowlist) 방식으로 바꾸는 일(남은 파서 차이 + 오탐을 같이 해결).
