# VideoBox MCP 범위 정의서 (2026-09-07 다시 씀)

> **이 문서는 2026-06-27 판을 대체한다.** 옛 판은 그대로 두지 않고 여기서 갈아
> 끼웠다 -- 두 벌을 두면 한 벌이 조용히 낡고, 그 일이 실제로 일어났기 때문이다.

## 0. 왜 다시 쓰는가 — 낡은 문서가 사람을 틀리게 했다

2026-09-07에 옆 저장소의 에이전트가 이 문서를 성실히 읽고 MCP 구현 계획을 세웠다.
**그 계획은 여러 군데가 틀렸고, 틀린 이유는 전부 이 문서였다.**

옛 판은 2026-06-27에 쓰였고 그 뒤로 **950커밋**이 지났다. 그동안 편집 세션,
유진 편집 적용, 자료실, 동영상 번역기, 인포그래픽이 통째로 생겼다. 문서는
그대로였다.

가장 위험했던 것: 그 계획은 "PNG는 자동 B-roll 후보가 아니다"를 전제로 삼았다.
**2026-09-06에 정확히 그 반대로 고쳤다** -- 사진이 유진 후보에 영원히 못 들어가던
것이 결함이었다(`director_proposal_service.py:95`). 옛 전제대로 만들었으면 어제
고친 버그를 다시 넣는 셈이었다.

**교훈은 문서 관리가 아니라 설계다.** 이 문서는 이제 **구체적인 도구 이름 목록을
진실의 근거로 삼지 않는다.** 도구는 실제 라우터에서 나오고, 여기서는 그 도구가
지켜야 할 **경계와 모양**만 정한다. 목록은 낡지만 경계는 덜 낡는다.

## 1. 그대로 두는 원칙 넷

옛 판의 §2·§8·§9·§10은 지금도 맞다. 요약해 옮긴다.

1. **VideoBox는 독립 제품이다.** 에이전트가 없어도 대표님이 화면에서 처음부터
   끝까지 만들 수 있어야 한다. MCP는 필수 런타임이 아니라 **외부 호출자**다.
2. **MCP는 제어면이다.** 무거운 처리를 MCP가 하지 않는다. 요청하고 상태를 묻는다.
3. **MCP → API → Core 순서를 지킨다.** core engine을 MCP가 직접 import하지 않는다.
   화면과 에이전트가 같은 문을 쓰게 하려는 것이고, 그래야 한쪽만 조용히 달라지지
   않는다.
4. **큰 바이너리를 들고 다니지 않는다.** `project_id`·`job_id`·`library_asset_id`·
   참조 URL만 돌려준다. 실제 파일은 VideoBox 저장소에 둔다.

## 1.1 폐기하는 원칙 하나

옛 §13.3은 "타임라인 세부 수정은 MCP보다 operator dashboard에 맡긴다"고 했다.
**이건 이제 제품과 어긋난다** -- 2026-09-01 승인으로 유진에게 말하면 편집이 바로
적용된다(`decisions/2026-09-01-yujin-chat-applies-edits-directly.ko.md`).

다만 결론은 우연히 같다. **MCP는 타임라인 세부 편집을 노출하지 않는다.** 이유가
달라졌을 뿐이다: 대시보드에 맡겨서가 아니라, **그 일은 이미 유진이 프로젝트 안에서
더 잘 하기 때문이다.** 밖에서 조각마다 지시하는 것은 유진을 우회하면서 더 나쁜
결과를 얻는 길이다.

## 2. 재고 나온 가장 중요한 사실 — 문이 고르지 않다

2026-09-07에 라우터 서른 개를 전수 조사했다. **이것이 이 문서에서 제일 중요한
부분이다.**

- 비동기 작업 방식이 **다섯 가지**다: DB 잡 행 + 데몬 스레드 / FastAPI
  `BackgroundTasks` / 메모리 딕셔너리 / SQLite claim 큐 / SSE 스트림.
- 상태를 묻는 주소 모양이 **열세 가지**다(`/jobs/transcription/{id}`,
  `/timelines/{id}`, `/final-renders/{id}`, `/exact-previews/{id}`,
  `/scene-videos/{id}`, `/capcut-draft-exports/{id}`, `.../dubbing/{id}` …).
  **`GET /api/jobs/{job_id}` 같은 공통 문은 없다.**
- 오래 걸리는데 **잡이 아예 없는** 문이 다섯이다: 장면 그림, 대본 초안,
  인포그래픽, 자동 컷 검출, 유진 대화 한 턴. 부르면 몇 분 동안 그냥 막힌다.

**그래서 도구를 라우트에 1:1로 얹으면 안 된다.** 그렇게 만들면 부르는 에이전트가
열세 가지 폴링 규칙과 다섯 가지 실패 모양을 다 알아야 한다. 그건 얇은 껍데기가
아니라 복잡함을 떠넘기는 것이다.

**MCP는 잡을 한 가지 모양으로 덮는다.** 시작하는 도구는 `{job_id, kind}`를 주고,
`videobox.job_status(job_id)` 하나가 모든 종류를 답한다. 안쪽에서 종류별 주소로
나눠 묻는 것은 MCP의 몫이다. 이건 "새 비즈니스 로직"이 아니라 **주소 대응표**다.

> **정해졌고 만들었다 (owner 결정 2026-09-07): `GET /api/projects/{id}/jobs/{job_id}`.**
> 대응표를 MCP에 두지 않고 문을 열었다 -- 화면도 같은 문을 쓸 수 있기 때문이다.
>
> **프로젝트를 함께 받는다.** 잡 id는 프로젝트 안에서만 유일하고
> (`transcription_job_001` 꼴), 로컬 저장소는 프로젝트마다 sqlite 파일이 따로라
> id만으로 찾으려면 전부 훑어야 한다. 부르는 쪽은 프로젝트를 늘 알고 있다.
>
> **여기서 못 보는 것을 분명히 해 둔다.** `jobs` 표에 행을 남기는 열네 가지만
> 보인다(`JobType`). 더빙·유튜브 학습은 메모리에만 있고, 유진 실행은 SSE로
> 흐르며, 장면 그림·대본 초안·인포그래픽·자동 컷은 잡 없이 요청 안에서 끝난다.
> 그 종류를 물으면 404가 나가는데 **그건 정직한 답이다** -- 없는 것을 있는 척하지
> 않는다. 그 넷을 잡으로 바꿀지는 별도 결정이다.

## 3. 노출하는 도구 — 다섯 묶음

이름은 실제 라우트에서 나온다. 아래 표의 라우트가 **없어지면 도구도 없앤다.**

### 3.1 프로젝트 (먼저)

| 도구 | 감싸는 문 |
|---|---|
| `create_project` | POST `/api/projects` |
| `list_projects` | GET `/api/projects` |
| `get_project` | GET `/api/projects/{id}` + GET `/api/projects/{id}/home-summary` |

### 3.2 자산 넣기 (다음)

| 도구 | 감싸는 문 |
|---|---|
| `register_project_asset` | POST `/api/projects/{id}/assets/{narration-audio,script-document,broll-video,raw-video,sfx,voice-sample}` — **경로를 받는다**. 다만 아래 상자를 먼저 읽어라 |
| `list_project_assets` | **공통 문이 없다.** 타입별 GET 셋을 합치거나(`assets.py:110/198/295`) 문을 하나 연다. 착수 전에 정한다. |
| `ingest_library_asset` | POST `/api/library/ingest-path` — **경로를 받는다**(2026-09-07에 열었다). 바이트를 올릴 거면 기존 `POST /api/library/ingest`(multipart) |
| `search_library` | GET `/api/library/search` |

> **여기에 풀리지 않은 긴장이 하나 있다.** `docs/2026-08-24-unowned-web-api-methods.ko.md`는
> `registerNarrationAudio`·`registerScriptDocument`를 **"지울 것"**으로 분류했다 --
> 이유는 "화면 파일 입력은 업로드 경로를 쓴다. 호스트 `source_path`를 받는 등록
> 래퍼는 화면 경계와 맞지 않는다"였다.
>
> 그 판단은 **화면만 생각했을 때** 옳다. 그런데 지금은 화면이 아닌 호출자가
> 생겼고, 그쪽에는 경로가 정확히 필요한 것이다. **둘 중 하나를 골라야 한다:**
> 그 래퍼들을 "밖에서 부르는 문"으로 다시 자리매김하거나, MCP도 바이트를 올리게
> 하거나. **지금 고르지 않으면 한쪽이 다른 쪽을 모른 채 지운다.**

### 3.3 시키고 묻기 (다음)

| 도구 | 감싸는 문 |
|---|---|
| `start_transcription` | POST `/api/projects/{id}/jobs/transcription` |
| `start_segment_analysis` | POST `/api/projects/{id}/jobs/segment-analysis` |
| `start_broll_recommendation` | POST `/api/projects/{id}/jobs/broll-recommendation` |
| `start_music_recommendation` | POST `/api/projects/{id}/jobs/music-recommendation` |
| `job_status` | **§2의 공통 문.** 위 넷과 아래 렌더를 다 덮는다 |

### 3.4 타임라인 (다음)

| 도구 | 감싸는 문 |
|---|---|
| `build_timeline` | POST `/api/projects/{id}/jobs/build-timeline` |
| `get_timeline` | GET `/api/projects/{id}/timelines/{job_id}` |

**타임라인 조각 편집은 노출하지 않는다** (§1.1). 편집 세션 라우트는 마흔 개가
넘고, 그 일은 유진이 프로젝트 안에서 한다.

### 3.5 결과물 (마지막)

| 도구 | 감싸는 문 |
|---|---|
| `start_preview_render` | POST `.../editing-sessions/{sid}/exact-preview` — **`/jobs/preview-render`가 아니다**(아래 상자) |
| `get_render_reference` | GET `/api/projects/{id}/final-renders/{job_id}` — **참조만, 바이트는 안 준다** |
| `export_capcut_draft` | POST `/api/projects/{id}/jobs/capcut-draft-export` — **`capcut-export`가 아니다**(아래 상자) |

> **제 초안도 여기서 한 번 틀렸다.** 처음엔 `/jobs/preview-render`를 적었는데,
> 그 문은 `capcut-export`와 **같은 이유로 화면에서 이미 거둔 것**이다 --
> `task22-parity-owners.test.ts:212`가 두 주소를 화면 모듈 그래프에서 아예 금지하고
> 있다. 옛 판이 그 둘을 대표 도구로 적어 둔 것이 사람을 그리로 끌었고, 나도 끌렸다.
>
> **다만 그 두 백엔드 문이 죽은 것은 아니다.** `capcut-export`는 `tests/test_api.py`
> 한 파일에서만 35군데가 부르고, 읽기 짝(`getExport`)은 옛 자료 호환을 위해
> **의도적으로 남겨 둔 것**이라 `docs/2026-08-24-unowned-web-api-methods.ko.md`가
> 백엔드 삭제를 명시적으로 승인하지 않는다. **화면에서만 거둔 것이지 지운 것이
> 아니다** -- 지우려 들면 안 된다.

**`start_final_render`는 이 목록에 없다.** 완성본 렌더는 검토 승인을 전제로 하고
(`outputs.py:180`), 승인은 사람 몫이다(§4).

## 4. 절대 만들지 않는 도구

**되돌릴 수 없는 것.** 실물 조사에서 나온 것을 그대로 적는다.

- `DELETE /api/projects/{id}` — 프로젝트를 지운다
- `DELETE /api/library/assets/{id}/permanent` — DB 행과 **디스크의 파일**을 지운다
- `DELETE .../assets/voice-sample/{id}` — 대표님이 직접 녹음한 목소리다
- `DELETE .../memory-candidates/{id}/stored-memory` — 유진의 기억을 지운다
- `DELETE .../director/conversations/{id}`, `DELETE /api/format-templates/{id}`

**사람이 서야 하는 자리.**

- `POST .../review-approvals/{job_id}/approve` — **완성본 렌더를 여는 문이다.**
  에이전트가 자기 작업을 스스로 승인하면 사람 게이트가 있으나 마나 하다.
- `POST .../memory-candidates/{id}/approve` / `store` — 대표님에 관한 사실을
  영구히 적는 일이다.
- `POST .../final-renders/{job_id}/share` — **누구나 볼 수 있는 주소를 만든다**
  (`preview_shares.py:44/51`은 토큰만으로 열린다). 밖으로 내보내는 결정은 사람 몫이다.

**한 번에 전면 적용하는 것.** 옛 판의 `apply_tts_to_entire_project` 금지는 그대로
유효하고, 지금은 짝이 더 있다 -- `POST .../director/proposals/{pid}/batch-apply`.
되돌릴 수 없는 것을 한 번에 거는 도구는 사고의 모양이다.

**자격증명은 도구 인자로 받지 않는다.**

## 5. 밖에서 부를 사람(AK-System)을 위한 세 가지 — 실측 결과

옆 저장소의 AI 직원 시스템이 이 MCP를 부를 예정이다. 그쪽이 요구한 셋을 실제로
재 봤다.

**① 자산 등록이 경로를 받는가 — 이제 맞다 (2026-09-07에 열었다).**
프로젝트 자산 일곱 문은 원래 JSON 본문에 `source_path`를 받았고(`models.py:380`),
자료실만 multipart 전용이었다. `POST /api/library/ingest-path`를 열어 맞췄다
(owner 결정).

**아무 경로나 받지는 않는다.** 받아 줄 폴더는 **드롭 폴더와 자료실 관리 폴더
둘뿐**이다. 자료 폴더 전체를 열면 자료실이 임의 파일 읽기 창구가 된다.
**설정이 비면 아무것도 안 받는다** -- 캡컷 다리의 같은 도우미는 기본값이 반대인데
(손으로 켜는 서비스라 그렇다), 밖에서 부르는 문은 닫힌 채로 있어야 한다.

**열쇠는 필수다.** multipart 쪽은 없으면 만들어 주지만(사람이 화면에서 끌어다
놓는 자리라 그렇다), 이 문은 기계가 부르므로 없으면 거절한다 -- 없으면 재시도가
매번 새 자산을 만든다.

**② 경로가 컨테이너에서 보이는지 판정할 수 있는가 — 이제 그 문이 답한다.**
`POST /api/library/ingest-path`가 세 가지를 **갈라서** 답한다:

| 사실 | 답 |
|---|---|
| 컨테이너가 그 이름을 모른다(호스트 경로를 그대로 넘겼다) | 403 `source_path_not_visible` + **볼 수 있는 폴더 목록** |
| 볼 수 있는 자리인데 파일이 없다 | 404 `source_path_not_found` |
| 파일이 아니라 폴더다 | 422 `source_path_not_a_file` |

**둘을 같은 오류로 내면 부르는 쪽이 파일을 다시 만들며 헛돈다** -- 파일은 멀쩡히
있고 이름을 모를 뿐이다. 그래서 볼 수 있는 폴더를 같이 알려 준다. 안 알려 주면
어디에 둬야 할지 알 방법이 없다.

경로 대응표(`CapCutHostPathMap`, `host_paths.py:94`)는 여전히 **컨테이너→호스트**
방향이고 그대로 둔다. 이 문은 대응이 아니라 **울타리**라서 대응표가 필요 없다.

**③ 이미지가 오버레이 전용인가 — 아니다. 이 전제를 쓰면 안 된다.**
2026-09-06에 사진도 **B-roll 자리 후보**가 되도록 고쳤다:
`director_proposal_service.py:95`가 이미지를 시각 분석 요구에서 면제하고,
`:303`의 대응표가 `"image": "broll"`로 센다. 오버레이 경로는 **따로 있는 것이지
대체가 아니다.** 도구 응답에 그 구분을 드러내되, 사진을 B-roll에서 빼지 않는다.

**이름 주의.** 이 저장소의 유진은 AK-System의 직원과 다른 물건이다. identity·
볼트·자격증명·mem0 네임스페이스를 재사용하지 않는다
(`docs/superpowers/specs/2026-07-17-videobox-hermes-hybrid-runtime-design.md:144`).

## 5.1 방향이 뒤집혔다 — 옛 판이 그린 그림과 다르다

옛 판은 "Hermes가 MCP로 VideoBox를 부른다"고 그렸다. **실제로 만들어진 것은 그
반대다.** 유진(Hermes)은 VideoBox API **안에서** 게이트웨이를 통해 불린다
(`agent_gateway_client.py`, `routers/hermes_conversation.py:24`), 그리고 그
에이전트에게 허용된 동작은 **딱 둘**이다 -- `read_context`, `publish_proposal`
(`hermes_capabilities.py:15`). 도구 목록이 아니다.

**그래서 이 MCP는 옛 그림의 실현이 아니라 새 방향이다.** VideoBox가 처음으로
*불리는 쪽*이 된다. 그 사실을 분명히 해 둔다 -- "원래 계획대로 마저 만든다"고
생각하면 이미 있는 유진 경로와 뒤섞인다.

## 6. 착수 전에 정할 것 — 넷 중 둘은 정해졌다

지금 답이 없는 것을 적어 둔다. **모르는 채로 시작하면 또 낡은 전제로 만든다.**

1. ~~잡 상태를 공통 문으로 열 것인가~~ — **열었다**(§2).
2. ~~자료실 경로 등록 문을 열 것인가~~ — **열었다**(§5-①).
3. **`list_project_assets`를 위해 문을 하나 열 것인가**, 타입별 셋을 합칠 것인가.
   지금은 공통 문이 없다. **§3.1(프로젝트 넷)은 이 결정 없이 먼저 열었다**
   (2026-09-08, 아래 §9) -- 자산 도구는 이 결정이 나온 뒤에 잇는다.
4. **경로를 받는 등록 래퍼를 살릴 것인가 지울 것인가**(§3.2 상자) -- **owner가
   "유지"로 결정했다**(2026-09-08,
   `docs/handoffs/2026-09-08-owner-decided-followups-csrf-async-captions.ko.md` §4).

## 9. 착수함 (2026-09-08) — §3.1 프로젝트 + `job_status`

`services/mcp/src/videobox_mcp/`에 stdio 전송 MCP 서버를 세웠다. 도구 넷
(`create_project`·`list_projects`·`get_project`·`job_status`)이 전부
`VideoBoxApiClient`(httpx)로만 API를 부른다 -- core engine·storage는 한
줄도 import하지 않는다(`tests/test_mcp_server.py`가 AST로 강제).

**실제 stdio 서브프로세스로 살아 있는 컨테이너에 대고 확인했다**(§7의
완료 정의): 정상 1건(프로젝트 생성→조회)과 실패 1건(없는 프로젝트 조회
→ `is_error: true` + 이유 있는 오류 문구)을 둘 다 직접 불러서 봤다. 시험
프로젝트는 지웠다.

**공식 SDK(`mcp`, modelcontextprotocol.io, MIT)가 stdio만 쓰는데도
starlette/uvicorn을 FastAPI보다 새 버전으로 요구한다** -- `requirements-mcp.txt`에
그 버전들을 다시 못박아 뒀다(실제로 stdio 경로는 옛 버전으로도 동작하는
것을 확인했다). 아직 컨테이너 이미지에는 안 넣었다 -- 이 서버를 어디서
띄울지(호스트 프로세스 vs 컨테이너 안)는 별도 배치 결정이라 이번 슬라이스
범위 밖으로 남겨 뒀다.

다음: `list_project_assets` 결정(§6-3) 뒤 §3.2(자산 넣기), 이어서 §3.3
나머지(시작류 도구)·§3.4(타임라인)·§3.5(결과물).

## 7. 완료의 정의

`CLAUDE.md` §4를 그대로 적용한다. **API 단건 확인은 완료가 아니다.**

- 도구마다 **정상 1건 + 실패 1건**을 실제로 불러 확인한다.
- 실패는 **조용한 0이 아니라 이유가 있는 오류**로 나와야 한다. "결과 없음"과
  "못 읽었음"이 같은 응답이면 결함이다.
- 완료는 **클라이언트에서 실제로 그 도구를 써서 결과를 얻었는가**다.

## 8. 지금 있는 것 — 착각하지 마라

MCP transport 구현은 **하나도 없다.** `modelcontextprotocol`·`fastmcp`·
`stdio_server` 어느 것도 이 저장소에 없다.

있는 것은 정책 껍데기뿐이다: `McpPolicy`
(`yujin_agent_package_contract.py:232`)는 도구 이름 하나(`get_project_status`)만
선언하고 `invocation: None`을 강제한다. 기본값은 거부(`MCP_DEFAULT_DECISION = "deny"`)다.
`config/hermes/yujin/config.yaml:11`의 `mcp_servers`는 비어 있다.

**"기존 MCP 계층을 확장한다"는 계획은 없는 것을 확장하는 것이다.** 기본 거부는
그대로 두고, 도구를 늘릴 때마다 선언에 명시적으로 더한다.
