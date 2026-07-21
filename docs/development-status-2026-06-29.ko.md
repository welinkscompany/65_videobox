# VideoBox 개발 상태 점검 2026-06-29

> 현재 authoritative 상태/next slice 판단은 `## 283. 2026-07-21 exact preview publish fence remediation closeout`를 우선 적용한다. 그 외 날짜 기반 상태 섹션은 당시 시점 기록을 보존한 historical log다.

## 283. 2026-07-21 exact preview publish fence remediation closeout

- `[~] 기술 remediation·focused 검증 완료, 공식 checkbox/사람 gate 동결`: `b781540ca`→`e27049fba`와 후속 bounded publish fence는 final render가 base/override B-roll·BGM·SFX, export overlay 및 virtual narration segment가 실제로 읽는 `narration_source_uri` project asset을 모두 SHA/revision 스냅샷한다. legacy clip에 기존 identity 필드가 없어도 현재 byte identity를 잡고, source 바이트가 바뀌면 final output/preview를 publish하지 않는다. 논리 `local://…/assets/{asset_id}` URI는 asset ID/project 경계로, direct storage URI는 등록된 project asset 역매핑으로 검증하며 둘 다 아니면 fail-closed다.
- exact preview의 큰 source SHA 재검증과 완성 MP4 copy/staging은 SQLite `BEGIN IMMEDIATE` writer lock 밖에서 한다. publish transaction은 이미 계산된 결과, session CAS·size/mtime의 constant-time 재확인·atomic rename·DB pointer만 수행한다. 회귀는 2 MiB B-roll의 post-render SHA가 한 번임, 느린 rehash와 artifact copy 중 별도 editing-session revision write가 1초 안에 끝나 preview가 obsolete 되는 것을 함께 증명한다.
- fresh verification: affected runtime suite `172 passed`(기존 multipart PendingDeprecationWarning 1), exact local 10초·1280×720 fixture cold `549.4ms`(≤20초), warm cache lookup `243.6ms`(≤500ms). 이 slice에서 frontend production build와 전체 Python regression은 다시 실행하지 않았다. 특히 사용자가 앞서 중단한 full Python regression은 **미검증**이며 focused pass를 full-pass로 해석하지 않는다.
- Task 9의 실제 두 번째 scene MP4·current-revision 사람 승인·실제 CapCut Desktop 증빙과 Task 11의 두 번째 사용자 시각 승인은 계속 필요하다. 따라서 공식 checkbox/누적은 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.
- 다음 작업: 사람 승인 gate를 우회하지 않는다. 사용자가 Task 11 시안을 승인 또는 수정 요청하면 공식 Task 14 read-only timeline geometry/navigation을 시작한다. Hermes Dashboard/provider 설정은 별도 사용자 요청 전까지 보류한다.

## 282. 2026-07-21 Task 12·13 exact preview technical verification closeout

- `[~] 기술 구현·자동 검증 완료, 공식 checkbox/사람 gate 동결`: `c6890becd`→`82f11e106`은 canonical composition plan과 durable generation fence를 통해 full/selected-range exact MP4를 만들고, source/revision/fingerprint 변화에는 stale 처리·Range delivery 거부·late completion fence를 적용한다. `dd570bbea`는 그 manifest 상태를 읽어 current artifact 한 개만 player로 mount하고, pending/failed/stale에는 재생 대신 refresh recovery를 제공한다. source audition은 합성 편집본이라고 주장하지 않고 같은 player shell을 교체하며 autoplay하지 않는다.
- 실제 local acceptance fixture(10초, 1280×720, LocalPipelineRunner)는 cold `472.5ms`(기준 ≤20초), warm cache lookup `84.3ms`(기준 ≤500ms)로 두 성능 gate를 통과했다. temporary local store/asset fixture만 사용했으며 provider/Hermes, output approval, CapCut 또는 editing mutation은 실행하지 않았다.
- 검증: `.venv\Scripts\python.exe -m pytest -q tests/test_exact_preview_artifact.py tests/test_api_exact_preview.py tests/test_local_pipeline_final_render.py tests/test_ffmpeg_final_renderer.py tests/test_editing_session.py`는 `102 passed`(기존 multipart PendingDeprecationWarning 1)였다. real ffprobe fixture는 H.264/AAC/faststart, burned ASS, Range, PTS zero, gap/overlap·overlay/audio control과 stale fence를 포함한다. `npm --prefix apps/web run test`는 `37 files / 335 tests passed`, production build, provenance verifier, exact PreviewStage E2E `5 passed`, isolated responsive workbench E2E `8 passed`, `git diff --check`를 통과했다. build 500 kB 안내와 기존 React `act(...)`/JSDOM stderr는 비차단 기존 경고다.
- 전체 Python regression은 이번 slice에서 실행하지 않았다. 사용자가 앞서 중단한 full regression은 이 closeout에서도 **미검증**이며, focused `102 passed`를 full-pass로 확대 해석하지 않는다.
- Task 9 사람/환경 acceptance는 실제 두 번째 scene MP4, current-revision 합성 MP4에 대한 사용자 승인, 같은 revision의 실제 CapCut Desktop 등록·열기·import 증빙 전까지 열려 있다. Task 11의 두 번째 사용자 시각 승인도 `approval_required`다. 사용자 지시에 따라 공식 Task checkbox와 누적은 **9/22 (40.9%)**, 잔여 **59.1%**로 유지한다.
- 다음 작업: 먼저 사용자가 Task 11 다섯 viewport 시안을 승인 또는 수정 요청한다. 그 승인 기록 뒤에만 Task 14의 read-only timeline geometry/navigation으로 진행한다. Hermes Dashboard/provider 설정은 별도 사용자 요청 전까지 보류한다.

## 281. 2026-07-20 Task 11 read-only editor workbench technical closeout

- `[~] 기술 구현 완료, 사용자 시각 승인 대기`: `2096043e2`, `67e1efd8`, `a170b834`, `ffbd77be`가 canonical editor route를 manifest 단일 read → immutable `EditorViewModel`으로 연결하고, metadata-only dock·preview slot·timeline·responsive drawer를 추가했다. 실제 preview/audio/video, editor mutation, Director/media stateful adapter, renderer, provider/Hermes 호출은 추가하지 않았다.
- 실제 workbench 폭으로 density를 계산한다. 1600+는 preview 720px 이상일 때만 양쪽 dock, 1280–1599는 preview `max(640px, available width의 50%)` 이상인 한 dock, 그 미만은 focus-managed drawer다. route/session 변경의 이전 view 노출, blank session, drag resize persistence, sidebar 재진입 첫 paint, disabled Eugene local draft도 fail-closed 또는 browser-local state로 고정했다.
- 검증: TDD RED 후 frontend full `34 files / 315 tests passed`, production build, 8000 fake API와 분리된 `npm --prefix apps/web run test:e2e:editor-workbench` `8 passed`, artifact/provenance pytest `16 passed`(기존 multipart PendingDeprecationWarning 1), PowerShell provenance verifier, `git diff --check`를 통과했다. 독립 사양·품질 재리뷰은 Critical 0 / Important 0이며 후속 minor도 닫았다. build의 500 kB chunk 안내와 기존 React `act(...)` stderr는 비차단 기존 경고다.
- 다섯 deterministic screenshot과 manifest/승인 문서는 생성했지만 `approval.status=pending`/`approval_required`다. 사용자 두 번째 명시적 시각 승인 전에는 Task 11 checkbox와 누적을 바꾸지 않는다. Task 9 사람/환경 acceptance도 별도 gate로 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.
- 다음 작업: Hermes Dashboard/provider 설정은 사용자가 요청할 때까지 보류한다. 사용자가 1920/1440/1280/768/390 작업판 시안을 명시 승인 또는 수정 요청한 뒤, 승인 기록만 갱신한다. 그 뒤 공식 Task 12 revision-bound exact FFmpeg proxy preview를 별도 TDD slice로 시작한다.

## 280. 2026-07-20 Platform-only Hermes source cleanup closeout

- `[x] 완료 (source/Compose contract)`: `a5f8fd2`에서 custom Hermes runtime·seed Compose 서비스 3개, 전용 network 2개와 model volume, 전용 Docker/assets, bootstrap/verifier source를 삭제했다. 공식 `videobox-hermes-dashboard`의 pinned image, loopback `127.0.0.1:9119`, OAuth state mount와 `videobox-hermes-provider-egress` 단일 network는 유지한다. 과거 종료 컨테이너는 사용자 소유 runtime artefact이므로 이 source cleanup에서 삭제하지 않았다.
- `[x] 완료 (review remediation)`: `b776820`은 OAuth bootstrap Compose image와 retained verifier의 digest를 일치시키고, 해당 불일치를 잡는 RED-first contract를 추가했다. OAuth bootstrap 설계는 Dashboard의 `Memory Provider → mem0 → Platform`과 사용자 직접 key 입력만 설명하도록 갱신했다. API key, memory 내용, OAuth/GPT 요청 또는 memory write 성공은 기록·주장하지 않았다.
- 검증: `.venv` focused Compose/Platform contract `8 passed`(기존 multipart PendingDeprecationWarning 1건), dummy process environment Compose config, 실제 Dashboard image/mount/network 경계와 HTTP `200`, 전체 Python `1324 passed, 20 skipped`, frontend production build가 통과했다. build의 500 kB chunk 안내는 기존 비차단 경고다. 독립 spec·quality review는 모두 Critical 0 / Important 0으로 재승인했다.
- Task 9 사람/환경 acceptance는 이 cleanup과 무관하다. 실제 두 번째 scene MP4, current-revision 합성 MP4의 영상·자막·소리·전환에 대한 사람 승인, 같은 revision의 실제 CapCut Desktop 등록·열기·import 증빙 전까지 누적은 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.
- 다음 작업: 사용자가 Dashboard UI에서 key를 직접 입력한 뒤 provider 연결 상태만 확인한다. 그 뒤에도 공식 편집기 다음 goal은 Task 9 수동 acceptance이며, asset/사람 gate를 자동화나 placeholder로 대체하지 않는다.

## 279. 2026-07-20 Hermes dashboard Platform Mem0 handoff

- `[~] 로컬 대시보드 기동`: `videobox-hermes-dashboard`는 공식 Hermes 최신 이미지 digest `sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787`로 `127.0.0.1:9119`에만 공개된다. 2026-07-20에 HTTP `200`과 `HERMES_DASHBOARD_READY` 로그를 확인했다.
- 대시보드는 VideoBox data/media/DB/API/internal/edge network와 분리되어 있고, `videobox-hermes-provider-egress`만 사용한다. local memory network `depends_on`은 없으며, 불필요한 로컬 모델 실행 artefact는 제거했다.
- Hermes Dashboard의 `Memory Provider → mem0 → Platform` 경로만 사용한다. Mem0 Platform API key 입력 및 provider 연결 성공은 사용자가 대시보드에서 수행할 다음 수동 단계이며, 아직 API key·memory write·GPT 요청 성공으로 주장하지 않는다.
- focused Compose/Hermes contract는 프로젝트 `.venv`에서 `14 passed`(기존 multipart PendingDeprecationWarning 1)였고, dummy environment Compose config, live local dashboard HTTP `200`, `git diff --check`를 확인했다. 전체 Python regression은 사용자 요청으로 종료해 **미검증**이다.
- Task 9 사람/환경 acceptance는 계속 별도이며 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다. Gemini provider call은 0을 유지한다.

## 277. 2026-07-20 Task 9 manual acceptance preflight

- `[!] BLOCKED (사람/자산 gate)`: 현재 `codex/videobox-container-compatibility`의 `29b2181e3`은 upstream과 같고 worktree는 clean이다. `B-roll Smoke Test`의 두 번째 장면(`script-2`, `5–10초`)에 쓸 실제 MP4는 현재 worktree와 `C:\Users\atgro\Videos` 범위에서 발견되지 않았다. 따라서 두 장면 readiness 재준비, current-revision 합성 MP4 생성·재생, CapCut handoff 등록/import는 시작하지 않았다. 임시 빈 장면이나 자동화 fake handoff를 증거로 쓰지 않았다.
- 환경 preflight만 실제로 확인했다. 대상 PC의 pre-existing CapCut Desktop executable `C:\Users\atgro\AppData\Local\CapCut\Apps\8.9.1.3802\CapCut.exe`(file version `8.9.1.3802`)를 실행해 홈 화면이 열렸다. 화면에 보인 기존 프로젝트는 현재 revision의 handoff가 아니므로 등록·열기·import 성공으로 기록하지 않는다.
- 사용자로부터 current-revision 영상, 자막, 소리, 장면 전환 각각의 명시 승인/거부도 아직 받지 않았다. external/Gemini provider call은 이 작업에서 0이다. Task 9은 계속 unchecked이며 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.
- 다음 행동: 사용자가 두 번째 장면에 쓸 실제 MP4를 VideoBox의 `B-roll Smoke Test` 자산으로 추가한다. 그 뒤 readiness를 재실행해 두 장면 후보를 확인하고, current-revision composited MP4를 재생한 뒤 영상·자막·소리·전환의 승인/거부를 기록한다. 마지막으로 같은 revision을 CapCut Desktop에 실제 등록·열고 import 결과를 기록한 뒤에만 Task 9 closeout 검증·진행률 갱신을 검토한다.

## 276. 2026-07-20 Yujin v3 prompt/soul/user-input audit closeout

- `[x] 완료 (static contract only)`: prompt/Soul/user input을 다시 대조했다. `yujin-prompt-v3`/`yujin-policy-v3`은 선택 project의 허용 상태 read, 편집 관련 질문, 실행 없는 제안을 분명히 구분하고 직접 편집 실행·승인·render/export·CapCut·memory·credential·다른 project를 막는다. Soul은 계속 `video_director_read_only`/`non_authorizing`이며 user preference는 `ko`, short action-oriented, memory opt-in `false`, scope `none`, retention `0`이다.
- user text는 별도 immutable untrusted data로만 envelope에 들어가며 profile/user preference를 수정할 수 없다. 대본·제목·타이틀·썸네일·추천 영상·영상 주제·커버 이미지·영상 설명·해시태그의 **생성·추천·제안·작성 의도**는 request와 candidate response 양쪽에서 거부한다. 공백·하이픈·전각 문자 표기도 NFKC와 구분자 제거 후 같은 deny set으로 판정한다. 단, 유튜브 쇼츠 편집이나 제목 카드 길이 조정처럼 제작이 아닌 편집 문맥은 실행 없는 제안으로 허용한다.
- TDD: 공백/기호/전각 우회와 system policy가 허용 skill과 충돌하던 RED, bare `제목`/`유튜브`의 편집 문맥 false-positive, `타이틀` 동의어 false-negative, 제목 후보·개수·짓기·고르기 의도, 한국어/영어 제목 카드 편집 예외를 확인한 뒤 최소 수정으로 보완했다. focused profile/package/gateway/approval/capability `130 passed` (기존 Starlette multipart warning 1), compileall, `git diff --check`, production Docker build, `--network none --read-only` import를 통과했고 독립 재검토는 `Critical 0 / Important 0`이다. 전체 Python suite는 64초 timeout으로 끝나 full-pass가 아니다.
- 다음 권장 작업은 Task 9 사람/환경 acceptance다. 두 번째 장면용 실제 MP4, current-revision 영상·자막·소리·전환에 대한 사용자 명시 승인, 대상 PC의 실제 CapCut Desktop handoff/import 결과가 모두 필요하다. 자동 smoke나 임시 빈 장면은 이를 대체하지 않으며 누적은 계속 **9/22 (40.9%)**다. external/Gemini provider call은 이 작업에서 0이다.

## 275. 2026-07-20 Yujin editing-only scope closeout

- `[x] 완료 (static contract only)`: 사용자 결정에 따라 VideoBox는 영상 편집·검수·CapCut 인계에 집중한다. 유진은 `yujin-prompt-v2`/`yujin-policy-v2`의 pinned profile과 갱신된 Agent Package manifest를 사용하며, 대본·제목·썸네일·추천 영상·영상 주제·커버 이미지·영상 설명·해시태그의 생성 또는 제안을 요청과 후보 응답 양쪽에서 `blocked`/fail-closed로 처리한다.
- 유진의 Soul은 계속 `video_director_read_only`/`non_authorizing`이고, user preference는 `ko`, short action-oriented, memory opt-in `false`, scope `none`, retention `0`이다. response-only skill 세 개와 declaration-only `get_project_status` 한 개만 남고, MCP 기본값은 deny다. provider, OAuth, Hermes MCP transport, DB/API route, memory storage, mutation/render/export, CapCut/host bridge는 이번 변경으로 시작하지 않았다.
- TDD: 정확한 제목·썸네일·추천 영상 표현의 RED 뒤, 독립 품질 리뷰가 발견한 영상 추천·주제·커버 이미지·설명·해시태그 우회 표현과 fixed system prompt 범위 누락을 다시 RED로 재현했다. 요청·응답 양방향 회귀와 versioned prompt/package manifest 재고정으로 보완했다.
- 검증: 관련 profile/package/gateway/approval/capability focused `111 passed` (기존 Starlette multipart PendingDeprecationWarning 1), compileall, `git diff --check`, 현재 worktree production Docker build, `--network none --read-only` container import 통과. 독립 재검토는 `Critical 0 / Important 0`이다. 전체 Python suite는 64초 timeout으로 끝나 full-pass/unverified가 아니다.
- Task 9 사람/환경 acceptance는 별도이며 누적은 계속 **9/22 (40.9%)**, 잔여 **59.1%**다. external/Gemini provider call은 이 작업에서 0이다.

## 274. 2026-07-20 agent foundation handoff

- 이번 시작 기준 브랜치 `codex/videobox-container-compatibility`의 HEAD와 `origin/codex/videobox-container-compatibility`는 동일한 `902e54a2e9bf4c8d878c08dcb77ed0a7771741bb`이며 worktree는 clean이었다.
- 이번 정적 Agent Foundation closeout에는 versioned Yujin profile/prompt (`1cc3d10`), static ToolSpec/Gateway (`e384ec4`), static redacted decision audit/retry (`eda1411`), static approval workflow (`ce341de`), Yujin Agent Package v1 (`019a9a6`)이 포함된다. Soul·user preference/consent·response-only skills·MCP default-deny는 manifest로 고정됐지만 실제 Hermes MCP transport, provider, OAuth, DB/API route, memory storage, render/mutation은 아직 없다.
- 최신 package-focused 검증은 `158 passed`, production workspace build와 `--network none --read-only` image import를 통과했다. Python 전체 suite는 반복해서 64초 timeout 뒤 pytest stdout `OSError`가 발생했으므로 full-pass로 주장하지 않는다.
- `[x] 완료 (static contract only, 2026-07-20)`: §23.2 issuer/revocation과 gateway-only split의 canonical static fail-closed contract를 추가했다. Compose declaration은 Python frozen contract와 field-by-field 일치해야 하며, issuance `false`, secret delivery/ordinary `/api/*` `forbidden`, named future gateway service/network absent, Hermes pre-auth `network_mode: none`을 확인한다. existing conditional status route의 durable consume/replay와 비교해 `LocalProjectStore.revoke_hermes_capability`는 storage primitive로만 기록하고 owner-authorized revoke writer는 `not_deployed`로 고정했다. default app의 capability/revoke/issue route 부재와 direct internal Hermes attachment 거부도 focused test로 확인했다.
- 검증: TDD RED 후 authority/status/Compose/profile/gateway focused `72 passed` (기존 multipart warning 1), dummy environment Compose config, production workspace build, `--network none --read-only` image import가 통과했다. Python full suite는 64초 timeout으로 끝나 full-pass로 주장하지 않는다. 독립 명세·품질 재검토는 P0/P1/P2 0이다.
- 계획 gap: owner-authorized revoke writer, signing secret delivery·rotation·key lifecycle, gateway audit, actual gateway service/route/network와 OAuth/provider 실행은 아직 없다. Hermes network, device-code OAuth, GPT/Qwen/Gemini call은 egress·text-only consent·request budget/audit gate 전까지 실행하지 않는다.
- Task 9 사람/환경 acceptance는 Agent Foundation closeout과 독립이다. 누적은 계속 **9/22 (40.9%)**, 잔여 **59.1%**다.

## 273. 2026-07-20 Yujin Agent Package v1 closeout

- `[x] 완료 (done)`: versioned Soul, user preference/consent, response-only skills, MCP default-deny manifest를 정적 package로 pin했다. memory opt-in은 false/scope none/retention 0이며 MCP는 declaration-only status read 하나 외 전부 deny다.
- package 경계는 Soul·user preference·skills·MCP policy의 canonical value와 exact type을 재검증해 constructor-bypass forged artifact를 거부한다. provider/Hermes/MCP transport/DB/API/UI/memory storage/mutation은 시작하지 않았고 Gemini call 0, Task 9은 9/22 (40.9%) 유지다.

## 272. 2026-07-20 static approval workflow closeout

- `[x] 완료 (done)`: immutable static proposal/approval-card/workflow preflight 계약을 추가했다. `네`는 approval이 아니고, card는 pinned prompt/no-skill manifests, project/conversation/run/proposal scope, revision, summary, rights blocker, expiry를 묶는다.
- reject·expire·stale·authority 부족과 기록된 approval 모두 executor 권한 0·side effect 0이며 applied transition은 이 slice에서 거부한다. provider/DB/API/mutation 없음, Gemini call 0, Task 9은 9/22 (40.9%) 유지다.

## 271. 2026-07-20 static gateway decision audit closeout

- `[x] 완료 (done)`: static decision audit/retry contract를 추가했다. backend-attested UUIDv4 correlation/idempotency/principal, fixed reason, profile/tool/request digest/no-result/principal hash/UTC time만 hash-bound event에 남기며 scope는 `in_memory_nonpersistent`다. raw prompt/media/credential/model claim은 기록하지 않는다.
- retry는 같은 principal·동일 input만 `replayed_nonexecuting`; 다른 input 또는 principal은 idempotency conflict로 끝나며 항상 executor 권한 0이다. 이는 durable ledger, signer, API route, provider runtime이 아니다. Gemini call은 0, Task 9은 9/22 (40.9%) 유지다.

## 270. 2026-07-20 static ToolSpec/Gateway contract closeout

- `[x] 완료 (done)`: `get_project_status` 하나의 pinned `tool-spec-v1`/`gateway-registry-v1` static contract를 추가했다. strict empty request/result schema, selected-project status redaction, context revision precondition, result 1,024 byte/1,000 ms cap, `read_only_research` phase를 manifest에 함께 묶었다.
- model tool/name/version/project/revision은 untrusted data다. exact scalar·empty-object 검증 뒤에도 backend-attested context/request와 대조하며, cross-project, revision mismatch, phase/byte/time 위반, direct public objects, hostile string comparison은 fail-closed다. `static_contract_accepted`도 실행 권한이 아니며 항상 `executor_authorized=false`다.
- private backend-adapter marker는 ordinary in-process application-contract guard이며 hostile in-process code security나 real capability signer가 아니다. provider/API route/tool executor/network/DB/UI/OAuth/mem0/mutation은 추가하지 않았고 Gemini call은 0이다. Task 9 누적은 계속 **9/22 (40.9%)**다.
- 검증: focused gateway/profile/evidence/harness/local-provider `150 passed`, independent spec/quality review P0/P1/P2 0, compileall/diff check, production image와 network-none/read-only reverse verification을 closeout 전에 실행한다.

## 269. 2026-07-20 Yujin versioned profile contract closeout

- `[x] 완료 (done)`: `yujin-video-director`의 첫 offline read-only profile contract를 추가했다. profile ID/version/policy/template/developer policy/context template/strict response schema/1,500 ms timeout은 literal manifest SHA-256과 exact built-in artifacts로 pin되어 self-consistent custom profile도 fail-closed로 거부한다. immutable registry와 prompt envelope은 `system → developer → task → user` 역할 순서를 고정한다.
- `[x] 완료 (done)`: context는 선택한 한 project의 allowlisted status 6개 field만 immutable digest와 함께 user data와 분리된 untrusted context data로 유지한다. 공개 envelope 생성도 key set·project binding·canonical digest를 재검증한다. raw path·secret·instruction·다른 project ID와 unsafe revision을 status model 단계에서 막는다. response는 4-way strict union, `action=null`, `needs_human_review`, `non_authorizing=true`만 허용하고 status-read capability는 선언일 뿐 실행하지 않는다. timeout·invalid structured response는 executor 없는 bounded `blocked` fallback이다. 사용자 입력의 한국어·영어 injection, approval/render/export/CapCut/memory/credential 및 cross-project 요청은 blocked지만 선택한 project ID의 정상 상태 언급은 허용한다.
- 독립 명세 재리뷰과 품질 재리뷰 모두 P0/P1/P2 0으로 닫았다. 리뷰에서 발견한 manifest self-consistency 우회, 한국어 injection/status reflection, schema union/revision-none/pattern mismatch, revision 안의 cross-project ID leakage, selected-project overblocking, 4-role registry/timeout gap, envelope context binding gap을 RED-first 회귀로 보완했다.
- 검증: profile/evidence/harness/local-provider focused `134 passed`, `compileall`, `git diff --check`, production workspace image build, `--network none --read-only` image import·`system → developer → task → user` envelope·선택 project context/status·cross-project blocked·timeout fallback 역방향 검증을 통과했다. 전체 Python suite는 `1275 tests collected`를 확인하고 최신 코드에서 다시 실행했지만 63초 timeout 뒤 pytest stdout `OSError`로 끝나 full-pass로 기록하지 않는다. Starlette multipart PendingDeprecationWarning 1건은 기존 비차단 경고다.
- 이 closeout은 provider/OAuth/Hermes bridge/tool executor/DB·API route/UI/mem0/편집·render·export를 시작하거나 활성화하지 않는다. Gemini provider call은 계속 0이다. Task 9 사람/환경 acceptance는 별도이며 누적은 계속 **9/22 (40.9%)**, 잔여 **59.1%**다.
- 다음은 profile을 실제 provider에 연결하는 일이 아니라, existing §23의 versioned ToolSpec/Gateway registry와 context filtering을 static·fail-closed contract로 좁게 고정하는 작업이다. capability signer, Hermes network, OAuth, real provider request는 해당 별도 gate 전까지 시작하지 않는다.

## 268. 2026-07-19 offline synthetic evidence intake closeout

- `[x] 완료 (done)`: 실제 provider call 없이 fixture-only owner-grant/intake preflight contract를 만들었다. grant는 opaque reference, fixed corpus SHA, exact synthetic provider/runtime, literal offline scope, UTC expiry 및 capture/token/latency budget을 묶는다. 이것은 real identity authentication·consent issuance·provider authorization이 아니며, 채팅의 긍정 문구도 grant가 아니다.
- `[x] 완료 (done)`: preflight는 capture/grant/expiry/budget/replay를 side effect `0`로 확인한다. accept는 prepared transaction journal과 crash-released OS advisory lock 아래에서 evidence append와 audit을 one-to-one으로 복구한다. ledger 또는 audit write 중단 뒤 fresh gateway retry는 prepared 시점의 grant validity와 original UTC audit time을 사용하며, 만료 뒤 새 승인으로 바꾸지 않는다.
- `[x] 완료 (done)`: 정상 writable path의 accepted와 denied는 redacted tamper-evident audit event를 남긴다. denied event는 evidence/budget을 소비하지 않으며, malformed raw capture/grant는 audit payload에 직렬화하지 않는다. lock/audit I/O 불가는 audit event를 억지로 만들지 않고 stable non-authorizing fail-closed로 끝난다. grant/owner는 unkeyed SHA-256 correlation hash만 기록하므로 confidentiality 보장이 아니며 sensitive ref를 이 offline fixture surface에 넣지 않는다. accepted-intake evidence sink와 accepted audit은 정확히 one-to-one으로 검증되고, marked sink mutation은 gateway private in-process writer capability에만 묶인다. 이 경계는 hostile code 보안이 아닌 application-contract bypass 방지이며, 일반 parent ledger는 pre-gate/offline test evidence라 intake sink를 우회하거나 막지 않는다.
- 검증: intake/evidence/harness focused `106 passed`, independent spec/quality/final review P0/P1/blocking P2 0, Windows에서 malformed concurrent deny 64개를 5회 반복해 audit 64/64 보존, `compileall`, `git diff --check`, production build와 `--network none --read-only` image import 통과. 기존 Starlette multipart PendingDeprecationWarning 1건은 비차단이다. full Python suite는 `1246 tests collected`까지 확인했지만 실행이 124초 timeout 및 종료 중 pytest stdout `OSError`로 끝나 full-pass로 기록하지 않는다.
- Gemini/GPT/Qwen provider call, Hermes bridge/container, OAuth, DB/API route/router activation, UI, mem0, Docker/Compose 변경은 시작하지 않았다. Gemini provider call은 0이다.
- 다음은 실제 provider 연결이 아니라, 유진의 versioned prompt/profile과 read-only 업무영역을 fixture replay와 injection-negative test로 고정하는 작업이다. 실제 OAuth/provider gateway는 그 별도 gate 뒤에만 판단한다.

## 267. 2026-07-19 offline provider evidence ledger closeout

- `[x] 완료 (done)`: 실제 provider 호출 없이 synthetic capture import contract를 구현했다. capture는 external SHA-256로 고정한 checked-in Korean corpus와 exact case identity, provider/runtime/model, canonical candidate payload digest, opaque reviewer attestation(점수·수정 시간·UTC)을 함께 묶는다. raw media/path, credential, tool, approval 데이터와 corpus/case/attestation/capture replay는 import 또는 append에서 fail-closed한다.
- `[x] 완료 (done)`: filesystem ledger는 application-contract 수준의 append-only hash chain과 write lock/atomic write로 record content·순서·중복 replay를 검증한다. write-once audit artifact는 당시 ordered record snapshot과 canonical report payload를 묶으며, 이후 정상 capture append가 과거 audit을 무효화하지 않는다. 서명 키·외부 앵커는 아직 없으므로 OS/adversary-proof immutable이라고 주장하지 않는다.
- `[x] 완료 (done)`: report decode는 scalar JSON type/finite/range를 strict하게 확인하고, 재생성 report와 persisted JSON을 canonical representation으로 비교한다. 따라서 rehashed라도 `1`과 `1.0`을 바꾼 type-spoof audit은 통과하지 않는다. 모든 report는 `needs_human_review`만 유지하며 route/권한을 활성화하지 않는다.
- 검증: evidence focused `28 passed`, harness/LM Studio/local provider 포함 focused `84 passed`, independent spec review와 quality review P0/P1/P2 0, `git diff --check` 통과. Starlette multipart PendingDeprecationWarning 1건은 기존 비차단 경고다.
- 실제 GPT/Qwen/Hermes/Gemini 호출, Hermes host bridge, OAuth, DB/API route, router activation은 시작하지 않았다. Gemini provider call은 0이다.
- 다음은 이 ledger로 실제 provider를 호출하는 일이 아니라, 기존 §23 gate가 허용된 뒤에만 실제 captured output을 import할 수 있는 owner-authorized evidence intake/consent·budget·gateway contract를 좁게 설계하는 것이다.

## 266. 2026-07-19 container snapshot/runtime and PostgreSQL recovery hardening

- verified immutable `snapshot/`과 writable `runtime/`을 분리했다. Compose API는 runtime만 write mount하고 snapshot은 `/videobox-snapshot:ro`로 mount한다. startup/importer/verifier 모두 manifest hash와 exact file set을 fail-closed로 확인한다.
- 기존 legacy flat copy가 runtime write로 hash mismatch이면 안전하게 거부하고 원본·legacy copy를 보존한다. 실제 컨테이너 운영은 원본에서 새 `65_videobox-container-data-v2` snapshot/runtime copy를 생성해 전환했다.
- PostgreSQL restart reconciliation은 copied SQLite가 아니라 PostgreSQL asset truth를 사용한다. concurrent creation brief/readiness/atomic draft는 한 durable winner를 재사용하도록 unique conflict를 정규화하고 PostgreSQL integration regression으로 검증했다.
- 최신 Compose runtime은 2 imported projects, snapshot 49 hashes, source preserved, internal API/PostgreSQL host-port 미공개, proxied current-revision MP4 `200 video/mp4`를 확인했다. focused suite `41 passed`, frontend production build, full Python suite `1164 passed, 3 skipped`가 통과했다.
- Hermes, GPT OAuth, mem0, Gemini provider call, OpenCut, host bridge, SaaS auth/billing은 여전히 구현하지 않았다. 다음 Hermes slice는 이 verified base 위에서 별도 설계/승인으로 시작한다.

## 265. 2026-07-19 container PostgreSQL shared-store isolation hardening

- PostgreSQL은 프로젝트별 SQLite 파일과 달리 하나의 공유 DB이므로, deterministic ID를 쓰는 project-owned table의 기존 SQLite SQL을 그대로 쓰면 다른 프로젝트 행이 섞일 수 있었다. 이를 인지한 뒤 타임라인·리뷰·편집 세션·export·transcript·분석·preview·subtitle·asset·segment·recommendation·job·TTS candidate·Gemini provider-key의 composite key와 query scope를 보완했다.
- 두 프로젝트가 같은 deterministic ID를 만들어도 서로의 timeline, editing session, export, asset, segment, recommendation, job, TTS candidate, provider-key를 읽거나 수정하거나 삭제하지 않는 PostgreSQL 통합 회귀를 추가했다. Gemini provider 호출은 하지 않았고 local persistence만 검증했다.
- 이전 단일-key import로 `progress-bar-live-test` timeline이 누락된 파생 PostgreSQL volume은 원본이 아닌 snapshot에서만 재생성했다. 재import 뒤 PostgreSQL에는 `b-roll-smoke-test` timeline 7개와 `progress-bar-live-test` timeline 1개가 존재한다.
- 최신 Compose 재build 뒤 verifier는 source preserved, snapshot hash 49개, project 2개, API/PostgreSQL host-port 미공개를 통과했다. `final_render_job_009/content`도 web proxy에서 `200 video/mp4`로 다시 확인했다. API의 user/media library root는 `/videobox-data/videobox-user-library`로 mount 안에 남는다.
- PostgreSQL 재import는 write 가능한 `/videobox-data`가 아니라 Compose가 read-only로 mount한 검증 snapshot `/videobox-snapshot`만 입력으로 사용한다.
- Task 9 사람/환경 acceptance와 CapCut Desktop evidence는 이 hardening으로 완료 처리하지 않는다. Hermes, GPT OAuth, mem0, OpenCut, host bridge, SaaS auth/billing은 계속 시작하지 않았다. Gemini provider call은 0이다.
- 최종 full suite와 closeout 전에는 모든 `LocalProjectStore` surface의 PostgreSQL parity를 완결했다고 주장하지 않는다. 다음 Hermes slice 전에는 별도 migration/recovery/concurrency audit를 다시 수행한다.

## 264. 2026-07-19 container PostgreSQL foundation

- 사용자의 명시 지시로 이전의 “host web/API/FFmpeg compatibility only” 경계를 PostgreSQL 포함 컨테이너 기반으로 확장했다. 이 변경은 Task 9 사람/환경 acceptance나 Hermes 구현을 완료 처리하지 않는다.
- Compose project는 `65_videobox`다. `videobox-web`만 `127.0.0.1:5173`에 공개하고, API/PostgreSQL은 `videobox-internal`에만 두었다. web은 edge+internal 두 네트워크를 사용해 loopback proxy만 제공한다.
- 원본 `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`는 변경하지 않았다. 새 `65_videobox-container-data`에 running SQLite를 read-only backup으로 snapshot했으며 49개 파일 hash 매니페스트로 검증한다.
- 실제 snapshot의 두 프로젝트를 internal PostgreSQL에 import했다. proxy `/api/projects`와 `b-roll-smoke-test`의 `final_render_job_009/content`는 `200 video/mp4`로 확인했다. verifier는 source preservation, 49개 snapshot hash, 2개 imported project, API/PostgreSQL host-port 미공개를 통과했다.
- PostgreSQL store는 새 project 생성·목록, snapshot import, 실제 playback path를 통합 검증했다. 전 편집 mutation/복구/concurrency PostgreSQL parity는 Hermes보다 먼저 끝낼 후속 hardening slice로 남긴다.
- external/Gemini provider call은 0이다. Hermes, GPT OAuth, mem0, OpenCut, host bridge, SaaS auth/billing은 아직 구현하지 않았다. mem0는 이후에도 Hermes 보조기억이며 VideoBox SSOT가 아니다.
- Task 9은 기존 사람/환경 acceptance 기록을 그대로 유지한다. 누적은 Task 9과 무관하게 기존 **9/22 (40.9%)**, 잔여 **59.1%**다.
- 검증은 container/PostgreSQL focused suite, renderer/playback suite, web production build, Docker runtime verifier까지 통과했다. Python full suite 첫 실행은 `1129 passed, 7 skipped, 4 failed`; source-audio expectation 2건은 바로 수정·focused green으로 재확인했고, 남은 editor UI source-provenance hash drift 2건은 이번 container diff와 무관한 기존 registry mismatch다. 전면 rerun 전에는 full green이라고 주장하지 않는다.

> 현재 authoritative 상태/next slice 판단은 `## 263. 2026-07-18 OSS Slice 2/3 commit and creator-flow recovery handoff`를 우선 적용한다. 그 외 날짜 기반 상태 섹션은 당시 시점 기록을 보존한 historical log다.

## 263. 2026-07-18 OSS Slice 2/3 commit and creator-flow recovery handoff

- 이번 closeout은 Task 9의 atomic draft bundle·current-revision playback 기술 구현, Task 10의 editor playback manifest/typed command boundary, 그리고 현장 제작 흐름에서 재현된 질문 답변 누수·이전 질문·빈 요약·재생 불가 B-roll 후보·누락 장면 차단 회귀를 함께 기록한다. 이 변경은 서로 겹친 파일이 있어 실제 범위를 왜곡해 분리하지 않고 한 커밋으로 보존한다.
- 제작 readiness는 로컬 `ffprobe`로 재생 가능한 영상 스트림과 양수 길이를 확인한 B-roll만 후보로 고른다. 장면당 후보는 최대 하나이며 구간은 유효 범위만 허용한다. 기존 readiness도 원본 SHA가 같을 때만 안전하게 정규화한다. 후보가 장면 수보다 적으면 누락 장면을 gap으로 기록해 일반 초안 생성을 막고, 사용자가 명시적으로 허용한 placeholder만 예외로 둔다.
- 현장 데이터 `b-roll-smoke-test` 역방향 확인: `Preview Test Clip`(34초)만 `script-1`의 `0–5초` 후보이고, `script-2`의 `5–10초`는 `needs_assets` gap이다. 가짜 0초 MP4와 역전된 구간은 더 이상 API 응답에 없다. 이것은 실제 완성 영상 승인이나 CapCut Desktop import 승인과 다르다.
- Task 9은 계속 unchecked다. 사용자가 실제 current-revision MP4를 재생·승인하고 대상 PC에서 실제 CapCut Desktop handoff 등록/열기/import를 확인하기 전에는 누적을 올리지 않는다. Task 10은 완료로 유지한다. 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.
- 이번 commit 직전 fresh 검증은 Python 전체 suite, frontend 전체 suite, production build, loopback-only Playwright, `git diff --check`로 다시 수행한다. external/Gemini provider call은 0이며 Hermes/container, OpenCut runtime, SaaS auth/billing은 시작하지 않았다.


## 262. 2026-07-18 OSS Slice 3 Task 10 closeout

- Task 10은 project/session/revision에 고정된 authoritative editor playback manifest를 만들었다. API의 시간 기준은 seconds이고 FPS는 `fps_num/fps_den` rational로 보존한다. frame 변환은 지정된 한 지점에서만 half-up을 적용하며, project/session/revision provenance, output geometry, typed track/clip/control, caption style, gap, source SHA/media revision과 current/stale 상태를 함께 전달한다.
- 재생 URL은 project-scoped path containment, 교차 프로젝트 404, Range `206`/invalid `416`, MIME과 `nosniff` 계약을 통과한 delivery만 사용한다. source audition은 exact/current preview 상태와 별도이며, stale artifact를 current playback으로 표시하지 않는다.
- frontend는 raw session/timeline DTO나 generic trim mutation 대신 typed `EditorViewModel`과 role별 `EditorCommandPort`만 사용한다. narration split/merge/bounds/reorder, B-roll/BGM/SFX의 apply/clear/update-media-controls, 지원된 overlay apply/clear, caption text/style만 노출한다. pinned `/projects/$projectId/editor?session_id=` boundary는 해당 manifest와 expected revision을 사용하며 manifest/port 실패 시 raw mutation fallback 없이 안전하게 막는다.
- 검증: Task 10 focused/backend manifest·delivery·atomic 호환 suite `37 passed`, frontend full `28 files / 290 tests passed`, loopback-only Playwright `13 passed`, production build, provenance/UI-system verifier와 provenance pytest `14 passed`, `git diff --check`가 통과했다. 독립 written-spec·코드 품질·계획 gap·source→runtime 역방향 검증에서 확인된 P0/P1은 TDD로 보완했다. external/Gemini provider call은 0이며 Hermes/container, OpenCut runtime, SaaS auth/billing은 시작하지 않았다.
- **Task 9 보존:** Task 9은 실제 current-revision composited MP4의 사람 승인과 대상 PC의 실제 CapCut Desktop 등록/열기 결과가 없으므로 unchecked/technical-gate 상태다. 이 Task 10 완료는 그 gate를 대체하지 않는다.
- 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다. Task 7·8·10은 완료로 집계하고 Task 9은 집계하지 않는다. Task 9과 Task 10 구현이 하나의 dirty worktree에 얽혀 있어 Task 10만의 clean logical commit을 거짓으로 만들 수 없으므로, 이번 closeout에서는 **commit/push를 하지 않았다**. Task 9 acceptance 뒤 실제 diff 경계를 다시 검사해 commit/push 전략을 결정한다.

## 261. 2026-07-18 OSS Slice 2 Task 9 technical gate

- Task 9의 코드와 자동 검증 범위는 준비됐다. 한 번의 명시적 `초안 만들기` 승인만 editing session·timeline placement bundle을 만들며, brief/draft-plan revision과 source SHA/media revision을 다시 확인한다. 중복·동시 요청은 같은 결과를 재사용하고, N번째 materialize 실패·재시작 orphan·부분 파일은 per-SHA staging/atomic rename/rollback으로 정리한다.
- 실제 timeline에는 대본 구간, 자막, 선택한 B-roll, BGM/SFX 정책, unresolved gap이 저장된다. 원본 영상 소리·완성 나레이션·녹음 업로드·결정적 project-local 무음 narration은 FFmpeg와 PyCapCut 경로 모두에서 검증했고, `voice_sample_audio`는 완성 나레이션으로 거절한다. gap-only 초안은 사용자의 명시적 임시 장면 승인이 있어야 만들 수 있고, 라벨된 placeholder를 보여 주되 final/CapCut 출력은 계속 막는다.
- `/projects/$projectId/editor`는 방금 만든 session을 열고, 실제 current revision FFmpeg output의 progress/stale/retry/download/content 경로와 in-app MP4 playback, CapCut handoff route를 browser smoke로 연결했다. 자동 smoke의 CapCut 등록은 쓰기 가능한 로컬 fake handoff 경로이며 Desktop 앱을 열거나 등록하지 않는다.
- 검증: atomic/API/readiness focused backend `34 passed`, frontend full `28 files / 281 tests passed`, loopback-only Playwright `13 passed`, production build, provenance/UI-system verifier와 provenance pytest `14 passed`, `git diff --check`가 통과했다. 독립 코드리뷰·계획 gap·source→runtime 역방향 검증에서 찾은 P1은 TDD로 보완했고, external/Gemini call 0, Hermes/container·OpenCut runtime·SaaS auth/billing 미도입을 유지했다. 이 기술 검증의 기준 HEAD는 Task 8 commit `93c5b7161` 위의 아직 closeout 전 작업이다.
- **완료 보류:** 실제 current-revision 합성 MP4를 사람이 재생·확인해 Task 9 가치를 승인하고, 대상 환경의 실제 CapCut Desktop 등록/열기 결과를 기록해야 한다. 따라서 Task 9 체크박스와 누적 진행률은 **8/22 (36.4%), 잔여 63.6%**로 유지한다. 다음 goal은 이 두 사람/환경 gate를 수행·기록한 뒤에만 Task 9 closeout/commit/push 여부를 결정한다.

## 260. 2026-07-18 OSS Slice 2 Task 8 closeout

- 승인된 유진 기획에서 나레이션과 자산을 확인하는 저장형 초안 준비 단계를 완료했다. 원본 영상 소리, 준비한 나레이션, 브라우저 녹음·파일 업로드, 무음 storyboard를 고를 수 있으며 음성 샘플은 완성 나레이션으로 고를 수 없다.
- 준비 기록은 단계·실패·재시도·취소·후보 선택/구간·자산 부족을 프로젝트별로 저장한다. 장면 후보를 미리보고 구간을 고치거나 건너뛸 수 있으며, 부족한 장면은 자산 화면에서 안전하게 업로드한 뒤 기획으로 돌아와 다시 준비한다. 이 단계는 editing session을 만들거나 바꾸지 않는다.
- 검증: Task 8/creation focused backend `34 passed`, frontend full `28 files / 278 tests passed`, loopback-only Playwright `11 passed`, production build, provenance/UI-system verifier와 provenance pytest `14 passed`, `git diff --check` 통과. 독립 코드리뷰·계획 gap·source→runtime 검증에서 확인된 P1을 모두 TDD로 보완했다. external/Gemini call 0, Hermes/container·OpenCut runtime·SaaS auth/billing 미도입을 유지했다.
- OSS dashboard/editor 누적은 8/22 (36.4%), 잔여 63.6%다. 다음은 Task 9: 한 번의 승인으로 실제 editing session과 timeline bundle을 원자적으로 만들고 실제 output까지 검증한다.

## 259. 2026-07-18 OSS Slice 2 Task 7 closeout

- Task 7의 유진 영상 기획 인터뷰를 완료했다. 사용자는 대본을 붙여넣거나 `.txt`/`.md`/`.srt` 파일을 선택해 기획을 시작하고, 이미 적힌 내용은 건너뛴 최대 5개의 질문에 답한 뒤 요약을 고치고 승인한다. `모르겠어요`, `추천해줘`, `건너뛰기`, 바로 요약 보기와 대본·기획 삭제를 제공한다.
- 기획·답변·현재 단계·대본 보관 참조·기능 설정·재시도 키를 프로젝트별 SQLite에 저장한다. 새로고침 재개, 중복 요청, 질문/요약 변경 충돌, 다른 프로젝트 접근, 잘못된 파일/문자 인코딩/1 MiB 초과를 막고, 삭제하면 보관한 대본 파일과 기록도 함께 지운다. 유진 인터뷰는 provider-neutral runtime이며 현재는 deterministic local driver만 연결한다.
- 검증: Task 7 backend/API focused `23 passed`, frontend full `28 files / 271 tests passed`, production build, loopback-only Playwright `10 passed`, OSS provenance/UI-system verifier, provenance pytest `14 passed`, `git diff --check`가 통과했다. 독립 코드리뷰, 계획 gap, source→runtime 역방향 검증의 open P0/P1은 0이다. external/Gemini provider call은 0이고 Hermes/container, OpenCut runtime, SaaS auth/billing은 시작하지 않았다.
- OSS dashboard/editor 누적은 7/22 (31.8%), 잔여 68.2%다. 다음 실행 단위는 Task 8 narration과 자산 readiness를 명시적 draft plan으로 만드는 일이며, 이 Task의 승인된 기획을 입력으로만 사용하고 editing session은 바꾸지 않는다.

## 258. 2026-07-18 OSS Slice 1 Task 6 closeout

- Task 6 product shell, Home/settings/empty routes, local-only capability visibility, and loopback-only Playwright harness를 완료했다. Hermes/container, OpenCut runtime, SaaS auth/billing은 시작하지 않았다.
- 검증: frontend 27 files/260 tests, production build, Playwright 10 tests with deterministic 1920/1440/1280/768/390 snapshots, UI/provenance verifiers, provenance pytest 14 passed. external/Gemini provider call은 0이다.
- OSS dashboard/editor 누적은 6/22 (27.3%), 잔여 72.7%다. 다음 실행 단위는 Task 7 persisted Eugene creation brief/adaptive interview이며, Task 6 route truth와 loopback E2E harness를 확장해서 사용한다.
> 이 문서의 기존 날짜 기반 섹션은 당시 시점 판단과 검증 수치를 보존한 historical snapshot이다. Local Media Director release truth는 `## 250`, 현재 다음 frontend 계획은 `## 251`을 기준으로 본다.
> 단, `2일 내 1차 데모 완성` 실행 레일은 `## 189`의 장기 우선순위를 그대로 넓게 집행하지 않고, `docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md`의 축소된 실행 계획을 우선 적용한다.

## 257. 2026-07-18 OSS Slice 1 Task 5 closeout

- 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`; handoff: `docs/handoffs/2026-07-18-videobox-oss-dashboard-editor-adoption-slice-1-task-5-closeout.ko.md`; commit은 closeout staging 뒤 pending이다.
- typed routing과 URL-owned workspace state를 검증했다. direct URL·refresh restore·zero/unknown project recovery·canonical redirect·project switch·active route·request dedupe는 route param에서 project truth를 파생하며 별도 선택 state를 만들지 않는다.
- verification: provenance `14 passed`, routing/router-provider/legacy baseline focused tests와 current full frontend evidence pass, production build 및 network guard pass. external/Gemini provider call 0과 Hermes/container 미구현 경계는 유지한다.
- OSS dashboard/editor 누적은 5/22 (22.7%), 잔여 77.3%다. 다음 실행 단위는 Task 6 app shell, Home/settings/empty-state routes이며 Task 5 routing truth를 우회하거나 legacy parity를 깨지 않는다.

## 256. 2026-07-18 OSS Slice 1 Task 4 closeout

- 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`; handoff: `docs/handoffs/2026-07-18-videobox-oss-dashboard-editor-adoption-slice-1-task-4-closeout.ko.md`; commit은 closeout staging 뒤 pending이다.
- locked shadcn/ui source, local Pretendard, token/legacy CSS isolation, `@/*` alias, deterministic browser network guard와 UI-system verifier를 구현했다. legacy scope는 migrated roots 밖에서 유지하며, global preflight와 remote font/provider 요청은 도입하지 않았다.
- verification: provenance `14 passed`, frontend `22 files / 240 tests passed`, production build pass, provenance/UI-system 두 verifier pass, independent spec/quality review와 source→runtime reverse review의 open P0/P1은 0이다.
- external/Gemini provider call 0과 Hermes/container 미구현 경계를 유지했다. untracked `apps/web/pnpm-lock.yaml`, `apps/web/pnpm-workspace.yaml`은 보존하고 Task 4 commit에서 제외한다.
- OSS dashboard/editor 누적은 4/22 (18.2%), 잔여 81.8%다. 다음은 Task 5 URL-owned workspace state와 typed routing이며, 그 Task의 executable TDD sub-plan과 독립 review가 먼저다.

## 255. 2026-07-18 OSS Slice 0 Task 3 closeout

- 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`; handoff: `docs/handoffs/2026-07-18-videobox-oss-dashboard-editor-adoption-slice-0-task-3-closeout.ko.md`; implementation commit: `a2a3cdc docs: govern editor OSS source adoption`.
- 7개 source( shadcn-admin, shadcn/ui, OpenCut current/classic, Opencast, Supabase, Pretendard)를 exact commit/path/SHA/license/disposition으로 고정했다. OpenCut current와 Supabase는 reference-only이고, source map·registry/dependency lock·NOTICE·generated-file drift contract가 이를 검증한다.
- RED는 누락 pin/path/hash/license/test, reference-only local copy, notice, runtime import, generated-file hash drift를 각각 실패시키는 assertion으로 관찰했다. GREEN: `.venv\\Scripts\\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py` `12 passed`, PowerShell provenance verifier pass, production build pass, `git diff --check` pass.
- source→runtime 역방향 검토가 Supabase reference-only runtime scan의 P1 gap을 확인했다. static/dynamic/require/URL/package manifest/package-lock 검사를 추가해 source-derived 또는 package 기반 Supabase runtime 유입을 막았고, 보완 뒤 focused provenance test는 `13 passed`, PowerShell verifier는 다시 pass했다.
- 실제 OSS UI code, dependency, Pretendard font binary는 아직 도입하지 않았다. external/Gemini provider call 0과 Hermes/container 미구현 경계도 유지한다. untracked `apps/web/pnpm-lock.yaml`, `apps/web/pnpm-workspace.yaml`은 보존하고 이 Task에서 제외했다.
- OSS dashboard/editor 누적은 3/22 (13.6%), 잔여 86.4%다. 다음 실행 단위는 Task 4 UI foundation이며, 그 Task의 executable TDD sub-plan과 독립 review가 먼저다.

## 254. 2026-07-17 OSS Slice 0 Task 2 closeout

- 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`; handoff: `docs/handoffs/2026-07-17-videobox-oss-dashboard-editor-adoption-slice-0-task-2-closeout.ko.md`.
- 세 화면(빈 Home, 대본/유진 인터뷰, 자산이 채워진 편집기)과 다섯 viewport(1920×1080, 1440×900, 1280×800, 768×1024, 390×844)의 정적 승인 자료를 완성했다. 사용자는 warm-white `#FAFAF9`, muted indigo `#4F46E5`, local Noto Sans KR Variable, dark-only preview `#18181B` 방향을 명시 승인했다. 이 결정은 manifest artifact aggregate SHA에만 연결되며, artifact 변경에는 재승인이 필요하다.
- fresh verification: `.venv\\Scripts\\python.exe -m pytest -q tests/test_ui_prototype_artifacts.py`는 `2 passed`; artifact verifier는 pass; Task 2 exact frontend 12 files는 `206 passed`; `npm --prefix apps/web run build`는 pass였다. 독립 spec/quality review와 source→runtime reverse review의 open P0/P1은 0이다. 승인 전 `--require-approved` 실패는 의도된 gate였고, 승인 record 뒤에는 성공해야 한다.
- 기본 dashboard copy는 제작 결과와 다음 행동을 말하고 표시 도우미 이름은 `유진`이다. 이 Task는 runtime/API/provider identifier, dependency, Hermes/container, Tailwind, shadcn, router, OpenCut runtime을 추가하거나 바꾸지 않았으며 external/Gemini provider call 0 계약을 유지한다.
- worktree에서 보존·제외할 관련 없는 항목은 untracked `apps/web/pnpm-lock.yaml`, `apps/web/pnpm-workspace.yaml` 두 파일뿐이다.
- OSS dashboard/editor 누적은 2/22 (9.1%), 잔여 90.9%다. 다음 실행 단위는 Task 3의 OSS source/license/dependency/generated-file provenance gate다. 경량 컷편집은 이후 Task 14→15→16에서 timeline geometry → navigation/performance → split/merge/bounds/reorder mutation 순서로 다루며 CapCut remote control이 아니다.

## 253. 2026-07-17 OSS Slice 0 Task 1 closeout

- 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`; handoff: `docs/handoffs/2026-07-17-videobox-oss-dashboard-editor-adoption-slice-0-task-1-closeout.ko.md`.
- current `main`과 `origin/main`은 작업 시작 시 같은 SHA `90a0f88`였고 clean이었다. historical Lumi UI dirty scope는 이미 upstream merge에 포함돼 있었으므로 reset/delete/separation 없이 그대로 보존했다.
- planning-time TypeScript 오류 5개는 현 HEAD에서 이미 해소돼 있었다. 새 legacy baseline의 project selection `aria-pressed` 계약을 RED(기대 `true`, 실제 없음)로 관찰한 뒤, project/section 선택 상태를 접근성 semantics로 고정했다.
- baseline은 project select, section select/settings, blocked Director의 직접 편집 fallback, current preview/final의 이용 가능 상태, stale artifact 재생성 안내를 보호한다. Lumi 문구 policy는 AST/금칙어 12 assertion을 유지한다. 독립 UI 검토는 일반 사용자 동사·즉시 다음 행동·구현 식별자 비노출의 세 기준으로 문구를 판단했으며, 이 정성 판단은 자동 assertion과 별개다.
- fresh verification: Task 1 focused 21 passed, frontend full suite 200 passed, production build success, `git diff --check` success. independent spec/quality review와 source→runtime reverse check의 open P0/P1은 0이다. 이 Task의 diff는 provider 호출을 추가하지 않았고 normal local/test external/Gemini call은 0 계약을 변경하지 않았다.
- OSS dashboard/editor 누적은 1/22 (4.5%), 잔여 95.5%다. 다음은 Task 2의 세 화면/다섯 viewport visual prototype 및 명시적 사용자 승인이고, Hermes/container 구현은 written-spec review와 별도 implementation plan 전까지 시작하지 않는다.

## 252. 2026-07-17 Hermes container design handoff

- 설계: `docs/superpowers/specs/2026-07-17-videobox-hermes-hybrid-runtime-design.md`
- handoff: `docs/handoffs/2026-07-17-videobox-hermes-container-design-handoff.ko.md`
- commit/push: `6d9d0a5 docs: design local VideoBox Hermes stack`, `origin/codex/production-readiness-blocker-slice-1` 동기화 확인.
- 결정: VideoBox와 Hermes는 하나의 `videobox-local` Compose 제품 스택 안에서 web/API/render worker/Hermes/분리 egress/memory gateway/storage-only mem0으로 분리한다. Windows host에는 LM Studio, CapCut Desktop과 최소 host bridge만 남긴다.
- security/architecture 독립 재리뷰의 최종 미폐쇄 P0/P1은 0이다. 이는 설계 검증이며 container/runtime 구현 또는 OAuth live call 성공을 뜻하지 않는다.
- OSS dashboard/editor 22개 Task 구현 누적은 계속 0/22 (0%), 잔여 100%다. Hermes 구현은 user written-spec review와 별도 implementation plan 전에는 시작하지 않는다.
- 즉시 next action은 기존 dirty Lumi copy를 OSS Slice 0 Task 1으로 closeout하는 것이다. 현재 worktree의 Lumi UI 변경은 preserve 대상이며 새 container/Hermes 구현과 섞지 않는다.
- 기록: session/status/handoff 저장, AK-Wiki promotion 보류, 삭제 없음.

## 251. 2026-07-17 OSS dashboard/editor adoption planning

현재 dashboard가 실제 사용자의 제작 흐름과 편집 작업판을 충분히 드러내지 못한다는 판단에 따라 shadcn-admin, shadcn/ui, OpenCut current/classic, Opencast Editor, Supabase Studio의 공식 source를 commit 단위로 재조사했다.

- 조사: `docs/research/2026-07-17-videobox-oss-dashboard-editor-adoption.ko.md`
- 설계: `docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md`
- 실행 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`
- 조사 claim ledger: 공식 source 기반 핵심 주장 6건의 schema/disposition 검증 완료, unresolved/refuted 0건. 이것은 production 구현이나 법률 검토 완료를 뜻하지 않는다.

확인된 핵심 사실:

- current OpenCut rewrite에는 아직 실제 editor route/timeline/preview/asset/inspector가 없다. classic은 archived이므로 SDK가 아니라 선별 source로만 사용한다.
- shadcn-admin은 responsive shell source가 유용하지만 upstream도 starter project가 아니라고 명시한다. layout composition만 port한다.
- shadcn/ui는 source distribution이므로 VideoBox가 component code를 소유하는 방식이 맞다. live registry 결과가 아니라 pinned source path와 normalized file SHA를 lock해야 한다.
- Opencast의 transcript/cue/waveform/cut UX는 유용하지만 Redux/MUI/player/browser decode는 VideoBox와 맞지 않는다. true clean-room이 아니라 Apache-2.0 attributed behavioral adaptation으로 기록한다.
- Supabase Studio는 대형 product workspace에 결합돼 있어 project/settings/mobile IA만 참고한다.
- VideoBox의 editing-session/revision/source provenance/FFmpeg/PyCapCut 계약은 외부 editor보다 강하므로 교체가 아니라 view/interaction adapter가 필요하다.

독립 plan-gap, UX, source→runtime 리뷰는 계획 초안에 P0를 확인했다: 단일 source URL을 실제 합성 preview로 오인할 위험, caption-only timing을 저장할 backend 부재, proposal/빈 session을 실제 자동 편집 초안으로 오인할 위험, 핵심 사용자 검증이 Task 15까지 밀린 순서다. 실행 전에 모두 반영했다.

실행은 7개 slice, 22개 Task로 재편했다. 순서는 current Lumi copy closeout → 세 화면/네 viewport 사용자 시각 승인 → deterministic source lock → shadcn foundation/shell → `대본→루미 인터뷰→자산 점검→한 번 승인→atomic real draft→editor/output handoff` 수직 Slice → authoritative adapter와 exact FFmpeg preview → timeline/waveform/linked caption → assets/Lumi → responsive/parity/release다. production 구현은 아직 시작하지 않았으므로 새 계획 누적은 0/22 Task(0%), 잔여 100%다. 기존 Local Media Director 18/18 완료는 취소되지 않는다.

정확한 편집본 preview는 current revision과 source SHA를 기존 FFmpeg final composition path로 합성한 freshness-bound proxy artifact다. 선택 source audition과 구분한다. caption timing은 current segment metadata 권한에 맞춰 segment-linked로 제한하며 independent cue timing은 후속 범위다. local/test 외부/Gemini call 0은 유지하되 creation interview runtime은 future managed SaaS driver를 막지 않는 provider-neutral port를 사용한다.

현재 immediate next action은 새 shell 구현이 아니라, 이미 worktree에 남아 있는 Lumi copy 변경의 focused test와 production build blocker를 먼저 닫아 baseline commit을 만드는 것이다. 그 뒤 Task 2의 production-code 이전 visual prototype 승인 gate로 진행한다. Hermes agent/container와 실제 SaaS auth/team/billing은 이번 22개 Task 밖이다.

Planning-time verification은 Lumi 관련 focused 3파일 `17 passed`를 확인했다. 같은 상태에서 production build는 `director-history-controls.test.tsx` nullable fixture와 `user-copy-policy.test.ts`의 Node type/AST/`ImportMeta.dirname` TypeScript 오류 5건으로 실패했다. 이 실패는 새 OSS shell 구현 실패가 아니라 아직 commit되지 않은 Lumi copy Task 1의 명시적 RED baseline이다. 조사 ledger는 verified 6/unresolved 0/refuted 0, report evaluation은 citation 13/13·orphan 0·leak 0으로 PASS했다. 3개 독립 UX/plan/source→runtime 재리뷰의 최종 미폐쇄 P0/P1은 0건이다.

## 250. 2026-07-17 Local Media Director Slice 3 Task 18 release closeout

- App은 reload endpoint로 persisted conversation/proposal/reference를 read-only 복구하고, 실제 proposal 생성은 명시적 `디렉터 시작`에서만 수행한다. apply는 한 번의 batch mutation 뒤 timeline/review/subtitle/preview/final/CapCut freshness를 함께 무효화한다. Director route와 기본 Settings는 Gemini/legacy LocalFirst runtime을 사용하거나 노출하지 않는다.
- RED→GREEN은 refresh recovery, ambiguity, materialize/batch 실패의 session 불변, blocked/error manual mode, Gemini bootstrap/key/provider request 0을 App contract로 고정했다. deterministic local structured runtime을 쓴 실제 B/M/S E2E는 source SHA·scene/audio controls가 timeline→FFmpeg→PyCapCut까지 보존됨, stale source가 final/draft를 모두 차단함, assetless BGM/SFX 거부, Korean SRT/MP4 audio/duration, unknown-rights warning metadata를 확인한다.
- release gate: focused backend `39 passed`, focused frontend `151 passed`, full backend `1027 passed, 3 skipped, 1 warning`, full frontend `168 passed`, production build 성공, real Media Director E2E `2 passed`, real Starter Pack E2E `2 passed`다. `media-director-live-smoke`는 실제 127.0.0.1:1234 loopback capability/vision/embedding/reopen store query `7 passed`를 확인했고, release의 deterministic E2E는 external/Gemini provider call 0을 assertion으로 증명한다.
- 실제 산출물 gate도 통과했다. `artifacts/task5-smoke`의 600초 Korean production-readiness smoke는 MP4/SRT/CapCut draft 및 control/hash 검사를, `artifacts/long-form-capcut-qa`의 three-fixture QA는 B-roll/audio controls와 CapCut ducking compatibility warning 보존을 검증했다. 자동 실행은 CapCut Desktop을 열거나 사람 판단을 대신하지 않는다.
- release audit 6개 gate: 최신 독립 사양·품질 코드리뷰 P0/P1 없음, Task 18 계획 gap 없음, source→runtime reverse trace/E2E 통과, live loopback·real output 확인, fast-path/SSOT 지침 갱신, staged하지 않는 artifacts 및 diff/status 검사로 찌꺼기 여부를 점검했다.
- 전체 구현 계획 누적 진행률은 18/18 Task (100.0%), 잔여 0%다. 남은 release follow-up은 human acceptance뿐이다: CapCut Desktop에서 draft 재생·export, 실제 음성 자연스러움 청취, 배포 전 자산 권리/라이선스 승인. 커밋/푸시 SHA는 이 closeout과 같은 Task 18 변경에 기록한다.

## 249. 2026-07-16 Local Media Director Slice 3 Task 17 closeout

- Director workspace는 desktop에서 360–420px aside와 접기 제어를 제공하고, 760px 이하에서는 portal 기반 `aria-modal` bottom sheet로 전환한다. sheet는 backdrop, background inert/aria-hidden, capture 차단으로 배경의 수동 BGM/B-roll mutation을 막는다.
- narrow sheet는 초기 내부 focus, 양방향 Tab trap, Escape/back/close focus 복귀, IME composition Escape 예외, breakpoint exit 시 desktop collapse 제어로의 focus 복원을 제공하며 입력 draft를 보존한다. candidate tray는 narrow carousel이며 reduced-motion 선호를 state/CSS에 반영한다.
- 검증: responsive RED(열기 제어 부재·IME Escape 닫힘·배경 B-roll mutation·breakpoint focus 유실)를 확인한 뒤 GREEN으로 닫았다. frontend 전체 `156 passed`, production build 성공, 관련 Director backend contract `16 passed`, `git diff --check` 통과. 독립 사양·품질 리뷰는 P0/P1 없이 승인됐다.
- 전체 구현 계획 누적 진행률은 17/18 Task (94.4%), 잔여 5.6%다. 다음 실행 단위는 Slice 3 Task 18 App integration, refresh recovery, real output E2E, release closeout이다.

## 248. 2026-07-16 Local Media Director Slice 3 Task 16 closeout

- Starter Pack BGM/SFX와 프로젝트 로컬 B-roll 수동 라이브러리를 `ManualMediaLibrary`로 추출했다. Director가 blocked/error여도 수동 미리보기·명시적 적용은 독립적으로 유지되며, 미리보기는 editing session을 변경하지 않는다.
- 글로벌 pack asset은 materialize 후 적용하고, 로컬 B-roll은 서버가 실제 `BROLL_VIDEO` 자산을 재해시해 SHA/revision을 editing session → partial regeneration → timeline clip → output-source verifier까지 보존한다. 출처가 바뀌면 출력 검증이 거절되는 회귀 테스트를 추가했다.
- 프로젝트 범위 favorite/recent, pin/exclude를 저장하고, SQLite `BEGIN IMMEDIATE`로 병렬 갱신의 read-modify-write 유실을 막았다. 로컬 B-roll 적용 직후 recent filter를 갱신하며, 키보드는 B-roll 카드 포커스 후 명시적 선택 구간 대상에서 Enter/Space로만 배치할 수 있다.
- 검증: ManualMediaLibrary RED/Green과 strict B-roll provenance RED/Green을 확인했다. 최종 frontend 전체 `145 passed`, `npm --prefix apps/web run build` 성공, 관련 backend focused `89 passed`, 전체 backend `1011 passed, 2 skipped`를 확인했다. 독립 사양 리뷰와 최종 품질 리뷰는 P0/P1 없이 승인됐다.
- 전체 구현 계획 누적 진행률은 16/18 Task (88.9%), 잔여 11.1%다. 다음 실행 단위는 Slice 3 Task 17 responsive bottom sheet와 focus/IME/a11y다.

## 235. 2026-07-14 Local Media Director implementation planning

사용자가 승인한 로컬 AI 디렉터 설계를 현재 코드와 역추적하고, backend architecture, frontend UX/component, verification/output 관점의 독립 감사를 반영해 실행 계획을 작성했다.

- 승인 설계: `docs/superpowers/specs/2026-07-14-local-media-director-design.md`
- 실행 계획: `docs/superpowers/plans/2026-07-14-local-media-director-implementation.md`
- 기준 HEAD: `8eddb7f`
- 계획 범위: 3개 순차 slice, 18개 TDD Task
- 설계/계획 진행률: 100%, 잔여 0%
- production code 구현 진행률: 14/18 Task (77.8%), 잔여 22.2%
- 완료 작업: Slice 1 Task 1 local-only runtime 경계와 deterministic test guard, Task 2 Vision/embedding/capability preflight provider, Task 3 durable MEDIA_ANALYSIS schema와 state machine, Task 4 FFmpeg probe/cache/quality gate/deterministic dispatcher, Task 5 analysis API/batch ingest/검수 UI, Task 6 actual LM Studio live release gate, Slice 2 Task 7 narration 없는 script draft session, Task 8 immutable proposal domain/persistence/ranking, Task 9 proposal API/preflight/refresh, Task 10 candidate preview와 project asset materializer, Task 11 atomic apply/named undo-redo/output freshness, Task 12 output hash/revision revalidation과 Slice 2 gate, Slice 3 Task 13 persistent conversation/reference command resolver, Task 14 frontend API DTO/pure reference-history-shortcut units
- 다음 작업: Slice 3 Task 15 Director panel, context bar, cards, preview, comparison tray
- 계획 commit `3fda0ae`는 remote에 push됐다. 다음 세션 재개용 handoff는 `docs/handoffs/2026-07-14-local-media-director-plan-closeout.ko.md`다.

확인된 구현 blocker는 text-only local provider, Gemini 자동 fallback, 외부 HTTP(S) runtime 허용, durable media-analysis 상태 부재, script-only session 부재, B/M/S mutation의 불완전한 undo, output SHA/revision 재검증 부재다. 계획은 이 순서대로 RED test를 먼저 만들고 provider → analysis → proposal → transaction → UI → output E2E를 연결한다.

UI는 4,396줄 `App.tsx`의 전면 rewrite를 하지 않고 `apps/web/src/features/director`와 `apps/web/src/features/media`에 새 책임을 분리한다. 현재 5,709줄 `app.test.tsx`에는 refresh/apply/materialize failure/ambiguity/manual fallback 통합 시나리오만 추가하고 세부 interaction은 component test로 분리한다.

### Slice 3 Task 13 closeout 및 중간점검 보완 (2026-07-15)

- SQLite conversation/message persistence와 client-message idempotency를 구현했다. owner-token claim/heartbeat/finalize fence가 동일 요청의 local generation 중복을 차단하며 stale crash claim은 안전하게 회수한다.
- assistant failure는 local-only trace를 가진 persisted `blocked` message이고 editing session은 변경하지 않는다. resolver는 open proposal과 실제 persisted B/M/S placement를 구분하고 ambiguity card 데이터를 반환한다. Gemini/external fake provider call은 0이다.
- 검증: focused `26 passed`, full backend `996 passed, 2 skipped`, frontend `108 passed`와 build success, `git diff --check` 통과. backend multipart warning 1건과 frontend ErrorBoundary/`act(...)` stderr는 기존 비차단 경고다.
- 계획 보완: independent review가 same-segment B/M/S resolver의 raw segment-ID collision, resolved command의 acknowledgement-only 흐름, optional history session scope를 P1으로 확인했고 모두 RED-first로 닫았다. typed placement identity와 action intent→immutable proposal/session preflight binding은 Task 13에 구현됐으며 Task 15/18은 explicit atomic apply E2E를 맡는다. `202 + Retry-After` duplicate 계약, conversation retention/index release audit, Director successful trace의 local-only route-surface 검증도 Task 14/18에 명시했다. full NLE/OpenCut과 Voice Capture & Narration은 현재 remediation 범위 밖의 별도 gate를 유지한다.

### Slice 3 Task 14 frontend contracts closeout (2026-07-16)

- Task 13 local-only conversation DTO와 API client를 연결했다. `202`는 exchange로 오인하지 않고 retry-after 상태로 반환하며 prepared submission이 동일 client message ID/body를 재사용한다.
- proposal/timeline typed reference label, stale-history selector, history action metadata, IME-safe undo/redo hook은 모두 App integration 전의 pure unit으로 분리했다. exchange/action intent는 editing session을 변경하거나 apply를 호출하지 않는다.
- independent review가 발견한 unsupported apply scope와 history metadata serialization gap은 RED-first로 닫았다. legacy artifact payload에서 `is_current` 누락은 current로 호환한다.
- 검증: frontend focused `15 passed`, backend contract `9 passed`, full backend `997 passed, 2 skipped`, frontend full `118 passed`/build success, diff check 통과. 다음은 Task 15 workspace UI와 explicit apply action이다.

### Slice 1 Task 5 closeout deferment

- Task 4의 `can_apply_media_analysis` gate는 durable store contract로 유지한다. 실제 Director proposal/apply consumer는 Slice 2 Task 8–11에서 처음 생기므로, 해당 consumer가 gate를 호출하는 검증도 그 범위에서 구현한다.
- media-analysis poller의 기본 50ms interval은 현재 deterministic local test/worker 운용을 위한 값이다. Slice 1 release gate 전 운영 profile에 맞는 interval/backoff tuning을 별도 검토한다.

### Slice 1 Task 1–5 release-blocking remediation (2026-07-15)

- 명시적 `enable_local_media_analysis` profile만 실제 LM Studio Vision/embedding provider와 FFmpeg probe를 내부 구성한다. transport는 매 요청 exact `http://127.0.0.1:1234/v1`·no-redirect를 재검증하고 capability preflight 뒤에만 worker를 연다. 기본 app은 provider 부재를 `blocked`로 보이며, production DI로 임의 provider 또는 legacy LocalFirst factory를 주입할 수 없다.
- analysis cache/idempotency에는 vision·embedding model identity를 포함한다. selected profile, scene window, embedding은 restart 뒤에도 저장되며, read-only provenance endpoint는 profile·scene timing·embedding dimension만 노출한다.
- analysis API/UI는 active queued/running job의 실제 `queue_position`만 보이고, result 없는 preview는 409으로 명시한다. batch client는 assets·analysis_jobs·per-file failures를 보존한다. 분석 상태는 기존 manual editor/library를 disable하지 않는다.
- RED→GREEN은 external LM Studio provider injection, legacy factory, model-profile cache collision, queue snapshot race, unavailable preview, restart provenance, batch contract를 포함한다. 독립 명세 재심사와 코드품질 재심사는 승인했다. focused backend 77 passed, frontend 5 passed, web build 및 `git diff --check`가 통과했다. Starlette `python_multipart` deprecation warning 1건은 기존 비차단 경고다.

### 후속 판단 보류: OpenCut 및 Voice Capture & Narration

- OpenCut은 현재 Task 4 및 Local Media Director 18개 Task의 구현 범위에 넣지 않는다. full editor 도입이 아니라 UX 참고 후보로만 보존하며, editing-session/FFmpeg/CapCut 계약 안정 후 별도 재분석한다.
- 사용자 음성 녹음·업로드→local STT 전사→자막/대본 정렬은 후속 Voice Capture & Narration slice 후보로 보존한다. voice cloning/TTS는 명시 동의·보관/삭제·approval 계약을 먼저 설계한 뒤 별도 판단한다.

### Slice 1 Task 6 live gate evidence — PASS (2026-07-15)

- `87be02e7eec1108bc2e758d595d926f558fcf6e4`에서 `VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE=1 pytest -q -rs tests/test_lm_studio_media_smoke.py -m live_lmstudio`가 `1 passed, 1 deselected`로 통과했다. normal pytest의 socket guard는 유지되고 marker+환경변수+exact `127.0.0.1:1234`일 때만 live 연결을 연다.
- native exact `GET /api/v1/models` inventory로 loaded Qwen Vision `qwen/qwen3.6-35b-a3b`와 BGE embedding `text-embedding-bge-m3`를 식별했다. structured JSON은 inventory metadata나 모델명으로 추정하지 않고, production fixed JSON Schema `POST /v1/chat/completions`의 성공 및 strict local parse로 증명했다. 이후 `POST /v1/embeddings`, finite vector, restart 뒤 durable semantic self-match까지 통과했다.
- custom Git-excluded artifact `C:\\Users\\atgro\\AppData\\Local\\Temp\\videobox-task6-release-evidence-87be02e\\live-media-success.json`은 sample SHA `944be1ad020b89fcb8a4c40e3be5e06ae581e751577483e3edf3bd8a7f7f3883`, native discovery 5회와 OpenAI runtime 2회의 exact loopback 요청(총 7), unfallbacked `lm_studio` trace, external provider call 0, Gemini call 0을 기록한다.
- native inventory가 malformed한 과거 호환 환경에만 former strict `loaded=true + native_capabilities` inventory를 fallback으로 허용한다. 일반 `/v1/models` ID나 model name만으로 capability를 만들지 않으며, generic ID-only inventory는 blocked다.

### Slice 2 Task 7 script draft session closeout (2026-07-15)

- script asset만으로 `POST /editing-sessions/from-script`가 provisional editing session을 만든다. 구간은 빈 줄 → 문장 종결부호(공백 없는 한국어 문장 포함) → character budget 순으로 deterministic하게 나뉘며, 공백 제외 Korean character count/초와 최소 2초로 provisional bounds를 만든다.
- session은 `timing_source=provisional_script`, `narration_alignment_required=true`, 안정된 `source_script_segment_id`를 durable store에 저장한다. narration alignment는 실제 bounds와 source ID를 유지하고 CAS revision 충돌에는 최신 session을 포함한 409을 반환하며, 실제 timing provenance로 바뀐 모든 source ID를 future proposal invalidation 목록에 남긴다. Task 8 proposal aggregate/table은 아직 만들지 않았다.
- API E2E는 script-only 생성·restart reload·non-script/empty script 차단과 alignment의 빈 목록, overlap, non-positive bounds 422을 고정한다. legacy editing-session JSON에는 absent 새 nullable metadata를 다시 직렬화하지 않아 기존 계약도 보존한다.
- TDD RED는 `videobox_core_engine.script_draft_session` 모듈 부재를 재현했다. 구현 계획의 `tests/test_api_media_director.py`는 실제 저장소에 없었으므로 API E2E를 새 `tests/test_script_draft_session.py`에 수용하도록 SSOT 파일 목록/명령을 바로잡았다.
- 검증: focused `66 passed`, final backend full `905 passed, 2 skipped`, frontend `107 passed`와 build success, `git diff --check` 통과(기존 `python_multipart` deprecation warning 1건은 비차단). 코드 commit은 `ed092d0`이다.

### Slice 2 Task 8 immutable proposal/ranking closeout (2026-07-15)

- immutable DirectorProposal/Candidate snapshot, durable proposal/base session/asset-index/source identity, project preference, expiry와 monotonic `P01` revision을 저장한다. 동일 proposal ID의 changed snapshot overwrite와 concurrent allocator race는 거절/원자 증가로 차단한다.
- ranking은 `music`→BGM alias, media-scoped B/M/S reference numbering, semantic score가 있으면 그 값을 사용하고 없으면 Korean lexical synonym fallback provenance를 남긴다. exclude/license/availability/review gate는 pin/favorite보다 먼저 적용된다.
- Task 7 narration alignment는 editing-session CAS와 matching ready proposal stale을 같은 SQLite transaction에서 수행한다. 실제 asset register/metadata/delete와 asset-index revision도 단일 transaction이며 실패 rollback을 고정했다. 이 작업 중 발견한 partial-regeneration writer 회귀도 별도 RED regression으로 복구했다.
- 검증: focused `79 passed`, final backend full `932 passed, 2 skipped`, frontend `107 passed`/build success, `git diff --check` 통과. 기존 backend multipart deprecation warning 1건과 frontend test stderr/`act(...)` warning은 이번 변경과 무관한 비차단 기존 경고다.
- 코드 commit은 `6a5d3ec`이다.

### Slice 2 Task 9 proposal API/preflight/refresh closeout (2026-07-15)

- immutable proposal은 one-read SQLite snapshot에서 생성되고 current B-roll SHA/succeeded analysis 또는 indexed BGM/SFX metadata를 확인한다. unknown user-owned B-roll은 warning provenance를 보존한다.
- API E2E는 create/get/preflight/refresh/preferences, immutable session, stable stale 409, exact diff, lifecycle event, local-only DI와 Gemini/external call 0을 고정했다. terminal analysis late derived data·index transition·basename collision도 remediation test로 닫았다.
- 검증: focused backend `90 passed`, backend full `948 passed, 2 skipped`, frontend `108 passed`/build success, `git diff --check` 통과. 기존 multipart deprecation 1건과 frontend stderr/`act(...)` warning은 비차단 기존 경고다.
- 코드 commit은 `37252c2`이다.

### Local Media Director 중간점검 보완 (2026-07-15)

- historical note: 이 중간점검 최초 시점의 HEAD는 `8b023f5`, 누적은 Task 1–8/18(44.4%)이었다. 이후 Task 9 code closeout `37252c2`와 Task 10 closeout이 완료됐으며, 현재 authoritative 상태는 이 섹션 상단의 10/18(55.6%), 다음 Task 11이다.
- 2026-07-15 후속 독립 감사에서 Task 9 preflight의 media-type policy mismatch를 확인했다. BGM/SFX proposal은 indexed canonical metadata만으로 생성되지만 preflight가 B-roll analysis까지 요구해 stale 처리된다. empty B-roll analysis result, nullable candidate `media_revision`, lifecycle status/event 분리 commit도 확인됐다. Task 10은 materializer 전에 이 항목을 RED-first remediation으로 처리한다.
- Task 10은 B-roll=non-empty succeeded analysis+SHA, BGM/SFX=indexed canonical metadata+SHA의 verifier를 분리하고 asset registration `created_at`을 candidate `media_revision`으로 고정한다. 그 뒤 SHA copy/staging cleanup·per-SHA lock·source-mutation race·candidate preview를 수행한다. OpenCut과 Voice Capture & Narration은 현재 18 Task 외부의 보류 범위를 유지한다.

### Slice 2 Task 10 candidate preview/materializer closeout (2026-07-15)

- preview는 immutable candidate controls와 exact in/out header를 유지한 verified temporary snapshot만 스트리밍하고, autoplay/session/timeline mutation을 만들지 않는다. snapshot과 source SHA가 다르면 응답하지 않고 cleanup한다.
- materializer는 candidate source→`.materializing` stage→새 project-local asset의 SHA를 순서대로 재검증한다. B-roll은 non-empty applicable analysis, BGM/SFX는 indexed required canonical metadata, 모두 registration revision을 다시 확인한다. per-SHA lock·provenance-safe reuse·post-registration compensation은 concurrent duplicate, source mutation, unlink failure에도 orphan을 남기지 않는다.
- 검증: RED 404 preview route 부재를 재현했다. focused backend `79 passed`, full backend `957 passed, 2 skipped`, frontend `108 passed`/build success, `git diff --check` 통과. 기존 backend multipart deprecation 1건과 frontend ErrorBoundary/`act(...)` stderr는 비차단 기존 경고다. 코드 commit은 `d1d3f98`이다.

### Slice 1 Task 1 closeout (2026-07-14)

- `LocalOpenAICompatibleRuntimeConfig`는 정확히 `http://127.0.0.1:1234/v1`만 허용하며, create_app 자동 pipeline은 Gemini provider를 생성하거나 LocalFirst fallback을 실행하지 않는다.
- LocalOnly runtime의 성공 trace는 `local_only`, local 실패 뒤 heuristic/rule/static fallback trace는 `local_provider_error`를 보존한다. API E2E는 Gemini fake provider 호출 수가 0임을 고정한다.
- pytest autouse network guard는 `connect`, `connect_ex`, `create_connection`을 차단한다. `live_lmstudio` marker의 정확한 loopback endpoint와 TestClient 내부 socketpair의 일회성 포트만 허용한다.
- TDD RED: 누락 runtime, 외부 endpoint/후행 slash 허용, Gemini fallback wiring, socket guard loopback 및 port-reuse/connect_ex 우회를 재현했다. GREEN: focused suite 40 passed, full `tests/test_api.py` exit 0, `git diff --check` 통과.

## 234. 2026-07-14 starter media pack release

Starter Media Pack Task 5 Step 3–5를 실제 source-byte build와 release 검증까지 완료했다. Git에 binary는 추가하지 않았으며 `dist/starter-media-pack` 및 `artifacts/starter-media-pack-sources`는 `.gitignore` 대상이다.

- 승인 ledger의 정확한 집합(30 music / 100 SFX)만 사용했다. 130 source bytes의 SHA-256, converted SHA-256·duration·official URL·selection evidence hash는 각각 `evidence/<asset_id>.txt`와 `manifest.json`에 고정됐다.
- `assets/` 130개만 library asset이며 music은 320kbps CBR MP3, SFX는 48kHz mono PCM WAV를 verifier가 실제 ffprobe/frame check로 확인한다. `source-archive/` 130개는 같은 승인 CC0 원본의 재현/감사용 보존본이며 manifest에 없으므로 검색·즐겨찾기·timeline materialize 대상이 아니다.
- 최종 manifest integrity: `starter-v1@1.0.0`, `493,018,539` bytes (약 470.2MiB), SHA-256 `f0d5249c2c1b268587a672bdc59956158f3f557654e3073e070adc90e08d60b2`. `scripts/verify-starter-media-pack.py dist/starter-media-pack`은 `OK`다.
- TDD: ledger 30/100 고정과 fingerprint, source archive 비선택성, source/converted SHA-256·duration·format evidence, low-rate music의 44.1kHz upsample→320kbps CBR, immutable metadata, 300–500MiB lower-bound, FMA User-Agent 403 재현을 RED→GREEN으로 추가했다.
- 전체 검증: Python 3.12 backend `801 passed, 1 warning in 172.70s`; frontend `105 passed`; production build success. frontend stderr의 intentional ErrorBoundary 및 기존 React `act(...)` hygiene output은 exit 0이다.
- 600-second Korean smoke: ingest → edit → SRT → final MP4 → CapCut draft 모든 checks true. SRT `artifacts/task5-smoke/projects/projects/production-readiness-korean-smoke-loop/subtitles/subtitle_001.srt`; MP4 SHA-256 `448c74034c3981ff7aa5264d12655eba6096b1653261e93d1ffae41a26342f29`; CapCut draft `artifacts/task5-smoke/projects/projects/production-readiness-korean-smoke-loop/exports/capcut_draft/export_002/timeline_002/draft_content.json`. 자동 smoke는 CapCut Desktop open을 주장하지 않는다.
- 2026-07-14 release closeout gap/reverse 검증: `VIDEOBOX_RUN_REAL_STARTER_PACK_E2E=1 .venv\\Scripts\\python.exe -m pytest -q tests/test_real_starter_media_pack_e2e.py`가 `1 passed, 1 warning in 14.18s`로 통과했다. 이 opt-in gate는 실제 ignored `dist/starter-media-pack` 470.2MiB를 install하고 130개 library surface에서 실제 music/SFX ID를 목록 선택·즐겨찾기·project-local materialize한 뒤 partial regeneration·실제 SRT 내용·FFmpeg MP4 audio stream/duration·PyCapCut real draft를 모두 실행한다. timeline/draft와 selectable path에 `source-archive`가 없음을 함께 assert한다. deterministic LLM/STT provider만 사용하므로 localhost/external LLM 호출은 없다.

다음 권장 작업:

- feature 작업은 완료됐다. 실제 운영 배포 전에는 기존 human acceptance runbook의 실제 사용자 음성 listening approval 및 별도 Windows PC CapCut Desktop open/edit/export 확인만 수행한다.

## 233. 2026-07-14 starter media pack official-license research (historical)

Task 5 Step 1의 source-level licensing gate를 시작했다. `docs/starter-media-pack-license-research.ko.md`가 asset-level candidate URL, creator, selection timestamp, official-page raw HTML SHA-256, attribution, commercial/raw redistribution/conversion 판정의 SSOT다.

- Pixabay, Mixkit, Uppbeat free tier는 일반적인 commercial video use와 달리 raw audio를 third party에게 pack으로 재배포하는 권한이 불명확하거나 금지되어 후보에서 제외했다.
- CC0 candidate는 music 30개와 SFX 100개다. CC0 legal code와 OpenGameArt/FMA의 author asset page를 근거로 commercial use, raw redistribution, conversion을 true로 판단했다.
- 130 direct asset URLs와 36 official asset pages를 HTTPS 200으로 재확인했으므로 starter-v1 **license research gate는 green**이다. source-byte hash, format conversion, manifest integrity가 아직 없으므로 이는 pack release green이 아니다.

다음 권장 작업:

- 이제 approved source만 download해 source-byte SHA-256, duration, codec, converted-file evidence snapshot을 고정한 뒤에만 300–500 MiB build를 시작한다.

## 232. 2026-07-14 starter media pack release-gate remediation

Task 5의 release verifier 코드리뷰 Critical/Important를 TDD로 보완했다. 이것은 **실물 starter pack release 완료가 아니며**, official license research·300–500 MiB 실제 asset build·10분 output smoke는 계속 다음 단계다.

- `MediaPackService.install()`은 source directory에서 immutable evidence, codec/format, MP3 CBR frame contract를 staging copy 전에 검증한다. failure는 `release_contract`이며 library index/activation을 만들지 않는다. cleanup은 이번 시도에서 만든 inactive index만 제거하므로 기존 stale index를 지우지 않는다.
- `media_pack_release` core-engine gate가 CLI verifier와 direct service의 단일 policy path다. legacy script wrapper는 parse/integrity adapter만 유지한다.
- MP3 CBR 판정은 모든 MPEG-1 Layer III frame이 320kbps인지 검사한다. average 320kbps VBR, ID3v2.4 footer, ID3v2.3 experimental-flag edge case를 contract test로 고정했다.
- TDD evidence: stale inactive index 삭제, source-before-staging gate, ID3v2.4 footer, ID3v2.3 experimental flag를 각각 RED로 재현 후 GREEN했다. focused backend `47 passed, 1 warning`; full Python 3.12 backend `793 passed, 1 warning in 186.66s`; frontend `105 passed`, production build success다.
- human acceptance는 `## 230` 및 해당 runbook대로 외부 입력 대기이며 변경하지 않았다.

다음 권장 작업:

- remediation slice는 최종 full backend/frontend/build 검증까지 green이다. 다음에만 Task 5 Step 1 official-license research와 ignored real pack build를 시작한다.

## 231. 2026-07-13 starter media pack release-review handoff

스타터 미디어팩 Task 5의 release verifier 기반은 commit `633fd9d`로 push했다. 이것은 실물 팩 release 완료가 아니라, 그 전 검증 계약을 추가한 중간 slice다. 상세 재개 정보는 `docs/handoffs/2026-07-13-starter-media-pack-task5-review.ko.md`가 authoritative다.

- 새 verifier는 CLI에서 music MP3 320 kbps, SFX PCM WAV 48 kHz mono, asset별 evidence snapshot hash, actual pack integrity를 install 전에 확인한다.
- 독립 review는 **Critical 1건**(direct `MediaPackService.install()`이 CLI 검증을 우회)과 **Important 1건**(average bitrate만으로 VBR을 확실히 거르지 못함)을 발견했다. 둘 다 다음 slice의 RED-first 수정 대상이며, 이 상태로 Task 5 또는 배포를 완료 처리하지 않는다.
- full backend은 `.venv\\Scripts\\python.exe -m pytest -q`에서 `783 passed, 1 failed, 1 warning in 175.73s`였다. 실패는 `tests/test_media_controls.py::test_manual_music_asset_uses_resolvable_asset_uri_in_the_render_timeline`의 missing BGM clip (`StopIteration`)이다. 이번 scripts-only diff가 원인인지 아직 증명하지 않았으므로 source trace 전에는 unrelated fix를 하지 않는다.
- frontend는 `105 passed`, production build success였다. `act(...)` 및 intentional error-boundary console은 known test hygiene output이며 exit 0이다.
- human acceptance는 `## 230` 및 해당 runbook대로 외부 입력 대기다.

다음 권장 작업:

- `docs/handoffs/2026-07-13-starter-media-pack-task5-review.ko.md`의 순서대로 service/API install gate Critical과 VBR Important를 TDD로 닫고, full backend failure를 root-cause trace한다. 그 뒤에만 실물 팩 build/release validation을 재개한다.

## 230. 2026-07-13 human acceptance preparation

release audit의 다음 권장 작업인 human acceptance를 시작하기 전, 실제 입력과 실행 환경을 read-only로 점검했다. 실행 runbook은 `docs/handoffs/2026-07-13-human-acceptance-runbook.ko.md`에 고정했다.

- 현재 `artifacts/`의 10분 한국어 WAV, `inputs/voice_samples/*.wav`, `tts_candidate.wav`는 모두 production smoke의 합성 음성이다. 실제 사용자 음성으로 오기하거나 청취 승인 근거로 사용하지 않는다.
- 기본 `scripts/run_api.py`는 TTS provider를 활성화하지 않는다. 실제 personal-voice candidate acceptance에는 `local_xtts` runtime 또는 사용자가 동의한 사전 clone ElevenLabs voice 설정이 필요하다. gTTS는 voice clone fallback이 아니다.
- UI/API/저장 계약은 준비되어 있다: upload → candidate generation → audio 청취 → pending listening review 승인/거부 → 승인 후보만 selection → timeline/output 경로다. 이 경로의 자동 contract는 이미 frontend/backend test 및 smoke로 확인됐지만 인간의 음질 판단을 대체하지 않는다.
- 다른 Windows PC CapCut smoke는 supported `8.7.x`/`8.9.x`, diagnostics ready, actual draft export, handoff registration, 사용자의 Desktop open/editability 확인으로 수행한다. 개발 PC의 diagnostics probe는 외부 사용자 profile/ACL/설치 variant를 증명하지 못한다.
- 현재 차단 입력: 실제 사용자 음성과 다른 Windows PC 접근이 없다. 이 PC에는 Coqui XTTS/Torch package는 있으나 XTTS-v2 model download와 Coqui license acceptance를 아직 수행하지 않았고, ElevenLabs SDK/credential/voice ID도 없다. 사용자가 CapCut을 강제 종료했으므로 자동 재실행하지 않는다.

다음 권장 작업:

- 사용자 동의 음성 파일과 cloning provider 준비가 되면 runbook A를, 외부 PC 접근이 가능해지면 runbook B를 실행한다. 둘 다 완료된 뒤 release audit protocol의 relevant gate만 재실행해 배포 판단을 갱신한다.

## 229. 2026-07-13 release audit protocol closeout

개발 종료 전 반복할 6개 gate를 `docs/superpowers/plans/2026-07-13-release-audit-protocol.ko.md`에 만들고, 현재 HEAD에 실제 적용했다. 고정 운영 규정은 `docs/development-fast-path.ko.md` 10.12에 연결했다.

- Gate 1 코드리뷰: Critical 1건과 Important 2건을 발견·수정했다. CapCut handoff는 ownership marker가 없는 동명 destination을 더 이상 지우지 않으며, marker 기록 실패 뒤 방금 만든 destination만 rollback한다. `8.7.x`와 `8.9.x`만 tested/supported로 판정하고 그 밖의 버전은 ready로 오기하지 않는다. reload는 최신 failed CapCut draft export의 error/retry를 복구하면서 마지막 성공 artifact를 함께 보존한다.
- Gate 2 갭 검증: 명시된 CapCut 3/3 long-form output, diagnostics, persisted nullable failure 경로를 코드·계약 테스트·local proof로 연결했다. 실제 사용자 녹음의 listening approval, 일반 사용자 PC 1대의 CapCut handoff smoke는 자동화로 대체할 수 없는 human acceptance로 남긴다.
- Gate 3 역방향 동작: `loop`, `crop_pad_overlay`, `audio_ducking`의 local final MP4가 모두 FFprobe `600.026848`초 및 이전 closeout의 SHA-256과 일치했다. 각 profile에서 local CapCut draft, VideoBox final MP4, `draft_content.json`, timeline, editing session, SRT가 존재함을 확인했다.
- Gate 4 전체 시스템: `.venv\\Scripts\\python.exe -m pytest -q`는 tool timeout을 피해 별도 프로세스로 끝까지 확인해 `700 passed, 1 warning in 160.49s`였다. `npm --prefix apps/web test`는 `102 passed`, `npm --prefix apps/web run build`는 성공했다. frontend test의 `act(...)` warning과 error-boundary test의 의도된 error console은 exit 0이며 새 release blocker가 아니라 test hygiene minor로 남긴다.
- Gate 5 문서·지침: 최신 authoritative pointer를 이 section으로 이동했고 protocol·운영 규정·historical QA log를 분리했다.
- Gate 6 파일 정리: `artifacts/`는 약 1GB의 QA/reproduction evidence이므로 보존하고 `.gitignore`에 명시했다. 비-artifact backup/tmp/orig/rej/pyc 후보는 없었고 `safe-to-delete` 0건이므로 삭제하지 않았다. `git check-ignore`로 artifacts exclusion을 확인했다.
- 현재 live diagnostics: CapCut `8.9.1.3802`, supported `true`, project root exists `true`, write access `true`, status `ready`.
- closeout 직전 Git 상태: `git diff --check` clean, upstream divergence `0/0`. commit 대상 외 artifact untracked 항목은 `.gitignore`로 숨겨져 있다.

다음 권장 작업:

- 새 기능보다 human acceptance 2건(실제 사용자 녹음 listening approval, 일반 사용자 PC의 CapCut handoff diagnostics)을 수행한 뒤, 현 release audit protocol을 다시 적용해 운영 배포 판단을 내린다.

## 228. 2026-07-13 long-form CapCut 3/3 final-render operating QA closeout

실제 CapCut Desktop `8.9.1.3802`에서 VideoBox long-form fixture `loop`, `crop_pad_overlay`, `audio_ducking` 3개를 모두 1080P/H.264/MP4/24fps로 local MP4 export했다. 이 QA는 draft open/editability가 아니라 final MP4까지 생성됐다는 운영 증거다.

- `loop`: `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Videos\\videobox-qa-loop-20260712.mp4`; FFprobe `600.026848` seconds, `73,526,175` bytes, SHA-256 `3DF607575BE81F1FD0050F1635B831E1C71D7DB6C7DA45E933D7848C23DF53F8`.
- `crop_pad_overlay`: `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Videos\\videobox-qa-crop-pad-overlay-20260712.mp4`; FFprobe `600.026848` seconds, `25,452,146` bytes, SHA-256 `839F83D911384B1BE72B8D983DA7AC16E34221CCE505935A0E31F8394187043B`. Inspector/timeline에서 10:00:00, caption, image/text overlay, B-roll crop/pad black-pad track을 확인했다.
- `audio_ducking`: `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Videos\\videobox-qa-audio-ducking-20260712.mp4`; FFprobe `600.026848` seconds, `73,882,181` bytes, SHA-256 `B23B2D7E7DDC01D3BDD0F49B11126EC80BA8CF90E3349F2DC29BC6AE72EAA11B`. Inspector/timeline에서 10:00:00, narration/TTS, `smoke-bgm.wav`, `smoke-impact.wav` track을 확인했다.
- 두 신규 export의 CapCut 완료 화면은 모두 `동영상이 데스크톱이나 노트북에 저장됐습니다`를 표시했다. export 중 오류, missing asset, UI option drift는 발생하지 않았다.
- CapCut video output은 개발 머신 local path이고 Git에 넣지 않는다. VideoBox source artifact도 수정하지 않았다.

다음 권장 작업:

- 3/3 CapCut final-render proof와 handoff diagnostics가 닫혔으므로, 다음 우선순위는 새 기능이 아니라 실제 사용자 녹음의 human listening approval과 일반 사용자 PC 1대의 handoff diagnostics smoke다. 이 두 항목은 자동화로 대체하지 않는 운영 acceptance 범위다.

## 227. 2026-07-13 CapCut handoff diagnostics closeout

CapCut handoff를 시도하기 전 PC 준비 상태를 확인하는 별도 read path를 추가했다. 이 진단은 source draft, export artifact, registered project copy를 읽거나 변경하지 않으며 CapCut app도 실행하지 않는다. write access는 실제 ACL 신뢰성을 위해 즉시 삭제되는 temporary file probe로만 검사한다.

- API: `GET /api/capcut/handoff-diagnostics`는 highest detected version의 `CapCut.exe` path/version, expected local project root, root existence, write access, status, Korean recovery message, checked time을 반환한다.
- failure: CapCut 미설치면 설치 확인, local project root 미생성이면 CapCut 1회 실행, 권한/디스크 문제면 project root 권한·공간 확인이라는 한글 복구 안내를 반환한다. handoff registration 자체는 수행하지 않는다.
- deterministic test: `create_app`은 injected `CapCutHandoffService(local_app_data=...)`로 fake Windows path를 사용하며 localhost LLM과 현재 PC CapCut을 호출하지 않는다.
- UI: `CapCut 연결 진단` 카드는 ready일 때 설치 버전/경로/project root/write result를, failed일 때 복구 안내와 `다시 진단` 버튼을 보여준다. initial load와 retry, page reload contract를 frontend test로 고정했다.
- live proof: 현재 Windows에서 `8.9.1.3802`, `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Apps\\8.9.1.3802\\CapCut.exe`, expected project root 존재, write access `true`, status `ready`를 확인했다.
- verification: focused backend `16 passed`, focused CapCut frontend `7 passed`, full Python 3.12 backend `698 passed`, frontend `101 passed`, production build success. `git diff --check` clean이며 `artifacts/`는 untracked로 유지한다.

다음 권장 작업:

- 제품 기능 확대보다 실제 운영 증거를 강화하는 것이 맞다. `crop_pad_overlay`, `audio_ducking` 두 600초 fixture를 CapCut에서 실제 MP4까지 export해 3/3 final-render proof를 닫는 QA slice를 우선한다.

## 226. 2026-07-12 CapCut local-project handoff registration closeout

VideoBox 원본 `draft_content.json`은 수정하지 않는다. `CapCutHandoffService`가 `%LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft\\videobox-<export_id>`에 별도 copy만 등록한다.

- 지원 범위는 `%LOCALAPPDATA%\\CapCut\\Apps` 아래 `CapCut.exe`가 있고, local project root가 존재하며 쓰기 가능한 Windows CapCut Desktop이다. CapCut 미설치, project root 미발견, 권한 거부는 각각 복구 안내가 포함된 failed handoff 상태로 저장한다.
- 완전한 destination은 idempotent하게 재사용하고, 불완전 destination과 임시 copy 실패는 안전하게 제거한다. source artifact, artifact export, 이전 failure reason은 덮어쓰지 않는다.
- API는 handoff source URI, registered path, ready/failed, error message, registration timestamp, reused 값을 persisted export metadata로 읽고 쓴다. create_app tests에는 injected `CapCutHandoffService(local_app_data=...)`를 써 실제 localhost LLM이나 로컬 CapCut 환경에 의존하지 않는다.
- 웹은 ready path와 실패/재시도, 새로고침 복구를 2개 contract UI test로 고정했다. 실패 시 `CapCut 등록 실패`와 복구 사유, `CapCut 등록 다시 시도`를 노출하면서 기존 draft artifact/error card를 유지한다.
- 실제 proof: 기존 VideoBox 600초 Korean loop draft를 handoff service로 등록했다. 첫 등록은 `ready/reused=False`, 두 번째는 `ready/reused=True`였고 registered path에 `draft_content.json`이 존재했다. CapCut Desktop에서 검색 후 `videobox-handoff-loop-20260712`을 열어 해당 registered path와 10분 timeline/한국어 caption/오디오 track을 확인했다. 이 과정에서 수동 project-folder copy는 하지 않았다.
- verification: focused backend `18 passed`, full Python 3.12 backend `693 passed`, frontend `99 passed`, production build 성공. `git diff --check` clean; `artifacts/`는 untracked로 유지한다.

다음 권장 작업:

- 기능을 더 넓히기보다, 실행 중이 아닌 사용자 PC와 CapCut 버전 변화를 실제 환경에서 확인할 수 있도록 handoff diagnostics 화면(설치 경로/쓰기 상태/복구 안내)을 먼저 추가한다. 실제 3개 fixture final MP4 3/3 증적 확장은 그 다음 운영 QA로 분리한다.

## 225. 2026-07-12 actual CapCut Desktop operating QA closeout

CapCut Desktop `8.7.0.3685`에서 long-form 600초 real draft 3개를 실제로 열어 운영 QA를 수행했다. VideoBox artifact 원본은 수정하지 않았고, CapCut이 인식하는 로컬 project root에 아래 QA 복사본을 만들었다.

- `videobox-qa-crop-pad-overlay-20260712`
- `videobox-qa-audio-ducking-20260712`
- `videobox-qa-loop-20260712`

실제 open 결과:

- `crop_pad_overlay`: project path가 CapCut inspector에 표시됐고 10:00:00 타임라인이 열렸다. 한국어 첫/최종 자막, `SMOKE IMAGE OVERLAY`/`SMOKE OVERLAY`, 이미지 asset, `videobox_black_pad_*` material 두 구간을 확인했다. 이는 crop + `trim_start_sec=0.2` + pad contract가 CapCut timeline surface까지 전달된 증거다.
- `audio_ducking`: 10분 narration/TTS, `smoke-bgm.wav`, `smoke-impact.wav`의 별도 audio track이 모두 열렸다. native ducking automation은 CapCut draft에 존재하지 않으므로 수동 후처리 필요 warning이 여전히 정당하다.
- `loop`: 10분 B-roll timeline clip, 한국어 자막/`SMOKE OVERLAY`, narration/TTS/SFX가 열렸고 video clip inspector도 표시됐다. loop fixture의 desktop draft open이 확인됐다.

수동 export 증적:

- `loop` draft에서 CapCut export dialog를 열어 1080P, H.264, MP4, 24fps, 10분 0초/예상 548MB 설정을 확인한 뒤 실제 export를 실행했다.
- CapCut 완료 화면의 `동영상이 데스크톱이나 노트북에 저장됐습니다`를 확인했고, output은 `C:\\Users\\atgro\\AppData\\Local\\CapCut\\Videos\\videobox-qa-loop-20260712.mp4`다.
- FFprobe: duration `600.026848` seconds, size `73,526,175` bytes; SHA-256 `3DF607575BE81F1FD0050F1635B831E1C71D7DB6C7DA45E933D7848C23DF53F8`.
- `crop_pad_overlay`와 `audio_ducking`도 CapCut editor의 export button/dialog가 열리는 것을 확인했지만, 중복 10분 MP4 생성은 하지 않았다. 따라서 두 project는 *export-ready UI 확인*, loop는 *실제 local MP4 완료*로 구분한다.

사용성/복구 판정:

- output artifact path는 VideoBox UI에서 표시·복구하도록 이미 계약화돼 있고, 이번 3개 CapCut open에서는 missing asset/failure가 발생하지 않았다. 따라서 genuine Desktop failure 뒤 VideoBox retry 흐름은 이번 수동 QA에서 재현하지 않았으며, API/UI null artifact·error_message·retry 계약은 `## 224`의 자동 test 증적으로만 확인됐다.
- `CapCut에서 후처리 필요`라는 한국어 heading은 ducking이 오류가 아니라 수동 편집 항목이라는 목적을 전달한다. 다만 현재 persisted ducking detail은 영어 원문이라, 한국어 사용자에게 실행 지시까지 완결하려면 known warning의 한국어 설명/행동 지시를 추가하는 것이 다음 UX 보강 사항이다.
- 현재 handoff는 CapCut default project root에 draft directory를 등록해야 열렸다. VideoBox에서 이 복사/등록을 자동화하지 않으므로, 실제 사용자 배포 전에는 `CapCut project folder에 복사` 안내 또는 one-click handoff를 제품화해야 한다.

제한:

- Desktop CapCut에서 원본 VideoBox artifact를 직접 double-click/import하는 경로는 확인하지 않았고, CapCut project root에 QA copy를 둔 방식만 확인했다.
- 세 fixture 각각의 최종 MP4를 모두 렌더한 것은 아니다. 실제 full export 완료 증적은 loop 1건이며, 3건 모두의 draft open/editability는 확인했다.
- QA output과 CapCut local project copy는 개발 머신 로컬 상태이며 Git에 포함하지 않는다.

다음 권장 작업:

- 기능을 넓히기보다 CapCut handoff registration 자동화와 persisted compatibility warning의 한국어 action copy를 작은 UX slice로 구현하고, crop/audio fixture도 실제 MP4 export까지 확장해 3/3 final render 증적으로 닫는다.

## 224. 2026-07-12 CapCut output observability and recovery UX closeout

CapCut real draft output의 관찰·복구 UX slice를 TDD로 완료했다.

- CapCut draft artifact contract은 persisted `notes`(compatibility warning)를 API response와 frontend type까지 보존한다.
- output panel은 artifact 경로, warning, nullable artifact 상태, 실제 실패 원인을 한글로 표시한다. warning은 오류 배너가 아니라 `CapCut에서 후처리 필요` 상태로 구분한다.
- 실패 상태에서만 `CapCut 초안 다시 시도` 버튼이 보이며, 최신 성공 artifact와 warning은 새로고침 뒤에도 jobs API에서 복구된다.
- failed job의 `error_message`는 pipeline read-path와 API response에서 누락되지 않게 보존했다.

검증:

- RED: 새로고침 뒤 warning 표시 요구 E2E가 UI 누락 상태에서 실패했다.
- focused: CapCut API/pipeline contract 8 passed, UI restore/failure boundary 2 passed.
- full backend: `.venv\\Scripts\\python.exe -m pytest -q` — Python 3.12, 683 passed, `python_multipart` PendingDeprecationWarning 1건.
- frontend: `npm --prefix apps/web test` — 97 passed; `npm --prefix apps/web run build` — success. ErrorBoundary intentional throw 및 기존 React `act(...)` stderr는 test failure가 아니다.
- `git diff --check` success. 기존 `artifacts/`는 생성 검증물로 Git에 포함하지 않는다.

진행률/다음:

- 상세 편집기 구현 계획 5개 Task는 기존대로 strict 100%, remaining 0%다. 이번 slice는 완료된 output recovery 범위의 관찰성 보강이다.
- 다음 권장 작업은 신규 편집 기능이 아니라 실제 CapCut desktop에서 기존 3개 10분 draft를 열고 warning 안내가 충분한지, asset path/overlay/한국어 typography/수동 export가 가능한지를 기록하는 운영 QA다.

## 223. 2026-07-12 long-form CapCut draft QA closeout

자동 CapCut draft QA slice를 완료했다. 이것은 CapCut desktop 앱을 열거나 조작하는 검증이 아니라, 실제 VideoBox API·FFmpeg·pycapcut draft artifact의 구조/경로/길이/경고를 3개 600초 fixture로 반복 검증하는 범위다.

- `loop`: 짧은 B-roll의 반복과 styled MP4/SRT/real draft를 검증한다.
- `crop_pad_overlay`: B-roll crop·trim·pad와 이미지·텍스트 overlay의 final MP4/draft 반영을 검증한다.
- `audio_ducking`: BGM/SFX gain·fade·ducking, 승인 개인 음성 TTS, CapCut ducking compatibility warning 영속화를 검증한다.
- runner: `scripts/verify-long-form-capcut-draft-qa.py`; fast-path: `./scripts/dev-fast-path.ps1 -Mode long-form-capcut-qa`.

검증 증적:

- loop final SHA-256 `448c74034c3981ff7aa5264d12655eba6096b1653261e93d1ffae41a26342f29`
- crop/pad/overlay final SHA-256 `f4d9826f9a8bcfafc9fb960209d6ba590e579b8a13d84efddca26032d05e8f7c`
- audio/ducking final SHA-256 `3d4291f1325bbc0e4449938bb84d4ff92793369c14112649fb999f7024ee2617`
- artifact root: `artifacts/long-form-capcut-qa/<profile>/`; 각 profile에 SRT, `output.mp4`, `draft_content.json`이 저장된다.
- audio fixture의 persisted warning: `ducking is not natively supported by CapCut draft export; apply it in CapCut after import`.

제한/다음 운영 QA:

- `desktop_capcut_opened`은 모든 manifest에서 명시적으로 `false`다. 자동화가 실제 CapCut desktop open/edit/export 성공을 주장하지 않는다.
- 남은 사람 작업은 CapCut desktop에서 위 3개 draft를 직접 열어 asset path, B-roll pad, overlay layout, 한국어 typography, ducking 안내 후 수동 편집/내보내기를 확인하는 것이다.
- 대용량 `artifacts/`는 Git에 포함하지 않는다.

## 222. 2026-07-12 detailed editor Task 5 closeout

상세 편집기 구현 계획의 Task 5, media controls·output error recovery·release evidence를 TDD로 완료했다. 이로써 `docs/superpowers/plans/2026-07-12-detailed-editor-upgrade-implementation.md`의 Task 1–5가 모두 완료됐다.

- BGM/SFX control은 `gain_db`, `fade_in_sec`, `fade_out_sec`, `ducking`을 정규화해 FFmpeg filter와 real CapCut draft audio segment에 동일하게 반영한다. CapCut이 native ducking을 지원하지 않는 한계는 draft warning으로 명시한다.
- B-roll control은 `fit/crop`, `loop`, `pad`, `trim_start_sec`을 정규화한다. loop 해제 뒤 짧은 source는 pad가 켜진 경우 FFmpeg black-frame pad와 project-local CapCut black pad material로 timeline window를 정확히 채우고, pad도 끈 경우에는 output 전에 복구 방법이 포함된 오류로 차단한다.
- 텍스트 overlay font와 B-roll/일반 media asset 누락은 FFmpeg 실행 전 사용자가 re-import/re-select 할 수 있는 메시지로 차단한다.
- preview/final/CapCut 실패는 nullable artifact를 안전하게 표시하고 재시도 동선을 제공한다. 마지막 성공 preview/final/CapCut artifact는 실패 뒤 유지되며, final/CapCut success job은 새로고침 뒤 jobs API에서 다시 복구한다.

검증:

- RED→GREEN 계약: `tests/test_media_controls.py`, `tests/test_ffmpeg_final_renderer.py`, `tests/test_pycapcut_adapter.py`, `apps/web/src/app.test.tsx`의 media control·missing font/media·failure/retry/reload 경로.
- full backend: `.venv\\Scripts\\python.exe -m pytest -q` — Python 3.12, 674 passed, warning 1건(`python_multipart` PendingDeprecationWarning).
- frontend: `npm --prefix apps/web test` — 96 passed; `npm --prefix apps/web run build` — success. 기존 ErrorBoundary intentional throw와 일부 React `act(...)` stderr는 test failure가 아니다.
- real smoke: `./scripts/dev-fast-path.ps1 -Mode smoke` — 600초 Korean ingest → edit → SRT → styled MP4 → real CapCut draft의 15개 checks 모두 true.
  - narration: `artifacts/task5-korean-600.wav`, SHA-256 `a0c7f05a7052be735dce56df38a45ae167a9b24cad122a3c518ef9025701ee0f`
  - SRT: `artifacts/task5-smoke/projects/projects/production-readiness-korean-smoke/subtitles/subtitle_001.srt`
  - final MP4: `artifacts/task5-smoke/projects/projects/production-readiness-korean-smoke/exports/final_render/export_001/output.mp4`, SHA-256 `448c74034c3981ff7aa5264d12655eba6096b1653261e93d1ffae41a26342f29`
  - real CapCut: `artifacts/task5-smoke/projects/projects/production-readiness-korean-smoke/exports/capcut_draft/export_002/timeline_002/draft_content.json`
  - warning: CapCut draft에서 ducking은 native control이 아니므로 CapCut import 뒤 적용하라는 compatibility warning을 반환한다.
- 대용량 `artifacts/task5-korean-600.wav` 및 smoke output은 Git에 포함하지 않는다.

진행률:

- 상세 편집기 구현 계획 5개 Task 중 Task 1–5 완료로 strict 100%, remaining 0%다.
- 다음 작업은 기능 구현이 아니라 실제 CapCut desktop에서 10분 프로젝트를 열고, ducking warning을 포함한 수동 open/edit/export UX QA를 3건 수행하는 운영 검증을 우선 권장한다.

## 221. 2026-07-12 detailed editor Task 4 closeout

상세 편집기 구현 계획의 Task 4, fixed-track timeline과 selected-range preview를 TDD로 완료했다.

- editing session은 구조 편집의 유일 SSOT다. segment split은 양쪽 0.2초 이상을 강제하고, merge는 목록상 인접하며 시간 경계가 맞닿은 경우만 허용한다. bounds 변경과 reorder relayout은 전체 overlap을 거부한다.
- split/merge는 caption, B-roll, BGM, SFX, TTS, overlay payload를 deep-copy하고 root/parent/source lineage와 media lineage를 남긴다. merge에서 하나의 legacy override 필드로 표현할 수 없는 미디어도 media lineage에서 잃지 않는다.
- undo/redo는 snapshot inverse/forward payload를 session JSON과 SQLite canonical snapshot에 보존하며 최근 100개 구조 편집만 유지한다. render/import audit event는 stack에 넣지 않는다. 모든 구조 mutation은 기존 CAS revision/409 recovery를 사용한다.
- UI/API는 narration, B-roll, BGM, SFX, overlay의 5개 고정 역할 track만 노출한다. 분할·인접 병합·앞/뒤 재배치·bounds·undo/redo와 선택 범위 미리보기를 제공한다. 미리보기에는 선택 범위 자막의 저장된 색상/크기 및 관련 overlay를 표시한다.
- `timeline_structure` partial regeneration field는 세션의 구조/순서/timing을 새 timeline build에 전달한다. 따라서 편집 세션의 구조 변경이 재생성 뒤 출력 timeline으로 이어진다.

검증:

- RED: domain 함수 부재 5건, persistence undo stack 부재, API split route 404, structural regeneration field 미지원, fixed-track UI 부재를 먼저 재현했다.
- focused: `.venv\\Scripts\\python.exe -m pytest tests\\test_editor_timeline_mutations.py tests\\test_editing_session.py -q` — 47 passed (known Starlette PendingDeprecationWarning 1건).
- full backend: `.venv\\Scripts\\python.exe -m pytest -q` — Python 3.12, 665 passed (동일 경고 1건).
- frontend: `npm --prefix apps/web test` — 95 passed; `npm --prefix apps/web run build` success.
- `git diff --check` success.

진행률:

- 상세 편집기 구현 계획 5개 Task 중 Task 1–4 완료로 strict 80%, remaining 20%다.
- 다음 Task는 media controls, output error recovery, release evidence를 다루는 Task 5다.

## 220. 2026-07-12 detailed editor Task 3 closeout

상세 편집기 구현 계획의 Task 3, preset/favorites/browser recovery를 TDD로 완료했다.

- built-in caption preset은 불변이며 project/global snapshot은 project artifact 밖 `videobox-user-library/user_library.json`에 저장된다. 최근 preset도 재시작 뒤 보존한다.
- favorite은 idempotent PUT이며 preset은 `project:<project_id>:<preset_id>`, local B-roll은 `pack:local:<asset_id>` canonical ID를 사용한다.
- 편집 화면은 preset/최근 항목, 즐겨찾기 토글, scope preflight와 명시적 적용 확인을 제공한다. preset/scope 변경 뒤 800ms debounce로 영향을 다시 계산한다.
- 409은 latest session을 안내하고, 사용자가 최신 내용을 적용하면 직접 수정한 draft field와 해당 선택 segment를 보존한다. 누락 preset/B-roll은 명확한 오류 문구로 표시한다.

검증:

- RED: UserLibraryStore recent/global snapshot 부재, preset/B-roll favorite UI 부재, 409 latest-session draft 손실을 먼저 재현했다.
- focused storage/API: `.venv\\Scripts\\python.exe -m pytest tests/test_user_library_store.py tests/test_api_editor_favorites.py -q` — 4 passed (Starlette deprecation warning 1건).
- full backend: `.venv\\Scripts\\python.exe -m pytest -q` — Python 3.12, 657 passed (동일 경고 1건).
- frontend: `npm --prefix apps/web test` — 94 passed; `npm --prefix apps/web run build` success.
- `git diff --check` success.

진행률:

- 상세 편집기 구현 계획 5개 Task 중 Task 1–3 완료로 strict 60%, remaining 40%다.
- 다음 Task는 fixed-track timeline 및 selected-range preview를 다루는 Task 4다.

## 219. 2026-07-12 detailed editor Task 2 closeout

상세 편집기 구현 계획의 Task 2, revisioned caption style persistence와 scoped style API를 TDD로 완료했다.

- editing session은 SQLite `session_revision`과 canonical `session_json`을 함께 보존한다. 변경은 compare-and-swap으로 저장되며 stale 요청은 최신 session을 포함한 409으로 반환한다.
- caption style은 `current_caption`, `selected_captions`, `from_current`, `whole_project`, `project_default` scope를 preflight와 mutation에서 동일하게 해석한다. global/default scope의 무관한 segment ID와 알 수 없는 style 필드는 422으로 거부한다.
- invalid style은 revision과 저장 payload를 변경하지 않는다. DB snapshot은 JSON cache write 실패 뒤에도 reload에서 복구된다.
- partial caption regeneration은 stale revision에서 새 timeline을 최신 수동 자막/스타일에 연결하지 않고 conflict를 반환한다. restart/reload 및 manual caption/style 보존 계약을 테스트로 고정했다.
- 실제 웹 편집기는 모든 PATCH/DELETE/partial regeneration 요청에 현재 `editingSession.session_revision`을 전달하며, 409 body는 `ApiConflictError.latestSession`으로 보존한다.

검증:

- RED: caption-style API, stale CAS, invalid style, DB/JSON recovery, partial regeneration conflict, unknown style/scope를 먼저 재현했다.
- focused/backend API: `.venv\\Scripts\\python.exe -m pytest tests\\test_api.py -q` — 394 passed (Starlette deprecation warning 1건).
- full backend: `.venv\\Scripts\\python.exe -m pytest -q` — Python 3.12, 653 passed (동일 경고 1건).
- frontend: `npm --prefix apps/web test` — 90 passed; `npm --prefix apps/web run build` success.
- `git diff --check` success.

진행률:

- 상세 편집기 구현 계획 5개 Task 중 Task 1–2 완료로 strict 40%, remaining 60%다.
- 다음 Task는 preset/favorites/409 UI recovery를 다루는 Task 3이다. 현재 409 payload 보존은 완료됐지만, Task 3의 사용자 preset·즐겨찾기·복구 UI는 아직 시작하지 않았다.

## 218. 2026-07-12 detailed editor Task 1 closeout

상세 편집기 구현 계획 `docs/superpowers/plans/2026-07-12-detailed-editor-upgrade-implementation.md`의 Task 1 자막 스타일 출력 수직 슬라이스를 TDD로 완료했다.

- editing session의 `caption_style`은 project JSON 저장과 저장소 재조회에서 유지된다.
- `subtitle.srt`는 기존 text/timing artifact로 유지하고, 새 `caption.ass`는 스타일 전용 artifact로 생성한다.
- FFmpeg final renderer는 ASS가 주어지면 libass burn-in MP4를 만들고 selectable subtitle stream을 mux하지 않는다.
- real pycapcut draft는 SRT import 대신 caption별 `TextSegment`를 만든다. color, size, outline, background를 draft JSON에서 검증했고, `shadow_blur_px`는 `capcut_compatibility_warnings`로 명시한다.
- output pipeline은 현재 timeline과 일치하는 latest editing session만 FFmpeg/CapCut 출력에 전달한다. 다른 timeline session을 출력에 섞지 않는다.

검증:

- RED: 새 ASS/caption-style 모듈 부재와 pipeline 전달 부재를 각각 재현했다.
- focused backend: caption style, ASS, FFmpeg, real pycapcut, final-render pipeline, CapCut pipeline 24 passed.
- full backend: `.venv\\Scripts\\python.exe -m pytest -q`에서 642 passed, Python 3.12.
- frontend impact: `npm --prefix apps/web test` 88 passed; `npm --prefix apps/web run build` success.
- real output: black B-roll 위 styled ASS caption burn-in MP4와 real CapCut `draft_content.json`의 styled text material을 자동 테스트로 검증했다.

진행률:

- 상세 편집기 구현 계획은 5개 Task 중 Task 1 완료로 strict 20%, remaining 80%다.
- 기존 production-readiness 39 milestone 진행률은 이 별도 확장 작업 때문에 재산정하지 않는다. 현재 남은 editor Task 2는 revisioned style mutation/API와 scope preflight다.

## 217. 2026-07-11 production-readiness blocker slice 1 closeout

이번 closeout의 기준 문서는 `docs/superpowers/plans/2026-07-11-production-readiness-blocker-slice-1.md`다. six blocker와 Task 1–9를 실제 worktree 기준으로 닫았다.

- first-project onboarding은 프로젝트 생성 후 narration/script 등록을 독립 상태로 처리한다. 부분 실패는 생성된 프로젝트를 되돌리지 않고 해당 소스만 retry한다.
- assetless BGM은 timeline media clip으로 자동 적용하지 않는다.
- final render와 real CapCut draft failure는 nullable artifact/error message로 API와 UI에 전달되고 ErrorBoundary가 예외 render를 격리한다.
- partial caption의 `caption_segments`는 candidate timeline, SRT, final subtitle input까지 유지된다.
- short B-roll/TTS는 FFmpeg에서 loop/pad/trim하며 real CapCut draft에는 B-roll 반복과 project-local persistent silence material로 target duration을 유지한다.
- `export_overlays`는 FFmpeg real frame(text/image)과 real CapCut draft text/image material에 반영된다.

검증:

- frontend `npm test -- --run`: 82 passed; `npm run build`: success.
- backend `.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider`: Python 3.12.10, 621 passed.
- Korean 600초 real smoke: fixture SHA-256 `a0c7f05a7052be735dce56df38a45ae167a9b24cad122a3c518ef9025701ee0f`, final MP4 600.000초 SHA-256 `45e430cae559e94b0b62eb2bf5f8178f74c0472a9fbadebb134ccb9bf9425c79`, ingest/edit/SRT/MP4 9개 checks 모두 true.
- 대용량 Korean WAV/MP4 smoke artifact는 Git에 포함하지 않는다.

전체 implementation milestone 39개 재판정: 완료 36, 부분 3, 미구현 0. strict `92.3%`, partial=0.5 weighted `96.2%`, weighted remaining `3.8%`. 부분 항목은 personal voice clone 품질, SFX 추천/선택, 실제 장기 프로젝트의 사람 검수 UX다.

다음 goal은 personal voice TTS acceptance, SFX real-asset 계약, 또는 다중 10분 프로젝트의 수동 CapCut QA 중 하나를 독립 slice로 선택한다.

## 216. 2026-07-07 output readiness UI closeout

이번 slice의 제품 결정은 `출력 가능 여부를 개요 화면에서 바로 보이게 한다`다.

확정된 기준은 아래다.

- output readiness UI는 새 truth를 만들지 않고 기존 `reviewSnapshot`과 `timeline`의 blocker/approval 상태만 읽는다.
- approved + blocker 없음이면 `내보내기 가능`과 다음 행동을 보여준다.
- blocker 없음 + 미승인이면 `승인 필요`와 `타임라인 승인` 다음 행동을 보여준다.
- blocker가 남아 있으면 `내보내기 보류`, 검수 표시 수, 대기 추천 수, 검수 탭 처리 안내를 보여준다.
- 타임라인/검수 데이터가 없으면 준비 확인 불가 상태로 둔다.

검증 결과는 아래다.

- `apps/web/src/App.tsx`의 출력 카드에 readiness banner를 추가했다.
- `apps/web/src/app.test.tsx`는 blocked / draft / approved 세 상태의 readiness 문구를 검증한다.
- `apps/web/src/styles.css`는 readiness 상태별 표시 스타일만 추가했다.
- 검증: exact RED 확인 후 GREEN 3 passed, `npm run test:focused` 75 passed, `npm run build` 통과, `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` 25 passed, `./scripts/dev-fast-path.ps1 -Mode output-gating` 24 passed.
- 전체 backend regression `py -m pytest -q`는 이번 turn에서 재시도하지 않았고, 전체 통과로 주장하지 않는다.

## 211. 2026-07-06 웹 대시보드 한글 표시 정책 closeout

이번 slice의 제품 결정은 `화면은 한글 우선, 추적값은 원문 유지`다.

확정된 기준은 아래다.

- 프로젝트명, 세그먼트 문장, 자산명, 파일명, 태그, 추천 이유, 검수 메시지는 웹 UI 표시 계층에서 한글 표시명 또는 한글 요약을 우선 사용한다.
- DB 원본 데이터는 변경하지 않는다.
- `asset_id`, `job_id`, `timeline_id`, `recommendation_id`, 모델명, `local://`/storage URI는 추적성과 디버깅 때문에 원문을 유지한다.
- 사용자 입력 form 값은 저장 원문을 유지하고, 읽기 화면/목록/카드/버튼 접근성 이름에만 한글 표시 helper를 적용한다.

검증 결과는 아래다.

- `apps/web/src/App.tsx`에 표시 전용 formatter를 추가해 B-roll picker, review snapshot, editing selected segment, Gemini key card의 서버 데이터 표시명을 한글화했다.
- `apps/web/src/app.test.tsx`의 focused frontend test를 한글 표시 정책 기준으로 갱신했다.
- `docs/implementation-plan.ko.md`의 `웹 대시보드 표시 언어 기준`을 원문 보존 정책에서 `화면 한글 우선 + 추적값 원문 유지` 정책으로 갱신했다.
- 검증: `npm run test:focused` 71 passed, `npm run build` 통과, 브라우저 smoke에서 개요/타임라인/검수/편집/B-roll picker/제미나이 form 확인.

## 212. 2026-07-06 한글 UX 자연어 품질 closeout

이번 slice의 제품 결정은 `설명문보다 짧은 작업 단어`다.

확정된 기준은 아래다.

- 화면 제목은 `진행`, `키`, `추천`, `표시`, `편집기`, `변경`, `판단`, `상세`, `트랙`처럼 짧게 쓴다.
- 추천 근거는 `키워드`, `매칭 태그`, `자산 태그` 같은 설명형 라벨보다 `사무실`, `사무실 · 팀`, `매칭`, `태그`처럼 즉시 읽히는 단어를 우선한다.
- B-roll title/tag fallback은 token 기반 표시 helper로 일반화한다.
- `asset_id`, `clip_id`, `seg_*`, `rec_*`, `job_id`, `timeline_id`, `local://`, 모델명, ISO 시간은 원문을 유지한다.
- DB 원본 데이터와 입력 form 값은 변경하지 않고, 읽기 화면/목록/카드/버튼 접근성 이름에만 표시 변환을 적용한다.

검증 결과는 아래다.

- `apps/web/src/App.tsx`의 표시 helper가 알려진 단어와 token fallback을 함께 처리한다.
- `apps/web/src/app.test.tsx`는 짧은 한글 표시 정책과 ID/URI/secret 원문 보존을 함께 검증한다.
- 검증: `npm run test:focused` 71 passed, `npm run build` 통과.
- 브라우저 smoke: 개요/타임라인/검수/편집/B-roll picker/제미나이 form 확인. 콘솔 오류는 favicon 404만 확인됐다.

## 213. 2026-07-06 B-roll thin editor polish closeout

이번 slice의 제품 결정은 `선택 결과를 picker 밖에서도 바로 보이게 한다`다.

확정된 기준은 아래다.

- B-roll picker는 유지한다.
- 선택된 B-roll은 별도 `선택 B롤` 요약으로 이름, `asset_id`, 태그를 함께 보여준다.
- 상단 세그먼트 요약은 raw ID 반복 대신 `B롤 선택됨`으로 줄인다.
- B-roll 가져오기 성공 시 `가져옴 N개` 또는 `보관함 N개`를 짧게 보여준다.
- 가져오기 실패 메시지는 기존처럼 `B롤 가져오기 실패` 중심으로 유지한다.
- DB 원본 데이터와 수동 `asset_id` 입력 경로는 변경하지 않는다.

검증 결과는 아래다.

- `apps/web/src/App.tsx`에 B-roll 표시 label helper, 선택 요약, 가져오기 성공 메시지를 추가했다.
- `apps/web/src/app.test.tsx`는 선택 요약과 가져오기 성공 후 picker 갱신을 검증한다.
- 검증: `npm run test:focused` 71 passed, `npm run build` 통과.
- 브라우저 smoke: 편집 탭에서 `선택 B롤` 요약, B-roll picker, 기본 폴더 가져오기, `가져옴 1개`, 새 picker option 반영 확인. 콘솔 오류는 favicon 404만 확인됐다.

## 214. 2026-07-06 B-roll library scale UX closeout

이번 slice의 제품 결정은 `자산이 늘어나면 select만으로는 부족하다`다.

확정된 기준은 아래다.

- B-roll picker와 수동 `asset_id` 입력은 유지한다.
- picker 앞에 `B롤 검색` 입력을 추가한다.
- 검색 대상은 표시명, 태그, `asset_id`로 제한한다.
- 검색 결과 수는 `보임 N/M`으로 짧게 보여준다.
- 현재 선택된 B-roll은 검색 결과 밖이어도 선택 상태와 요약 카드에서 유지한다.
- DB 원본 데이터는 변경하지 않고 웹 UI 상태만 추가한다.

검증 결과는 아래다.

- `apps/web/src/App.tsx`에 B-roll 검색 상태, 필터링된 asset option, 결과 수 표시를 추가했다.
- `apps/web/src/app.test.tsx`는 표시명/태그/`asset_id` 검색과 필터 후 저장 흐름을 검증한다.
- 검증: `npm run test:focused` 72 passed, `npm run build` 통과.
- 브라우저 smoke: 편집 탭에서 `B롤 검색`, `보임 7/7`, `팀` 검색 후 `보임 1/7`, 검색 결과 선택, `B롤 저장`, 선택 요약 갱신 확인. 콘솔 오류는 favicon 404만 확인됐다.

## 215. 2026-07-06 편집 저장 피드백 UX closeout

이번 slice의 제품 결정은 `저장 버튼은 누른 뒤 바로 결과를 보여준다`다.

확정된 기준은 아래다.

- 자막, 컷, B롤, 음악, 설명, 이미지, 표, TTS 저장/해제/삭제 mutation은 공통 저장 helper에서 짧은 성공/실패 메시지를 보여준다.
- 성공 메시지는 `자막 저장됨`처럼 항목명과 저장 결과만 보여준다.
- 실패 메시지는 `자막 저장 실패`, `B롤 해제 실패`처럼 항목명과 동작을 앞에 두고 API 오류 내용을 뒤에 붙인다.
- DB 원본 데이터, 저장 API, editing session 갱신, partial regeneration invalidation 흐름은 변경하지 않는다.

검증 결과는 아래다.

- `apps/web/src/App.tsx`에 편집 저장 피드백 상태와 mutation key 기반 표시 label helper를 추가했다.
- `apps/web/src/app.test.tsx`는 저장 성공 메시지와 저장 실패 메시지를 검증한다.
- 검증: `npm run test:focused` 74 passed, `npm run build` 통과.
- 브라우저 smoke: 편집 탭에서 자막을 저장한 뒤 `자막 저장됨` 노출과 재생성 타임라인 무효화 확인. 콘솔 오류는 favicon 404만 확인됐다.

## 1. 결론

현재 개발은 계획서에서 크게 새지 않았다.
그리고 `경량 후편집기 UI`가 아니라 `편집 세션 기반`으로 먼저 가야 한다는 방향도 실제 코드로 반영됐다.

현재까지 반영된 핵심은 아래다.

- `editing session` 모델
- 수정 저장 구조
- 수정 API
- 부분 재생성 규칙
- 설명 카드 / 이미지 / 표 편집 mutation
- TTS replacement 선택 / 해제 mutation

## 2. 확인된 사실

현재 기준 아래는 코드와 테스트로 확인됐다.

- 로컬 프로젝트/자산/job 저장 구조 존재
- segment analysis 파이프라인 존재
- transcript alignment 존재
- B-roll 추천과 음악 추천 존재
- timeline 생성과 review approval 존재
- subtitle render, preview render, CapCut export 존재
- Local Qwen 우선 + Gemini fallback runtime 존재
- editing session 생성/조회 존재
- caption / cut / B-roll / visual overlay / music override 수정 API 존재
- explanation card / image overlay / table overlay / TTS replacement 수정 API 존재
- partial regeneration request contract와 explicit downstream rerun mapping 존재
- partial regeneration 실제 backend job 실행 존재
- 전체 테스트 `221 passed`

## 3. 아직 부족한 부분

아래는 다음 단계 전에 필요한 핵심 빈칸이다.

- TTS replacement의 baseline narration asset swap / preview/export 반영은 이미 연결되어 있고, 남은 일은 approval/review contract를 더 세분화하는 단계
- image/table/explanation 편집을 프런트 편집기 UI에서 직접 다루는 단계
- partial regeneration preflight의 비파괴 확인 경로는 이미 API와 UI에 노출되어 있고, 남은 일은 contract 세분화다
- 실제 오디오 치환 이후 review 승인과 export 반영 규칙을 더 세분화하는 단계

## 4. 왜 지금 UI부터 가면 안 되는가

UI부터 만들면 아래 문제가 바로 생긴다.

- 수정 결과를 어디에 저장할지 기준이 없다
- 부분 재생성을 어디까지 다시 돌릴지 합의가 없다
- 자막 수정, 컷 수정, B-roll 교체가 서로 다른 임시 구조로 흩어질 가능성이 크다
- 나중에 오픈소스 편집기 셸을 붙일 때 다시 뜯어고치게 된다

그래서 순서는 `편집 규칙 고정 -> 얇은 UI 검증 -> 필요 시 OSS 셸 반입`이 맞다.

## 5. 다음 구현 범위 고정

다음 goal은 아래 범위로 묶는 것이 맞다.

1. TTS replacement의 연결된 narration replacement baseline 위에 approval/review contract를 더 고정
2. review-required 상태에서 subtitle/preview/export가 어떻게 막히고 안내되는지 추가 경계를 더 고정
3. partial regeneration preflight의 API/UI 노출 이후 read-only contract와 resume/prediction 경계를 더 세분화
4. 얇은 내부 편집 UI에서 새 mutation을 직접 검증
5. 해당 범위 TDD 완료

## 6. 이번 단계에서 의도적으로 안 하는 것

- 풀 편집기 UI
- 오픈소스 편집기 통째 반입
- 고급 오디오 믹싱
- 색보정
- 자유 키프레임
- 프리미어급 멀티트랙 편집 기능

## 7. 구현 시작 조건

현재 브랜치/워킹트리 기준으로 바로 다음 goal 구현 시작 가능하다.
테스트 베이스라인은 안정적이고, 계획서 기준 다음 빈칸도 명확하다.

## 8. 2026-06-29 추가 검증 기록

이번 재검증에서 아래를 다시 확인했다.

- 전체 백엔드 회귀 테스트 `221 passed`
- blank caption 거부 동작 정상
- invalid partial regeneration request 거부 동작 정상
- unknown session segment / unsupported field 거부 동작 정상
- `editing_sessions` 저장/조회와 기존 프로젝트 self-heal 동작 유지
- explanation/image/table/TTS mutation API 정상
- image/table/visual overlay 삭제 경로 정상
- legacy `visual-overlay`가 다른 overlay 타입을 덮어쓰지 않도록 정리됨
- empty visual overlay state가 partial regeneration 결과에서 실제 clear로 반영됨

이번 재검증 기준 신규 치명 버그는 다시 확인되지 않았다.
다만 다음 구현 전 반드시 채워야 할 빈칸은 여전히 아래다.

- TTS replacement의 실제 narration/output 반영 이후 approval/review contract 세분화
- review-required TTS 흐름의 승인 후 적용 규칙
- 새 mutation을 직접 다루는 편집기 UI 검증

## 9. 외부 참고 후보 기록

당장 반입하지 않지만 나중에 다시 볼 가치가 있는 외부 레퍼런스는 아래처럼 기록해 둔다.

- `SamurAIGPT/AI-Youtube-Shorts-Generator`
  - 분류: `exclude for now`, `partial port candidate later`
  - 이유: 현재 VideoBox의 설명형/나레이션 편집 중심 구조와 직접 정합성이 낮고, shorts 추출기 성격이 강하다
  - 현재 판단: 이번 `editing session`/`partial regeneration`/`review` 마일스톤에는 반입하지 않는다
  - 재검토 시점: shorts 파생 기능 milestone
  - 참고 포인트: highlight scoring, vertical reframe/local crop pipeline

## 10. 2026-06-30 상태 갱신

이번 후속 작업으로 `thin internal editor mutation verification` 단계는 계획서 기준 완료로 봐도 된다.

현재 추가로 확인된 사실은 아래와 같다.

- thin editor에서 explanation / image / table / TTS clear/remove 경로가 직접 검증 가능
- clear/remove 이후 active candidate invalidation이 caption 외 mutation에도 회귀 테스트로 고정됨
- incomplete input에 대한 invalid-state visibility가 문구와 접근성 연결까지 포함해 고정됨
- mutation 저장/삭제 중에는 preflight / rerun 버튼이 잠겨 stale session race를 막음
- clear/remove 이후 실제 editor state 제거까지 테스트가 확인함
- frontend focused test `30 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. thin editor mutation happy-path save
2. thin editor clear/remove
3. active candidate invalidation
4. preflight-first gating 유지
5. resume/readability 관련 기존 계약 유지

현재 이 단계에서 다음 핵심 빈칸은 다시 아래로 정리된다.

- `latest editing session` 조회 실패를 너무 넓게 `null`로 삼키는 기존 복원 경로 리스크 점검
- 이후 main goal 측면에서는 TTS replacement baseline 연결 여부가 아니라, approval/output hardening과 더 상위 milestone 사이 우선순위 판단

## 11. 2026-06-30 resumed candidate restore visibility 완료 기록

이번 후속 작업으로 `resumed partial-regeneration candidate restore visibility` hardening은 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- refresh-resume 중 candidate result fetch 실패와 review snapshot fetch 실패가 더 이상 `그냥 resume candidate 없음`처럼 묻히지 않는다
- resumed preflight fetch 실패는 full editor failure가 아니라 제한된 degraded warning으로 분리된다
- stale restore warning이 target 변경, 새 preflight 요청, approval, reopen 이후 남지 않도록 정리됐다
- valid resume 동작과 기존 freshness gate / preflight-first / multi-segment readability 계약은 유지됐다
- frontend focused test `38 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. no resumable candidate / degraded resume / full candidate resume success 구분
2. resumed preflight limited degradation visibility
3. stale restore warning cleanup
4. 기존 refresh-resume 계약 회귀 유지

 현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 이번 브랜치의 상위 계획서 기준 다음 대형 goal 재선정
- refresh-resume보다 더 큰 제품 milestone로 넘어갈 때 필요한 다음 SSOT 문서 갱신

## 12. 2026-06-30 review snapshot to editing session handoff 기록

이번 후속 작업으로 `review snapshot -> editing session handoff`의 첫 실제 slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- review snapshot 세그먼트 카드에서 대상 세그먼트를 editing session으로 바로 열 수 있다
- pending recommendation 카드에서 현재 UI가 지원하는 recommendation type은 해당 rerun field로 바로 좁혀서 editor를 열 수 있다
- unsupported recommendation type은 강제 매핑하지 않고 세그먼트 기본 rerun scope로 fallback 한다
- review flag 카드에서 editor로 이동해도 기본 rerun scope를 덮어쓰지 않는다
- placeholder global review action 버튼은 이 단계에서 의도적으로 그대로 유지됐다
- frontend focused test `42 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot segment direct-open
2. pending recommendation -> mapped field narrowing
3. unsupported recommendation -> default rerun fallback
4. review flag -> default rerun preserve

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- thin editor 범위에서 아직 UI parity가 덜 채워진 `music override` 흐름 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 13. 2026-06-30 thin editor music override parity 기록

이번 후속 작업으로 `thin editor music override parity`의 첫 실제 slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- thin editor에서 music asset id를 직접 입력하고 저장할 수 있다
- incomplete music draft는 asset id가 들어오기 전까지 로컬 상태로만 남고 저장은 막힌다
- music override 저장 후 active candidate invalidation은 기존 mutation 흐름과 같은 규칙으로 유지된다
- 저장된 music override는 rerun scope에서 `music` field로 바로 보이고 preflight request에도 반영된다
- music override만 있는 후순위 세그먼트도 기본 editor focus 대상으로 잡힌다
- frontend focused test `44 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. thin editor music save
2. incomplete music local draft blocking
3. save 후 candidate invalidation
4. rerun scope music visibility
5. music-only later segment default focus

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review->editor recommendation mapping coverage 중 `broll` happy-path 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 44. 2026-07-04 timeline builder review snapshot legacy string false recommendation fields closeout

이번 후속 작업에서는 이미 닫힌 store fallback 경계를 다시 넓히지 않고, 그 바로 인접면인 `timeline_builder.build_review_snapshot()` direct dict 입력에서 legacy false-like recommendation payload가 applied truth를 pending blocker로 뒤집는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `build_review_snapshot(...)`는 direct dict recommendation 입력의 `auto_apply_allowed="true"` / `review_required="false"` 값을 raw `bool(...)`로 읽어 applied recommendation을 pending recommendation으로 잘못 분류하고 있었다
- strict TDD로 `test_timeline_builder_review_snapshot_treats_string_false_recommendation_fields_as_applied` exact regression을 먼저 추가했고, 실제로 `applied_recommendations == []` RED를 확인했다
- 구현 전에 검토한 `partial regeneration result` 후보 경계는 현재 코드 기준 이미 닫혀 있었고, 실제 runtime 반환 계약에 맞게 test setup을 보정한 뒤 exact regression이 바로 GREEN이었다
- 원인은 builder review snapshot read path가 upstream/store normalization을 재사용하지 않고 recommendation bool fields를 raw truthiness로 다시 판정하던 점이었다
- 최소 수정으로 `build_review_snapshot(...)`도 `_recommendation_payload(...)`를 거쳐 bool-ish normalization을 먼저 적용하도록 맞춰 legacy false-like recommendation fields를 canonical applied/pending truth로 분류하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder review snapshot truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder review snapshot bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder review snapshot direct dict 입력이 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` shape를 pending blocker로 오판하지 않음
2. applied recommendation truth가 builder review snapshot에서도 그대로 유지됨
3. builder review snapshot truth와 store fallback / API read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 112. 2026-07-04 partial regeneration trimmed BGM target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 인접한 partial regeneration runtime applied recommendation refresh family에서 stale whitespace BGM `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result bgm track에 stale clip과 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`가 stale applied recommendation 제거 시 `target_segment_id.strip()` 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration BGM refresh 제거 비교 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `2 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 111. 2026-07-04 partial regeneration trimmed B-roll target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 인접한 partial regeneration runtime applied recommendation refresh family에서 stale whitespace B-roll `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result broll track에 stale clip과 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_broll_refresh_step(...)`가 stale applied recommendation 제거 시 `target_segment_id.strip()` 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration B-roll refresh 제거 비교 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `3 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 110. 2026-07-04 partial regeneration trimmed TTS target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 partial regeneration runtime의 stale whitespace TTS `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result narration clip `asset_uri`가 stale generated TTS asset URI 그대로 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`가 stale applied recommendation 제거 시 `target_segment_id.strip()` 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration TTS refresh 제거 비교 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `3 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 109. 2026-07-04 timeline builder trimmed TTS target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 timeline builder consumer family에서 approved TTS recommendation의 stale whitespace `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 generated TTS asset이 아니라 original segment URI로 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `_recommendation_payload(...)`가 `target_segment_id`를 `strip()` 기준으로 정규화하도록 맞춰, segment bucket lookup과 applied recommendation surface가 같은 canonical id를 쓰게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder의 TTS target-segment matching 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip" -vv`
- focused verification
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip" -vv`
  - 결과 `3 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 108. 2026-07-04 TTS output trimmed target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 output consumer family에서 applied TTS recommendation의 stale whitespace `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover 첫 segment `source_uri`가 generated TTS asset이 아니라 original narration source로 남는 RED를 확인했다
- 최소 수정으로 `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 narration override segment set과 같은 규칙을 쓰는 `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 TTS segment set 모두 `str(...).strip()` 기준으로 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview/export TTS target-segment matching 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources" -vv`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources or test_capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement or test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources" -vv`
  - 결과 `5 passed`
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false or test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_target_segment_id_for_narration_source or test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source" -vv`
  - 결과 `4 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 107. 2026-07-04 output blocker detail trimmed pending identity closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 output blocker detail surface의 stale whitespace pending recommendation identity 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_output_blocker_detail_trims_pending_recommendation_identity_fields` exact regression을 먼저 추가했고, 실제로 preview render 차단 detail이 `tts_replacement: rec_tts_seg_001 @ seg_001 `처럼 raw whitespace를 노출하는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_normalized_runtime_pending_recommendations(...)`가 dedupe key만 trim하던 상태에서 blocker surface에 쓰는 `recommendation_id`, `target_segment_id`도 trim된 값으로 다시 써 주도록 좁혔다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output blocker detail surface 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_output_blocker_detail_trims_pending_recommendation_identity_fields" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_output_blocker_detail_trims_pending_recommendation_identity_fields or test_output_blocker_detail_canonicalizes_mixed_case_pending_recommendation_type or test_output_blockers_deduplicate_repeated_persisted_pending_recommendation_entries or test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline or test_approved_review_state_still_blocks_outputs_when_only_pending_recommendations_remain or test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail" -vv`
  - 결과 `6 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 177. 2026-07-06 capcut export adapter trims top-level subtitle file uri surface closeout

## 182. 2026-07-06 preflight request ignores non-dict session segments closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 이어지는 partial regeneration request / targeted-segment read-path의 non-dict session segment 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/editing_session.py`의 `build_partial_regeneration_request(...)`는 session `segments`를 모두 dict라고 가정한 set comprehension으로 `session_segment_ids`를 만들고 있어, stale 문자열 같은 non-dict session segment entry 하나만 있어도 preflight request preview가 `AttributeError`로 500 실패하고 있었다
- 같은 family의 `services/api/src/videobox_api/main.py` `_build_targeted_segments(...)`도 session `segments`를 dict라고 가정하고 있어, request builder를 통과하더라도 targeted-segment response surface에서 같은 stale shape에 다시 취약한 상태였다
- strict TDD로 `test_editing_session_api_ignores_non_dict_session_segments_in_preflight_fallback` exact regression을 먼저 추가했고, 실제로 source timeline fallback preflight 요청이 HTTP `500`과 `"'str' object has no attribute 'get'"` detail을 반환하는 RED를 확인했다
- 최소 수정으로 request builder의 `session_segment_ids`와 API targeted-segment lookup 모두 non-dict session segment를 먼저 건너뛰도록 맞춰, stale session junk는 무시하고 valid session segment만 기준으로 preflight request/response가 만들어지게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight request contract의 session-segment filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend preflight `59 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight request contract의 session-segment filtering 한 점 수정이라 exact + preflight-backend focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight request가 session `segments` 안의 stale non-dict entry 하나 때문에 500으로 중단되지 않는다
2. targeted session segment lookup과 response surface는 valid dict segment만 기준으로 동작한다
3. preflight contract가 source review-flag/pending-recommendation stale-shape 방어 다음 단계까지 같은 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 181. 2026-07-06 capcut export adapter ignores non-dict track clips closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 CapCut export adapter의 non-dict `tracks[].clips` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_promptable_tracks(...)`는 `clips`가 list이기만 하면 raw 리스트를 그대로 export track에 넘기고 있어, list 안에 stale 문자열 같은 non-dict clip entry가 섞여 있으면 voiceover/audio segment 생성 중 `clip.get(...)`가 터지고 export payload가 깨질 수 있었다
- strict TDD로 `test_capcut_export_adapter_ignores_non_dict_track_clips_in_voiceover_surface` exact regression을 먼저 추가했고, 실제로 `["stale_clip_entry", {...}]` 입력에서 `_build_clip_track(...)`가 `AttributeError`로 중단되는 RED를 확인했다
- 최소 수정으로 `_promptable_tracks(...)`가 dict clip만 `valid_clips`로 유지하도록 맞춰, stale non-dict clip entry는 건너뛰고 CapCut export payload가 canonical clip input만 기준으로 voiceover/video/audio segments를 만들게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 clip filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 clip filtering 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter는 `tracks[].clips` list 안의 stale non-dict entry 때문에 voiceover/audio segment 생성 중 예외로 중단되지 않는다
2. export payload의 voiceover/video/audio segments는 canonical dict clip만 기준으로 만들어진다
3. review/output gating 인접 export surface가 non-list clip container 방어 다음 단계까지 같은 stale-shape 방어 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 180. 2026-07-06 preview renderer ignores non-dict track clips closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 preview renderer의 non-dict `tracks[].clips` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 `_promptable_tracks(...)`는 `clips`가 list이기만 하면 raw 리스트를 그대로 preview payload/HTML 생성에 넘기고 있어, list 안에 stale 문자열 같은 non-dict clip entry가 섞여 있으면 narration source HTML 생성이 `AttributeError`로 깨지고 `clip_count`도 실제보다 크게 계산될 수 있었다
- strict TDD로 `test_preview_renderer_ignores_non_dict_track_clips_in_track_summary_surfaces` exact regression을 먼저 추가했고, 실제로 `["stale_clip_entry", {...}]` 입력에서 `player_html` 생성 중 `clip.get(...)`가 터지는 RED를 확인했다
- 최소 수정으로 `_promptable_tracks(...)`가 dict clip만 `valid_clips`로 유지하도록 맞춰, stale non-dict clip entry는 건너뛰고 preview payload `clips` surface와 narration source HTML이 canonical clip input만 기준으로 만들어지게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview renderer의 clip filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 clip filtering 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer는 `tracks[].clips` list 안의 stale non-dict entry 때문에 narration source HTML 생성 중 예외로 중단되지 않는다
2. preview payload의 `clip_count`와 HTML track summary는 canonical dict clip만 기준으로 계산된다
3. review/output gating 인접 preview surface가 non-list clip container 방어 다음 단계까지 같은 stale-shape 방어 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 179. 2026-07-06 review guidance ignores non-dict segments needing attention closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `Segments needing attention` segment input 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_segments_needing_attention(...)`는 `segments`를 모두 dict라고 가정한 list comprehension으로 순회하고 있어, stale 문자열 같은 non-dict segment entry 하나만 있어도 blocked guidance prompt 계산이 `AttributeError`로 깨지고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_non_dict_segments_needing_attention` exact regression을 먼저 추가했고, 실제로 `["stale_segment_entry", {"segment_id": "seg_001", "review_required": True}]` 입력에서 helper가 그대로 예외로 중단되는 RED를 확인했다
- 최소 수정으로 `_segments_needing_attention(...)`가 dict가 아닌 segment entry를 먼저 건너뛰도록만 맞춰, stale non-dict segment는 무시하고 실제 review-required segment id만 attention surface에 남게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance segment-attention helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance segment-attention helper 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 stale non-dict `segments` entry 하나 때문에 attention 계산 중 예외로 중단되지 않는다
2. `Segments needing attention` surface는 실제 review-required segment id만 남긴다
3. review/output gating 인접 guidance surface가 review-flags/pending-recommendations 다음 단계까지 같은 stale-shape 방어 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 178. 2026-07-06 output operator copy ignores non-dict track clips in prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `track_summary.clip_count` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 valid track의 `clips`가 list이기만 하면 `len(clips)`를 그대로 summary에 쓰고 있어, list 안에 stale 문자열 같은 non-dict clip entry가 섞여 있으면 실제 clip 수보다 큰 `clip_count`를 operator prompt에 노출하고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_non_dict_track_clips_in_prompt` exact regression을 먼저 추가했고, 실제로 `tracks[].clips = ["stale_clip_entry", {"clip_id": "clip_001"}]` 입력에서 prompt 본문에 `"'clip_count': 2"`가 그대로 남는 RED를 확인했다
- 최소 수정으로 track summary loop에서 dict clip만 `valid_clips`로 세도록 맞춰, stale non-dict clip entry는 건너뛰고 valid runtime clip만 기준으로 `clip_count`가 계산되게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 clip-count normalization 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 clip-count normalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 `tracks[].clips` list 안의 stale non-dict entry를 실제 clip count처럼 세지 않는다
2. approved preview/export guidance는 canonical dict clip만 기준으로 track summary를 만든다
3. review/output gating 인접 prompt surface가 non-list clip container 방어 다음 단계까지 같은 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, output family 안에서 CapCut export adapter의 top-level `subtitle_file_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 `capcut_tracks[].source_uri`와 별개로 top-level `subtitle_file_uri`는 raw 문자열 그대로 보존하고 있어, whitespace가 섞인 stale subtitle file uri가 export payload metadata surface에 그대로 노출되고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_top_level_subtitle_file_uri_surface` exact regression을 먼저 추가했고, 실제로 top-level `subtitle_file_uri`가 ` local://...subtitle_001.srt `처럼 padded/raw URI를 노출하는 RED를 확인했다
- 최소 수정으로 CapCut export adapter가 top-level `subtitle_file_uri`도 `strip()` 기준으로 정리한 뒤 같은 canonical 값을 subtitle track에도 넘기도록 맞춰, export payload metadata surface가 canonical subtitle uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 top-level subtitle file URI surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 top-level subtitle file URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export payload의 top-level subtitle metadata surface가 whitespace stale subtitle file uri도 canonical trimmed `subtitle_file_uri`로 노출한다
2. export payload의 subtitle metadata surface와 subtitle track surface가 같은 subtitle URI trim 기준으로 더 정렬됐다
3. 실제 subtitle file은 맞는데 top-level export payload metadata URI만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 176. 2026-07-06 capcut export adapter trims overlay text surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, output family 안에서 CapCut export adapter의 overlay text surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 `export_overlays[].text`를 필터링할 때만 trim 가능 여부를 보고, 실제 segment payload `text`에는 raw 문자열을 그대로 남기고 있어, whitespace가 섞인 stale overlay copy가 export payload의 visible text-track surface에 그대로 노출되고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_overlay_text_surface` exact regression을 먼저 추가했고, 실제로 overlay segment `text`가 `" Start strong "`처럼 padded/raw 문자열로 남는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 overlay text surface도 `strip()` 기준으로 정리해 내보내도록 맞춰, export payload text-track surface가 canonical overlay copy 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 overlay text surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 overlay text surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export payload의 overlay copy surface가 whitespace stale text도 canonical trimmed text로 노출한다
2. export payload의 narration/B-roll/subtitle/overlay type/overlay text surface가 같은 trim 기준으로 더 정렬됐다
3. 실제 overlay 내용은 맞는데 export payload copy만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 175. 2026-07-06 capcut export adapter trims overlay type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, output family 안에서 CapCut export adapter의 overlay type surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 `export_overlays[].overlay_type`를 필터링할 때만 trim 가능 여부를 보고, 실제 `track_name`과 segment payload `overlay_type`에는 raw 문자열을 그대로 남기고 있어, whitespace가 섞인 stale overlay type이 export payload의 visible text-track surface에 그대로 노출되고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_overlay_type_surface` exact regression을 먼저 추가했고, 실제로 canonical `hook_title` track이 생성되지 않고 raw `" hook_title "` track 이름으로만 남는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 overlay type surface도 `strip()` 기준으로 정리해 내보내도록 맞춰, export payload text-track surface가 canonical overlay type 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 overlay type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 overlay type surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export payload의 text-track surface가 whitespace stale overlay type도 canonical trimmed `track_name`과 `overlay_type`으로 노출한다
2. export payload의 narration/B-roll/subtitle/overlay surface가 같은 trim 기준으로 더 정렬됐다
3. 실제 overlay 내용은 맞는데 export payload track 이름만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 174. 2026-07-06 capcut export adapter trims subtitle source uri surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, output family 안에서 CapCut export adapter의 subtitle `source_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 `subtitle_file_uri`를 raw 문자열 그대로 `source_uri`에 넣고 있어, whitespace가 섞인 stale subtitle file uri가 export payload의 visible subtitle surface에 그대로 노출되고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_subtitle_source_uri_surface` exact regression을 먼저 추가했고, 실제로 subtitle track `source_uri`가 ` local://...subtitle_001.srt `처럼 padded/raw URI를 노출하는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 subtitle `source_uri`도 `strip()` 기준으로 정리해 내보내도록 맞춰, export payload surface가 canonical subtitle uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 subtitle source URI surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 subtitle source URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export payload의 subtitle surface가 whitespace stale subtitle file uri도 canonical trimmed `source_uri`로 노출한다
2. export payload의 narration/B-roll/subtitle surface가 같은 URI trim 기준으로 더 정렬됐다
3. 실제 subtitle file은 맞는데 export payload URI만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 173. 2026-07-06 capcut export adapter trims broll source uri surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output` 바로 인접 output family에서 CapCut export adapter의 B-roll `source_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_broll_track(...)`는 B-roll clip `asset_uri`를 raw 문자열 그대로 `source_uri`에 넣고 있어, whitespace가 섞인 stale asset uri가 export payload의 visible B-roll surface에 그대로 노출되고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_broll_source_uri_surface` exact regression을 먼저 추가했고, 실제로 B-roll 첫 segment `source_uri`가 ` local://...asset_001 `처럼 padded/raw URI를 노출하는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 B-roll `source_uri`도 `strip()` 기준으로 정리해 내보내도록 맞춰, export payload surface가 canonical asset uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 B-roll source URI surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 B-roll source URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export payload의 B-roll surface가 whitespace stale `asset_uri`도 canonical trimmed `source_uri`로 노출한다
2. export payload의 narration/B-roll surface가 같은 asset-uri trim 기준으로 더 정렬됐다
3. 실제 B-roll asset은 맞는데 export payload URI만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 172. 2026-07-06 capcut export adapter trims tts narration source uri surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 CapCut export adapter의 voiceover `source_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_clip_track(...)`는 approved TTS segment에 대해 narration clip `asset_uri`를 raw 문자열 그대로 `source_uri`에 넣고 있어, whitespace가 섞인 stale selected narration asset uri가 export payload의 visible voiceover surface에 그대로 노출되고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_tts_narration_source_uri_surface` exact regression을 먼저 추가했고, 실제로 voiceover 첫 segment `source_uri`가 ` local://...asset_tts_001.wav `처럼 padded/raw URI를 노출하는 RED를 확인했다
- 최소 수정으로 CapCut export adapter도 narration source URI를 `strip()` 기준으로 정리해 내보내도록 맞춰, export payload surface가 canonical selected narration uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export adapter의 TTS narration source URI surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 TTS narration source URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved TTS export voiceover surface가 whitespace stale `asset_uri`도 canonical trimmed narration source uri로 노출한다
2. TTS approval/output export payload surface가 preview/API/prompt 쪽 selected asset uri canonicalization 흐름과 더 일치하게 정렬됐다
3. 실제 approved narration source는 맞는데 export payload URI만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 154. 2026-07-04 heuristic review guidance default pending recommendation reason closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 heuristic review guidance fallback의 `reason` 없는 `pending_recommendations` default-reason surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder`는 valid pending recommendation에 `reason`이 없을 때 local-first prompt family나 API read-path default reason 기준과 달리 canonical default blocker message를 쓰지 않고, 더 약한 generic blocker 문구로 action item을 채우고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason` exact regression을 먼저 추가했고, 실제로 action item이 `Operator review required before approval or output.`가 아니라 `Resolve review blockers before approval.`로 내려오는 RED를 확인했다
- 최소 수정으로 heuristic fallback이 valid `pending_recommendations.recommendation_id/target_segment_id/recommendation_type`가 있고 `reason`만 비어 있는 경우에는 canonical default blocker message를 action item으로 채우도록 맞춰, runtime fallback guidance도 review/output gating과 API response 쪽 default blocker reason 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 heuristic review guidance fallback의 default-reason surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - `316 deselected`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic fallback pending-recommendation default-reason canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance fallback이 `reason` 없는 valid `pending_recommendations`에도 canonical default blocker message를 action item으로 surface한다
2. runtime fallback guidance가 missing reason pending recommendation을 generic blocker 문구로만 뭉개지 않는다
3. heuristic review guidance fallback의 pending-recommendation reason surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 163. 2026-07-06 review guidance prompt ignores unknown pending recommendation count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 review guidance prompt의 stale unknown `pending_recommendations` count surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `LocalFirstReviewGuidanceBuilder._build_prompt(...)`는 prompt row surface 자체는 filtering하면서도 `Pending recommendation count`는 raw 리스트 길이를 그대로 쓰고 있어, supported set 밖의 stale unknown recommendation 하나만 있어도 count가 `1`로 부풀려지고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` exact regression을 먼저 추가했고, 실제로 surface는 비어 있는데 prompt count만 `1`로 남는 RED를 확인했다
- 최소 수정으로 `_build_prompt(...)`도 filtered `review_flags` / `pending_recommendations` prompt row를 먼저 만든 뒤 count와 surface에 같은 값을 재사용하도록 맞춰, junk recommendation이 blocker count를 부풀리지 않게 정리했다
- 이번 focused verification은 review guidance prompt와 heuristic fallback의 인접 범위만 다시 돌렸다. helper의 backend output-gating 전체 lane은 이번 수정면보다 검증 범위가 넓어서 직접 인접한 exact/focused 테스트를 우선 사용했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 review guidance prompt의 pending-recommendation count surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count or test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_heuristic_review_guidance_builder_ignores_unknown_pending_recommendation_type or test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason" -vv` -> `5 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` -> `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt count surface 한 점 수정이라 exact + 같은 review guidance family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt는 unknown junk pending recommendation 때문에 `Pending recommendation count`를 부풀리지 않는다
2. review guidance prompt의 blocker count와 pending recommendation surface가 같은 filtered canonical 기준을 사용한다
3. review guidance prompt와 heuristic fallback이 junk pending recommendation 무시 기준에서 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 162. 2026-07-06 heuristic review guidance ignores unknown pending recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 heuristic review guidance fallback의 stale unknown `pending_recommendations.recommendation_type` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder.build(...)`는 raw `pending_recommendations` 리스트가 비어 있지 않기만 하면 blocked fallback 경로로 들어가서, supported set 밖의 stale unknown recommendation type 하나만 있어도 approved guidance를 blocked guidance로 뒤집을 수 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_ignores_unknown_pending_recommendation_type` exact regression을 먼저 추가했고, 실제로 `review_status="approved"`인데도 unknown pending recommendation 때문에 blocked summary가 내려오는 RED를 확인했다
- 최소 수정으로 heuristic fallback도 canonical blocker identity를 가진 review flag와 supported recommendation type을 가진 pending recommendation만 실제 blocker로 읽도록 좁혀, junk pending input은 무시하고 valid blocker truth만 guidance에 반영하게 정리했다
- 이번 focused verification은 review guidance fallback과 인접 prompt surface 범위만 다시 돌렸다. helper의 backend output-gating 전체 lane은 이번 수정면보다 검증 범위가 넓어서 직접 인접한 exact/focused 테스트를 우선 사용했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 heuristic review guidance fallback의 unknown pending-type blocker 판정 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_heuristic_review_guidance_builder_ignores_unknown_pending_recommendation_type" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_heuristic_review_guidance_builder_ignores_unknown_pending_recommendation_type or test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason or test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv` -> `5 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` -> `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic fallback unknown pending-type filtering 한 점 수정이라 exact + 같은 review guidance family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance fallback은 supported set 밖의 stale unknown pending recommendation type을 실제 blocker처럼 취급하지 않는다
2. approved guidance truth는 junk pending recommendation input 하나 때문에 blocked guidance로 뒤집히지 않는다
3. review guidance prompt와 heuristic fallback이 pending recommendation validity 판정에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 161. 2026-07-06 capcut export ignores unknown track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 CapCut export adapter의 stale unknown `track_type` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_promptable_tracks(...)`는 canonical empty `track_type`만 걸러서, supported set 밖의 stale unknown track도 export payload `tracks` surface에 그대로 올리고 있었다
- strict TDD로 `test_capcut_export_adapter_ignores_unknown_track_type_in_export_payload` exact regression을 먼저 추가했고, 실제로 `legacy_overlay` track이 export payload `tracks` 첫 항목에 그대로 남는 RED를 확인했다
- 최소 수정으로 CapCut export adapter도 supported runtime track type 집합 `narration/broll/bgm`만 promptable track으로 유지하도록 좁혀, unknown `track_type`는 export payload에서 건너뛰고 valid runtime track input만 manifest에 남기게 정리했다
- 이번 focused verification은 이 수정이 직접 닿는 export consumer family만 다시 돌렸다. helper의 output-gating backend lane은 이번 slice 변경면과 직접 연결되지 않아 재사용하지 않았다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 CapCut export adapter의 unknown runtime track surface 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_unknown_track_type_in_export_payload" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_unknown_track_type_in_export_payload or test_capcut_export_adapter_builds_structured_track_manifest_from_timeline_schema or test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track or test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface" -vv` -> `4 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` -> `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter unknown track filtering 한 점 수정이라 exact + 같은 export consumer family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter는 supported set 밖의 stale unknown `track_type`를 export payload `tracks` surface에 노출하지 않는다
2. CapCut export manifest는 supported runtime track type만 기준으로 source track 목록을 만든다
3. subtitle render / output operator copy / preview renderer / CapCut export adapter가 runtime track summary read-path에서 같은 supported track-type 기준으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 160. 2026-07-06 preview renderer ignores unknown track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 preview renderer의 stale unknown `track_type` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 `_promptable_tracks(...)`는 canonical empty `track_type`만 걸러서, supported set 밖의 stale unknown track도 preview payload `clips` surface와 HTML track summary에 그대로 올리고 있었다
- strict TDD로 `test_preview_renderer_ignores_unknown_track_type_in_track_summary_surfaces` exact regression을 먼저 추가했고, 실제로 `legacy_overlay` track이 preview payload `clips` 첫 항목과 HTML track summary에 그대로 남는 RED를 확인했다
- 최소 수정으로 preview renderer도 supported runtime track type 집합 `narration/broll/bgm`만 promptable track으로 유지하도록 좁혀, unknown `track_type`는 payload/HTML surface에서 모두 건너뛰고 valid runtime track summary만 남기게 정리했다
- focused verification에서 프로젝트 helper의 backend lane은 현재 환경에서 `pytest.exe` 실행이 애플리케이션 제어 정책에 막혀 실패했고, 같은 focused pattern을 `py -m pytest`로 직접 실행해 backend output-gating / preflight 검증을 이어갔다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 preview renderer의 unknown runtime track surface 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_ignores_unknown_track_type_in_track_summary_surfaces" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - backend preflight `59 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer unknown track filtering 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer는 supported set 밖의 stale unknown `track_type`를 preview payload `clips` surface에 노출하지 않는다
2. preview renderer는 supported runtime track type만 HTML track summary와 narration source 입력으로 사용한다
3. subtitle render / output operator copy / preview renderer가 runtime track summary read-path에서 같은 supported track-type 기준으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 159. 2026-07-06 output operator copy ignores unknown track type prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale unknown `track_type` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `track_type`이 비어 있지 않기만 하면 prompt track summary에 올리고 있어, supported set 밖의 legacy unknown track도 valid runtime track summary처럼 operator prompt에 섞여 들어가고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_unknown_track_type_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `legacy_overlay` track이 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 prompt track summary loop에서 supported runtime track type 집합 `narration/broll/bgm`만 유지하도록 좁혀, stale unknown `track_type`는 건너뛰고 valid runtime track summary surface만 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 output operator copy prompt의 unknown track-type 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - backend preflight `59 passed`
  - frontend preflight focused command exit code `0` 확인
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 unknown track-type 입력 경계 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 supported set 밖의 stale unknown track을 valid runtime track summary처럼 노출하지 않는다
2. approved preview/export guidance는 canonical runtime track type만 기준으로 track summary를 만든다
3. review/output gating 인접 prompt surface가 subtitle read-path의 unknown-track hardening과 같은 기준으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 158. 2026-07-06 subtitle segment order ignores unknown track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 직접 맞닿은 subtitle render segment-order read path의 stale unknown `track_type` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_segments_for_timeline(...)`는 `track_type`이 비어 있지 않기만 하면 subtitle segment order source로 읽고 있어, supported set 밖의 legacy unknown track도 실제 subtitle source track처럼 세그먼트 순서에 끼어들 수 있었다
- strict TDD로 `test_segments_for_timeline_ignores_unknown_track_type` exact regression을 먼저 추가했고, 실제로 stale `seg_legacy`가 canonical narration segment보다 먼저 subtitle order에 들어오는 RED를 확인했다
- 최소 수정으로 subtitle segment-order 수집 시 supported runtime track type 집합 `narration/broll/bgm`만 읽도록 좁혀, stale unknown `track_type`는 건너뛰고 valid runtime track input만 subtitle source로 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 subtitle render의 unknown track-type 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - backend preflight `59 passed`
  - frontend preflight focused command exit code `0` 확인
- broader verification
  - 실행하지 않음
  - 판단:
    - subtitle segment-order read path의 unknown track-type 경계 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. subtitle render의 segment order가 supported set 밖의 stale unknown track에 끌려가지 않는다
2. approved subtitle output은 canonical runtime track type만 기준으로 세그먼트 순서를 잡는다
3. review/output gating 인접 subtitle read path가 minimal-track hardening 다음 단계까지 같은 기준으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 157. 2026-07-06 subtitle segment order ignores stale minimal track without track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 직접 맞닿은 subtitle render segment-order read path의 stale minimal track 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_segments_for_timeline(...)`는 `tracks`가 dict이고 `clips`만 list면 모두 subtitle segment order source로 읽고 있어, `track_type` 없이 남은 stale minimal-dict track도 실제 subtitle source track처럼 세그먼트 순서에 끼어들 수 있었다
- strict TDD로 `test_segments_for_timeline_ignores_minimal_dict_track_without_track_type` exact regression을 먼저 추가했고, 실제로 stale `seg_stale`가 canonical narration segment보다 먼저 subtitle order에 들어오는 RED를 확인했다
- 최소 수정으로 subtitle segment-order 수집 시 canonical `track_type`가 있는 track만 읽도록 좁혀, stale minimal-dict track은 건너뛰고 valid track input만 subtitle source로 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 subtitle render의 stale minimal track 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating focused command exit code `0` 확인
  - backend preflight focused command exit code `0` 확인
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - subtitle segment-order read path의 stale minimal track 경계 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

focused 검증 메모:

- `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`는 이번 환경에서도 backend `pytest.exe` 표준출력 인코딩 문제로 실패해 신뢰하지 않았다
- backend focused는 `py -m pytest ...` 표준 명령으로 직접 다시 확인했다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. subtitle render의 segment order가 `track_type` 없는 stale minimal-dict track에 끌려가지 않는다
2. approved subtitle output은 canonical track input만 기준으로 세그먼트 순서를 잡는다
3. review/output gating 인접 subtitle read path가 preview/export prompt 쪽 track hardening 방향과 같은 기준으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 156. 2026-07-05 review guidance reuse key ignores stale unknown and minimal blocker entries closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 직접 맞닿은 blocked review guidance persistence 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_build_review_guidance_reuse_key(...)`는 blocked snapshot의 `review_flags`/`pending_recommendations`에 dict 형태만 있으면 모두 reuse key에 넣고 있어, stale unknown code review flag나 minimal/unknown-type pending recommendation dict가 섞인 경우 실제 blocker surface는 같아도 persisted guidance 재사용 키가 달라질 수 있었다
- strict TDD로 `test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries` exact regression을 먼저 추가했고, 실제로 canonical blocker snapshot과 stale-shape가 섞인 snapshot의 reuse key가 달라지는 RED를 확인했다
- 최소 수정으로 blocked guidance reuse key 생성 시 supported review-flag code와 canonical `segment_id`, supported recommendation type과 canonical recommendation identity/segment를 가진 entry만 키에 반영하도록 좁혀, stale unknown/minimal blocker dict는 persistence key에서 제외하고 valid blocker truth만 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, output gating truth를 건드리지 않고 blocked review guidance persistence key의 stale-shape 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - backend preflight focused command exit code `0` 확인
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - blocked guidance persistence reuse key의 stale-shape 경계 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. blocked review guidance persistence가 stale unknown/minimal blocker dict 때문에 같은 blocker truth를 다른 reuse key로 취급하지 않는다
2. persisted operator guidance 재사용 판단은 canonical blocker surface 기준으로만 움직인다
3. review/output gating 인접 persistence behavior가 기존 blocker truth 정리 방향과 같은 기준으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 155. 2026-07-05 preview renderer ignores stale non-list track clips closeout

이번 후속 작업에서는 코드리뷰/갭검증/역방향 동작검증 관점에서, 직전에 hardened된 output operator copy와 preview visible surface가 stale `tracks[].clips` shape를 다르게 처리하던 가장 가까운 output 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`는 이미 non-list `tracks[].clips`를 건너뛰도록 hardened됐지만, `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 여전히 `len(track.get("clips", []))`와 raw narration clip loop를 사용하고 있어 stale 문자열 clip container 하나만 있어도 preview HTML 생성이 `AttributeError`로 깨질 수 있었다
- strict TDD로 `test_preview_renderer_ignores_non_list_track_clips_in_track_summary_surfaces` exact regression을 먼저 추가했고, 실제로 preview renderer가 narration source loop에서 문자열 clip entry를 dict처럼 읽다가 RED로 깨지는 것을 확인했다
- 최소 수정으로 preview renderer에 promptable track filter를 추가해 non-dict track, empty canonical `track_type`, non-list `clips`를 모두 건너뛰고, preview payload의 `clips` surface와 HTML track summary/narration source surface가 같은 canonical track input만 보도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 preview visible surface의 stale track read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_ignores_non_list_track_clips_in_track_summary_surfaces" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과 `24 passed, 325 deselected`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 stale non-list clip filtering 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer는 stale non-list `tracks[].clips` 값을 실제 clip count처럼 세지 않는다
2. preview renderer는 stale non-list `tracks[].clips` 때문에 narration source HTML 생성 중 예외로 깨지지 않는다
3. preview visible surface와 output operator copy prompt가 stale track summary input을 더 비슷한 기준으로 걸러낸다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 156. 2026-07-05 capcut export adapter ignores stale non-list track clips closeout

이번 후속 작업에서는 장기 queue를 유지한 채, `TTS approval/output` 인접 export consumer surface에서 preview/output prompt와 같은 stale `tracks[].clips` shape를 아직 더 넓게 믿고 있던 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 mixed-case `track_type`나 trimmed TTS segment matching은 이미 정리돼 있었지만, 여전히 `tracks[].clips`를 list라고 가정하고 raw loop를 돌고 있어 stale 문자열 clip container 하나만 있어도 voiceover export track 생성 중 `AttributeError`로 깨질 수 있었다
- strict TDD로 `test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface` exact regression을 먼저 추가했고, 실제로 voiceover track 생성이 문자열 clip entry를 dict처럼 읽다가 RED로 깨지는 것을 확인했다
- 최소 수정으로 CapCut export adapter에 promptable track filter를 추가해 non-dict track, empty canonical `track_type`, non-list `clips`를 모두 건너뛰고, export consumer가 canonical track input만 넘기도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 CapCut export consumer의 stale track read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface or test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_narration_clip_segment_id_for_segment_level_narration_sources" -vv`
  - 결과 `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 CapCut export adapter의 stale non-list clip filtering 한 점에 한정돼 있어, exact + 같은 export consumer family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter는 stale non-list `tracks[].clips` 값을 voiceover/audio/video segment source처럼 순회하지 않는다
2. CapCut export adapter는 stale non-list `tracks[].clips` 때문에 export manifest 생성 중 예외로 깨지지 않는다
3. preview/output/export 인접 consumer surface가 stale track input을 더 비슷한 기준으로 걸러낸다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 157. 2026-07-05 subtitle render ignores stale non-list track clips closeout

이번 후속 작업에서는 장기 queue를 유지한 채, `review/output gating` 인접 output consumer인 subtitle render에서 stale non-list `tracks[].clips` shape를 그대로 믿고 있던 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_segments_for_timeline(...)`는 timeline `tracks[].clips`를 모두 list[dict]라고 가정하고 raw loop를 돌고 있어, stale 문자열 clip container 하나만 있어도 subtitle render의 timeline segment ordering read-path가 `AttributeError`로 깨질 수 있었다
- strict TDD로 `test_start_subtitle_render_ignores_stale_non_list_track_clips` exact regression을 먼저 추가했고, 실제로 subtitle render 시작이 문자열 clip entry를 dict처럼 읽다가 RED로 깨지는 것을 확인했다
- 최소 수정으로 `_segments_for_timeline(...)`가 non-dict track, non-list `clips`, non-dict clip을 모두 건너뛰도록 맞춰, subtitle render가 canonical clip input만 기준으로 segment order를 잡게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 subtitle output read-path의 stale track/clip filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_start_subtitle_render_ignores_stale_non_list_track_clips" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_start_subtitle_render_ignores_stale_non_list_track_clips or test_start_subtitle_render_uses_only_segments_from_the_approved_timeline or test_start_preview_render_marks_job_failed_when_renderer_errors" -vv`
  - 결과 `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 subtitle render와 같은 timeline-segment ordering consumer 한 점에 한정돼 있어, exact + 같은 subtitle/output family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. subtitle render는 stale non-list `tracks[].clips` 값을 subtitle segment source처럼 순회하지 않는다
2. subtitle render는 stale non-list `tracks[].clips` 때문에 output 생성 중 예외로 깨지지 않는다
3. preview/output/export/subtitle 인접 consumer surface가 stale track input을 더 비슷한 기준으로 걸러낸다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 158. 2026-07-05 approved tts apply ignores stale non-dict tracks closeout

이번 후속 작업에서는 장기 queue를 유지한 채, `TTS approval/output` 인접 approval-apply read-path에서 stale non-dict `tracks` shape를 그대로 믿고 있던 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `apply_approved_recommendation_to_timeline(...)`는 timeline `tracks`를 모두 dict라고 가정하고 raw `track.get(...)`를 호출하고 있어, stale 문자열 track entry 하나만 있어도 approved TTS recommendation 적용 경로가 `AttributeError`로 깨질 수 있었다
- strict TDD로 `test_apply_approved_tts_recommendation_ignores_non_dict_tracks` exact regression을 먼저 추가했고, 실제로 approved TTS asset swap 적용이 stale 문자열 track entry에서 RED로 깨지는 것을 확인했다
- 최소 수정으로 `apply_approved_recommendation_to_timeline(...)`가 non-dict track을 먼저 건너뛰도록 맞춰, approved narration asset swap이 canonical narration track input에만 적용되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 TTS approval apply read-path의 stale track filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_apply_approved_tts_recommendation_ignores_non_dict_tracks" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_apply_approved_tts_recommendation_ignores_non_dict_tracks or test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type or test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source" -vv`
  - 결과 `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 approved TTS apply 한 점에 한정돼 있어, exact + 같은 TTS approval/output family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved TTS recommendation apply path는 stale non-dict `tracks` entry를 target narration track처럼 읽지 않는다
2. approved narration asset swap은 stale non-dict track 때문에 예외로 깨지지 않는다
3. output/preview/export/subtitle/approval-apply 인접 consumer surface가 stale track input을 더 비슷한 기준으로 걸러낸다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 159. 2026-07-05 approved tts apply ignores stale non-dict clips closeout

이번 후속 작업에서는 장기 queue를 유지한 채, `TTS approval/output` 인접 approval-apply read-path에서 stale non-dict `clips` shape를 그대로 믿고 있던 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `apply_approved_recommendation_to_timeline(...)`는 직전 slice로 non-dict `tracks`는 건너뛰게 됐지만, `clips` list 내부 entry는 여전히 모두 dict라고 가정하고 raw `clip.get(...)`를 호출하고 있어 stale 문자열 clip entry 하나만 있어도 approved TTS recommendation 적용 경로가 `AttributeError`로 깨질 수 있었다
- strict TDD로 `test_apply_approved_tts_recommendation_ignores_non_dict_clips` exact regression을 먼저 추가했고, 실제로 approved TTS asset swap 적용이 stale 문자열 clip entry에서 RED로 깨지는 것을 확인했다
- 최소 수정으로 `apply_approved_recommendation_to_timeline(...)`가 non-dict clip도 먼저 건너뛰도록 맞춰, approved narration asset swap이 canonical narration clip input에만 적용되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 TTS approval apply read-path의 stale clip filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_apply_approved_tts_recommendation_ignores_non_dict_clips" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_apply_approved_tts_recommendation_ignores_non_dict_clips or test_apply_approved_tts_recommendation_ignores_non_dict_tracks or test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type" -vv`
  - 결과 `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 approved TTS apply 내부의 stale clip filtering 한 점에 한정돼 있어, exact + 같은 TTS approval/output family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved TTS recommendation apply path는 stale non-dict `clips` entry를 target narration clip처럼 읽지 않는다
2. approved narration asset swap은 stale non-dict clip 때문에 예외로 깨지지 않는다
3. output/preview/export/subtitle/approval-apply 인접 consumer surface가 stale track/clip input을 더 비슷한 기준으로 걸러낸다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 165. 2026-07-05 review guidance ignores stale minimal review flag prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 review guidance prompt의 stale minimal-dict `review_flags` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 non-dict entry만 걸러내고 있어, `segment_id` 없이 `code`만 남은 stale minimal-dict blocker도 valid review flag prompt row처럼 operator guidance prompt에 섞여 들어가고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `segment_review_required` entry가 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 review guidance prompt도 canonical blocker `code`와 `segment_id`를 모두 가진 entry만 유지하도록 좁혀, stale minimal-dict input은 건너뛰고 valid blocker surface만 남기게 정리했다
- 같은 수정에서 pending recommendation prompt identity도 supported recommendation type 집합과 같은 기준으로 묶어, review guidance prompt가 output-side prompt와 같은 canonical identity 규칙을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 stale minimal review-flag 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review-guidance prompt focused slice `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 stale minimal review-flag input 한 점 수정이라 exact + 인접 prompt focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 `segment_id` 없이 남은 stale minimal-dict `review_flags` entry를 valid blocker처럼 노출하지 않는다
2. blocked operator guidance prompt는 canonical blocker identity와 supported code를 가진 valid review flag surface만 유지한다
3. review guidance prompt의 blocker identity 기준이 output operator copy prompt와 더 가깝게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 166. 2026-07-05 finish stabilization and closeout plan alignment

이번 turn에서는 새 runtime 경계를 구현하지 않고, 현재 브랜치의 남은 안정화 작업과 최종 마감 작업을 분리한 실행 계획을 SSOT에 고정했다.

이번에 정리한 핵심은 아래와 같다.

- 현재 브랜치는 대형 기능 추가 단계가 아니라 `작은 stale-shape 안정화 -> 전체 검증/QA/정리` 순서가 맞다는 점을 다시 고정했다
- 이를 위해 `docs/superpowers/plans/2026-07-05-finish-stabilization-and-closeout-plan.ko.md`를 추가해, 페이즈 A 안정화와 페이즈 B/C 마감 작업의 순서, 종료 조건, 검증 범위를 문서화했다
- `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업`에도 위 계획 문서를 공식 참조로 연결해, 다음 turn부터 다시 설명하지 않고 바로 그 계획 기준으로 이어갈 수 있게 맞췄다

이번 turn의 verification은 아래와 같다.

- `git status --short --branch`
- `git log -5 --oneline`
- SSOT 재확인
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - `docs/development-fast-path.ko.md`
- closeout / plan 정합성 확인
  - `docs/session-context-2026-07-05-output-operator-copy-ignore-stale-non-list-track-clips-closeout.ko.md`
  - `docs/session-context-2026-07-05-preview-renderer-ignore-stale-non-list-track-clips-closeout.ko.md`
  - `docs/session-context-2026-07-05-review-guidance-ignore-stale-minimal-review-flag-entry-closeout.ko.md`

이 갱신으로 아래 범위는 현재 기준 정리됐다.

1. 남은 안정화 작업과 최종 마감 작업의 순서가 문서로 고정됨
2. 다음 turn부터는 `작은 안정화 slice 계속 진행`과 `전체 마감 검증 페이즈 전환`의 기준이 분명해짐
3. 전체 QA/시스템 검증/문서 정리/리팩터링/찌꺼기 정리 작업이 언제 들어가야 하는지 SSOT 기준이 생김

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 페이즈 A 기준으로 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개를 다시 고른다
- 작은 stale-shape 안정화 slice를 더 닫는다
- 그다음 전체 검증/QA/정리 페이즈로 넘어갈 시점을 판단한다

## 167. 2026-07-05 pending recommendation decision extraction rejects unknown type entries closeout

이번 후속 작업에서는 페이즈 A를 유지한 채, `TTS approval/output` approval decision extraction read-path에서 unknown `recommendation_type`를 가진 stale `pending_recommendations` shape를 valid recommendation row처럼 승인하던 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `_is_valid_pending_recommendation_entry(...)`는 `recommendation_type`가 비어 있지만 않으면 truthy로 통과시키고 있어, unknown legacy type을 가진 stale pending row도 approval decision extraction 대상이 될 수 있었다
- strict TDD로 `test_extract_pending_recommendation_decision_rejects_unknown_type_entry` exact regression을 먼저 추가했고, 실제로 `KeyError`가 나야 하는 기대와 달리 unknown type row가 그대로 승인되는 RED를 확인했다
- 최소 수정으로 approval decision extraction도 supported recommendation type 집합만 통과시키도록 좁혀, unknown type stale row는 건너뛰고 valid pending recommendation row만 승인/거절 decision 대상으로 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 approval decision extraction read-path의 unknown-type pending-entry filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - approval decision/apply focused slice `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 approval decision extraction의 unknown-type pending-entry filtering 한 점에 한정돼 있어, exact + 같은 TTS approval/output family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approval decision extraction path는 unknown `recommendation_type`를 가진 stale `pending_recommendations` entry를 valid recommendation row처럼 승인하지 않는다
2. approved/rejected recommendation extraction은 supported recommendation type을 가진 pending row에만 적용된다
3. approval decision extraction read-path가 non-dict junk filtering, minimal-dict junk filtering 다음 단계인 unknown-type junk filtering까지 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 160. 2026-07-05 pending recommendation decision extraction ignores stale non-dict entries closeout

이번 후속 작업에서는 장기 queue를 유지한 채, `TTS approval/output` 인접 approval decision extraction read-path에서 stale non-dict `pending_recommendations` shape를 그대로 믿고 있던 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `extract_pending_recommendation_decision(...)`는 `pending_recommendations` list entry를 모두 dict라고 가정하고 raw `item.get(...)`를 호출하고 있어 stale 문자열 entry 하나만 있어도 approval/rejection decision 추출 경로가 `AttributeError`로 깨질 수 있었다
- strict TDD로 `test_extract_pending_recommendation_decision_ignores_non_dict_entries` exact regression을 먼저 추가했고, 실제로 recommendation decision extraction이 stale 문자열 pending entry에서 RED로 깨지는 것을 확인했다
- 최소 수정으로 `extract_pending_recommendation_decision(...)`가 non-dict pending entry를 먼저 건너뛰도록 맞춰, approved/rejected recommendation decision extraction이 canonical recommendation input에만 적용되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 approval decision extraction read-path의 stale pending-entry filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_ignores_non_dict_entries" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_ignores_non_dict_entries or test_apply_approved_tts_recommendation_ignores_non_dict_clips or test_apply_approved_tts_recommendation_ignores_non_dict_tracks" -vv`
  - 결과 `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 approval mutation family 안의 stale pending-entry filtering 한 점에 한정돼 있어, exact + 같은 TTS approval/output family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approval decision extraction path는 stale non-dict `pending_recommendations` entry를 valid recommendation row처럼 읽지 않는다
2. approved/rejected recommendation extraction은 stale non-dict pending entry 때문에 예외로 깨지지 않는다
3. output/preview/export/subtitle/approval-apply/decision-extraction 인접 consumer surface가 stale track/recommendation input을 더 비슷한 기준으로 걸러낸다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 161. 2026-07-05 pending recommendation decision extraction rejects stale minimal dict entries closeout

이번 후속 작업에서는 장기 queue를 유지한 채, 같은 `TTS approval/output` approval decision extraction read-path에서 `recommendation_id`만 남은 stale minimal-dict `pending_recommendations` shape를 valid recommendation row처럼 승인해 버리던 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `extract_pending_recommendation_decision(...)`는 dict 여부만 통과하면 해당 entry를 recommendation row로 채택하고 있어, `recommendation_id`만 남고 `target_segment_id`나 canonical `recommendation_type`가 비어 있는 stale minimal-dict entry도 승인 대상으로 통과시킬 수 있었다
- strict TDD로 `test_extract_pending_recommendation_decision_rejects_stale_minimal_dict_entry` exact regression을 먼저 추가했고, 실제로 `KeyError`가 나야 하는 기대와 달리 stale minimal row가 그대로 승인되는 RED를 확인했다
- 최소 수정으로 decision extraction read-path에 `recommendation_id + target_segment_id + canonical recommendation_type` 유효성 체크만 추가해, stale minimal-dict pending entry는 건너뛰고 valid recommendation row만 승인/거절 decision 대상으로 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 approval decision extraction read-path의 stale minimal pending-entry filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_rejects_stale_minimal_dict_entry" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_ignores_non_dict_entries or test_extract_pending_recommendation_decision_rejects_stale_minimal_dict_entry or test_apply_approved_tts_recommendation_ignores_non_dict_clips or test_apply_approved_tts_recommendation_ignores_non_dict_tracks" -vv`
  - 결과 `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 approval decision extraction의 stale minimal pending-entry filtering 한 점에 한정돼 있어, exact + 같은 TTS approval/output family focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approval decision extraction path는 `recommendation_id`만 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation row처럼 승인하지 않는다
2. approved/rejected recommendation extraction은 canonical recommendation identity/type/segment를 가진 pending row에만 적용된다
3. approval decision extraction read-path가 non-dict junk filtering 다음 단계인 minimal-dict junk filtering까지 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 162. 2026-07-05 review guidance prompt ignores stale non-dict review flag entries closeout

이번 후속 작업에서는 장기 queue를 유지한 채, `review/output gating`에 가장 가까운 review guidance prompt의 stale non-dict `review_flags` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `LocalFirstReviewGuidanceBuilder._prompt_review_flags(...)`는 모든 `review_flags` entry를 dict라고 가정하고 raw `dict(flag)`를 호출하고 있어, stale 문자열 같은 non-dict review flag entry 하나만 있어도 blocked review guidance prompt 생성이 `ValueError`로 깨지고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_non_dict_review_flags_in_prompt` exact regression을 먼저 추가했고, 실제로 `dictionary update sequence element #0 has length 1; 2 is required` RED를 확인했다
- 최소 수정으로 prompt `review_flags` 루프에서 dict가 아닌 entry를 건너뛰도록만 맞춰, valid blocker prompt surface는 그대로 유지하면서 stale non-dict entry가 review guidance prompt 생성을 깨지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 review guidance prompt의 stale review-flag input 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_review_flags_in_prompt" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_review_flags_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt or test_review_guidance_builder_trims_review_flag_segment_id_in_prompt or test_review_guidance_builder_defaults_review_flag_message_in_prompt" -vv`
  - 결과 `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 review guidance prompt의 stale non-dict review-flag input 한 점에 한정돼 있어, exact + 같은 prompt surface focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 stale non-dict `review_flags` entry 하나 때문에 예외로 중단되지 않는다
2. blocked review guidance prompt는 valid blocker surface만 유지하고 junk review-flag input은 건너뛴다
3. review guidance prompt surface가 output operator copy prompt의 stale review-flag input 방어 방향과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 163. 2026-07-05 review guidance prompt ignores stale non-dict pending recommendation entries closeout

이번 후속 작업에서는 장기 queue를 유지한 채, 같은 `review/output gating` review guidance prompt의 stale non-dict `pending_recommendations` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `LocalFirstReviewGuidanceBuilder._prompt_pending_recommendations(...)`는 모든 `pending_recommendations` entry를 dict라고 가정하고 raw `dict(item)`를 호출하고 있어, stale 문자열 같은 non-dict pending recommendation entry 하나만 있어도 blocked review guidance prompt 생성이 `ValueError`로 깨지고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt` exact regression을 먼저 추가했고, 실제로 `dictionary update sequence element #0 has length 1; 2 is required` RED를 확인했다
- 최소 수정으로 prompt `pending_recommendations` 루프에서 dict가 아닌 entry를 건너뛰도록만 맞춰, valid recommendation prompt surface는 그대로 유지하면서 stale non-dict entry가 review guidance prompt 생성을 깨지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 review guidance prompt의 stale pending-recommendation input 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt or test_review_guidance_builder_trims_pending_recommendation_reason_in_prompt" -vv`
  - 결과 `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 review guidance prompt의 stale non-dict pending-recommendation input 한 점에 한정돼 있어, exact + 같은 prompt surface focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 stale non-dict `pending_recommendations` entry 하나 때문에 예외로 중단되지 않는다
2. blocked review guidance prompt는 valid recommendation surface만 유지하고 junk pending-recommendation input은 건너뛴다
3. review guidance prompt surface가 output operator copy prompt의 stale pending-recommendation input 방어 방향과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 164. 2026-07-05 review guidance prompt ignores stale minimal pending recommendation entries closeout

이번 후속 작업에서는 장기 queue를 유지한 채, 같은 `review/output gating` review guidance prompt의 `recommendation_id`만 남은 stale minimal-dict `pending_recommendations` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `LocalFirstReviewGuidanceBuilder._prompt_pending_recommendations(...)`는 dict 여부만 통과하면 해당 entry를 prompt row로 그대로 올리고 있어, `recommendation_id`만 남고 `target_segment_id`나 canonical `recommendation_type`가 비어 있는 stale minimal-dict pending recommendation도 blocked review guidance prompt에 valid recommendation처럼 섞여 들어가고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `rec_stale_minimal` entry가 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 prompt `pending_recommendations` row 생성 전에 `recommendation_id + target_segment_id + canonical recommendation_type` 유효성 체크만 추가해, stale minimal-dict entry는 건너뛰고 valid recommendation prompt row만 유지하게 했다
- focused verification 중 기존 mixed-case recommendation-type test fixture가 새 최소 identity/type/segment 계약을 만족하지 않아, `target_segment_id`를 추가해 현재 계약 기준으로 바로잡았다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 review guidance prompt의 stale minimal pending-recommendation input 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv`
  - 결과 `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt or test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt" -vv`
  - 결과 `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 이번 수정은 review guidance prompt의 stale minimal pending-recommendation input 한 점에 한정돼 있어, exact + 같은 prompt surface focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 491 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 `recommendation_id`만 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation prompt row처럼 노출하지 않는다
2. blocked review guidance prompt는 canonical recommendation identity/type/segment를 가진 valid recommendation surface만 유지한다
3. review guidance prompt surface가 output operator copy prompt의 stale minimal pending-recommendation input 방어 방향과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 153. 2026-07-04 heuristic review guidance default review flag message closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 heuristic review guidance fallback의 message 없는 `review_flags` default-message surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder`는 valid review flag에 `message`가 없을 때 local-first prompt family와 달리 canonical default blocker message를 쓰지 않고, 더 약한 generic blocker 문구로 action item을 채우고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_defaults_missing_review_flag_message` exact regression을 먼저 추가했고, 실제로 action item이 `Operator review required before approval or output.`가 아니라 `Resolve review blockers before approval.`로 내려오는 RED를 확인했다
- 최소 수정으로 heuristic fallback이 valid `review_flags.code/segment_id`가 있고 `message`만 비어 있는 경우에는 canonical default blocker message를 action item으로 채우도록 맞춰, runtime fallback guidance도 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 heuristic review guidance fallback의 default-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - `315 deselected`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic fallback action-item default-message canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance fallback이 message 없는 valid `review_flags`에도 canonical default blocker message를 action item으로 surface한다
2. runtime fallback guidance가 missing message review flag를 generic blocker 문구로만 뭉개지 않는다
3. heuristic review guidance fallback의 review-flag message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 152. 2026-07-04 review guidance review flag default message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 message 없는 `review_flags` default-message surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 직전 slice들로 `code/segment_id/message` trim surface는 정리됐지만, message가 없는 valid review flag는 raw dict 그대로 두고 있어 API/read-path가 채우는 canonical default blocker message가 operator guidance prompt에는 비어 있었다
- strict TDD로 `test_review_guidance_builder_defaults_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `'message': 'Operator review required before approval or output.'`를 포함하지 않는 RED를 확인했다
- 최소 수정으로 `_prompt_review_flags(...)`에서 비어 있는 `message`에 canonical default blocker message를 채우도록 맞춰, review guidance prompt의 message 없는 review-flag surface가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 default-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag default-message canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 message 없는 valid `review_flags`에도 canonical default blocker message를 surface한다
2. operator guidance prompt가 missing message review flag를 빈 surface로 남기지 않는다
3. review guidance prompt의 review-flag message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 151. 2026-07-04 output operator copy review flag default message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 message 없는 `review_flags` default-message surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `review_flags.code/segment_id/message` trim surface는 정리됐지만 message가 없는 valid review flag는 그대로 raw dict로 두고 있어, API/read-path가 채우는 canonical default blocker message가 preview/export operator guidance prompt에는 비어 있었다
- strict TDD로 `test_output_operator_copy_builder_defaults_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `'message': 'Operator review required before approval or output.'`를 포함하지 않는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 만들 때 `message`가 비어 있으면 canonical default blocker message를 채우도록 맞춰, output operator copy prompt의 message 없는 review-flag surface가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 default-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag default-message canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 message 없는 valid `review_flags`에도 canonical default blocker message를 surface한다
2. preview/export guidance prompt가 missing message review flag를 빈 surface로 남기지 않는다
3. output operator copy prompt의 review-flag message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 150. 2026-07-04 output operator copy review flag message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 `review_flags.message` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice에서 `review_flags.code`와 `review_flags.segment_id`는 정리됐지만 `message`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale review-flag message가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'message': ' Review narration replacement '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 만들 때 `message`도 trim하도록 맞춰, output operator copy prompt의 review-flag-message surface가 review/output gating과 API response 쪽 canonical blocker message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 review-flag-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag-message trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `review_flags.message`도 trimmed blocker message로 surface한다
2. preview/export guidance prompt가 raw padded review-flag message 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 review-flag-message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 149. 2026-07-04 output operator copy review flag segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 `review_flags.segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice에서 `review_flags.code`는 canonicalize하게 됐지만 `segment_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale review-flag segment id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_review_flag_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'segment_id': ' seg_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 만들 때 `segment_id`도 trim하도록 맞춰, output operator copy prompt의 review-flag-segment-id surface가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 review-flag-segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag-segment-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `review_flags.segment_id`도 trimmed segment id로 surface한다
2. preview/export guidance prompt가 raw padded review-flag segment id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 review-flag-segment-id surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 148. 2026-07-04 output operator copy review flag code prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 `review_flags.code` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `pending_recommendations` 주요 surface는 대부분 정리됐지만 `review_flags`는 여전히 raw list 그대로 prompt에 넣고 있어, mixed-case stale `review_flags.code`가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'code': ' TTS_REPLACEMENT_REVIEW_REQUIRED '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 따로 만들고 `code`만 canonical lowercase로 정리하도록 맞춰, output operator copy prompt의 review-flag-code surface가 review/output gating 쪽 canonical review-flag 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 review-flag-code surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag-code canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 mixed-case stale `review_flags.code`도 canonical lowercase code로 surface한다
2. preview/export guidance prompt가 raw padded review-flag code 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 review-flag-code surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 147. 2026-07-04 output operator copy pending decision state prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 `TTS approval/output` 사이에서 가장 인접한 output operator copy prompt의 `pending_recommendations.decision_state` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`, `selected_asset_id`, `recommendation_id`, `created_at`, nested `payload.selected_asset_uri`는 정리됐지만 `decision_state`는 여전히 raw 문자열 그대로 넣고 있어, mixed-case stale decision state가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_pending_recommendation_decision_state_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'decision_state': ' Approved '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `decision_state`도 canonical lowercase로 정리하도록 맞춰, output operator copy prompt의 decision-state surface가 approve/read-path 쪽 canonical decision-state 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 decision-state surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt decision-state canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 mixed-case stale `pending_recommendations.decision_state`도 canonical lowercase 상태로 surface한다
2. preview/export guidance prompt가 raw padded decision state 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 decision-state surface가 approve/read-path truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 39. 2026-07-04 rule based music recommender string false segment review_required closeout

이번 후속 작업에서는 queue 1~3의 직접 출력/사전검증 경계가 대부분 닫힌 상태에서, 계획서 5번의 작은 evidence gap에 해당하는 recommendation generation 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/recommenders.py`의 `RuleBasedMusicRecommender`는 segment payload의 `review_required`를 raw truthiness로 읽고 있어, legacy string false shape인 `review_required="false"`를 truthy로 오판해 실제 review blocker가 없는 segment도 `"light neutral bed"` branch로 보내고 있었다
- strict TDD로 `test_rule_based_music_recommender_ignores_string_false_segment_review_required` exact regression을 먼저 추가했고, 실제로 `"Quarterly finance summary"` segment가 기대한 `"focused corporate"`가 아니라 `"light neutral bed"` reason으로 내려가는 RED를 확인했다
- 최소 수정으로 recommender에도 bool-ish normalization helper를 추가해 segment `review_required`를 canonical bool로 해석하도록 맞춰, false-like string shape가 neutral-bed fallback branch를 잘못 타지 않게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation generation 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_recommendations.py` `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rule-based music recommender의 bool-ish normalization 한 점 수정이라 exact + file-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. rule-based music recommender가 legacy string false `review_required="false"`를 truthy review blocker로 오판하지 않음
2. review blocker가 없는 일반 segment는 neutral-bed fallback이 아니라 기본 music mood branch를 유지함
3. recommendation generation의 bool-ish false 해석이 다른 read/write normalization 규칙과 더 가까워짐

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 130. 2026-07-04 review guidance trimmed pending recommendation target segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.target_segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 prompt용 pending recommendation surface는 `recommendation_type`은 이미 canonical lowercase 기준으로 정리하고 있었지만, `target_segment_id`는 raw 문자열 그대로 두고 있어 `" seg_001 "` 같은 whitespace stale shape가 operator-facing guidance prompt에 그대로 남고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `{'target_segment_id': ' seg_001 '}`를 그대로 담는 RED를 확인했다
- 최소 수정으로 prompt용 pending recommendation surface가 `target_segment_id.strip()` 기준을 사용하도록 맞춰, guidance prompt가 canonical trimmed target segment id를 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 target-segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / operator copy 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 trimmed target-segment-id canonicalization 한 점 수정이라 exact + 인접 guidance/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `target_segment_id`도 canonical trimmed id로 surface한다
2. operator-facing guidance prompt가 raw padded target segment id를 그대로 남기지 않는다
3. review guidance prompt의 target segment id 기준이 TTS/output read-path 쪽 canonical segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 129. 2026-07-04 review guidance mixed-case pending recommendation type prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_build_prompt(...)`는 `pending_recommendations`를 raw dict 그대로 prompt에 넣고 있어, legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale `recommendation_type`가 operator-facing guidance prompt에 그대로 남고 있었다
- strict TDD로 `test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `{'recommendation_type': ' TTS_REPLACEMENT '}`를 그대로 담는 RED를 확인했다
- 최소 수정으로 review guidance prompt용 pending recommendation surface가 `recommendation_type.strip().lower()` 기준을 사용하도록 맞춰, guidance prompt가 canonical lowercase recommendation type을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation-type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / operator copy 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 recommendation-type canonicalization 한 점 수정이라 exact + 인접 guidance/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 legacy mixed-case `recommendation_type`도 canonical lowercase type으로 surface한다
2. operator-facing guidance prompt가 raw stale recommendation type 문자열을 그대로 남기지 않는다
3. review guidance prompt의 recommendation type 기준이 approved/read-path 쪽 canonical type 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 128. 2026-07-04 review guidance trimmed segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `Segments needing attention` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_segments_needing_attention(...)`는 `review_required` 판정은 canonical bool-ish 기준으로 하고 있었지만, 반환하는 `segment_id`는 raw 문자열 그대로 두고 있어 `" seg_001 "` 같은 whitespace stale shape가 operator-facing guidance prompt에 그대로 남고 있었다
- strict TDD로 `test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `Segments needing attention: [' seg_001 ']`를 그대로 담는 RED를 확인했다
- 최소 수정으로 `_segments_needing_attention(...)`가 `segment_id.strip()` 기준을 사용하도록 맞춰, guidance prompt가 canonical trimmed segment id를 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / operator copy 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 trimmed segment-id canonicalization 한 점 수정이라 exact + 인접 guidance/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `segment_id`도 canonical trimmed id로 surface한다
2. operator-facing guidance prompt가 raw padded segment id를 그대로 남기지 않는다
3. review guidance prompt의 세그먼트 식별 기준이 preflight/runtime 쪽 trimmed segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 123. 2026-07-04 CapCut export mixed-case narration track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 CapCut export voiceover track surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 track loop에서 `track_type`를 raw 문자열 그대로 `narration`과 비교하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 남으면 voiceover track 자체를 만들지 못하고 있었다
- strict TDD로 `test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track` exact regression을 먼저 추가했고, 실제로 `payload["capcut_tracks"]`에서 `voiceover` track을 찾지 못하는 RED를 확인했다
- 최소 수정으로 CapCut export adapter에 track type canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, mixed-case narration track도 voiceover track으로 정확히 내보내게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 CapCut export narration track type read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export voiceover 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export narration track-type canonicalization 한 점 수정이라 exact + export 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 legacy mixed-case narration `track_type`도 canonical lowercase 기준으로 해석한다
2. stale narration track type 때문에 voiceover track이 통째로 빠지는 문제를 막는다
3. approved narration/TTS output surface가 preview/export 계열에서 더 같은 canonical track type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 124. 2026-07-04 preview renderer mixed-case narration track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview narration source surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 narration sources HTML surface를 만들 때 `track_type`를 raw 문자열 그대로 `narration`과 비교하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 남으면 narration source list가 비어 있었다
- strict TDD로 `test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML의 `Narration sources`가 빈 `<ul></ul>`로 남는 RED를 확인했다
- 최소 수정으로 preview renderer에 track type canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, mixed-case narration track도 narration sources surface에 정확히 반영되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 preview narration track type read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview narration source 인접 exact
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer narration track-type canonicalization 한 점 수정이라 exact + preview 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy mixed-case narration `track_type`도 canonical lowercase 기준으로 해석한다
2. stale narration track type 때문에 narration sources surface가 비는 문제를 막는다
3. preview visible narration source surface가 CapCut export voiceover surface와 더 같은 canonical track type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 125. 2026-07-04 preview renderer mixed-case track type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 preview visible track summary surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 `Track summary` HTML surface에서 `track_type`를 raw 문자열 그대로 출력하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 visible output surface에 그대로 노출되고 있었다
- strict TDD로 `test_preview_renderer_canonicalizes_mixed_case_track_type_surface` exact regression을 먼저 추가했고, 실제로 preview HTML이 `<strong> NARRATION </strong>`를 그대로 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer의 track summary surface도 기존 `_canonical_track_type(...)` helper를 재사용하도록 맞춰 `strip().lower()` 기준으로 canonical lowercase type을 출력하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 preview visible track-type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview visible surface 인접 exact
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer track-type visible surface canonicalization 한 점 수정이라 exact + preview 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy mixed-case `track_type`도 canonical lowercase type으로 surface한다
2. preview `Track summary`가 raw stale track type 문자열을 그대로 노출하지 않는다
3. preview narration source read-path와 preview visible track summary surface가 더 같은 canonical track type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 126. 2026-07-04 review approval mixed-case narration track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 review recommendation approval mutation 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `apply_approved_recommendation_to_timeline(...)`는 approved TTS replacement를 narration clip에 반영할 때 `track_type`를 raw 문자열 그대로 `narration`과 비교하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 남으면 target narration clip을 찾지 못하고 실패하고 있었다
- strict TDD로 `test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type` exact regression을 먼저 추가했고, 실제로 `Approved TTS replacement requires a matching target narration clip.` 예외가 나는 RED를 확인했다
- 최소 수정으로 review action mutation에 track type canonical helper를 추가해 `strip().lower()` 기준으로 narration track을 찾도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 approved TTS narration 적용의 track-type read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review approval / TTS output 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approved TTS narration track-type canonicalization 한 점 수정이라 exact + approval/output 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review recommendation approval mutation이 legacy mixed-case narration `track_type`도 canonical lowercase 기준으로 해석한다
2. stale narration track type 때문에 approved TTS asset이 target narration clip에 반영되지 않는 문제를 막는다
3. review approval mutation, preview renderer, CapCut export가 narration track type 해석에서 더 같은 canonical 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 118. 2026-07-04 output operator copy mixed-case review status prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 operator copy prompt surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 operator-facing preview/export guidance prompt에 `timeline["review_status"]`를 raw 문자열 그대로 넣고 있어, legacy `" APPROVED "` 같은 mixed-case stale shape가 runtime/operator copy 입력 surface에 그대로 남고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `Review status:  APPROVED `를 그대로 담는 RED를 확인했다
- 최소 수정으로 output operator copy builder에 review status canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, prompt surface가 canonical lowercase status를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 operator copy prompt surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - operator copy / preview review-status 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - operator copy prompt의 review-status canonicalization 한 점 수정이라 exact + output guidance 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy builder가 legacy mixed-case `review_status`도 canonical lowercase 상태로 prompt에 반영한다
2. preview/export guidance prompt가 raw stale review status 문자열을 그대로 runtime 입력으로 넘기지 않는다
3. operator copy prompt surface가 output gating/readiness와 preview visible status의 canonical status 기준과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 119. 2026-07-04 heuristic review guidance mixed-case approved status closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance approved-status 해석 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder.build(...)`는 blocker가 없는 review snapshot에서도 `review_status`를 raw 문자열로 읽고 있어, legacy `" APPROVED "` 같은 mixed-case stale shape를 approved가 아니라 `승인 대기`로 오판하고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status` exact regression을 먼저 추가했고, 실제로 guidance summary가 `Timeline is ready for approval before output generation.`으로 잘못 나오는 RED를 확인했다
- 최소 수정으로 review guidance에 review status canonical helper를 추가해 heuristic fallback 분기와 prompt builder가 모두 `strip().lower()` 기준을 사용하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance status 해석 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / review-status 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic review guidance의 approved-status canonicalization 한 점 수정이라 exact + review guidance 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance가 legacy mixed-case `review_status`도 canonical lowercase 승인 상태로 해석한다
2. blocker가 없는 approved review snapshot은 stale casing 때문에 `승인 대기` 안내로 되돌아가지 않는다
3. review guidance fallback 분기와 prompt surface가 output gating/readiness와 더 같은 review-status 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 127. 2026-07-04 output operator copy mixed-case track type prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 operator copy `track summary` prompt surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 operator-facing preview/export guidance prompt에서 `track_summary`의 `track_type`을 raw 문자열 그대로 넣고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 runtime/operator copy 입력 surface에 그대로 남고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_mixed_case_track_type_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `{'track_type': ' NARRATION '}`를 그대로 담는 RED를 확인했다
- 최소 수정으로 output operator copy builder에 track type canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, prompt의 `track_summary` surface가 canonical lowercase track type을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 operator copy prompt의 track summary surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - operator copy / preview / review guidance 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - operator copy prompt의 track-type canonicalization 한 점 수정이라 exact + 인접 prompt/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy builder가 legacy mixed-case `track_type`도 canonical lowercase track type으로 prompt에 반영한다
2. preview/export guidance prompt가 raw stale track type 문자열을 그대로 runtime 입력으로 넘기지 않는다
3. operator copy prompt의 track summary surface가 preview visible track summary와 더 같은 canonical track-type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 120. 2026-07-04 review approval mixed-case review flag cleanup closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review recommendation approve cleanup 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `should_keep_review_flag(...)`는 stale review flag의 `code`를 `strip()`만 하고 raw casing으로 비교하고 있어, legacy `" BROLL_REVIEW_REQUIRED "` 같은 mixed-case stale flag는 마지막 pending recommendation 승인 뒤에도 같은 blocker로 인식하지 못해 제거하지 못하고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_mixed_case_review_flag_code_for_same_segment` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 최소 수정으로 review action mutation에 review flag code canonical helper를 추가해 lowercase code 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approve cleanup의 mixed-case review flag code 해석 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review flag cleanup / output gating 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - mixed-case review flag cleanup 한 점 수정이라 exact + approve/output 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. 마지막 pending recommendation approve가 mixed-case stale review flag code도 canonical lowercase 기준으로 제거한다
2. blocker가 없는 approve 결과가 stale review flag casing 때문에 `blocked`로 잘못 남지 않는다
3. output gating에서 mixed-case flag code를 blocker로 읽는 경로와 approve cleanup에서 mixed-case flag code를 제거하는 경로가 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 121. 2026-07-04 review snapshot persisted guidance mixed-case approved status reuse closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review snapshot persisted guidance 재사용 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `get_review_snapshot(...)`는 timeline 쪽 `review_status`와 persisted review state를 raw 문자열로 직접 비교하고 있어, legacy `" APPROVED "` 같은 mixed-case stale status면 같은 승인 상태여도 persisted operator guidance를 재사용하지 못하고 다시 생성 경로로 빠지고 있었다
- strict TDD로 `test_local_pipeline_review_snapshot_reuses_persisted_guidance_for_mixed_case_approved_status` exact regression을 먼저 추가했고, 실제로 persisted guidance를 바로 돌려주지 않고 review guidance builder를 다시 호출하는 RED를 확인했다
- 최소 수정으로 local pipeline에 runtime review status canonical helper를 추가하고, persisted guidance reuse/save 조건 비교를 `strip().lower()` 기준으로 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot guidance reuse의 status 비교 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - persisted guidance / review-status 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot persisted guidance reuse의 mixed-case approved status 비교 한 점 수정이라 exact + guidance reuse 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot이 legacy mixed-case `review_status`도 canonical lowercase 승인 상태로 비교해 persisted guidance를 재사용한다
2. 같은 승인 상태인데 raw casing 차이 때문에 operator guidance를 불필요하게 다시 만들지 않는다
3. review guidance fallback, operator copy prompt, persisted guidance reuse가 review-status 비교에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 122. 2026-07-04 timeline builder mixed-case applied recommendation type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 timeline builder applied recommendation surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`는 approved TTS recommendation의 분기 판단에는 canonical type을 쓰고 있었지만, `_recommendation_payload(...)`가 returned surface의 `recommendation_type`을 raw 문자열로 남기고 있어 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale shape가 `applied_recommendations` surface에 그대로 남고 있었다
- strict TDD로 `test_timeline_builder_canonicalizes_mixed_case_applied_recommendation_type_surface` exact regression을 먼저 추가했고, 실제로 `timeline.applied_recommendations[0]["recommendation_type"] == " TTS_REPLACEMENT "` RED를 확인했다
- 최소 수정으로 timeline builder `_recommendation_payload(...)`도 `recommendation_type`을 canonical lowercase로 정리해 builder output surface가 approved TTS read-path truth와 같은 기준을 사용하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder recommendation_type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - timeline builder / TTS output 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder applied recommendation type surface canonicalization 한 점 수정이라 exact + TTS/output 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder가 legacy mixed-case `recommendation_type`도 canonical lowercase type으로 surface한다
2. approved TTS recommendation이 builder output surface에서 raw stale casing을 그대로 남기지 않는다
3. builder output surface, preview renderer, output read-path가 recommendation type 해석에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 82. 2026-07-04 recommendation row trimmed broll provider trace closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 recommendation row read-path의 작은 stale-shape 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `list_recommendation_rows(...)`는 persisted row의 `recommendation_type`을 raw 문자열로 비교하고 있어 whitespace가 섞인 stale `broll` row에서 missing `provider_trace` fallback을 `heuristic_fallback`이 아니라 `rule_based_fallback`으로 잘못 채우고 있었다
- strict TDD로 `test_store_list_recommendation_rows_uses_trimmed_broll_type_for_default_provider_trace` exact regression을 먼저 추가했고, 실제로 `provider_trace.final_provider == "rule_based_fallback"` RED를 확인했다
- 원인은 recommendation row read path의 default provider-trace 분기가 approve/review snapshot 쪽과 달리 canonical trimmed recommendation type을 재사용하지 않던 점이었다
- 최소 수정으로 `list_recommendation_rows(...)`의 fallback provider-trace 분기도 `str(payload["recommendation_type"] or "").strip()` 기준으로 비교하도록 좁혀, stale whitespace `broll` row도 기존 review/output truth와 같은 `heuristic_fallback`을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation row read-path의 fallback trace 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_api.py`
    - `test_store_list_recommendation_rows_uses_trimmed_broll_type_for_default_provider_trace`
    - `test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false`
    - 결과: `2 passed`
  - `tests/test_review_timeline.py`
    - `test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace`
    - 결과: `1 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation row read-path의 trimmed type comparison 한 점 수정이라 exact + 인접 read-path focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation row read path가 whitespace가 섞인 stale `broll` recommendation type도 canonical B-roll type으로 인식한다
2. missing `provider_trace` legacy row도 downstream read path에서 `heuristic_fallback` trace를 유지한다
3. recommendation row read truth와 approve/review snapshot provider-trace fallback truth가 같은 trim 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 83. 2026-07-04 preflight prediction targeted-segment string false review_required closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 prediction helper stale-shape 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 targeted segment의 `review_required`를 raw `bool(...)`로 판정하고 있어, legacy string false shape인 `review_required="false"`를 blocker로 오판해 `draft`여야 할 prediction을 `blocked`로 뒤집고 있었다
- strict TDD로 `test_preflight_review_prediction_ignores_string_false_targeted_segment_review_required` exact regression을 먼저 추가했고, 실제로 helper 반환값이 `draft`가 아니라 `blocked`가 되는 RED를 확인했다
- 원인은 preflight prediction helper가 source recommendation/review flag 쪽에는 normalization을 쓰면서도 targeted segment review-required 판정만 raw truthiness를 남겨 두고 있던 점이었다
- 최소 수정으로 targeted segment review-required 판정도 `_normalize_boolish_response(...)` 기준으로 맞춰, legacy false-like shape가 clean rerun scope를 blocker로 뒤집지 않게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction helper의 targeted-segment bool 판정 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_preflight_review_prediction_ignores_string_false_targeted_segment_review_required or test_editing_session_api_normalizes_string_false_review_required_in_preflight_targeted_segments or test_editing_session_api_marks_preflight_as_draft_for_clean_rerun_scope"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend -BackendPattern "normalizes_string_false_review_required_in_preflight_targeted_segments or marks_preflight_as_draft_for_clean_rerun_scope"`
  - 결과: `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction helper의 targeted segment bool 판정 한 점 수정이라 exact + 인접 preflight focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preflight prediction helper가 targeted segment의 legacy string false `review_required="false"`를 blocker로 오판하지 않는다
2. clean rerun scope prediction이 helper direct call과 API preflight read path 모두에서 같은 `draft` truth를 유지한다
3. targeted segment bool 판정이 source recommendation/review flag normalization과 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 84. 2026-07-04 recommendation response mixed-case decision-state closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 `TTS approval/output`에 같이 닿는 recommendation response helper 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 `decision_state`를 `strip()`만 하고 raw casing을 그대로 남기고 있어, legacy 또는 mixed-case shape인 `" Approved "`가 API response에서 canonical `"approved"`가 아니라 `"Approved"`로 surface되고 있었다
- strict TDD로 `test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state` exact regression을 먼저 추가했고, 실제로 normalized response의 `decision_state == "Approved"` RED를 확인했다
- 원인은 recommendation response helper가 bool-ish fields와 recommendation type은 canonicalize하면서도 decision-state casing만 정규화하지 않고 있던 점이었다
- 최소 수정으로 response helper의 `decision_state`도 `strip().lower()` 기준으로 정리해, approve/timeline/review snapshot read family가 같은 lowercase surface를 유지하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation response helper의 decision-state surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state or test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths or test_timeline_api_normalizes_legacy_string_false_pending_recommendation_fields"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "surfaces_approved_decision_state_in_read_paths or normalizes_legacy_string_false_pending_recommendation_fields"`
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation response helper의 decision-state canonicalization 한 점 수정이라 exact + 인접 output-gating focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation response helper가 mixed-case 또는 whitespace decision-state shape를 canonical lowercase로 정리한다
2. approve/timeline/review snapshot read family가 같은 `approved` surface를 유지한다
3. decision-state surface 정규화가 recommendation type / bool field 정규화와 같은 response helper 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 85. 2026-07-04 recommendation response mixed-case recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 `TTS approval/output`에 같이 닿는 recommendation response helper의 recommendation type surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 `recommendation_type`을 `strip()`만 하고 raw casing을 그대로 남기고 있어, legacy 또는 mixed-case shape인 `" TTS_REPLACEMENT "`가 API response에서 canonical `"tts_replacement"`가 아니라 `"TTS_REPLACEMENT"`로 surface되고 있었다
- strict TDD로 `test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type` exact regression을 먼저 추가했고, 실제로 normalized response의 `recommendation_type == "TTS_REPLACEMENT"` RED를 확인했다
- 원인은 recommendation response helper가 bool-ish fields와 decision-state는 정리해도 recommendation type casing은 canonicalize하지 않고 있던 점이었다
- 최소 수정으로 response helper의 `recommendation_type`도 `strip().lower()` 기준으로 정리해, approve/timeline/review snapshot/TTS read family가 같은 lowercase surface를 유지하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation response helper의 type surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type or test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state or test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "surfaces_approved_decision_state_in_read_paths or normalizes_legacy_string_false_pending_recommendation_fields"`
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation response helper의 recommendation type canonicalization 한 점 수정이라 exact + 인접 output-gating focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation response helper가 mixed-case 또는 whitespace recommendation type shape를 canonical lowercase로 정리한다
2. approve/timeline/review snapshot/TTS read family가 같은 lowercase recommendation type surface를 유지한다
3. recommendation type surface 정규화가 decision-state / bool field 정규화와 같은 response helper 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 86. 2026-07-04 approve/read path mixed-case broll recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 approve mutation과 downstream read path 사이의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`, `packages/core-engine/src/videobox_core_engine/local_pipeline.py`, `packages/storage-abstractions/src/videobox_storage/local_project_store.py`는 mixed-case `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, pending `BROLL` approve 뒤 applied recommendation이 review snapshot / refreshed timeline surface에서 빠지거나 fallback `provider_trace`가 `rule_based_fallback`으로 틀어질 수 있었다
- strict TDD로 `test_review_snapshot_api_approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback` exact regression을 먼저 추가했고, 실제로 approve 응답의 `applied_recommendations`가 비어 있는 RED를 확인했다
- 원인은 approve mutation의 fallback trace 선택, runtime timeline hydration의 supported-type 판정, store review snapshot/read path의 supported-type 및 fallback trace 판정이 모두 mixed-case canonicalization 없이 따로 비교하던 점이었다
- 최소 수정으로 세 경로에 recommendation type `strip().lower()` canonicalization helper를 추가해, mixed-case `BROLL`도 approve 이후 canonical B-roll type으로 판정되도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approve/read path의 mixed-case recommendation type 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback or test_review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback or approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or canonicalizes_mixed_case_recommendation_type"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve mutation + runtime hydration + store read path의 mixed-case canonicalization 경계는 exact + output-focused + current-focused-parallel evidence가 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. pending `BROLL` approve도 mixed-case recommendation type shape를 canonical B-roll type으로 판정한다
2. approve 응답과 refreshed timeline read path가 같은 applied recommendation surface를 유지한다
3. mixed-case type에서도 fallback provider trace가 B-roll 기준 `heuristic_fallback`으로 일관되게 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 87. 2026-07-04 preview renderer mixed-case tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview renderer의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 applied recommendation의 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` shape를 approved TTS override로 인식하지 못하고 preview HTML에 original narration source를 계속 노출하고 있었다
- strict TDD로 `test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML이 `tts_selected.wav`가 아니라 original narration source를 노출하는 RED를 확인했다
- 원인은 preview renderer의 TTS applied-segment 판정이 trimmed whitespace는 처리해도 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 preview renderer에 recommendation type `strip().lower()` canonicalization helper를 추가해, mixed-case `TTS_REPLACEMENT`도 canonical TTS override로 인식하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview/TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_mixed_case_tts_recommendation_type_for_narration_source or matches_trimmed_tts_recommendation_type_for_narration_source or string_false_tts_recommendation_review_required_as_false"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 mixed-case TTS type canonicalization 한 점 수정이라 exact + output-focused + current-focused-parallel evidence가 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 mixed-case `TTS_REPLACEMENT` shape도 canonical TTS override로 인식한다
2. preview HTML narration source가 mixed-case type에서도 selected TTS source를 유지한다
3. preview/TTS read truth가 trimmed type / bool-ish normalization 규칙과 같은 canonical lowercase type 기준을 사용한다

## 88. 2026-07-04 capcut export mixed-case tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 바로 닿는 CapCut export adapter의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 applied recommendation의 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` shape를 approved TTS override로 인식하지 못하고 CapCut voiceover track 첫 segment에 original narration source를 계속 남기고 있었다
- strict TDD로 `test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover 첫 segment `source_uri`가 generated TTS asset이 아니라 original narration source로 남는 RED를 확인했다
- 원인은 CapCut export adapter의 narration override segment 계산이 trimmed whitespace는 처리해도 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 adapter에 recommendation type `strip().lower()` canonicalization helper를 추가해, mixed-case `TTS_REPLACEMENT`도 canonical TTS override로 인식하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources"`
  - 결과: `3 passed`
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- helper override note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or string_false_tts_review_required_as_false_for_segment_level_narration_sources"`
  - 결과: `279 deselected`
  - 판단:
    - 이번 exact 이름들은 현재 helper의 backend lane 수집 범위와 맞지 않아 direct focused pytest가 더 직접적인 evidence였다
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 mixed-case type canonicalization 한 점 수정이라 exact + family-focused + current-focused-parallel evidence가 직접적이다
    - latest full broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 mixed-case `TTS_REPLACEMENT` shape도 canonical TTS override로 인식한다
2. CapCut voiceover track source가 mixed-case type에서도 selected narration source를 유지한다
3. CapCut export TTS read truth가 preview renderer / trimmed type / bool-ish normalization 규칙과 같은 canonical lowercase type 기준을 사용한다

## 89. 2026-07-04 development operating rules promoted to top-level plan closeout

이번 후속 작업에서는 기능 slice를 넓히지 않고, 직전에 fast-path SSOT에 저장한 개발 운영 규정을 실제 프로젝트 개발 최상위 문서에도 연결하는 문서 경계 1개만 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`에는 운영 규정이 들어갔지만, 최상위 구현 계획서인 `docs/implementation-plan.ko.md` 상단에는 그 규정이 프로젝트 전역 기본값이라는 연결 고리가 아직 직접 적혀 있지 않았다
- 이 상태로 두면 다음 turn에 구현 계획서만 먼저 읽는 흐름에서 운영 규정이 최상위 기준으로 보이지 않을 수 있었다
- 최소 수정으로 `docs/implementation-plan.ko.md` 상단에 `docs/development-fast-path.ko.md ## 10`을 프로젝트 전역 개발 운영 규정으로 적용한다는 문장을 추가해, 계획서 실행 규칙과 운영 규정의 우선순위를 같은 입구에서 바로 확인할 수 있게 맞췄다
- 이번 수정은 기능 동작, 테스트 경로, SSOT 계약을 건드리지 않고 문서 상위 규칙 연결만 좁게 정리했다

이번 turn의 verification은 아래와 같다.

- `git status --short --branch`
  - clean branch 확인
- `git log -5 --oneline`
  - 직전 운영 규정 반영 커밋 확인
- SSOT 확인
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - `docs/development-fast-path.ko.md`
- diff 확인
  - 구현 계획서 상단 연결과 상태 문서 기록, closeout 문서 외 불필요한 변경이 없는지 확인

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. 개발 운영 규정이 fast-path 문서뿐 아니라 최상위 구현 계획서 입구에서도 바로 보인다
2. 이후 turn에서 계획서 우선 진입 시에도 운영 규정의 전역 적용 범위를 놓치지 않는다
3. 기능 slice와 운영 규정 SSOT의 문서 우선순위가 더 분명해졌다

## 90. 2026-07-04 timeline builder mixed-case tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 `timeline_builder`의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`는 recommendation type을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` shape를 supported recommendation으로 유지하면서도 narration clip 반영 분기에서는 승인된 TTS override로 인식하지 못하고 있었다
- strict TDD로 `test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 generated TTS asset이 아니라 original segment URI로 남는 RED를 확인했다
- 원인은 supported-type 필터와 narration/B-roll/BGM clip 반영 분기가 whitespace trim까지만 하고 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 `timeline_builder`에 recommendation type `strip().lower()` helper를 추가하고 supported-type 판정과 narration/B-roll/BGM clip 반영 분기에 재사용해, mixed-case `TTS_REPLACEMENT`도 canonical TTS override로 인식하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace"`
  - 결과: `3 passed`
- helper override note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or review_snapshot_uses_trimmed_broll_type_for_default_provider_trace"`
  - 결과: `279 deselected`
  - 판단:
    - 이번 exact 이름들은 helper backend lane 기본 수집 범위와 맞지 않아 direct focused pytest가 더 직접적인 evidence였다
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 첫 실행:
    - backend output-gating `1 failed`
    - backend preflight `1 failed`
    - 같은 `_create_timeline_review_project()` setup에서 `broll-recommendation` 응답이 `job_id`를 주지 못하는 비결정성 실패
  - 단일 exact 재검증:
    - `py -m pytest tests/test_api.py -q -k "test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail" -vv`
    - 결과: `1 passed`
  - 두 번째 `current-focused-parallel` 재실행:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
  - 판단:
    - 첫 실패는 이번 수정의 직접 회귀라기보다 병렬 helper 실행의 일시적 비결정성으로 봤고, exact 재검증과 helper 재실행으로 현재 slice 기준 green을 다시 확인했다
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder mixed-case type canonicalization 한 점 수정이라 exact + 인접 focused + current-focused-parallel evidence가 직접적이다
    - latest full broader baseline은 기존 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder가 mixed-case `TTS_REPLACEMENT` shape도 canonical TTS override로 인식한다
2. narration clip `asset_uri`가 mixed-case type에서도 selected TTS source를 유지한다
3. timeline builder의 recommendation type 판정이 preview renderer / CapCut export / trimmed type canonicalization 규칙과 같은 canonical lowercase type 기준을 사용한다

## 91. 2026-07-04 partial regeneration mixed-case stale tts recommendation replacement closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 partial regeneration runtime의 mixed-case stale TTS recommendation 교체 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`는 source timeline `applied_recommendations` 정리 시 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` stale recommendation이 남아 있으면 새 manual TTS selection이 기존 stale asset을 교체하지 못하고 있었다
- strict TDD로 `test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result narration clip `asset_uri`가 stale mixed-case TTS asset URI 그대로 남는 RED를 확인했다
- 원인은 runtime `tts_refresh` stale recommendation 제거 분기가 whitespace trim까지만 하고 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 `tts_refresh` stale recommendation 제거 비교도 기존 runtime helper `_canonical_runtime_recommendation_type(...)`를 재사용하게 맞춰, mixed-case `TTS_REPLACEMENT` stale recommendation도 새 manual TTS selection으로 정상 교체되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration TTS refresh truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused adjacency verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration"`
  - 결과: `1 passed`
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과: `1 passed`
- attempted grouped verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과:
    - mixed-case exact는 pass
    - `_create_timeline_review_project()` setup 안의 `broll-recommendation` 응답이 `job_id`를 주지 못하는 비결정성 failure가 재발
- helper note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과: 인접 테스트에서 같은 `_create_timeline_review_project()` setup 비결정성 failure가 재발
  - 판단:
    - 이번 slice의 직접 회귀라기보다 existing helper/setup instability로 봤고, exact + 인접 개별 재검증을 현재 근거로 채택했다
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating lane와 backend preflight lane에서 같은 `_create_timeline_review_project()` / `broll-recommendation` setup failure가 재현
    - frontend preflight `25 passed`
  - 판단:
    - current-focused helper는 현재 브랜치에 이미 존재하는 setup instability 때문에 이번 turn close 근거로 쓰기 어렵고, 이번 코드 변경의 직접 영향 증거는 exact + 인접 개별 재검증이 더 정확했다
- broader verification
  - 실행하지 않음
  - 판단:
    - partial regeneration runtime mixed-case TTS replacement 한 점 수정이라 exact + adjacency evidence가 직접적이다
    - 다만 helper/setup instability는 별도 리스크로 남긴다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime `tts_refresh`가 mixed-case `TTS_REPLACEMENT` stale recommendation도 canonical lowercase type 기준으로 제거한다
2. partial regeneration result narration clip `asset_uri`가 stale mixed-case TTS asset 대신 새 manual TTS source를 유지한다
3. partial regeneration runtime의 TTS recommendation type 판정이 timeline builder / preview renderer / CapCut export와 같은 canonical lowercase type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 38. 2026-07-04 capcut export string false tts review_required closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, 방금 닫은 CapCut export trimmed type 경계와 같은 출력 family에서 `TTS approval/output`에 바로 닿는 legacy bool-shape 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 applied TTS recommendation의 `auto_apply_allowed` / `review_required`를 raw `bool(...)`로 읽고 있어, legacy string false shape인 `review_required="false"`를 truthy로 오판해 narration override segment를 놓치고 있었다
- strict TDD로 `test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 export manifest의 first `voiceover` segment가 generated TTS source가 아니라 original narration source로 내려가는 RED를 확인했다
- 최소 수정으로 CapCut export adapter에도 bool-ish normalization helper를 추가해 `auto_apply_allowed/review_required`를 canonical bool로 해석하도록 맞춰, legacy string false shape여도 segment-level narration source override truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 export output 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_preview_export.py` focused `3 passed`
  - `tests/test_api.py` preview/export flow focused `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 bool-ish normalization 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace가 섞인 stale approved `tts_replacement` type도 canonical TTS override로 인식함
2. CapCut export adapter가 legacy string false `review_required="false"`도 canonical false로 해석함
3. preview/export output이 approved TTS selection truth를 같은 기준으로 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 37. 2026-07-04 capcut export trimmed tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, 방금 닫은 preview renderer와 같은 출력 family에서 `TTS approval/output`에 가장 가까운 CapCut export adapter의 trimmed recommendation type regression 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 applied recommendation의 `recommendation_type` 비교에 raw equality를 쓰고 있어, `" tts_replacement "`처럼 whitespace가 섞인 stale approved shape를 narration override segment로 인식하지 못하고 CapCut voiceover track 첫 segment를 original narration source로 유지하고 있었다
- strict TDD로 `test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 export manifest의 first `voiceover` segment가 generated TTS source가 아니라 original narration source로 내려가는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 narration override segment 판정도 `recommendation_type.strip() == "tts_replacement"` 기준을 사용하도록 맞춰, stale whitespace type shape여도 segment-level narration source override truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 export output 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_preview_export.py` focused `2 passed`
  - `tests/test_api.py` export/preview flow focused `1 passed`
  - helper output-gating override `1 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 trimmed recommendation-type 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 whitespace가 섞인 stale approved `tts_replacement` type도 canonical TTS override로 인식함
2. CapCut export adapter도 whitespace가 섞인 stale approved `tts_replacement` type을 canonical TTS override로 인식함
3. preview/export output이 approved TTS selection truth를 같은 기준으로 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 36. 2026-07-04 preview renderer trimmed tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 실제 출력 경계로 남아 있던 preview renderer의 trimmed recommendation type regression 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 applied recommendation의 `recommendation_type` 비교에 raw equality를 쓰고 있어, `" tts_replacement "`처럼 whitespace가 섞인 stale approved shape를 TTS override로 인식하지 못하고 preview HTML narration source를 original narration source로 되돌리고 있었다
- strict TDD로 `test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML에 `tts_selected.wav` 대신 original narration source가 노출되는 RED를 확인했다
- 최소 수정으로 preview renderer의 TTS segment 판정도 `recommendation_type.strip() == "tts_replacement"` 기준을 사용하도록 맞춰, stale whitespace type shape여도 selected narration source를 계속 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview output 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 trimmed recommendation-type 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy false-like recommendation fields를 canonical bool로 해석함
2. preview renderer가 whitespace가 섞인 stale approved `tts_replacement` type도 canonical TTS override로 인식함
3. preview HTML narration source가 approved TTS selection truth를 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 35. 2026-07-04 partial regeneration trimmed stale applied bgm replacement closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지하되, 이미 닫은 TTS/B-roll trim family와 같은 자리에서 `local_pipeline` partial regeneration output path에 남아 있던 가장 작은 BGM 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- partial regeneration runtime의 `music_refresh`는 source timeline `applied_recommendations`에 whitespace가 섞인 stale approved `recommendation_type=" bgm "`가 남아 있으면 기존 applied recommendation을 제거하지 못해 stale music clip과 새 manual music clip을 함께 남기고 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 bgm track 첫 clip이 `music_manual_001`이 아니라 stale `music_stale_001`로 남고 manual clip이 뒤에 추가되는 RED를 확인했다
- 원인은 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`가 stale applied recommendation 제거 시 `recommendation_type` 비교에 `strip()`을 쓰지 않던 점이었다
- 최소 수정으로 `music_refresh`도 TTS/B-roll과 같은 canonical trim 비교를 사용하도록 맞춰, manual music override가 stale whitespace recommendation type을 덮어쓰는 runtime truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration music replacement 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 같은 trim family의 `music_refresh` 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime의 `tts_refresh`가 stale trimmed applied TTS recommendation을 manual selection truth로 교체함
2. partial regeneration runtime의 `broll_refresh`가 stale trimmed applied B-roll recommendation을 manual selection truth로 교체함
3. partial regeneration runtime의 `music_refresh`도 stale trimmed applied BGM recommendation을 manual selection truth로 교체함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 57. 2026-07-04 review snapshot helper unknown pending recommendation surface closeout

이번 후속 작업에서는 direct review-snapshot helper의 stale recommendation family를 한 단계 더 좁혀, unknown legacy pending recommendation이 status는 막지 않더라도 `pending_recommendations` surface에는 blocker처럼 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 helper status 계산은 이미 canonical blocker만 보도록 좁혀졌지만, `pending_recommendations` surface는 `decision_state="pending"`만 보면 recommendation type validity와 무관하게 그대로 남기고 있었다
- strict TDD로 `test_store_build_review_snapshot_filters_unknown_pending_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `pending_recommendations`에 `legacy_overlay_pick` stale entry가 그대로 남는 RED를 확인했다
- 최소 수정으로 direct helper pending surface도 canonical blocking pending recommendation만 유지하도록 좁혀, unknown / non-blocking pending recommendation은 status뿐 아니라 helper surface에서도 blocker처럼 남지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper pending-surface truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper unknown-pending surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_pending_recommendations` shape를 `pending_recommendations` surface에 blocker처럼 남기지 않음
2. helper status truth와 pending surface truth가 stale recommendation family에서 같은 기준을 사용함
3. helper pending surface와 runtime output gating / preflight read truth가 같은 canonical blocker 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 58. 2026-07-04 timeline persistence unknown pending recommendation initial status closeout

이번 후속 작업에서는 direct review-snapshot helper와 output gating truth를 다시 넓히지 않고, 그 바로 아래 persistence initial review state가 unknown pending recommendation stale entry 하나 때문에 `blocked`로 저장되는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)`는 initial review status를 계산할 때 pending/applied bucket 안 recommendation의 normalized `decision_state == "pending"`만 보면 blocker로 세고 있어, `legacy_overlay_pick` 같은 unknown recommendation type도 `blocked` 초기 상태로 저장하고 있었다
- strict TDD로 `test_store_save_timeline_run_ignores_unknown_pending_recommendation_when_setting_initial_status` exact regression을 먼저 추가했고, 실제로 `review_state["status"] == "blocked"` RED를 확인했다
- 최소 수정으로 persistence initial status 계산도 canonical blocking pending recommendation만 blocker로 세도록 좁혀, unknown / non-blocking pending recommendation 하나만으로는 `draft` truth를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence initial-status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline persistence initial-status blocker classification 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline persistence initial review state가 unknown / non-blocking `pending_recommendations` shape 하나만으로 `blocked`를 저장하지 않음
2. canonical blocking pending recommendation이 없는 경우 persisted initial review state가 `draft` truth를 유지함
3. persistence initial-status truth와 review snapshot helper / runtime output gating truth가 같은 canonical blocker 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 59. 2026-07-04 timeline API unknown applied recommendation surface closeout

이번 후속 작업에서는 이미 닫힌 pending-like misbucketed applied 경계를 다시 넓히지 않고, timeline API read path에 남아 있던 unknown stale recommendation applied-surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_hydrate_timeline_review_status(...)`는 applied recommendation read path에서 pending-like blocker만 제외하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry는 approved timeline의 `applied_recommendations` surface에 그대로 남기고 있었다
- strict TDD로 `test_timeline_api_filters_unknown_type_entry_misbucketed_into_applied_recommendations` exact regression을 먼저 추가했고, 실제로 `payload["applied_recommendations"]`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 timeline API applied surface도 canonical supported recommendation type만 유지하도록 좁혀, unknown / non-blocking applied stale entry는 user-facing surface에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline API applied-surface truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline API applied-surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline API read path가 unknown / non-blocking `applied_recommendations` stale entry를 applied surface에 남기지 않음
2. canonical supported recommendation type만 user-facing applied surface에 유지됨
3. timeline API applied surface truth와 pending blocker read truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 60. 2026-07-04 review snapshot helper unknown applied recommendation surface closeout

이번 후속 작업에서는 timeline API applied-surface truth를 다시 넓히지 않고, direct review-snapshot helper override 입력에 남아 있던 unknown applied stale recommendation surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 applied surface를 만들 때 `decision_state="approved"`만 보면 recommendation type validity와 무관하게 그대로 남기고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry를 applied surface에 계속 노출하고 있었다
- strict TDD로 `test_store_build_review_snapshot_filters_unknown_applied_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `snapshot["applied_recommendations"]`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 direct helper applied surface도 canonical supported recommendation type만 유지하도록 좁혀, unknown / non-blocking applied stale entry는 helper surface에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper applied-surface truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper applied-surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_applied_recommendations` stale entry를 applied surface에 남기지 않음
2. canonical supported recommendation type만 helper applied surface에 유지됨
3. review snapshot helper applied surface truth와 timeline API read truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 61. 2026-07-04 timeline builder unknown applied recommendation surface closeout

이번 후속 작업에서는 helper/API applied-surface truth를 다시 넓히지 않고, partial regeneration runtime이 직접 의존하는 timeline builder source-truth에 남아 있던 unknown applied stale recommendation surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `build(...)`는 recommendation을 normalized bool fields만 보고 분류하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry도 `auto_apply_allowed=true` / `review_required=false`이면 applied surface에 그대로 남기고 있었다
- strict TDD로 `test_timeline_builder_filters_unknown_applied_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `timeline.applied_recommendations`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 builder도 canonical supported recommendation type만 recommendation flow에 반입하도록 좁혀, unknown / non-blocking applied stale entry는 source-truth 단계에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder source-truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder source-truth filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder가 unknown / non-blocking recommendation stale entry를 applied/pending surface에 반입하지 않음
2. canonical supported recommendation type만 builder source-truth에 유지됨
3. builder source-truth와 review snapshot helper / timeline API applied surface truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 62. 2026-07-04 timeline builder review snapshot unknown applied recommendation surface closeout

이번 후속 작업에서는 timeline builder 본체 applied-surface truth를 다시 넓히지 않고, 같은 파일의 review snapshot direct dict 입력면에 남아 있던 unknown applied stale recommendation surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `build_review_snapshot(...)`는 recommendation을 bool fields만 보고 분류하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry도 `auto_apply_allowed=true` / `review_required=false`이면 applied surface에 그대로 남기고 있었다
- strict TDD로 `test_timeline_builder_review_snapshot_filters_unknown_applied_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `snapshot["applied_recommendations"]`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 builder review snapshot도 canonical supported recommendation type만 recommendation flow에 반입하도록 좁혀, unknown / non-blocking applied stale entry는 source-truth 단계에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder review snapshot truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder review snapshot source-truth filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder review snapshot이 unknown / non-blocking recommendation stale entry를 applied/pending surface에 반입하지 않음
2. canonical supported recommendation type만 builder review snapshot truth에 유지됨
3. timeline builder 본체와 builder review snapshot truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 81. 2026-07-04 partial regeneration trimmed stale applied broll replacement closeout

이번 후속 작업에서는 방금 닫은 partial regeneration `tts_refresh` trim family를 `broll_refresh`까지 이어, stale approved recommendation 교체 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_broll_refresh_step(...)`도 refresh 전에 기존 B-roll recommendation을 걷어낼 때 raw `recommendation_type` 비교를 써 source timeline에 `" broll "` stale approved recommendation이 남아 있으면 제거하지 못하고 carry-forward하고 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration 결과 broll track에 stale clip과 새 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `broll_refresh` 기존 recommendation 제거 분기도 canonical trimmed type 기준으로 비교하게 맞춰, whitespace가 섞인 stale approved B-roll recommendation도 새 manual selection으로 정상 교체되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime `broll_refresh` trim 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_api.py -k "replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace"` -> `2 passed`

남은 판단:

- broader verification은 이번 수정이 partial regeneration runtime `broll_refresh` type 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 80. 2026-07-04 partial regeneration trimmed stale applied tts replacement closeout

이번 후속 작업에서는 timeline builder 쪽에서 막 닫은 trimmed recommendation type family를 partial regeneration runtime의 `tts_refresh` 단계까지 이어, stale approved recommendation 교체 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`는 refresh 전에 기존 TTS recommendation을 걷어낼 때 raw `recommendation_type` 비교를 써 source timeline에 `" tts_replacement "` stale approved recommendation이 남아 있으면 제거하지 못하고 carry-forward하고 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration 결과 narration clip이 새 manual TTS asset이 아니라 stale approved asset URI를 계속 쓰는 RED를 확인했다
- 최소 수정으로 `tts_refresh` 기존 recommendation 제거 분기도 canonical trimmed type 기준으로 비교하게 맞춰, whitespace가 섞인 stale approved TTS recommendation도 새 manual selection으로 정상 교체되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime `tts_refresh` trim 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_api.py -k "replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type"` -> `2 passed`

남은 판단:

- broader verification은 이번 수정이 partial regeneration runtime `tts_refresh` type 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 79. 2026-07-04 timeline builder trimmed approved recommendation type closeout

이번 후속 작업에서는 방금 닫은 review snapshot helper trim family를 timeline builder 본체까지 이어, approved recommendation clip 반영 분기에 남아 있던 whitespace recommendation type 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`는 recommendation type 지원 여부 필터에서는 이미 `strip()`을 쓰고 있었지만, 실제 narration/B-roll/BGM clip 반영 분기에서는 raw `recommendation_type` 비교를 써 `" tts_replacement "` stale shape를 approved recommendation으로 유지하면서도 narration clip 반영은 놓치고 있었다
- strict TDD로 `test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 source segment URI로 남는 RED를 확인했다
- 최소 수정으로 timeline builder 내부의 approved recommendation type 분기도 canonical trimmed type 기준으로 비교하게 맞춰, whitespace가 섞인 approved recommendation도 narration/B-roll/BGM clip 반영 truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder approved recommendation type 분기 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_review_timeline.py -k "timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"` -> `2 passed`

남은 판단:

- broader verification은 이번 수정이 timeline builder의 approved recommendation type 비교 2줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 78. 2026-07-04 review snapshot trimmed provider-trace fallback recommendation type closeout

이번 후속 작업에서는 approve mutation 쪽에서 막 닫은 trimmed provider-trace fallback family를 review snapshot helper read path까지 이어, 같은 stale whitespace recommendation type 경계 1개만 다시 닫았다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_review_snapshot_recommendation_payload(...)`는 recommendation `provider_trace`가 비어 있으면 recommendation type으로 fallback provider를 고르는데, 여기만 `recommendation_type` trim이 빠져 `" broll "` stale shape가 `rule_based_fallback`으로 잘못 내려가고 있었다
- strict TDD로 `test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace` exact regression을 먼저 추가했고, 실제로 review snapshot `applied_recommendations[0].provider_trace.final_provider == "rule_based_fallback"` RED를 확인했다
- 최소 수정으로 review snapshot helper fallback provider 선택도 `recommendation_type.strip()` 기준으로 비교하게 맞춰, whitespace가 섞인 persisted B-roll recommendation도 review snapshot applied recommendation에서 `heuristic_fallback` trace를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper provider-trace fallback 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_review_timeline.py -k "trimmed_broll_type_for_default_provider_trace"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"` -> `3 passed`

남은 판단:

- broader verification은 이번 수정이 review snapshot helper fallback provider 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 77. 2026-07-04 approve trimmed provider-trace fallback recommendation type closeout

이번 후속 작업에서는 이미 닫힌 TTS approve mutation과 output gating 경계를 다시 넓히지 않고, approve mutation fallback trace 선택에 남아 있던 recommendation type trim 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `extract_pending_recommendation_decision(...)`는 approve 시 `provider_trace`가 비어 있으면 recommendation type으로 fallback provider를 고르는데, 여기만 `recommendation_type` trim이 빠져 `" broll "` stale shape가 `rule_based_fallback`으로 잘못 내려가고 있었다
- strict TDD로 `test_review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback` exact regression을 먼저 추가했고, 실제로 approve response의 `applied_recommendations[0].provider_trace.final_provider == "rule_based_fallback"` RED를 확인했다
- 최소 수정으로 fallback provider 선택도 `recommendation_type.strip()` 기준으로 비교하게 맞춰, whitespace가 섞인 persisted B-roll recommendation도 approve response와 persisted applied recommendation에서 `heuristic_fallback` trace를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approve mutation provider-trace fallback 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_api.py -k "approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_can_reject_pending_recommendation_without_leaving_it_pending or approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail"` -> `4 passed`

남은 판단:

- broader verification은 이번 수정이 approve mutation fallback provider 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 76. 2026-07-04 review snapshot approve trimmed recommendation type closeout

이번 후속 작업에서는 현재 clean baseline을 넓게 흔들지 않고, `TTS approval/output` approve mutation 안에 남아 있던 stale whitespace recommendation-type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `apply_approved_recommendation_to_timeline(...)`는 `recommendation_type`만 `strip()` 없이 raw 비교하고 있어, persisted pending recommendation의 type이 `" tts_replacement "`처럼 저장된 stale shape면 approve 성공 뒤에도 narration clip `asset_uri` 반영을 건너뛰고 있었다
- strict TDD로 `test_review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type` exact regression을 먼저 RED로 확인했고, 실제로 approve 뒤 persisted narration clip `asset_uri`가 original source 그대로 남는 실패가 났다
- 원인은 approve mutation이 canonical TTS type인지 판정하는 분기에서 whitespace normalization을 빠뜨린 점이었다
- 최소 수정으로 `recommendation_type` 비교에도 `.strip()`을 적용해, stale whitespace type shape여도 canonical `tts_replacement` 기준으로 narration clip 반영을 계속 수행하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 TTS approve mutation stale-type tolerance 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `16 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - TTS approve recommendation-type trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. pending `tts_replacement` approve가 whitespace가 섞인 persisted `recommendation_type` stale shape여도 narration clip 반영을 계속 수행한다
2. approve mutation의 recommendation-type trim tolerance가 기존 segment-id / recommendation-id trim hardening 방향과 맞춰졌다
3. TTS approve persisted truth와 preview/export read path가 type whitespace 때문에 어긋나지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 75. 2026-07-04 review timeline import-cycle closeout

이번 후속 작업에서는 이미 닫힌 review snapshot split/output gating 경계를 다시 넓히지 않고, 그 검증 자체를 막고 있던 import-cycle collection 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `tests/test_review_timeline.py::test_review_snapshot_splits_applied_and_pending_recommendations`는 현재 worktree에서 `videobox_storage.local_project_store -> videobox_core_engine.provider_trace` import 경로가 package-level eager import chain을 타면서 `LocalProjectStore` circular import collection error로 막히고 있었다
- strict TDD로 위 exact를 그대로 RED로 확인했고, 실제로 assertion failure가 아니라 `ImportError: cannot import name 'LocalProjectStore' from partially initialized module ...` collection error가 났다
- 원인은 `packages/core-engine/src/videobox_core_engine/__init__.py`가 `LocalPipelineRunner` 등 heavy module을 package import 시점에 eager import하고 있어, provider_trace 하나만 읽어도 local pipeline과 gemini runtime까지 같이 올라가던 점이었다
- 최소 수정으로 package root를 lazy export `__getattr__` 기반으로 바꿔 `videobox_core_engine.provider_trace` 같은 direct submodule import가 heavy eager import chain을 타지 않도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 test collection/import boundary만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- direct helper file
  - `2 passed`
- output-gating focused slice
  - `40 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - package import-cycle 한 점에 국한된 수정이라 exact + direct helper file + review-snapshot focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. `tests/test_review_timeline.py`가 review snapshot helper exact를 다시 collection error 없이 수집하고 실행한다
2. `videobox_core_engine.provider_trace` import가 package root eager import 때문에 local pipeline/gemini runtime circular chain으로 번지지 않는다
3. review snapshot helper exact와 output-gating review-snapshot lane을 현재 worktree에서도 다시 직접 검증할 수 있다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 74. 2026-07-04 review snapshot split without inline recommendation type closeout

이번 후속 작업에서는 이미 닫힌 stale pending/provider-trace/string-false 경계를 다시 넓히지 않고, review snapshot helper의 direct recommendation input applied/pending split 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `tests/test_review_timeline.py::test_review_snapshot_splits_applied_and_pending_recommendations`는 현재 worktree에서 import collection error가 먼저 발생해 exact RED로 쓰기 어려웠고, 실제 경계는 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)` direct recommendations 분기였다
- strict TDD로 같은 helper 로직을 `tests/test_api.py::test_store_build_review_snapshot_splits_applied_and_pending_recommendations_without_inline_type` exact regression으로 먼저 RED로 확인했고, 실제로 `applied_recommendations == []` 실패가 났다
- 원인은 direct recommendation 입력에 inline `recommendation_type`가 빠져 있으면 helper가 canonical recommendation type truth를 잃은 채 supported-type filter에서 그대로 버리던 점이었다
- 최소 수정으로 direct recommendations 분기에서 missing inline type이 있을 때만 persisted recommendation rows를 읽고, target segment / selected asset / reason / score가 유일하게 맞는 경우에만 canonical `recommendation_type`을 복원하도록 좁혀, applied/pending split truth를 다시 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper direct-input recommendation type truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `40 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper direct-input type hydration 한 점에 국한된 수정이라 exact + review-snapshot focused evidence가 더 직접적이다
    - `tests/test_review_timeline.py` collection error는 별도 next slice에서 다시 다루는 편이 정확하다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 inline `recommendation_type`가 비어 있는 historical recommendation 입력도 persisted truth와 유일하게 매칭되면 applied/pending split을 유지한다
2. direct helper applied/pending surface truth와 persisted recommendation row truth가 다시 어긋나지 않는다
3. missing type 복원은 유일 매칭일 때만 수행돼 unknown stale recommendation surface를 다시 넓히지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 73. 2026-07-04 approve persists remaining segment review-required blocker closeout

이번 후속 작업에서는 이미 닫힌 whitespace/provider-trace/rollback 경계를 다시 넓히지 않고, broader verification에서 실제로 드러난 `TTS approval/output` persisted blocker 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_persist_pending_recommendation_decision(...)`는 approve mutation timeline을 먼저 저장한 뒤 synthetic blocker를 다시 계산하고 있어, last pending `tts_replacement` approve 뒤 다른 segment의 `review_required=true` truth가 persisted timeline `review_flags`에는 다시 쓰이지 않고 있었다
- strict TDD로 `test_approving_last_pending_tts_replacement_persists_remaining_segment_review_required_blocker` exact regression을 먼저 RED로 확인했고, 실제로 approve 뒤 persisted timeline `review_flags == []` 실패가 났다
- 원인은 normalized blocker 재계산 시점이 timeline persist보다 늦어 최종 `segment_review_required` synthetic flag가 저장 파일에 반영되지 않던 점이었다
- 최소 수정으로 `_persist_pending_recommendation_decision(...)`가 timeline persist 전에 normalized `review_flags` / `pending_recommendations`를 먼저 계산해 payload에 반영하도록 순서를 좁혀, approve 뒤 남아 있는 segment-level blocker truth도 persisted timeline에 그대로 쓰이게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 TTS approve persisted-blocker truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - persisted blocker write-order 한 점에 국한된 수정이라 exact + output-gating focused evidence가 더 직접적이다
    - broader에서 남아 있던 다른 실제 실패는 다음 slice에서 별도로 exact RED부터 다시 다루는 편이 더 정확하다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. last pending `tts_replacement` approve 뒤에도 다른 segment의 `review_required=true` truth가 persisted timeline `review_flags`에 synthetic `segment_review_required` blocker로 다시 남는다
2. approve mutation의 persisted timeline truth와 output gating / review snapshot blocker truth가 다시 어긋나지 않는다
3. TTS approval persistence가 final blocker normalization 순서를 기준으로 같은 저장 진실을 유지한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 72. 2026-07-04 approve rollback raw persisted timeline closeout

이번 후속 작업에서는 새로운 approval/output stale-shape slice를 더 열지 않고, 누적 변경 검증 중 드러난 review-action rollback 회귀 1개를 먼저 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_prepare_pending_recommendation_decision(...)`는 rollback용 `original_timeline`을 raw persisted timeline이 아니라 `get_timeline_result(...)`의 hydrated response shape에서 가져오고 있어, review state 저장 실패 후 rollback이 실행되면 provider trace가 없는 pending recommendation까지 hydrated shape로 다시 저장하고 있었다
- 기존 exact regression `test_review_snapshot_api_approve_rolls_back_timeline_and_recommendation_when_review_state_save_fails`를 다시 RED로 확인했고, 실제로 rollback 뒤 persisted `pending_recommendations`가 original raw timeline과 달라지는 실패가 났다
- 원인은 rollback source timeline이 API read-path hydration을 이미 거친 객체였다는 점이었다
- 최소 수정으로 pending recommendation decision 준비 단계는 job type에 따라 store의 raw timeline payload만 직접 읽어 rollback source로 보관하도록 좁혀, downstream failure 후 timeline rollback이 original persisted shape를 그대로 복구하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review-action rollback raw-timeline restoration 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- paired rollback regression
  - `1 passed`
- review-action backend focused slice
  - `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rollback source timeline 한 점에 국한된 수정이라 exact + paired exact + review-action focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve rollback이 raw persisted timeline shape를 hydrated response shape로 오염시키지 않는다
2. 같은 rollback source 수정으로 reject rollback도 original pending/applied/review-flag truth를 그대로 복구한다
3. review-action rollback hardening이 response hydration 규칙과 분리된 raw persistence truth를 유지한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 71. 2026-07-04 approve trimmed target segment id blocker cleanup closeout

이번 후속 작업에서는 방금 닫은 approval/output applied recommendation id canonicalization 경계를 다시 넓히지 않고, 같은 helper 안에 남아 있던 `target_segment_id` whitespace stale shape로 인한 blocker cleanup 비대칭 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 review flag cleanup은 `should_keep_review_flag(...)` 내부 비교는 trim 기준으로 맞춰졌지만, 그 앞단 `filtered_review_flags_after_recommendation_decision(...)`가 `decided_recommendation.target_segment_id`를 raw로 유지하고 있어 whitespace가 섞인 stale pending recommendation이면 last pending approve 뒤에도 blocker가 남고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_blocker_with_trimmed_target_segment_id` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 원인은 cleanup helper가 `target_segment_id`를 trim하지 않고 recommendation flag key를 계산하던 점이었다
- 최소 수정으로 review flag cleanup helper의 `target_segment_id`도 trim해서 canonical target segment 기준으로 비교하도록 좁혀, stale whitespace target segment shape여도 blocker cleanup이 같은 기준으로 동작하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output target-segment blocker-cleanup 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - target segment blocker cleanup trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject review-flag cleanup이 whitespace가 섞인 persisted `target_segment_id`도 canonical target segment로 식별한다
2. stale trimmed target segment id 때문에 last pending approve 뒤 `review_status=blocked`가 남지 않는다
3. approval/output helper의 trim stale-shape family가 selection, decision-map, applied surface, blocker cleanup에서 같은 canonical segment/id 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 70. 2026-07-04 approve trimmed persisted applied recommendation id closeout

이번 후속 작업에서는 방금 닫은 approval/output decision-map stale-key cleanup 경계를 다시 넓히지 않고, 같은 helper 안에 남아 있던 persisted `applied_recommendations` recommendation id canonicalization 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 pending recommendation decision extraction은 route의 canonical id로 대상을 찾더라도, `decided_recommendation` 자체에는 source pending item의 whitespace `recommendation_id`를 그대로 남겨 persisted `applied_recommendations` surface가 stale id를 보존하고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_persists_canonical_trimmed_recommendation_id` exact regression을 먼저 추가했고, 실제로 approve 뒤 persisted `applied_recommendations[0].recommendation_id`가 whitespace id 그대로 남는 RED를 확인했다
- 원인은 `extract_pending_recommendation_decision(...)`가 matched recommendation을 deepcopy한 뒤 canonical route id로 `recommendation_id`를 덮어쓰지 않던 점이었다
- 최소 수정으로 matched `decided_recommendation`의 `recommendation_id`를 route의 canonical id로 즉시 정규화해, persisted applied recommendation surface도 selection truth와 같은 canonical id를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output applied-recommendation id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - applied recommendation id canonicalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject selection이 canonical route id를 찾으면 persisted `applied_recommendations` surface도 같은 canonical id를 유지한다
2. stale trimmed pending recommendation id 때문에 applied recommendation surface가 whitespace id를 다시 노출하지 않는다
3. approval/output helper의 trim stale-shape family가 selection, decision-map, applied surface까지 같은 canonical id 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 69. 2026-07-04 approve trimmed recommendation decision key closeout

이번 후속 작업에서는 방금 닫은 approval/output recommendation-id trim selection 경계를 다시 넓히지 않고, 같은 helper 안에 남아 있던 `recommendation_decisions` stale key cleanup 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `timeline_recommendation_decisions(...)`는 whitespace가 섞인 persisted decision key를 필터링만 하고 canonical key로 정규화하지 않아, 같은 recommendation approve 뒤에도 stale key와 canonical key가 동시에 남고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_rewrites_trimmed_recommendation_decision_key` exact regression을 먼저 추가했고, 실제로 approve 뒤 `recommendation_decisions`에 stale whitespace key가 그대로 남는 RED를 확인했다
- 원인은 `timeline_recommendation_decisions(...)`가 기존 dict를 복사할 때 `str(key)` / `str(value)`를 그대로 보존하던 점이었다
- 최소 수정으로 decision map normalization도 key/value를 trim해서 보관하도록 좁혀, stale whitespace key가 canonical recommendation id key 하나로 정리되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output decision-map stale-key cleanup 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation decision-key trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject decision map이 whitespace가 섞인 persisted key도 canonical recommendation id key 하나로 정리한다
2. stale trimmed decision key 때문에 같은 recommendation decision이 중복 key로 남지 않는다
3. approval/output helper의 trim stale-shape family가 selection, review-flag cleanup, decision-map cleanup에서 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 68. 2026-07-04 approve trimmed recommendation id closeout

이번 후속 작업에서는 방금 닫은 review-flag cleanup trim family를 다시 넓히지 않고, 같은 approval/output decision-selection helper 안에 남아 있던 `recommendation_id` whitespace stale shape 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 pending recommendation selection은 route에서 받은 canonical `recommendation_id`와 persisted pending entry의 `recommendation_id`를 raw 문자열로 비교하고 있어 whitespace가 섞인 stale pending entry를 같은 recommendation으로 찾지 못하고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_matches_trimmed_recommendation_id` exact regression을 먼저 추가했고, 실제로 approve 응답이 `404`로 떨어지는 RED를 확인했다
- 원인은 `extract_pending_recommendation_decision(...)`가 `item["recommendation_id"]`를 trim하지 않고 route id와 직접 비교하던 점이었다
- 최소 수정으로 pending recommendation selection이 persisted `recommendation_id`도 trim해서 route의 canonical recommendation id와 비교하도록 좁혀, stale whitespace id shape여도 approve/reject mutation이 같은 recommendation에 적용되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output recommendation-selection stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve/reject recommendation-id trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject recommendation selection이 whitespace가 섞인 persisted `recommendation_id`도 같은 recommendation으로 식별한다
2. stale trimmed recommendation id 때문에 approve/reject가 `404`로 떨어지지 않는다
3. approval/output decision-selection helper가 `recommendation_id`, `review_flag.code`, `review_flag.segment_id` 모두 같은 trim 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 67. 2026-07-04 approve trimmed review flag code closeout

이번 후속 작업에서는 방금 닫은 review-flag `segment_id` trim cleanup 경계를 다시 넓히지 않고, 같은 approval/output cleanup helper 안에 남아 있던 `review_flag.code` whitespace stale shape 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 review flag 정리 로직은 `segment_id` trim은 맞춰졌지만 persisted review flag의 `code`는 raw 문자열로 비교하고 있어 whitespace가 섞인 stale canonical flag code를 같은 blocker로 인식하지 못한 채 남기고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_trimmed_review_flag_code_for_same_segment` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 원인은 `should_keep_review_flag(...)`가 `flag.code`를 trim하지 않고 `recommendation_flag_code`와 직접 비교하던 점이었다
- 최소 수정으로 review flag keep 판정이 `code`도 trim해서 비교하도록 좁혀, stale whitespace canonical review flag code가 approve/reject 뒤 blocker로 남지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output review-flag code cleanup stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve/reject review-flag code trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject review-flag cleanup이 whitespace가 섞인 persisted canonical `code`도 같은 blocker flag로 식별한다
2. stale trimmed review flag code 때문에 last pending approve 뒤 `review_status=blocked`가 남지 않는다
3. approval/output review-flag cleanup helper가 `code`와 `segment_id` 모두 같은 trim 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 66. 2026-07-04 approve trimmed review flag segment id closeout

이번 후속 작업에서는 방금 닫은 TTS approve clip-match stale shape를 다시 넓히지 않고, 같은 approval/output 경계 안에서 persisted review flag 정리 비대칭 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 review flag 정리 로직은 recommendation 쪽 `target_segment_id`와 달리 persisted review flag의 `segment_id`를 raw 문자열로 비교하고 있어 whitespace가 섞인 stale review flag를 같은 세그먼트 blocker로 인식한 채 남기고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_trimmed_review_flag_for_same_segment` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 원인은 `should_keep_review_flag(...)`가 `flag.segment_id`와 remaining pending recommendation의 `target_segment_id`를 trim하지 않고 비교하던 점이었다
- 최소 수정으로 review flag keep 판정도 양쪽 `segment_id`를 trim해서 비교하도록 좁혀, stale whitespace review flag가 approve/reject 뒤 blocker로 남지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output review-flag cleanup stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve/reject review-flag segment-id trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject review-flag cleanup이 whitespace가 섞인 persisted `segment_id`도 같은 세그먼트 flag로 식별한다
2. stale trimmed review flag 때문에 last pending approve 뒤 `review_status=blocked`가 남지 않는다
3. approval/output review-flag cleanup truth가 방금 닫은 clip-match trim truth와 같은 stale-shape 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 65. 2026-07-04 review snapshot approve trimmed target narration clip segment id closeout

이번 후속 작업에서는 just-closed provider-trace/read-contract family를 다시 넓히지 않고, `TTS approval/output` 경계에서 persisted timeline stale shape 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 TTS approve mutation은 recommendation 쪽 `target_segment_id`는 trim해서 읽지만, narration clip 쪽 `segment_id`는 raw 문자열로 비교하고 있어 whitespace가 섞인 persisted clip을 target clip으로 찾지 못했다
- strict TDD로 `test_review_snapshot_api_approve_tts_replacement_matches_trimmed_target_narration_clip_segment_id` exact regression을 먼저 추가했고, 실제로 approve 응답이 `400`으로 떨어지는 RED를 확인했다
- 원인은 approve mutation의 target narration clip match가 `str(clip.get("segment_id") or "") == target_segment_id` raw 비교에 머물러 있던 점이었다
- 최소 수정으로 approved TTS replacement가 narration clip `segment_id`도 trim해서 target segment와 비교하도록 좁혀, stale whitespace clip shape여도 기존 approve truth와 같은 clip을 업데이트하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 TTS approve clip-match stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - TTS approve clip-match trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. TTS approve mutation이 whitespace가 섞인 persisted narration clip `segment_id`도 target clip으로 매칭한다
2. stale clip segment-id shape 때문에 approved `selected_asset_uri` 반영이 `400`으로 막히지 않는다
3. TTS approve mutation truth가 preflight/runtime의 trimmed segment-id handling 방향과 더 이상 어긋나지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 64. 2026-07-04 review snapshot persisted operator guidance default provider trace closeout

이번 후속 작업에서는 partial regeneration result response fallback 경계를 다시 넓히지 않고, 같은 review/output read-contract 축의 바로 인접면인 persisted `operator_guidance` legacy shape 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 review snapshot 응답은 recommendation/review_flag와 달리 persisted `operator_guidance`를 raw `OperatorGuidanceResponse`에 바로 넣고 있어, legacy guidance에 `provider_trace`가 빠져 있으면 응답 모델 validation error가 났다
- strict TDD로 `test_review_snapshot_fills_default_provider_trace_for_persisted_operator_guidance` exact regression을 먼저 추가했고, 실제로 `operator_guidance.provider_trace Field required` RED를 확인했다
- 첫 최소 수정에서 generic response fallback을 재사용하면 `rule_based_fallback`이 들어가 review guidance truth와 어긋났고, guidance response normalization을 별도로 두어 missing trace일 때 `heuristic_fallback`을 채우는 쪽으로 한 단계 더 좁혀 맞췄다
- 최소 수정으로 review snapshot / approve / reject 응답의 operator guidance response layer만 normalization 하도록 좁혀, persisted legacy guidance shape도 canonical fallback trace를 가진 review snapshot response로 읽히게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot operator-guidance read-contract 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot operator-guidance response normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot read path가 missing `provider_trace` persisted operator guidance shape를 그대로 validation error로 흘리지 않음
2. persisted operator guidance response가 `heuristic_fallback` trace를 채운 canonical shape를 유지함
3. review snapshot guidance read truth와 최근 recommendation/provider-trace fallback read truth가 같은 방향의 canonical response 규칙을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 63. 2026-07-04 partial regeneration result applied recommendation default provider trace closeout

이번 후속 작업에서는 partial regeneration source-truth나 blocker 경계를 다시 넓히지 않고, result read path에서 applied recommendation `provider_trace` 누락이 그대로 API validation error로 이어지는 가장 작은 response-contract 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `GET /api/projects/{project_id}/partial-regenerations/{job_id}`는 raw timeline payload를 그대로 `TimelinePayloadResponse`에 넣고 있어, applied recommendation에 `provider_trace`가 빠진 legacy shape가 있으면 응답 모델 validation error가 났다
- strict TDD로 `test_partial_regeneration_result_fills_default_provider_trace_for_applied_recommendation` exact regression을 먼저 추가했고, 실제로 `applied_recommendations.0.provider_trace Field required` RED를 확인했다
- 응답 normalization 연결 뒤에는 `_normalize_provider_trace_response(...)` fallback helper import가 빠져 있어 `NameError`가 드러났고, 이 import 복구까지 포함한 최소 수정으로 canonical fallback trace response를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration result read-contract 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - partial regeneration result response normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration result read path가 missing `provider_trace` applied recommendation shape를 그대로 validation error로 흘리지 않음
2. applied recommendation response가 fallback trace를 채운 canonical shape를 유지함
3. partial regeneration result read truth와 timeline/read response truth가 recommendation provider trace fallback에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 56. 2026-07-04 review snapshot helper unknown pending recommendation approved-status closeout

이번 후속 작업에서는 direct review-snapshot helper의 stale recommendation family를 다시 좁혀, unknown legacy pending recommendation이 존재해도 persisted approved status를 `blocked`로 다시 뒤집는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 normalized pending override가 비어 있지 않기만 하면 recommendation type validity와 무관하게 `review_status="blocked"`를 우선하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type도 persisted approved status를 다시 막고 있었다
- strict TDD로 `test_store_build_review_snapshot_ignores_unknown_pending_recommendation_for_status_when_persisted_approved` exact regression을 먼저 추가했고, 실제로 `snapshot["review_status"] == "blocked"` RED를 확인했다
- 최소 수정으로 direct helper status 계산도 canonical blocking pending recommendation만 blocker로 세도록 좁혀, unknown / non-blocking pending recommendation은 surface에 남더라도 persisted approved truth를 다시 뒤집지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper pending-status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper unknown-pending status precedence 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_pending_recommendations` shape 하나만으로 persisted approved status를 다시 `blocked`로 뒤집지 않음
2. canonical blocking pending recommendation이 없는 경우 helper `review_status`가 persisted approved truth를 유지함
3. helper status truth와 runtime output gating / preflight read truth가 같은 stale recommendation family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 55. 2026-07-04 review snapshot helper unknown review flag approved-status closeout

이번 후속 작업에서는 direct review-snapshot helper의 stale review-flag family를 다시 좁혀, unknown legacy review flag가 surface에는 남아 있어도 persisted approved status를 `blocked`로 다시 뒤집는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_review_flags`가 비어 있지 않기만 하면 code validity와 무관하게 `review_status="blocked"`를 우선하고 있어, `legacy_review_flag` 같은 unknown metadata도 persisted approved status를 다시 막고 있었다
- strict TDD로 `test_store_build_review_snapshot_ignores_unknown_review_flag_for_status_when_persisted_approved` exact regression을 먼저 추가했고, 실제로 `snapshot["review_status"] == "blocked"` RED를 확인했다
- 최소 수정으로 direct helper status 계산도 canonical blocking review flag만 blocker로 세도록 좁혀, unknown / non-blocking review flag는 surface에 남더라도 persisted approved truth를 다시 뒤집지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `58 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper unknown-review-flag status precedence 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_review_flags` shape 하나만으로 persisted approved status를 다시 `blocked`로 뒤집지 않음
2. canonical blocking review flag가 없는 경우 helper `review_status`가 persisted approved truth를 유지함
3. helper status truth와 runtime output gating / preflight read truth가 같은 stale review-flag family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 54. 2026-07-04 timeline persistence stale non-list review flags initial status closeout

이번 후속 작업에서는 stale review-flag family를 저장 시점까지 다시 내려가 확인해, non-list `review_flags` shape 하나만으로 timeline persistence가 initial review state를 `blocked`로 저장하는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)`는 initial review state를 계산할 때 `review_flags`를 raw truthiness로만 보고 있어, `"stale_review_flag_container"` 같은 non-list shape도 `blocked` 근거로 오판하고 있었다
- strict TDD로 `test_store_save_timeline_run_ignores_stale_nonlist_review_flags_when_setting_initial_status` exact regression을 먼저 추가했고, 실제로 persisted review state가 `draft`가 아니라 `blocked`인 RED를 확인했다
- 최소 수정으로 save path도 canonical blocking review flag만 blocker로 세도록 검증을 좁혀, stale non-list / non-blocking `review_flags` shape는 initial review state를 막지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence initial status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline persistence initial status의 stale review-flag normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline save path가 stale non-list `review_flags` shape 하나만으로 `blocked` review state를 저장하지 않음
2. persisted initial review state가 canonical blocking review flag truth가 없으면 `draft`를 유지함
3. persistence truth와 preflight/read-path truth가 같은 stale review-flag family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 53. 2026-07-04 review snapshot helper persisted-approved pending-override status closeout

이번 후속 작업에서는 direct store helper의 review status 일관성 경계를 다시 좁혀, pending override나 blocker flag가 이미 존재하는데도 persisted approved status를 그대로 우선하는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_id`가 있고 persisted review state가 `approved`면, pending recommendation override가 이미 존재해도 `review_status="approved"`를 그대로 반환하고 있었다
- strict TDD로 `test_store_build_review_snapshot_marks_status_blocked_when_pending_override_exists_despite_persisted_approved` exact regression을 먼저 추가했고, 실제로 `snapshot["review_status"] == "approved"` RED를 확인했다
- 최소 수정으로 direct helper도 `timeline_review_flags`나 `pending` recommendation이 이미 계산된 경우 persisted status보다 blocker truth를 우선해 `review_status="blocked"`를 반환하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper status precedence 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 pending override나 blocker flag 존재 시 persisted approved status를 그대로 우선하지 않음
2. computed blocker truth와 `review_status`가 helper 수준에서도 일치함
3. helper status truth와 timeline/review snapshot/preflight read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 52. 2026-07-04 timeline persistence misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 stale bucket family를 저장 시점까지 내려가 확인해, pending-like legacy recommendation이 `applied_recommendations` bucket에 잘못 들어 있는 경우 timeline persistence가 initial review state를 `draft`로 저장하는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)`는 initial review state를 `review_flags`와 `pending_recommendations` 존재 여부만으로 결정하고 있어, `applied_recommendations`에 misbucket된 pending-like recommendation은 무시한 채 `draft`를 저장하고 있었다
- strict TDD로 `test_store_save_timeline_run_marks_misbucketed_applied_pending_like_recommendation_as_blocked` exact regression을 먼저 추가했고, 실제로 persisted review state가 `blocked`가 아니라 `draft`인 RED를 확인했다
- 최소 수정으로 save path도 `pending_recommendations + applied_recommendations` 양쪽에서 recommendation dict를 모은 뒤 `_normalize_recommendation_decision_state(...) == "pending"`인 항목이 있으면 initial review state를 `blocked`로 저장하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline persistence initial review-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline save path가 misbucketed pending-like applied recommendation을 무시한 채 `draft` review state를 저장하지 않음
2. persisted initial review state가 source recommendation truth와 맞게 `blocked`를 유지함
3. persistence truth와 timeline/review snapshot/preflight read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 51. 2026-07-04 preflight misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 같은 stale bucket family를 preflight prediction read path로 옮겨, pending-like legacy recommendation이 `applied_recommendations` bucket에 잘못 들어 있는 경우 source blocker truth를 놓치는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source timeline의 `pending_recommendations`만 blocker source로 보고 있었고, `applied_recommendations`에 misbucket된 pending-like recommendation은 무시해 `draft` prediction을 반환하고 있었다
- strict TDD로 `test_editing_session_api_marks_preflight_blocked_when_source_timeline_has_misbucketed_applied_pending_like_recommendation` exact regression을 먼저 추가했고, 실제로 `predicted_review_status_after_rerun == "draft"` RED를 확인했다
- 최소 수정으로 preflight prediction도 blocker source를 `pending_recommendations + applied_recommendations`로 합쳐 같은 bool-ish normalization 기준으로 필터링하도록 맞춰, misbucketed pending-like recommendation을 unresolved blocker로 다시 복원하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `57 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction blocker-source normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preflight prediction이 misbucketed pending-like applied recommendation을 unresolved blocker로 다시 복원함
2. source blocker truth와 `predicted_review_status_after_rerun`가 `blocked`로 일치함
3. preflight prediction truth와 timeline/review snapshot read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 50. 2026-07-04 timeline API misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 review snapshot API와 같은 stale bucket family의 바로 옆 read surface인 timeline API에서, pending-like legacy recommendation이 `applied_recommendations` bucket에 남아 있어 review truth와 applied surface가 어긋나는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 timeline hydration은 pending-like recommendation을 blocker로는 복원할 수 있어도 `applied_recommendations` 컬렉션 자체는 그대로 두고 있어 timeline API response에서 stale applied entry가 계속 노출되고 있었다
- strict TDD로 `test_timeline_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations` exact regression을 먼저 추가했고, 실제로 `review_status="blocked"`이더라도 `applied_recommendations`에 해당 recommendation이 남는 RED를 확인했다
- 최소 수정으로 hydration 단계가 runtime blocker shape를 `applied_recommendations`에서도 먼저 제외하도록 맞춰 timeline API response의 applied surface와 synthesized pending blocker truth를 일치시켰다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline API read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline API read truth와 hydration cleanup 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline API가 misbucketed pending-like applied recommendation을 applied surface에서 제거함
2. `review_status`와 pending blocker truth가 timeline response에서도 일관되게 유지됨
3. timeline/read truth와 review snapshot/read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 49. 2026-07-04 review snapshot API misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 direct store helper보다 한 단계 위 read path인 review snapshot API에서, pending-like legacy recommendation이 stale하게 `applied_recommendations` bucket에 들어 있는 경우 pending blocker truth와 `review_status`를 같이 잃는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 timeline hydration은 pending blocker normalization을 `pending_recommendations`만 기준으로 보고 있었고, `applied_recommendations`에 잘못 들어간 pending-like legacy recommendation은 blocker로 보지 않아 `review_status=approved`가 유지됐다
- strict TDD로 `test_review_snapshot_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations` exact regression을 먼저 추가했고, 실제로 review snapshot API가 `review_status="approved"`를 반환하는 RED를 확인했다
- 최소 수정으로 timeline hydration의 blocker source에 `applied_recommendations`도 포함해 pending-like recommendation을 다시 blocker로 복원했고, 같은 recommendation이 snapshot에서 duplicate pending blocker로 늘어나지 않도록 review snapshot API applied collection에서도 runtime blocker shape를 먼저 제외했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot API read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot API read truth와 runtime blocker synthesis 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot API가 misbucketed pending-like applied recommendation을 pending blocker로 다시 복원함
2. `review_status`가 pending blocker truth와 맞게 `blocked`로 유지됨
3. 같은 recommendation이 applied/pending 양쪽에 중복으로 남지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 48. 2026-07-04 review snapshot applied override legacy pending-like recommendation closeout

이번 후속 작업에서는 직전 pending override 경계의 대칭면인 review snapshot direct applied override 입력을 다시 좁혀, `timeline_applied_recommendations` 안의 legacy pending-like recommendation이 applied로 고정되는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_applied_recommendations` override 경로에서 모든 항목에 fallback `decision_state="approved"`를 강제로 써서 `auto_apply_allowed="false"` / `review_required="true"` legacy pending-like recommendation까지 applied recommendation으로 고정하고 있었다
- strict TDD로 `test_store_build_review_snapshot_reclassifies_legacy_pending_like_timeline_applied_override` exact regression을 먼저 추가했고, 실제로 `applied_recommendations`에 해당 recommendation이 그대로 남는 RED를 확인했다
- 원인은 direct applied override 경로도 raw item의 recommendation truth를 먼저 판단하지 않고 caller bucket을 그대로 우선시하던 점이었다
- 최소 수정으로 applied override 입력도 raw item 기준 `_normalize_recommendation_decision_state(...)`를 먼저 계산한 뒤 payload fallback에 반영하고, applied/pending 컬렉션을 같은 normalized decision-state 기준으로 다시 나누도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct applied override 입력이 legacy pending-like recommendation shape를 applied recommendation으로 오판하지 않음
2. `decision_state`가 비어 있어도 pending truth에 해당하는 recommendation shape는 pending recommendation으로 재분류됨
3. review snapshot helper truth와 runtime output gating / preflight prediction / store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 47. 2026-07-04 review snapshot pending override legacy applied-like recommendation closeout

이번 후속 작업에서는 runtime caller filter에만 의존하던 review snapshot direct helper 경계를 다시 좁혀, `timeline_pending_recommendations` override 입력 안의 legacy applied-like recommendation이 pending blocker로 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_pending_recommendations` override 경로에서 모든 항목에 fallback `decision_state="pending"`를 강제로 써서 `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like recommendation까지 pending recommendation으로 고정하고 있었다
- strict TDD로 `test_store_build_review_snapshot_reclassifies_legacy_applied_like_timeline_pending_override` exact regression을 먼저 추가했고, 실제로 `applied_recommendations == []` RED를 확인했다
- 원인은 direct pending override 경로가 raw item의 recommendation truth를 먼저 판단하지 않고 caller bucket만 그대로 우선시하던 점이었다
- 최소 수정으로 pending override 입력도 raw item 기준 `_normalize_recommendation_decision_state(...)`를 먼저 계산한 뒤 payload fallback에 반영하도록 맞춰 legacy applied-like recommendation은 applied 쪽으로 재분류되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct pending override 입력이 legacy applied-like recommendation shape를 pending blocker로 오판하지 않음
2. `decision_state`가 비어 있어도 applied truth에 해당하는 recommendation shape는 applied recommendation으로 재분류됨
3. review snapshot helper truth와 runtime output gating / preflight prediction / store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 46. 2026-07-04 output gating legacy applied-like pending recommendation closeout

이번 후속 작업에서는 이미 닫힌 `approved/rejected decision_state stale pending recommendation` 경계를 다시 넓히지 않고, 그 바로 인접면인 runtime output gating에서 legacy applied-like pending recommendation shape가 unresolved blocker로 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_is_runtime_blocking_pending_recommendation(...)`는 `decision_state`가 비어 있는 `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like recommendation을 subtitle / preview / export blocker로 오판하고 있었다
- strict TDD로 `test_output_jobs_ignore_legacy_applied_like_entries_left_in_pending_recommendations` exact regression을 먼저 추가했고, 실제로 subtitle render start가 `202`가 아니라 `400`으로 막히는 RED를 확인했다
- 원인은 runtime blocker 판정이 explicit `decision_state`만 보고 있었고, applied-like bool-ish truth를 보지 않던 점이었다
- 최소 수정으로 runtime pending recommendation blocker 판정에도 bool-ish normalization을 적용해 `auto_apply_allowed=true`이면서 `review_required=false`인 recommendation shape는 blocker에서 제외하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output gating truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime output gating bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline output gating이 legacy applied-like pending recommendation shape를 unresolved blocker로 오판하지 않음
2. `decision_state`가 비어 있어도 applied truth에 해당하는 recommendation shape는 subtitle / preview / export를 막지 않음
3. runtime output gating truth와 preflight prediction/API response/store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 45. 2026-07-04 preflight legacy applied-like pending recommendation prediction closeout

이번 후속 작업에서는 이미 닫힌 approved/rejected `decision_state` stale pending recommendation 경계를 다시 넓히지 않고, 그 바로 인접면인 preflight prediction read path에서 legacy applied-like recommendation payload가 unresolved blocker로 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source timeline `pending_recommendations`를 필터링할 때 `decision_state`와 식별자만 보고 있었고, `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like shape를 unresolved blocker recommendation으로 오판하고 있었다
- strict TDD로 `test_editing_session_api_filters_legacy_applied_like_source_pending_recommendation_from_preflight_prediction` exact regression을 먼저 추가했고, 실제로 preflight prediction이 `draft`가 아니라 `blocked`가 되는 RED를 확인했다
- 원인은 preflight prediction read path가 API response/runtime/store 쪽에서 이미 쓰는 bool-ish normalization 기준을 재사용하지 않고 raw pending collection shape만 보고 blocker 여부를 결정하던 점이었다
- 최소 수정으로 preflight pending recommendation filter에도 bool-ish normalization을 적용해 `auto_apply_allowed=false` 또는 `review_required=true`인 recommendation만 unresolved blocker로 남도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `56 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight prediction이 source timeline의 legacy applied-like pending recommendation을 unresolved blocker로 오판하지 않음
2. `decision_state`가 비어 있어도 applied truth에 해당하는 recommendation shape는 `draft` prediction을 유지함
3. preflight prediction truth와 runtime/API response/store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 16. 2026-07-03 Task 2 real-project smoke + evidence freeze 기록

이번 후속 작업으로 `Task 2: 실제 프로젝트 1개 happy-path smoke + evidence freeze`는 완료로 본다.

이번에 추가로 확인된 사실은 아래와 같다.

- 실제 smoke에서 `partial_regeneration_job_*` candidate를 review snapshot / approve / output에 넘길 때 `candidate timeline` 대신 persisted `partial_regeneration_id`를 timeline id처럼 읽어 `404`가 나는 경계가 있었다
- strict TDD로 `test_review_snapshot_api_uses_partial_regeneration_job_id_for_candidate_timeline` exact regression을 추가했고, 실제로 `404` RED를 확인한 뒤 최소 수정으로 닫았다
- `local_pipeline.get_timeline_result()`는 이제 `partial_regeneration` job일 때 persisted run에서 candidate timeline을 읽어 review snapshot / approve / subtitle / preview / export가 같은 truth를 타도록 맞춰졌다
- clean real-project smoke를 다시 수행했고 아래 흐름이 실제로 끝까지 통과했다
  - timeline build
  - review snapshot
  - editing session
  - mutation 1회
  - preflight
  - partial regeneration
  - approve
  - subtitle / preview / export
- smoke evidence 기준 clean project의 candidate approve 이후 output artifact도 정상 확인됐다
  - subtitle file uri `local://projects/task2-smoke-project/subtitles/subtitle_001.srt`
  - preview player uri `local://projects/task2-smoke-project/previews/preview_001.html`
  - CapCut export adapter `capcut_v1_port`
  - export track order `voiceover / broll / subtitle / bgm`
- exact backend regression `1 passed`
- exact frontend regression `1 passed`
- frontend build 성공
- full backend regression `334 passed`

이 갱신으로 아래 범위는 현재 기준 실제 증거로 닫혔다.

1. partial regeneration candidate job id review snapshot read
2. partial regeneration candidate approve routing
3. partial regeneration candidate subtitle / preview / export routing
4. 실제 프로젝트 1개 happy-path smoke
5. Task 2 evidence / closeout / SSOT freeze

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue로 복귀
- `review/output` 또는 `preflight contract` 중 가장 작은 남은 경계 1개만 재선정
- exact failing test 1개로 다음 slice 시작

## 17. 2026-07-03 partial regeneration start prediction symmetry 기록

이번 후속 작업에서는 `partial regeneration start` 응답이 preflight와 같은 review prediction contract를 유지하는지 작은 리스크 관점에서 다시 고정했다.

이번에 새로 확인된 사실은 아래와 같다.

- clean scope partial regeneration start 응답도 `predicted_review_status_after_rerun`를 `unknown`이 아니라 실제 `draft`로 surface해야 한다
- blocked scope partial regeneration start 응답도 preflight와 같은 `prediction_reasons`를 유지해야 한다
- strict TDD로 아래 exact regression을 고정했다
  - `test_editing_session_api_surfaces_draft_prediction_when_starting_partial_regeneration`
  - `test_editing_session_api_surfaces_blocked_prediction_when_starting_partial_regeneration`
- 구현은 `services/api/src/videobox_api/main.py`의 start endpoint에서 source timeline + targeted segments 기준 prediction 계산을 재사용하는 최소 수정으로 닫았다
- exact clean-scope regression `1 passed`
- exact blocked-scope regression `1 passed`
- focused backend verification
  - `4 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend` -> `55 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight 응답 prediction surface
2. partial regeneration start 응답 clean-scope prediction surface
3. partial regeneration start 응답 blocked-scope prediction surface

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue 유지
- 이번에는 `review/output` 쪽에서 가장 작은 남은 경계 1개를 다시 고르는 편이 더 효율적이다

## 19. 2026-07-03 Task 1 회귀 증거 고정

이번 후속 작업에서는 `approved TTS persisted truth gap`을 실제 코드 변경보다 `회귀 증거 강화` 관점에서 다시 확인했다.

이번에 새로 확인된 사실은 아래와 같다.

- 기존 코드 기준으로도 `approve -> persisted timeline 갱신` 계약은 이미 살아 있었다
- 기존 코드 기준으로도 `approved timeline -> preview/export consumer` 계약은 이미 살아 있었다
- 다만 이 둘 사이의 middle link는 단일 회귀로는 약했기 때문에 아래 두 exact regression을 새로 고정했다
  - `test_review_approval_persists_tts_narration_asset_uri_before_preview_and_export_read_timeline`
  - `test_review_approval_duplicate_tts_narration_clips_flow_through_preview_and_export_outputs`
- `scripts/dev-fast-path.ps1`의 `output-gating` 기본 패턴도 위 두 회귀를 포함하도록 갱신했다
- helper regression `6 passed`
- output-gating focused slice `24 passed`
- current-focused-parallel 재검증 결과
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`

이 기록의 의미는 아래와 같다.

- Task 1은 이번 시점에서 `새 runtime bug fix`보다 `already-true contract를 stronger regression과 helper rail로 고정`한 slice로 보는 것이 맞다
- 따라서 다음 실제 작업은 Task 2인 `실제 프로젝트 1개 happy-path smoke + evidence freeze`로 넘어가는 편이 더 효율적이다

## 17. 2026-07-01 시스템 정비 기준 최신 상태

이번 정비에서 현재 코드/문서/검증 기준을 다시 맞춰 확인한 결과, 아래는 더 이상 `계획 중`이 아니라 `실제 연결 완료` 상태다.

- review action family
  - `Approve recommendation` 실제 persistence 연결 완료
  - `Reject recommendation` 실제 persistence 연결 완료
  - `Mark for manual edit` 기존 editor flow 재사용 연결 완료
- reject explicit decision-state contract 반영 완료
- review snapshot의 timeline-local truth 보존 완료
- approve/reject mutation의 rollback hardening 완료
- rollback failure warning surface 추가 완료
- review-action mutation helper 일부 분리로 `local_pipeline` 중복 감소
- pending `tts_replacement` approve 시 target narration clip `asset_uri`가 승인된 `selected_asset_uri`로 즉시 동기화되도록 보강 완료
- pending `tts_replacement` approve 시 같은 target segment를 가리키는 duplicate narration clip이 있어도 첫 clip만 갱신하고 멈추지 않고 모든 target narration clip `asset_uri`를 승인된 `selected_asset_uri`로 동기화하도록 보강 완료
- pending `tts_replacement` approve는 `payload.selected_asset_uri`가 비어 있는 stale recommendation shape를 더 이상 승인 상태로 통과시키지 않고 `400`으로 즉시 거부하도록 보강 완료
- pending `tts_replacement` approve는 `target_segment_id`에 대응하는 narration clip이 없는 stale timeline shape도 더 이상 승인 상태로 통과시키지 않고 `400`으로 즉시 거부하도록 보강 완료
- pending `tts_replacement` approve 뒤 `applied_recommendations` read path는 `decision_state=approved`와 `recommendation_type=tts_replacement`를 approve 응답, timeline, review snapshot에서 일관되게 surface하도록 보강 완료
- approved timeline이라도 snapshot `review_flags/pending_recommendations`가 비어 있는 상태에서 segment-level `review_required=true`가 남아 있으면 subtitle/preview/export를 계속 막는 output gating 경계 고정 완료
- approved timeline의 stale non-bool `segment.review_required` shape는 synthetic output blocker로 오판하지 않고 canonical bool/string 값만 review-required blocker로 인정하도록 보강 완료
- 위 segment-level `review_required` blocker는 last pending recommendation approve 이후에도 synthetic `segment_review_required` flag가 API read path와 review snapshot에 반영돼 review_status와 output gating이 어긋나지 않도록 보강 완료
- malformed duplicated segment entry가 같은 `segment_id`로 반복돼도 synthetic `segment_review_required` blocker detail이 중복으로 불어나지 않도록 dedupe 고정 완료
- synthetic blocker 때문에 effective review status가 `approved -> blocked`로 바뀌는 경우에도 persisted approved `operator_guidance`를 재사용하지 않고 blocked snapshot 기준 guidance를 다시 계산하도록 보강 완료
- unknown dict-shaped `review_flag.code`는 approved timeline output gating blocker로 오판하지 않고 canonical review flag code만 blocker로 유지하도록 보강 완료
- approved timeline의 persisted duplicate `review_flags`도 output blocker detail에서 code/segment 기준으로 dedupe되어 같은 blocker가 중복 노출되지 않도록 보강 완료
- approved timeline의 persisted duplicate `pending_recommendations`도 output blocker detail에서 recommendation id / target segment / recommendation type 기준으로 dedupe되어 같은 blocker가 중복 노출되지 않도록 보강 완료
- partial regeneration preflight의 TTS affected-output label을 `narration audio`에서 `narration track`으로 정렬 완료
- partial regeneration preflight의 `prediction_reasons` 조합을 `source only / target only / both` 기준 테스트로 분리 완료
- partial regeneration preflight의 repeated `segment_ids`는 first-seen order를 유지한 채 dedupe되어 read-only scope와 targeted segment preview에 중복이 남지 않도록 고정 완료
- partial regeneration preflight는 editing session 내부에 같은 `segment_id`가 중복 저장된 stale shape여도 targeted segment preview에서 first-seen segment를 유지하고 뒤의 stale duplicate가 canonical 값을 덮어쓰지 않도록 고정 완료
- partial regeneration preflight는 whitespace가 섞인 legacy session `segment_id`도 trimmed request scope와 같은 세그먼트로 맞춰 targeted segment preview를 비우지 않도록 고정 완료
- partial regeneration preflight의 repeated `fields`도 first-seen order를 유지한 채 dedupe되어 read-only scope와 downstream step preview에 중복이 남지 않도록 고정 완료
- partial regeneration preflight의 stale `visual_overlays: null`도 targeted segment preview에서는 빈 리스트로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 empty `visual_overlays` dict entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 stale minimal-dict `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 `overlay_type`만 있는 stale `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 unknown `overlay_type` stale `visual_overlays` entry도 targeted segment preview에서는 제거되고 canonical overlay만 유지되도록 고정 완료
- partial regeneration preflight의 legacy `hook_title` overlay는 targeted segment preview에서 runtime과 어긋나게 사라지지 않고 기존 shape를 유지하도록 고정 완료
- partial regeneration preflight의 stringified falsey `review_required`도 targeted segment preview와 prediction에서는 실제 `False`로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `broll_override`도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 empty `broll_override` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `music_override`도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 empty `music_override` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `tts_replacement`도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 empty `tts_replacement` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-list source `review_flags`는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale non-dict-only source `review_flags` list는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale minimal-dict source `review_flags` entry는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 `code`만 있는 source `review_flags` stale dict는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 unknown `review_flags.code` source stale dict는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale non-dict-only source `pending_recommendations` list는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale minimal-dict source `pending_recommendations` entry는 read-only prediction에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 `recommendation_id`만 있는 source `pending_recommendations` stale dict는 read-only prediction에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 unknown `recommendation_type` source `pending_recommendations` stale dict는 read-only prediction과 runtime carry-forward 모두에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction/result를 유지하도록 고정 완료
- partial regeneration runtime도 stale minimal-dict source `pending_recommendations` entry를 그대로 blocker로 들고 가지 않고 clean scope rerun result의 `review_status/pending_recommendations/review_flags`를 `draft/[]/[]`로 유지하도록 고정 완료
- partial regeneration runtime fallback은 source timeline 세그먼트가 비어 있을 때 editing-session의 stringified falsey `review_required`를 실제 `False`로 정규화해 clean scope rerun result의 `review_flags/review_status`를 `[]/draft`로 유지하도록 고정 완료
- partial regeneration runtime fallback은 source timeline 세그먼트가 비어 있을 때 editing-session의 stale invalid `cut_action`을 실제 `keep`으로 정규화해 clean scope rerun result의 regenerated segment `cut_action`을 canonical 값으로 유지하도록 고정 완료
- partial regeneration runtime은 `cut_action` field rerun 시에도 target session segment의 stale invalid `cut_action`을 실제 `keep`으로 정규화해 regenerated segment `cut_action`을 canonical 값으로 유지하도록 고정 완료
- partial regeneration runtime은 preflight와 마찬가지로 whitespace가 섞인 legacy session `segment_id`도 trimmed request scope와 같은 세그먼트로 맞춰 actual rerun target lookup과 regenerated segment 반영이 비지 않도록 고정 완료
- partial regeneration runtime은 actual overlay refresh에서도 unknown `overlay_type` session overlay를 persisted timeline `export_overlays`에 싣지 않고 canonical overlay만 반영하도록 고정 완료
- partial regeneration runtime은 targeted overlay rerun에서 target segment의 stale unknown existing overlay도 preserve path로 되살리지 않고 canonical overlay만 남기도록 고정 완료
- partial regeneration runtime은 preflight와 마찬가지로 nested dict `target_segment_id`가 섞인 stale source `pending_recommendations`를 blocker recommendation으로 복원하지 않고 clean scope rerun result의 `review_status/pending_recommendations/review_flags`를 `draft/[]/[]`로 유지하도록 고정 완료
- current-priority helper `scripts/dev-fast-path.ps1`를 추가해 `output gating / preflight backend / preflight frontend / broader` 검증 레일을 분리 완료
- 일반 preflight UI에서도 blocked prediction reason의 combined 문구 두 개가 모두 surface되는지 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 scope가 resumed candidate와 다르면 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `session_id`가 resumed candidate와 다르면 scope가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `fields`에 duplicate가 섞여 있으면 scope member가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments`가 resumed candidate scope와 어긋나면 `segment_ids/fields/session_id`가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.review_required`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.tts_replacement`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.visual_overlays`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.broll_override`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.music_override`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- frontend preflight helper가 blocked-warning만이 아니라 resumed preflight degraded warning, mismatch non-reuse, resumed warning cleanup, resumed multi-segment scope cleanup까지 실제로 포함하도록 정렬 완료
- frontend preflight field inference는 backend canonical `image_card` overlay를 `image_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정 완료
- pending `tts_replacement` blocker가 남아 있을 때 subtitle-render도 preview/export와 같은 blocker detail surface와 failed job/no-artifact 상태를 유지하는 회귀를 고정 완료
- blocker가 없는 clean timeline이라도 explicit approval이 없으면 subtitle-render도 preview/export와 같은 failed job/no-artifact 상태를 유지하는 회귀를 고정 완료
- approved timeline을 `reopen review`한 뒤에는 subtitle/preview/export가 다시 explicit approval을 요구하며 막히는 전이 경계를 focused regression으로 고정 완료
- approved timeline의 stale truthy `review_flags` / `pending_recommendations` shape는 output gating에서 실제 blocker로 오판하지 않고 유효 blocker만 기준으로 막도록 고정 완료
- approved timeline을 `reopen review`할 때 stale truthy `review_flags` / `pending_recommendations` shape는 residual blocker로 오판하지 않고 `draft` 상태로 되돌린 뒤 explicit approval gating만 다시 요구하도록 고정 완료
- approved timeline을 `reopen review`한 뒤 stale truthy `review_flags` / `pending_recommendations` shape가 timeline/review snapshot read path를 깨뜨리지 않고 빈 blocker 컬렉션으로 정규화돼 직렬화되도록 고정 완료
- last pending recommendation approve 경로는 stale non-dict `review_flags` entry가 섞여 있어도 review action을 500으로 깨뜨리지 않고 blocker 정리 후 `draft`와 explicit approval gating을 유지하도록 고정 완료
- unsupported partial-regeneration field scope는 preflight prediction으로 흘리지 않고 `400`으로 즉시 거부하며 no-job 상태를 유지하는 계약을 고정 완료
- partial regeneration preflight는 source timeline의 valid `review_flags.code/segment_id` 조합이 `message` 없이 저장된 legacy shape여도 runtime blocker 의미를 보존해 `blocked` prediction으로 올바르게 분류하도록 고정 완료
- partial regeneration preflight는 source timeline의 valid `review_flags.code`라도 nested stale `segment_id` shape면 blocker로 오판하지 않고 clean scope `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight는 source timeline의 valid `pending_recommendations.target_segment_id`라도 nested stale shape면 blocker로 오판하지 않고 clean scope `draft` prediction을 유지하도록 고정 완료

이번 정비 시점의 실제 검증 결과:

- review-action backend focused slice `6 passed`
- current-focused helper backend output-gating slice `18 passed`
- current-focused helper backend preflight slice `55 passed`
- frontend `src/app.test.tsx` 전체 `66 passed`
- helper `frontend-focused` gate `2 passed`
- frontend build 성공
- full backend regression `314 passed`
- full backend regression은 현재 direct 실행 기준으로 다시 확인됐다
- focused output gating regression `2 passed`
- explicit approval gating regression `1 passed`
- reopen-after-approval gating regression `1 passed`
- preflight focused regression `11 passed`
- preflight normalization hardening 추가 후 `current-focused` backend preflight slice `23 passed`
- frontend preflight blocked-warning regression `1 passed`
- resumed multi-segment scope cleanup regression `1 passed`
- resumed multi-segment field-change cleanup regression `1 passed`
- preflight unsupported-field rejection regression `1 passed`
- current-priority helper `./scripts/dev-fast-path.ps1 -Mode current-focused`
  - backend output-gating slice `18 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
- speed-up helper `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - backend output-gating slice `18 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
- frontend preflight field inference는 backend legacy `image` overlay도 `image_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
- frontend preflight field inference는 backend legacy `hook_title` overlay도 `visual_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
- frontend preflight field inference는 backend canonical `visual_overlay`도 `visual_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 backend canonical `visual_overlay`도 legacy `hook_title`와 같은 visual-overlay 계열로 보존해 read-only scope에서 saved overlay가 unknown 타입처럼 사라지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 backend canonical `image_overlay`도 legacy `image`/`image_card` 계열과 같은 이미지 오버레이로 보존해 read-only scope에서 saved overlay가 unknown 타입처럼 사라지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 backend canonical `table_overlay`도 legacy `table_card` 계열과 같은 테이블 오버레이로 보존해 read-only scope에서 saved overlay가 unknown 타입처럼 사라지지 않도록 고정했다
- partial regeneration runtime은 backend canonical `table_overlay`도 legacy `table_card` 계열과 같은 targeted overlay refresh 대상으로 받아 실제 rerun 결과의 `export_overlays`에서 사라지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 stale non-bool `review_required` shape도 `False`로 정규화해 clean scope prediction이 불필요하게 `blocked`로 기울지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 nested stale `broll_override.asset_id` shape도 `None`으로 정규화해 invalid override object가 read-only scope에 남지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 nested stale `music_override.asset_id` shape도 `None`으로 정규화해 invalid music override object가 read-only scope에 남지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 nested stale `tts_replacement.recommendation_id` shape도 `None`으로 정규화해 invalid replacement object가 read-only scope에 남지 않도록 고정했다
- broader verification 재실행
  - frontend build 성공
  - full backend regression `314 passed`
- output-gating persisted duplicate review-flag dedupe 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `315 passed`
- preflight duplicate session-segment first-seen preserve 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `316 passed`
- TTS duplicate target narration clip propagation 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `317 passed`
- output-gating persisted duplicate pending-recommendation dedupe 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `318 passed`
- TTS approve missing `selected_asset_uri` hardening 추가 후 focused / broader verification 재실행
  - backend output-gating slice `20 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
  - frontend build 성공
  - full backend regression `325 passed`
- TTS approve missing target narration clip hardening 추가 후 focused / broader verification 재실행
  - backend output-gating slice `21 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
  - frontend build 성공
  - full backend regression `327 passed`
- TTS approve decision-state read-path hardening 추가 후 focused / broader verification 재실행
  - backend output-gating slice `22 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
  - frontend build 성공
  - full backend regression `329 passed`
- 이 체크포인트 직전 latest pushed closeout commit
  - `9df0363 Harden preflight pending recommendation prediction`

이 갱신으로 아래 판단은 더 이상 현재 truth가 아니다.

- `review action placeholder를 실제 persistence contract와 연결할지 여부 설계`
- `Approve recommendation`이 아직 첫 slice만 된 상태라는 판단

현재 기준 남은 핵심 범위는 다시 아래다.

- TTS replacement의 실제 narration/output propagation baseline, approve 후 target clip 반영, missing `selected_asset_uri` stale approval 차단, missing target narration clip stale approval 차단, approved decision-state/read-path surface까지 연결되어 있고, 남은 일은 approval/review contract의 추가 경계 보강이다
- review-required 상태의 subtitle/preview/export gating은 기본 경로와 reopen-after-approval 전이까지 고정돼 있고, 남은 일은 다른 승인 후 반영 규칙 세분화와 추가 경계 검증이다
- partial regeneration preflight의 비파괴 조회 경로는 baseline, duplicate-scope normalization, 일반 preflight blocked-warning combined reason surface까지 연결되어 있고, 남은 일은 backend read-only/prediction contract의 추가 경계와 frontend resume 경계 정리다
- TTS replacement approval/output contract의 아직 테스트로 고정되지 않은 추가 경계 보강
- `local_pipeline`의 다음 대형 분리 후보인 partial regeneration / output 경로 정리

아래 이어지는 `## 16` 이하의 낮은 번호 섹션들도 당시 시점 기록을 보존한 historical log다.
현재 truth나 현재 next slice 판단에는 위 `## 17. 2026-07-01 시스템 정비 기준 최신 상태`를 우선 적용한다.

## 18. 2026-07-03 partial regeneration candidate provider-trace upstream audit closeout

이번 후속 작업에서는 `review/output` 장기 queue를 다시 보되, provider trace audit이 partial regeneration candidate timeline까지 같은 truth를 유지하는지 가장 작은 리스크 1개만 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- 기존 `provider-traces?timeline_id=...&include_upstream=true` filter는 `TIMELINE_BUILD` job에만 기대고 있어 partial regeneration candidate timeline에서는 upstream lineage를 비워 버리는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_timeline_filter_include_upstream_supports_partial_regeneration_candidate` exact regression을 먼저 추가했고, 실제로 candidate timeline의 `upstream_entries == []` RED를 확인했다
- 최소 수정으로 timeline filter가 `TIMELINE_BUILD` job 유무와 관계없이 persisted timeline lineage를 직접 읽도록 바꿔 candidate timeline도 source segment analysis / recommendation upstream entry를 같이 보여주게 맞췄다
- 이번 수정은 review/output gating, TTS approve/output truth, editing-session SSOT, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit filter 계산 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `30 passed`
- frontend build 성공
- full backend regression `337 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review snapshot audit entry 노출
2. partial regeneration candidate timeline filter direct review guidance 유지
3. partial regeneration candidate timeline filter include_upstream lineage 복원

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 19. 2026-07-03 partial regeneration candidate review guidance job lineage closeout

이번 후속 작업에서는 직전 candidate upstream lineage 복원 다음으로 가장 가까운 남은 provider trace audit 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- 기존 candidate timeline의 `review_guidance` audit entry는 `timeline_id`는 맞아도 `job_id/source_job_id`가 비어 있어, 어떤 partial regeneration job에서 나온 guidance인지 바로 추적할 수 없는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_entry_uses_partial_regeneration_job_id` exact regression을 먼저 추가했고, 실제로 `job_id == None` RED를 확인했다
- 최소 수정으로 provider trace audit이 review guidance용 timeline->source job 매핑을 `TIMELINE_BUILD`뿐 아니라 `PARTIAL_REGENERATION` 결과까지 읽도록 보강해 candidate timeline도 `partial_regeneration_job_*` lineage를 유지하게 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `31 passed`
- broader verification은 이번 turn에서 생략
  - 판단:
    - 같은 provider-trace audit lane 내부의 국소 mapping 수정이라 exact + focused evidence가 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance audit entry 노출
2. partial regeneration candidate review guidance direct timeline filter 유지
3. partial regeneration candidate review guidance job/source job lineage 연결

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 20. 2026-07-03 partial regeneration candidate review guidance attempt job truth closeout

이번 후속 작업에서는 같은 provider trace audit 축 안에서 `review_guidance_attempt`의 candidate truth를 가장 작은 남은 경계 1개로 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate timeline의 `review_guidance_attempt` audit entry는 `job_id/source_job_id`는 partial regeneration job을 가리켜도 `job_type`을 `timeline_build`로 고정해서 surface하는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_attempt_entry_uses_partial_regeneration_job_truth` exact regression을 먼저 추가했고, 실제로 `job_type == "timeline_build"` RED를 확인했다
- 최소 수정으로 attempt audit event writer가 실제 source job type을 같이 저장하고, read path도 persisted `job_type`을 그대로 surface하도록 바꿔 candidate attempt entry가 `partial_regeneration` truth를 유지하게 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit attempt read/write path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `32 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - provider trace audit attempt path 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 21. 2026-07-03 partial regeneration candidate review guidance attempt finished_at closeout

이번 후속 작업에서는 같은 candidate `review_guidance_attempt` 축 안에서 남아 있던 `finished_at` truth 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `review_guidance_attempt` audit entry는 `job_type/job_id/source_job_id`는 partial regeneration truth를 가리켜도 `finished_at`은 빈 문자열로 남는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_attempt_entry_uses_partial_regeneration_finished_at` exact regression을 먼저 추가했고, 실제로 `finished_at == ""` RED를 확인했다
- 최소 수정으로 attempt read path도 candidate review guidance용 job 매핑을 재사용하게 바꿔 `partial_regeneration_job_*`의 `finished_at`을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit attempt read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `33 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - provider trace audit attempt timestamp truth 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 22. 2026-07-03 partial regeneration candidate preview provider-trace created_at closeout

이번 후속 작업에서는 candidate output artifact 쪽에서 가장 작은 남은 provider-trace audit 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `preview_render` audit entry는 `job_id/source_job_id/timeline_id`는 partial regeneration truth를 가리켜도 `created_at`은 `None`으로 비는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_preview_render_entry_uses_preview_created_at` exact regression을 먼저 추가했고, 실제로 `created_at == None` RED를 확인했다
- 최소 수정으로 preview read path가 persisted preview row의 `created_at`을 payload에 실어 주고, provider trace audit preview entry도 그 값을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 preview provider-trace read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `34 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - 같은 provider-trace audit lane 내부의 preview artifact timestamp truth 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 23. 2026-07-03 partial regeneration candidate export provider-trace created_at closeout

이번 후속 작업에서는 candidate output artifact 쪽에서 preview 다음으로 가장 가까운 남은 provider-trace audit 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `capcut_export` audit entry는 `job_id/source_job_id/timeline_id`는 partial regeneration truth를 가리켜도 `created_at`은 `None`으로 비는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_capcut_export_entry_uses_export_created_at` exact regression을 먼저 추가했고, 실제로 `created_at == None` RED를 확인했다
- 최소 수정으로 export read path가 persisted export row의 `created_at`을 payload에 실어 주고, provider trace audit export entry도 그 값을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 export provider-trace read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `35 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - 같은 provider-trace audit lane 내부의 export artifact timestamp truth 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 24. 2026-07-03 partial regeneration candidate failed preview trace filter closeout

이번 후속 작업에서는 review/output과 바로 맞닿은 candidate failed output trace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate `preview_render` failed job은 jobs 목록에는 남아도 `provider-traces?timeline_id=<candidate>` filter에서는 빠지는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_timeline_filter_includes_failed_preview_render_without_approval` exact regression을 먼저 추가했고, 실제로 failed preview entry를 찾지 못하는 `StopIteration` RED를 확인했다
- 원인은 2개였다
  - approval gate failure 경로가 failed provider-trace audit event를 남기지 않았다
  - candidate failed entry가 `source_job_id=partial_regeneration_job_*`를 candidate `timeline_id`로 역매핑하지 못했다
- 최소 수정으로 preview approval-gate failure도 failed provider-trace audit event를 저장하게 하고, partial regeneration job id -> candidate timeline id 역매핑을 provider-trace read path에 추가해 candidate timeline filter가 failed preview entry를 계속 보여주도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate failed preview provider-trace save/filter 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `36 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - candidate failed preview trace save/filter 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지
7. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 25. 2026-07-03 partial regeneration candidate failed export trace filter closeout

이번 후속 작업에서는 직전 candidate failed preview trace 다음으로 가장 가까운 failed output trace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate `capcut_export` failed job도 jobs 목록에는 남아도 `provider-traces?timeline_id=<candidate>` filter에서는 빠지는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_timeline_filter_includes_failed_capcut_export_without_approval` exact regression을 먼저 추가했고, 실제로 failed export entry를 찾지 못하는 `StopIteration` RED를 확인했다
- 원인은 preview와 같은 approval gate failure 경로였다
  - export approval gate failure 경로가 failed provider-trace audit event를 남기지 않았다
- 최소 수정으로 export approval-gate failure도 failed provider-trace audit event를 저장하게 바꿔 candidate timeline filter가 failed export entry를 계속 보여주도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate failed export provider-trace save 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `37 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - candidate failed export trace save 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지
7. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지
8. partial regeneration candidate timeline filter가 approval 없이 막힌 failed capcut_export output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 26. 2026-07-03 partial regeneration candidate failed subtitle trace filter closeout

이번 후속 작업에서는 candidate failed preview/export trace 다음으로 가장 가까운 failed output trace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate `subtitle_render` failed job도 jobs 목록에는 남아도 `provider-traces?timeline_id=<candidate>` filter에서는 빠지는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_timeline_filter_includes_failed_subtitle_render_without_approval` exact regression을 먼저 추가했고, 실제로 failed subtitle entry를 찾지 못하는 `StopIteration` RED를 확인했다
- 원인은 preview/export와 같은 approval gate failure 경로였다
  - subtitle approval gate failure 경로가 failed provider-trace audit event를 남기지 않았다
- 최소 수정으로 subtitle approval-gate failure도 failed provider-trace audit event를 저장하게 바꿔 candidate timeline filter가 failed subtitle entry를 계속 보여주도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate failed subtitle provider-trace save 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `38 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - candidate failed subtitle trace save 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지
7. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지
8. partial regeneration candidate timeline filter가 approval 없이 막힌 failed capcut_export output job도 유지
9. partial regeneration candidate timeline filter가 approval 없이 막힌 failed subtitle_render output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 27. 2026-07-03 partial regeneration runtime nested pending recommendation closeout

이번 후속 작업에서는 provider-trace 축이 아니라 `preflight는 통과하지만 runtime 결과 조회는 깨지는` 실제 계약 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- source timeline의 `pending_recommendations[].target_segment_id`가 nested dict stale shape여도 preflight prediction은 이미 blocker recommendation으로 취급하지 않고 `draft`를 예측하고 있었다
- 하지만 실제 partial regeneration runtime은 같은 stale entry를 그대로 carry-forward해서 결과 timeline에 남겼고, 그 결과 partial regeneration result API read path가 `target_segment_id string required`와 `provider_trace required` validation error로 깨졌다
- strict TDD로 `test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 result 조회 시 Pydantic validation error가 나는 RED를 확인했다
- 원인은 `_is_runtime_blocking_pending_recommendation(...)`가 `target_segment_id`를 string인지 보지 않고 `str(...)` truthy만 확인해서 nested dict stale shape까지 blocker recommendation으로 통과시키는 점이었다
- 최소 수정으로 runtime pending recommendation 판정이 string `recommendation_id`와 string `target_segment_id`만 blocker recommendation으로 인정하게 좁혀, runtime도 preflight와 같은 기준으로 nested stale shape를 버리도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime pending recommendation normalization 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `5 passed`
- full backend regression `346 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 nested stale `pending_recommendation.target_segment_id`를 blocker prediction으로 복원하지 않음
2. partial regeneration runtime도 같은 nested stale source pending recommendation을 blocker result로 복원하지 않음
3. clean scope rerun result의 `review_status/pending_recommendations/review_flags`가 `draft/[]/[]`로 유지됨
4. partial regeneration result API read path가 stale nested pending recommendation 때문에 validation error로 깨지지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 28. 2026-07-03 partial regeneration candidate subtitle provider-trace created_at closeout

이번 후속 작업에서는 review/output과 맞닿은 provider-trace audit 축에서 가장 작은 남은 subtitle artifact 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate failed `subtitle_render` trace는 이미 timeline filter에 보였지만, 성공한 candidate `subtitle_render` artifact entry는 `provider-traces?timeline_id=<candidate>&artifact_type=subtitle_render`에서 아예 빠지고 있었다
- strict TDD로 `test_provider_trace_audit_candidate_subtitle_render_entry_uses_subtitle_created_at` exact regression을 먼저 추가했고, 실제로 filtered `entries`가 빈 배열인 RED를 확인했다
- 원인은 provider-trace read path가 성공 artifact backfill에서 `preview_render`와 `capcut_export`만 append하고 `subtitle_render`는 누락하고 있던 점이었다
- 최소 수정으로 성공한 `subtitle_render` job도 provider-trace artifact entry로 backfill하고 persisted subtitle row의 `created_at`을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 subtitle provider-trace read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `39 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - subtitle provider-trace read path 한 점에 국한된 수정이라 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate subtitle_render created_at truth 유지
6. partial regeneration candidate preview_render created_at truth 유지
7. partial regeneration candidate capcut_export created_at truth 유지
8. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지
9. partial regeneration candidate timeline filter가 approval 없이 막힌 failed capcut_export output job도 유지
10. partial regeneration candidate timeline filter가 approval 없이 막힌 failed subtitle_render output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 29. 2026-07-03 partial regeneration runtime source review flag preserve closeout

이번 후속 작업에서는 provider-trace 축이 아니라 `preflight는 blocked인데 runtime candidate 결과는 draft로 풀리는` 실제 계약 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- preflight는 source timeline의 valid `review_flags.code/segment_id` blocker를 보면 이미 `blocked` prediction을 내리고 있었다
- 하지만 실제 partial regeneration runtime은 source `pending_recommendations`만 carry-forward하고 source `review_flags`는 버리고 있어서, 같은 입력에서도 candidate result의 `review_status`가 `draft`로 풀렸다
- strict TDD로 `test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_remains` exact regression을 먼저 추가했고, 실제로 `review_status == "draft"` RED를 확인했다
- 첫 GREEN 시도에서는 source review flag를 복원했지만 legacy `message`가 비어 API response validation error가 나왔고, 여기서 `message` canonicalization까지 이 경계에 포함해야 한다는 점을 추가로 확인했다
- 같은 slice의 역방향 검증으로 `test_editing_session_api_ignores_nested_segment_id_source_review_flag_when_running_partial_regeneration`도 추가했고, 실제로 nested dict `segment_id` stale shape가 runtime preserve 경로를 통과해 partial regeneration result API response validation error를 만드는 RED를 확인했다
- 최소 수정으로 runtime이 valid source blocker review flag를 `code + segment_id` 기준으로 dedupe해 candidate timeline payload에 복원하고, legacy shape도 API contract를 깨지 않도록 default message를 채우게 맞췄다
- 동시에 `_is_runtime_blocking_review_flag(...)`를 string `code`와 string `segment_id`만 blocker review flag로 인정하게 축소해 nested stale shape를 runtime preserve에서 다시 살리지 않도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime source review flag carry-forward 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `6 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - runtime source review flag carry-forward 한 점에 국한된 수정이라 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 valid source review flag blocker를 `blocked` prediction으로 유지함
2. partial regeneration runtime도 같은 source review flag blocker를 candidate result에 복원함
3. candidate result의 `review_status`가 `blocked`로 유지됨
4. preserved source review flag가 legacy message 부재 때문에 API response validation error를 내지 않음
5. nested dict `segment_id`가 섞인 stale source review flag는 runtime에서도 blocker review flag로 복원되지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 30. 2026-07-03 partial regeneration runtime pending recommendation default provider-trace closeout

이번 후속 작업에서는 직전 nested pending recommendation 경계의 인접면에서 남아 있던 `runtime preserve는 되지만 result API read path가 깨지는` 실제 계약 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- preflight는 source timeline의 valid `pending_recommendations` blocker를 보면 이미 `blocked` prediction을 유지하고 있었다
- runtime도 같은 valid source pending recommendation을 candidate 결과에 복원하고 있었지만, legacy source shape에 `provider_trace`가 빠져 있으면 partial regeneration result API read path가 `provider_trace Field required` validation error로 깨졌다
- strict TDD로 `test_partial_regeneration_result_preserves_source_pending_recommendation_with_default_provider_trace` exact regression을 먼저 추가했고, 실제로 result 조회 시 Pydantic validation error가 나는 RED를 확인했다
- 원인은 `_normalized_runtime_pending_recommendations(...)`가 valid blocker recommendation 자체는 통과시키면서도 missing `provider_trace`를 canonicalize하지 않아 response model contract를 깨뜨리는 점이었다
- 최소 수정으로 runtime pending recommendation normalization이 valid source blocker를 복원할 때 dict `provider_trace`가 없으면 `build_provider_trace(final_provider="rule_based_fallback")`를 채우도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime pending recommendation canonicalization 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `6 passed`
- broader fast-path verification
  - `backend output-gating 24 passed`
  - `backend preflight 55 passed`
  - `frontend preflight 25 passed`
- full broader baseline은 이번 turn에서 다시 돌리지 않았다
  - 판단:
    - runtime pending recommendation fallback trace 한 점에 국한된 수정이라 exact + focused + current-focused-parallel evidence로 충분하다
    - latest full broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 valid source pending recommendation blocker를 `blocked` prediction으로 유지함
2. partial regeneration runtime도 같은 source pending recommendation blocker를 candidate result에 복원함
3. preserved source pending recommendation에 `provider_trace`가 빠져 있어도 default fallback trace로 canonicalize되어 result API validation error를 내지 않음
4. candidate result의 `review_status`가 `blocked`로 유지됨

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 31. 2026-07-03 partial regeneration candidate review guidance job type closeout

이번 후속 작업에서는 review/output 장기 우선순위 queue를 유지한 채 provider-trace audit 인접면의 가장 작은 남은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `review_guidance` audit entry는 이미 `job_id/source_job_id`는 `partial_regeneration_job_*`를 가리키고 있었지만, `job_type`은 여전히 `timeline_build`로 잘못 고정돼 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_entry_uses_partial_regeneration_job_type` exact regression을 먼저 추가했고, 실제로 `timeline_build != partial_regeneration` RED를 확인했다
- 원인은 provider-trace read path가 candidate `review_guidance` entry를 복원할 때 linked job을 찾고도 `job_type`만은 `timeline_build` 상수로 넣고 있던 점이었다
- 최소 수정으로 candidate/legacy review guidance entry가 linked timeline job이 있으면 그 job의 `job_type`을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate review guidance provider-trace read path의 job type truth만 좁게 수정했다
- exact regression `1 passed`
- focused provider-trace audit slice `40 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - provider-trace review guidance read path의 job type truth 한 점에 국한된 수정이라 exact + provider-trace focused evidence가 더 직접적이다
    - latest full broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance entry가 `partial_regeneration_job_*`의 job id truth를 유지함
2. partial regeneration candidate review guidance entry가 `partial_regeneration_job_*`의 source job truth를 유지함
3. partial regeneration candidate review guidance entry가 `partial_regeneration_job_*`의 job type truth를 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 32. 2026-07-04 approved timeline stale pending decision-state output gating closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채 `review/output gating`과 `TTS approval/output`이 맞닿는 가장 작은 stale pending 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approved timeline의 `pending_recommendations`에 이미 `decision_state=approved`인 stale recommendation entry가 잘못 남아 있으면, 실제로는 unresolved blocker가 아니어야 하지만 output gating은 그대로 막고 있었다
- strict TDD로 `test_output_jobs_ignore_approved_decision_state_entries_left_in_pending_recommendations` exact regression을 먼저 추가했고, 실제로 subtitle render가 `400`으로 막히는 RED를 확인했다
- 원인은 `_is_runtime_blocking_pending_recommendation(...)`가 `recommendation_id/target_segment_id/recommendation_type`만 보고 blocker 여부를 판정해, 이미 `approved/rejected`로 끝난 stale entry까지 pending blocker로 취급하던 점이었다
- 최소 수정으로 runtime pending blocker 판정이 explicit `decision_state`가 있을 때는 `pending`만 unresolved blocker로 인정하게 좁혀, API read path와 subtitle / preview / export가 stale approved/rejected entry를 무시하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 stale pending blocker normalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - stale pending decision-state blocker normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline에 stale `decision_state=approved/rejected` pending recommendation entry가 남아 있어도 unresolved blocker로 오판하지 않음
2. subtitle / preview / export output gating이 stale pending decision-state entry 때문에 다시 막히지 않음
3. timeline read path와 review snapshot도 stale pending entry를 canonical pending blocker로 surface하지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 33. 2026-07-04 partial regeneration preflight stale pending decision-state prediction closeout

이번 후속 작업에서는 방금 닫은 output gating 경계와 같은 stale pending family 안에서, `preflight contract` 쪽에 남아 있던 가장 작은 prediction 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- output gating/runtime은 이미 `decision_state=approved/rejected` stale pending recommendation entry를 unresolved blocker로 보지 않게 맞춰졌지만, partial regeneration preflight prediction은 같은 source shape를 여전히 blocker로 취급하고 있었다
- strict TDD로 `test_editing_session_api_filters_approved_decision_state_source_pending_recommendation_from_preflight_prediction` exact regression을 먼저 추가했고, 실제로 `predicted_review_status_after_rerun == blocked` RED를 확인했다
- 원인은 `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`가 source pending recommendation을 필터링할 때 `decision_state`를 보지 않고 `recommendation_id/target_segment_id/recommendation_type`만으로 blocker 후보를 유지하던 점이었다
- 최소 수정으로 preflight source pending recommendation filter도 explicit `decision_state`가 있을 때 `pending`만 unresolved blocker로 인정하도록 좁혀, preflight prediction이 runtime/output truth와 같은 기준을 쓰게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight pending blocker normalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `55 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight source pending decision-state prediction 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 source timeline의 stale `decision_state=approved/rejected` pending recommendation entry를 unresolved blocker prediction으로 복원하지 않음
2. clean scope preflight prediction이 stale pending decision-state entry 때문에 `blocked`로 오염되지 않음
3. preflight prediction과 runtime/output gating이 stale pending decision-state family에서 같은 blocker 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 34. 2026-07-04 timeline builder string false recommendation review_required closeout

이번 후속 작업에서는 stale pending decision-state family를 더 넓히지 않고, `review/output` truth에 바로 닿는 timeline build 경계의 가장 작은 legacy bool-shape 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `TimelineBuilder`는 recommendation dict의 `review_required="false"` 같은 legacy string false shape를 그대로 `bool(...)`로 해석해 pending recommendation과 review blocker로 오판하고 있었다
- strict TDD로 `test_timeline_builder_treats_string_false_recommendation_review_required_as_false` exact regression을 먼저 추가했고, 실제로 auto-apply 가능한 B-roll recommendation이 applied로 가지 않고 pending으로 남는 RED를 확인했다
- 원인은 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`가 dict recommendation/segment payload를 그대로 보존한 채 `bool(recommendation.get("review_required"))`를 사용하던 점이었다
- 최소 수정으로 `TimelineBuilder` 내부 bool-ish normalization을 추가해 dict segment/recommendation payload의 false-like string을 canonical bool로 맞추고, build/build-review-snapshot 계열이 같은 기준을 쓰게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline build truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline build가 recommendation의 `review_required="false"` legacy string shape를 review blocker로 오판하지 않음
2. auto-apply 가능한 recommendation이 stale string false 때문에 pending recommendation으로 밀리지 않음
3. timeline build truth와 output gating truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 35. 2026-07-04 recommendation store string false review_required closeout

이번 후속 작업에서는 방금 닫은 timeline build 경계보다 한 단계 앞단인 저장소 write path에서, 같은 legacy bool-shape가 persisted truth를 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `save_recommendation_run(...)`는 incoming recommendation dict의 `review_required="false"` 같은 legacy string false shape를 그대로 `bool(...)`로 해석해 persisted recommendation과 DB row를 blocker truth로 저장하고 있었다
- strict TDD로 `test_store_save_recommendation_run_treats_string_false_review_required_as_false` exact regression을 먼저 추가했고, 실제로 returned payload의 `review_required is True` RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`가 recommendation 저장 시 `auto_apply_allowed/review_required`를 그대로 `bool(...)`로 캐스팅하던 점이었다
- 최소 수정으로 저장소 write path에 bool-ish normalization을 추가해 `auto_apply_allowed/review_required`의 false-like string을 canonical bool로 저장하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation persistence truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation store bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation 저장 write path가 `review_required="false"` legacy string shape를 blocker truth로 저장하지 않음
2. returned recommendation payload와 DB row가 canonical false를 유지함
3. recommendation persistence truth와 downstream timeline build truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 36. 2026-07-04 recommendation read path legacy string false closeout

이번 후속 작업에서는 저장소 write path 다음 단계인 recommendation read path에서, legacy DB text bool-shape가 read truth를 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `list_recommendation_rows(...)`는 legacy DB row의 `auto_apply_allowed="false"` / `review_required="false"` text 값을 그대로 `bool(...)`로 해석해 read path에서 truthy로 뒤집고 있었다
- strict TDD로 `test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false` exact regression을 먼저 추가했고, 실제로 `auto_apply_allowed is True` RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 recommendation row hydration이 DB 값을 그대로 `bool(...)`로 캐스팅하던 점이었다
- 최소 수정으로 recommendation read path도 같은 bool-ish normalization을 재사용해 legacy string false를 canonical false로 읽도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation read-path bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation read path가 legacy DB text `"false"` shape를 truthy blocker로 읽지 않음
2. hydrated recommendation row가 canonical false를 유지함
3. recommendation read truth와 write truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 37. 2026-07-04 editing session legacy string false segment review_required closeout

이번 후속 작업에서는 recommendation bool-ish family를 더 넓히지 않고, editing-session SSOT에 직접 닿는 segment read path의 가장 작은 legacy bool-shape 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `list_segments(...)`와 `build_editing_session(...)`는 legacy segment row의 `review_required="false"` text 값을 그대로 truthy로 취급해 editing session 생성 시 `review_required=True`로 오염시키고 있었다
- strict TDD로 `test_editing_session_api_normalizes_legacy_string_false_segment_review_required_from_store` exact regression을 먼저 추가했고, 실제로 create editing session 응답의 `review_required`가 `True`로 뒤집히는 RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 segment row hydration과 `packages/core-engine/src/videobox_core_engine/editing_session.py`의 session segment 빌드가 모두 `bool(...)` 기반으로 legacy string false를 읽던 점이었다
- 최소 수정으로 두 read path에 같은 bool-ish normalization을 적용해 legacy segment row의 false-like string을 canonical false로 읽도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 editing-session segment truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `56 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - editing session segment bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. editing session 생성 read path가 legacy segment row의 `review_required="false"` shape를 truthy review-required로 읽지 않음
2. session segment payload와 downstream preflight targeted segment가 canonical false를 유지함
3. segment read truth와 editing-session SSOT가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 38. 2026-07-04 segment analysis write path string false segment review_required closeout

이번 후속 작업에서는 방금 닫은 editing-session segment read path보다 한 단계 앞단인 persistence write path에서, 같은 legacy bool-shape가 stored segment truth를 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `save_segment_analysis(...)`는 incoming segment dict의 `review_required="false"` 값을 그대로 truthy로 취급해 persisted `segments.review_required`를 `1`로 저장하고 있었다
- strict TDD로 `test_editing_session_api_preserves_string_false_segment_review_required_after_segment_analysis_write` exact regression을 먼저 추가했고, 실제로 segment analysis 저장 이후 create editing session 응답의 `review_required`가 `True`로 오염되는 RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 segment insert path가 `review_required`를 그대로 `bool(...)` 기반 truthiness로 저장하던 점이었다
- 최소 수정으로 segment analysis write path에도 같은 bool-ish normalization을 적용해 false-like string을 canonical false로 저장하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 segment persistence truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `56 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - segment analysis write-path bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. segment analysis 저장 write path가 `review_required="false"` legacy string shape를 truthy review-required로 저장하지 않음
2. persisted segment row와 downstream editing session이 canonical false를 유지함
3. segment write truth와 read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 39. 2026-07-04 timeline response legacy string false recommendation fields closeout

이번 후속 작업에서는 bool-ish false family를 더 넓히지 않고, timeline/read contract에 직접 닿는 API response layer의 가장 작은 legacy recommendation 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 legacy timeline payload 안의 `auto_apply_allowed="false"` / `review_required="false"` text 값을 그대로 truthy로 취급해 timeline API response에서 `True`로 뒤집고 있었다
- strict TDD로 `test_timeline_api_normalizes_legacy_string_false_pending_recommendation_fields` exact regression을 먼저 추가했고, 실제로 timeline API의 pending recommendation response에서 두 필드가 모두 `True`로 뒤집히는 RED를 확인했다
- 원인은 API response normalization이 recommendation bool 필드를 raw `bool(...)`로 캐스팅하던 점이었다
- 최소 수정으로 response layer에도 bool-ish normalization helper를 추가해 legacy false-like string을 canonical false로 읽도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline/read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - API response bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline API response가 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` shape를 truthy recommendation state로 읽지 않음
2. pending recommendation response가 canonical false를 유지함
3. timeline/read truth와 downstream review snapshot/partial regeneration result response가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 40. 2026-07-04 approve rollback legacy string false recommendation fields closeout

이번 후속 작업에서는 timeline/read response 경계보다 한 단계 아래인 recommendation rollback persistence에서, downstream failure 후 legacy false-like payload가 DB row truth를 다시 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- review state 저장 실패 후 rollback이 실행될 때 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`는 original recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` 값을 raw `bool(...)`로 다시 써서 DB row를 `(1, 1, "pending")`로 오염시키고 있었다
- strict TDD로 `test_review_snapshot_api_approve_rollback_normalizes_legacy_string_false_recommendation_fields` exact regression을 먼저 추가했고, 실제로 approve rollback 뒤 recommendation row가 `(0, 0, "pending")`이 아니라 `(1, 1, "pending")`가 되는 RED를 확인했다
- 원인은 `_rollback_recommendation_review_mutation(...)`의 recommendation row restore path가 legacy false-like string을 canonicalize하지 않던 점이었다
- 최소 수정으로 rollback persistence path에도 runtime bool-ish normalization을 적용해 legacy false-like recommendation fields를 canonical false DB 값으로 복구하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation rollback truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rollback persistence bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve rollback persistence가 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` shape를 truthy DB row로 복구하지 않음
2. downstream failure 뒤 recommendation row가 canonical false와 original decision state를 유지함
3. recommendation rollback truth와 timeline/read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 41. 2026-07-04 preview renderer string false TTS recommendation review_required closeout

이번 후속 작업에서는 review mutation rollback보다 더 사용자 출력에 가까운 `TTS approval/output` 인접면에서, preview narration source 선택이 legacy false-like recommendation field 때문에 틀어지는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 applied `tts_replacement` recommendation의 `auto_apply_allowed="true"` / `review_required="false"` 값을 raw `bool(...)`로 읽어 실제 selected narration source 대신 original narration source를 preview HTML에 노출하고 있었다
- strict TDD로 `test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false` exact regression을 먼저 추가했고, 실제로 preview HTML이 selected TTS source를 잃고 original narration source를 계속 노출하는 RED를 확인했다
- 원인은 preview renderer의 TTS applied-segment 판정이 bool-ish false normalization 없이 raw truthiness를 쓰던 점이었다
- 최소 수정으로 preview renderer에도 bool-ish normalization helper를 추가해 legacy false-like recommendation fields를 canonical bool로 해석하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview/TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 applied `tts_replacement` recommendation의 `review_required="false"` legacy string shape를 blocker로 오판하지 않음
2. preview HTML narration source가 selected TTS source를 유지함
3. preview/TTS read truth와 timeline/recommendation normalization이 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 42. 2026-07-04 review snapshot fallback legacy string false recommendation decision-state closeout

이번 후속 작업에서는 preview/TTS read path 다음 인접면인 review snapshot fallback classification에서, legacy false-like recommendation payload가 applied recommendation truth를 pending blocker로 뒤집는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_derive_recommendation_decision_state(...)`는 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` 값을 raw truthiness로 읽어 review snapshot fallback에서 `pending`으로 오판하고 있었다
- strict TDD로 `test_store_build_review_snapshot_treats_legacy_string_false_recommendation_as_approved` exact regression을 먼저 추가했고, 실제로 review snapshot의 `applied_recommendations`가 비고 recommendation이 pending 쪽으로 밀리는 RED를 확인했다
- 원인은 fallback decision-state derivation이 bool-ish false normalization 없이 raw truthiness를 쓰던 점이었다
- 최소 수정으로 `_derive_recommendation_decision_state(...)`도 같은 bool-ish normalization을 사용하도록 맞춰 legacy recommendation payload를 canonical decision-state로 분류하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot fallback truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot fallback decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot fallback classification이 legacy recommendation payload의 `review_required="false"` shape를 pending blocker로 오판하지 않음
2. auto-apply 가능한 recommendation이 applied recommendation truth를 유지함
3. review snapshot fallback truth와 recommendation persistence/read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 43. 2026-07-04 review guidance string false segment review_required closeout

이번 후속 작업에서는 review snapshot fallback 다음 인접면인 operator guidance prompt surface에서, legacy false-like segment payload가 attention-required segment를 잘못 늘리는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_segments_needing_attention(...)`는 segment payload의 `review_required="false"` 값을 raw truthiness로 읽어 operator guidance prompt에 실제로는 review가 필요 없는 segment까지 attention 대상으로 포함하고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_string_false_segment_review_required` exact regression을 먼저 추가했고, 실제로 `["seg_001", "seg_002"]`가 나와야 할 자리에 `["seg_002"]`만 남아야 하는 RED를 확인했다
- 원인은 operator guidance의 segment attention 계산이 bool-ish false normalization 없이 raw truthiness를 쓰던 점이었다
- 최소 수정으로 review guidance에도 bool-ish normalization helper를 추가해 legacy false-like segment fields를 canonical bool로 해석하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 operator guidance prompt truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - operator guidance bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. operator guidance prompt가 legacy segment payload의 `review_required="false"` shape를 attention-required segment로 오판하지 않음
2. `segments needing attention` 계산이 실제 review-required segment만 유지함
3. operator guidance truth와 segment persistence/read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 16. 2026-06-30 review recommendation approve persistence 착수 기록

이번 후속 작업으로 `review action placeholder -> first approve persistence`의 최소 slice는 착수 및 focused verification까지는 됐다고 본다.

이번에 추가로 확인된 사실은 아래와 같다.

- review panel의 `Approve recommendation` 버튼이 실제 approve API 호출로 연결됐다
- backend에서 pending recommendation을 applied recommendation으로 이동시키고 관련 review flag를 제거할 수 있다
- recommendation row의 `auto_apply_allowed/review_required` 값이 승인 결과에 맞게 갱신된다
- approve 후 review snapshot과 timeline refresh가 같이 일어나도록 frontend 배선이 연결됐다
- backend focused test `1 passed`
- frontend focused test `1 passed`

다만 이 단계는 아직 완결 milestone로 닫지 않았다.

- 아직 확인하지 않은 것
  - frontend build
  - full backend regression
  - reject/manual-edit persistence
- 따라서 현재 상태는 `작동하는 첫 slice`이지 `완료된 review action family`는 아니다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- approve persistence slice의 broader verification
- non-target recommendation/flag 보존에 대한 역방향 검증 보강
- reject/manual-edit 중 다음 최소 persistence slice 선정

## 15. 2026-06-30 thin editor B-roll override clear 기록

이번 후속 작업으로 `thin editor B-roll override clear/remove` slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- editing session 도메인과 API에서 saved B-roll override clear 경로가 실제로 연결됐다
- thin editor에서 `Clear B-roll override`를 직접 실행할 수 있다
- clear 후 active candidate invalidation은 기존 mutation 규칙 그대로 유지된다
- clear 후 rerun scope의 `broll` 선택 상태도 stale하게 남지 않는다
- focused backend regression `143 passed`
- frontend focused test `46 passed`
- frontend build 성공
- full backend regression `234 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. B-roll override save
2. B-roll override clear/remove
3. clear 후 candidate invalidation
4. clear 후 rerun scope cleanup

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review->editor recommendation mapping coverage 중 `broll` happy-path 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 14. 2026-06-30 thin editor music override clear 기록

이번 후속 작업으로 `thin editor music override clear/remove` slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- editing session 도메인과 API에서 saved music override clear 경로가 실제로 연결됐다
- thin editor에서 `Clear music override`를 직접 실행할 수 있다
- clear 후 active candidate invalidation은 기존 mutation 규칙 그대로 유지된다
- clear 후 rerun scope의 `music` 선택 상태도 stale하게 남지 않는다
- focused backend regression `141 passed`
- frontend focused test `45 passed`
- frontend build 성공
- full backend regression `232 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. music override save
2. music override clear/remove
3. clear 후 candidate invalidation
4. clear 후 rerun scope cleanup

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review->editor recommendation mapping coverage 중 `broll` happy-path 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 92. 2026-07-04 preflight mixed-case pending recommendation type prediction closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 source pending recommendation stale-shape 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source pending recommendation의 `recommendation_type`을 `strip()`만 한 채 `VALID_PREVIEW_RECOMMENDATION_TYPES`와 비교하고 있어, mixed-case stale blocker인 `" TTS_REPLACEMENT "`를 valid unresolved blocker로 복원하지 못하고 `draft` prediction으로 흘리고 있었다
- strict TDD로 `test_editing_session_api_preserves_mixed_case_source_pending_recommendation_type_in_preflight_prediction` exact regression을 먼저 추가했고, 실제로 `predicted_review_status_after_rerun == "blocked"` 기대가 `draft`로 깨지는 RED를 확인했다
- 원인은 preflight prediction helper의 source pending recommendation type 필터가 다른 mixed-case canonicalization 경계들과 달리 lowercase normalization을 재사용하지 않던 점이었다
- 최소 수정으로 type 비교를 `strip().lower()` 기준으로 좁혀, mixed-case stale pending recommendation blocker도 canonical lowercase type 기준으로 `blocked` prediction truth를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction helper의 mixed-case blocker type 판정 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- preflight-backend focused slice
  - `57 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction helper의 type canonicalization 한 점 수정이라 exact + preflight focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 source timeline의 mixed-case stale pending recommendation type도 valid unresolved blocker로 유지한다
2. clean target segment여도 source blocker가 있으면 `predicted_review_status_after_rerun`가 `draft`로 풀리지 않고 `blocked` truth를 유지한다
3. preflight prediction의 pending recommendation type 판정이 다른 mixed-case recommendation canonicalization 경계와 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 93. 2026-07-04 partial regeneration mixed-case pending recommendation dedupe closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 맞닿은 partial regeneration runtime carry-forward 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 runtime pending recommendation dedupe key는 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, source timeline에 `"tts_replacement"`와 `" TTS_REPLACEMENT "`가 함께 남아 있으면 같은 blocker인데도 partial regeneration result의 `pending_recommendations`에 2개가 동시에 남고 있었다
- strict TDD로 `test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 result timeline의 `pending_recommendations` 길이가 기대한 `1`이 아니라 `2`가 되는 RED를 확인했다
- 원인은 runtime carry-forward 초입의 `_normalized_runtime_pending_recommendations(...)`와 persisted timeline merge 직전의 `existing_pending_keys`가 모두 recommendation type canonicalization 없이 dedupe key를 만들고 있던 점이었다
- 최소 수정으로 두 dedupe key 모두 `_canonical_runtime_recommendation_type(...)`를 재사용하게 맞춰, mixed-case stale pending blocker duplicate도 canonical lowercase type 기준으로 한 번만 유지되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime pending blocker dedupe 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - mixed-case preflight/runtime pending blocker family exact `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime carry-forward pending dedupe key canonicalization 두 군데만 바뀐 좁은 수정이라 exact + 인접 family exact evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime이 source timeline의 mixed-case stale pending recommendation duplicate를 한 번만 유지한다
2. runtime result의 `pending_recommendations`와 `review_flags`가 같은 blocker를 중복 surface하지 않는다
3. preflight prediction의 mixed-case blocker 판단과 runtime carry-forward dedupe가 같은 canonical lowercase recommendation type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 94. 2026-07-04 recommendation run mixed-case type read closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 recommendation artifact read-path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_recommendation_run(...)`는 saved recommendation run JSON의 top-level `recommendation_type`을 raw 문자열로 비교하고 있어, `" BROLL "` 같은 stale mixed-case shape가 들어오면 artifact read가 바로 `Recommendation run type mismatch`로 실패하고 있었다
- strict TDD로 `test_recommendation_run_accepts_mixed_case_recommendation_type` exact regression을 먼저 추가했고, 실제로 `store.get_recommendation_run(...)`가 `KeyError`를 던지는 RED를 확인했다
- 원인은 recommendation run loader가 row/review snapshot/timeline 쪽에서 이미 맞춘 canonical recommendation type 비교를 file-level recommendation run read path에는 재사용하지 않던 점이었다
- 최소 수정으로 loader의 type 검증도 `_canonical_recommendation_type(...)`를 재사용하게 맞춰, mixed-case stale recommendation run artifact도 canonical lowercase type 기준으로 계속 읽히게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation run read-path의 mixed-case type 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - recommendation run read family exact `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation run loader의 file-level type 비교 한 줄 수정이라 exact + 인접 read-path exact evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation run read path가 mixed-case stale top-level `recommendation_type`도 canonical lowercase type 기준으로 허용한다
2. recommendation result/output build 경로가 stale artifact type casing 때문에 바로 끊기지 않는다
3. recommendation run type 허용과 provider-trace backfill read-path가 같은 artifact read 경계에서 함께 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 95. 2026-07-04 recommendation run mixed-case type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, 방금 닫은 recommendation run read-path 경계와 같은 가족 안에서 returned surface canonicalization 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_recommendation_run(...)`는 mixed-case stale top-level `recommendation_type`을 더 이상 read failure로 막지는 않았지만, returned payload에는 `" BROLL "` 같은 raw casing을 그대로 남기고 있었다
- strict TDD로 `test_recommendation_run_accepts_mixed_case_recommendation_type`의 기대값을 canonical `"broll"` surface로 강화했고, 실제로 `loaded_run["recommendation_type"] == " BROLL "` RED를 확인했다
- 원인은 loader가 type validation에서는 canonical comparison을 이미 쓰고 있으면서도, 반환 payload에는 canonicalized type을 다시 쓰지 않던 점이었다
- 최소 수정으로 accepted type을 returned payload에도 `_canonical_recommendation_type(...)` 결과로 다시 넣어, recommendation run read-path의 artifact truth와 surface truth를 같은 lowercase 기준으로 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation run read family의 type surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - recommendation run read family exact `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - loader returned surface canonicalization 한 줄 수정이라 exact + 인접 read-path exact evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation run read path가 mixed-case stale top-level `recommendation_type`도 canonical lowercase type 기준으로 읽는다
2. returned payload surface도 raw casing이 아니라 canonical lowercase type을 유지한다
3. recommendation run type surface와 provider-trace backfill read-path가 같은 artifact read 경계에서 함께 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 96. 2026-07-04 top-level AGENTS instruction promotion closeout

이번 후속 작업에서는 이미 문서 SSOT에 저장된 운영 규정을 저장소 최상위에서도 바로 보이게 해야 한다는 요구에 맞춰, 중복 없이 연결되는 top-level instruction 경계만 좁게 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- 현재 브랜치의 개발 운영 규정 본문은 `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`에 있지만, 저장소 루트에는 이를 바로 가리키는 `AGENTS.md`가 없어서 최상위 진입점이 비어 있었다
- 사용자가 제시한 `AGENTS.md` 원칙은 기존 운영 규정과 충돌하기보다, 정확성 우선, 리스크 공개, 관련 없는 변경 금지, 검증 전 완료 금지 같은 상위 태도를 더 분명하게 만드는 역할에 가깝다
- 그래서 같은 규정을 여러 문서에 복제하지 않고, 루트 `AGENTS.md`는 최상위 지침 요약과 SSOT 링크 역할만 맡기고 authoritative 운영 본문은 계속 fast-path 문서에 두는 편이 drift를 줄이는 가장 작은 수정이었다
- 구현 계획서 상단과 fast-path 규정 섹션도 루트 `AGENTS.md`를 함께 참조하도록 좁게 연결해, 다음 turn부터는 계획서만 읽어도 최상위 지침이 빠지지 않게 맞췄다

이번 turn의 verification은 아래와 같다.

- 상태 확인
  - `git status --short --branch`
- 최근 closeout 확인
  - `git log -5 --oneline`
- SSOT 재확인
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - `docs/development-fast-path.ko.md`
- diff 확인
  - 루트 `AGENTS.md` 추가와 상위 SSOT 링크 수정만 들어갔는지 확인

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. 저장소 최상위에서도 개발 운영 지침을 바로 읽을 수 있다
2. 운영 규정 본문은 fast-path SSOT에 두고, 루트 `AGENTS.md`는 링크형 상위 진입점으로 유지한다
3. 구현 계획서와 fast-path 문서가 같은 top-level instruction을 함께 참조한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 97. 2026-07-04 output blocker mixed-case pending recommendation detail closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 output blocker detail surface의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_normalized_runtime_pending_recommendations(...)`는 mixed-case stale pending recommendation을 blocker로는 올바르게 복원하고 dedupe key에도 canonical lowercase type을 쓰고 있었지만, normalized item 자체의 `recommendation_type`은 raw casing을 그대로 남기고 있었다
- 그 결과 `_ensure_timeline_has_no_blockers(...)`가 만드는 output gating 에러 detail에는 `" TTS_REPLACEMENT :rec_tts_seg_001@seg_001"` 같은 raw stale type surface가 그대로 노출되고 있었다
- strict TDD로 `test_output_blocker_detail_canonicalizes_mixed_case_pending_recommendation_type` exact regression을 먼저 추가했고, 실제로 preview output gating detail이 canonical `"tts_replacement:rec_tts_seg_001@seg_001"` 대신 raw mixed-case shape를 내보내는 RED를 확인했다
- 최소 수정으로 runtime pending recommendation normalization 단계에서 `recommendation_type`도 `_canonical_runtime_recommendation_type(...)` 결과로 다시 써, blocker 판정 / dedupe / detail surface가 모두 같은 canonical lowercase type 기준을 쓰도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output blocker detail surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime blocker normalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline output gating detail이 mixed-case stale pending recommendation type도 canonical lowercase type 기준으로 surface한다
2. runtime blocker dedupe key와 blocker detail surface가 같은 canonical recommendation type 기준을 사용한다
3. output blocker detail이 stale raw casing 때문에 브랜치 전체 canonicalization 흐름과 어긋나지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 98. 2026-07-04 output gating mixed-case review flag code closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 mixed-case review flag code blocker 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 runtime output gating은 `review_flags.code`를 `strip()`만 한 채 `VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale flag code를 실제 blocker로 복원하지 못하고 있었다
- 그 결과 approved timeline에 unresolved review flag가 남아 있어도 preview output이 `400`이 아니라 `202`로 통과하는 실제 계약 누수가 있었다
- strict TDD로 `test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline` exact regression을 먼저 추가했고, 실제로 preview render 시작이 허용되는 RED를 확인했다
- 최소 수정으로 runtime review flag normalization에 `_canonical_runtime_review_flag_code(...)` helper를 추가하고, blocker 판정 / dedupe key / normalized surface 모두 같은 lowercase code 기준을 쓰도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output gating review flag code 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime review flag code canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline output gating이 mixed-case stale `review_flags.code`도 canonical lowercase blocker code로 복원한다
2. blocker 판정과 detail surface가 같은 canonical review flag code 기준을 사용한다
3. unresolved review flag가 raw casing 때문에 output approval을 우회하지 못한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 99. 2026-07-04 preflight mixed-case source review flag code closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 source review flag code canonicalization 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source `review_flags.code`를 `strip()`만 한 채 `VALID_PREVIEW_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale blocker code를 unresolved blocker로 복원하지 못하고 있었다
- 그 결과 source timeline에 review blocker가 남아 있어도 preflight prediction이 `blocked`가 아니라 `draft`로 흘러, rerun 전 read-only prediction contract가 output gating truth와 어긋나고 있었다
- strict TDD로 `test_editing_session_api_marks_preflight_blocked_when_source_review_flag_has_mixed_case_valid_code` exact regression을 먼저 추가했고, 실제로 mixed-case stale source review flag가 있는 preflight response가 `draft`를 반환하는 RED를 확인했다
- 최소 수정으로 preflight helper에 `_canonical_preview_review_flag_code(...)`를 추가하고 source review flag filter가 lowercase code 기준을 쓰도록 맞춰, mixed-case stale blocker code도 canonical preview blocker code 기준으로 `blocked` prediction을 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight source review flag code 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - 결과: `58 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight helper의 review flag code canonicalization 한 점 수정이라 exact + preflight-backend focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 mixed-case stale source `review_flags.code`도 canonical lowercase blocker code 기준으로 복원한다
2. source blocker가 남아 있으면 preflight prediction이 `draft`로 풀리지 않고 `blocked` truth를 유지한다
3. preflight prediction의 review flag code 판정이 output gating 쪽 canonical blocker code 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 100. 2026-07-04 partial regeneration runtime mixed-case source review flag carry-forward closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 맞닿은 partial regeneration runtime source review-flag carry-forward 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 partial regeneration runtime은 source `review_flags.code`를 `strip()`만 한 채 `VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale blocker code를 candidate timeline 결과에 다시 복원하지 못하고 있었다
- 그 결과 source blocker가 남아 있어도 partial regeneration result timeline의 `review_status`가 `blocked`가 아니라 `draft`로 풀리는 실제 계약 누수가 있었다
- strict TDD로 `test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_has_mixed_case_valid_code` exact regression을 먼저 추가했고, 실제로 result timeline이 `draft`를 반환하는 RED를 확인했다
- 최소 수정으로 runtime source review-flag carry-forward가 `_canonical_runtime_review_flag_code(...)`를 재사용하도록 맞추고, carry-forward dedupe key도 같은 lowercase code 기준을 쓰게 해 mixed-case stale source blocker를 canonical surface로 한 번만 복원하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime source review-flag carry-forward 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration source review-flag family exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime source review-flag carry-forward와 dedupe key 두 지점만 바뀐 좁은 수정이라 exact + 인접 family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime이 mixed-case stale source `review_flags.code` blocker도 candidate timeline 결과에 다시 복원한다
2. result timeline의 `review_status`와 `review_flags` surface가 canonical lowercase review flag code 기준으로 유지된다
3. source review-flag carry-forward 판정과 dedupe key가 preflight/output canonicalization 흐름과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 101. 2026-07-04 partial regeneration broll refresh mixed-case applied recommendation closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 인접한 partial regeneration runtime applied recommendation refresh 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `broll_refresh`는 source timeline의 stale applied recommendation을 지울 때 `recommendation_type`을 `strip()`만 한 채 `RecommendationType.BROLL.value`와 비교하고 있어, `" BROLL "` 같은 mixed-case stale shape를 기존 B-roll recommendation으로 인식하지 못하고 있었다
- 그 결과 manual B-roll override로 partial regeneration을 다시 돌려도 stale applied B-roll clip이 제거되지 않고 새 manual clip과 함께 중복으로 남는 실제 계약 누수가 있었다
- strict TDD로 `test_editing_session_api_replaces_mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 stale clip과 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `broll_refresh`와 같은 가족인 `music_refresh`의 stale recommendation 제거 비교도 `_canonical_runtime_recommendation_type(...)`를 재사용하도록 맞춰, mixed-case stale applied recommendation도 canonical lowercase type 기준으로 기존 recommendation을 교체하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration refresh family의 mixed-case stale applied recommendation 제거 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration applied recommendation refresh family exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - `broll_refresh`/`music_refresh`의 stale removal comparison 두 줄만 바뀐 좁은 수정이라 exact + 인접 family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime의 `broll_refresh`가 mixed-case stale applied `recommendation_type`도 기존 B-roll recommendation으로 인식해 교체한다
2. manual B-roll override rerun 뒤 stale B-roll clip과 새 manual clip이 동시에 남지 않는다
3. refresh family의 stale applied recommendation 제거 기준이 TTS canonicalization 흐름과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 102. 2026-07-04 timeline persistence mixed-case review flag initial status closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 timeline persistence initial review-state 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_is_store_blocking_review_flag(...)`는 `review_flags.code`를 `strip()`만 한 채 `VALID_STORE_BLOCKING_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale blocker code를 store-level blocker로 인식하지 못하고 있었다
- 그 결과 timeline 저장 시 initial review state가 `blocked`가 아니라 `draft`로 저장되는 실제 계약 누수가 있었다
- strict TDD로 `test_store_save_timeline_run_marks_mixed_case_review_flag_as_blocked_initial_status` exact regression을 먼저 추가했고, 실제로 `review_state["status"] == "draft"` RED를 확인했다
- 최소 수정으로 store helper에 `_canonical_review_flag_code(...)`를 추가하고 blocking review flag 판정이 lowercase code 기준을 쓰도록 맞춰, mixed-case stale review flag code도 canonical blocker로 인식하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence initial review-state 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - timeline persistence initial-status family exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - store-level review flag blocker 판정 helper 한 점 수정이라 exact + 인접 initial-status family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline persistence initial review state가 mixed-case stale `review_flags.code` blocker도 canonical lowercase code 기준으로 `blocked`로 저장한다
2. 저장 직후 review state truth가 output/preflight 쪽 mixed-case review flag canonicalization 흐름과 더 가까워졌다
3. stale non-list review flag 무시와 unknown pending recommendation 무시 계약은 그대로 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 103. 2026-07-04 review snapshot mixed-case review flag surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 맞닿은 review snapshot direct helper의 mixed-case review flag surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 mixed-case stale `review_flags.code`를 blocker로는 인식하게 됐지만, returned `review_flags` surface에는 `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 raw casing과 whitespace를 그대로 남기고 있었다
- 그 결과 direct helper를 바로 쓰는 read path나 테스트 면에서는 `review_status=blocked`와 `review_flags` surface truth가 서로 다른 canonicalization 기준을 갖는 작은 계약 틈이 남아 있었다
- strict TDD로 `test_review_snapshot_canonicalizes_mixed_case_review_flag_code` exact regression을 먼저 추가했고, 실제로 helper 반환 `review_flags`가 raw stale shape를 그대로 내보내는 RED를 확인했다
- 최소 수정으로 store helper에 review flag payload normalization을 추가하고 `build_review_snapshot(...)`가 canonical lowercase code, trimmed segment id, default message 기준의 normalized surface를 반환하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot direct helper의 review flag surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review snapshot direct helper family exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - helper returned review flag surface 한 점 수정이라 exact + 인접 helper family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 mixed-case stale `timeline_review_flags.code` blocker도 canonical lowercase code 기준으로 surface한다
2. helper returned `review_flags`가 trimmed segment id와 default message를 함께 유지한다
3. `review_status=blocked` truth와 `review_flags` surface truth가 같은 review flag canonicalization 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 104. 2026-07-04 API review flag response mixed-case code closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 API review-flag response normalization helper 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_review_flags_for_response(...)`는 `review_flags.code`를 `strip()`만 한 채 response surface로 내보내고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale code를 raw casing 그대로 노출하고 있었다
- strict TDD로 `test_review_flag_response_normalization_canonicalizes_mixed_case_code` exact regression을 먼저 추가했고, 실제로 helper 반환 `review_flags[0]["code"] == "TTS_REPLACEMENT_REVIEW_REQUIRED"` RED를 확인했다
- 최소 수정으로 response helper가 `code`를 `strip().lower()` 기준으로 canonicalize하도록 맞춰, timeline/review response 경로가 canonical lowercase review flag code를 일관되게 쓰도록 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 API review-flag response normalization helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - API response normalization helper 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - API helper의 lowercase canonicalization 한 줄 수정이라 exact + helper-adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. API review flag response helper가 mixed-case stale `review_flags.code`를 raw casing 그대로 노출하지 않는다
2. helper returned `review_flags`가 canonical lowercase code / trimmed segment id / default message surface를 함께 유지한다
3. recommendation response helper와 review flag response helper가 timeline/review API normalization에서 같은 canonical surface 규칙을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 105. 2026-07-04 preflight request trimmed segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 targeted-segment request normalization 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_targeted_segments(...)`는 session 쪽 `segment_id`는 trim해서 lookup table을 만들지만, request `segment_ids`는 raw 문자열 그대로 조회하고 response `segment_id` surface에도 raw 값을 다시 쓰고 있었다
- 그 결과 `" seg_001 "` 같은 whitespace stale request segment id를 가진 preflight/partial-regeneration request는 기존 session segment를 놓치고 targeted segment preview를 비우거나 raw id를 그대로 surface할 수 있는 실제 계약 누수가 있었다
- strict TDD로 `test_build_targeted_segments_matches_trimmed_request_segment_ids` exact regression을 먼저 추가했고, 실제로 helper가 `[]`를 반환한 RED를 확인했다
- 첫 최소 수정 뒤 같은 exact test에서 returned `segment_id`가 raw `" seg_001 "`로 남는 두 번째 RED를 확인했고, helper가 request segment id도 `strip()` 기준으로 lookup하고 returned surface에도 canonical trimmed id를 쓰도록 맞춰 GREEN으로 닫았다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight targeted-segment helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 중간 RED 1회 추가 확인 후 `1 passed`
- focused verification
  - preflight targeted-segment helper 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - request segment id trim과 returned surface canonicalization 두 줄 수정이라 exact + helper-adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preflight targeted-segment helper가 whitespace가 섞인 request `segment_ids`도 canonical trimmed id 기준으로 session segment와 매칭한다
2. helper returned `targeted_segments[].segment_id`가 raw request id가 아니라 canonical trimmed id를 유지한다
3. preflight scope request surface와 session segment lookup 기준이 같은 trimmed segment id 규칙을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 106. 2026-07-04 partial regeneration source segment lookup trimmed id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 `local_pipeline` partial regeneration runtime에 가장 가까운 source segment lookup 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_segments_for_timeline(...)`는 timeline clip 쪽 `segment_id`는 trim해서 읽지만, `store.list_segments(...)`로 받은 source segment row는 raw `segment_id`를 key로 보관하고 있어 `" seg_001 "` 같은 whitespace stale source row를 clip 쪽 canonical id와 매칭하지 못하고 있었다
- strict TDD로 `test_partial_regeneration_helper_matches_trimmed_source_segment_ids` exact regression을 먼저 추가했고, 실제로 helper가 `[]`를 반환하는 RED를 확인했다
- 최소 수정으로 source segment lookup key도 `strip()` 기준으로 canonicalize해, persisted source segment row의 padded id도 clip/timeline 쪽 trimmed id와 매칭되도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime source segment lookup helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration runtime helper 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - source segment lookup key canonicalization 한 점 수정이라 exact + helper-adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime helper가 whitespace가 섞인 persisted source segment row id도 canonical trimmed id 기준으로 clip/timeline과 매칭한다
2. source segment lookup이 raw row id 때문에 refresh 대상 segment를 놓치지 않는다
3. partial regeneration runtime의 source segment lookup 기준이 preflight/session 쪽 trimmed segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 107. 2026-07-04 partial regeneration music refresh trimmed source segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 `local_pipeline` partial regeneration runtime에 가장 가까운 `music_refresh` source segment id 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`는 source segment row가 `" seg_001 "`처럼 whitespace stale `segment_id`를 가지면 targeted `segment_ids=["seg_001"]`와 매칭하지 못해 refreshed music recommendation을 만들지 못하고 있었다
- strict TDD로 `test_editing_session_api_matches_trimmed_source_segment_id_for_music_refresh_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result의 bgm clip이 `['seg_002']`만 남는 RED를 확인했다
- 첫 시도에서는 adjacent `broll_refresh` 줄에 trim이 잘못 들어가 exact가 그대로 RED였고, 실제 누수 지점을 다시 확인한 뒤 `music_refresh` 대상 segment 선택 줄을 `strip()` 기준으로 맞춰 같은 exact test를 GREEN으로 닫았다
- 같은 slice에서 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 dict segment payload도 `segment_id`를 trim하도록 맞춰, refreshed recommendation은 canonical id인데 segment payload만 raw padded id를 유지해 timeline track 결합이 어긋나는 인접 누수도 함께 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration music refresh와 timeline build의 segment-id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration music 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - music refresh source segment match와 timeline builder segment payload canonicalization 두 점에 국한된 수정이라 exact + 인접 music family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `music_refresh`가 whitespace stale persisted source segment id도 canonical trimmed id 기준으로 다시 선택한다
2. refreshed music recommendation과 timeline builder segment payload가 같은 trimmed segment id 기준으로 결합된다
3. partial regeneration result가 raw padded source segment id 때문에 targeted bgm refresh를 놓치지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 108. 2026-07-04 partial regeneration overlay refresh trimmed existing segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 `local_pipeline` partial regeneration runtime에 가장 가까운 `overlay_refresh` existing overlay segment id 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_overlay_refresh_step(...)`는 existing overlay의 `segment_id`를 raw 문자열로 비교하고 있어 `" seg_001 "`처럼 whitespace stale `segment_id`를 가진 overlay가 targeted full overlay refresh에서도 제거되지 않고 그대로 남을 수 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_segment_id_existing_overlay_when_running_full_overlay_refresh` exact regression을 먼저 추가했고, 실제로 stale `hook_title` overlay와 새 `image_card` overlay가 같이 남는 RED를 확인했다
- 최소 수정으로 existing overlay preserve path, same-segment preserve path, base overlay lookup path 모두 `strip()` 기준으로 맞춰 targeted full overlay refresh가 canonical segment id 기준으로 동작하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration overlay refresh의 segment-id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration overlay 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - overlay refresh existing overlay segment-id canonicalization 세 점에 국한된 수정이라 exact + 인접 overlay family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `overlay_refresh`가 whitespace stale existing overlay segment id도 canonical trimmed id 기준으로 targeted full refresh에서 교체한다
2. same-segment preserve / base overlay lookup / target exclusion이 같은 trimmed segment id 기준을 사용한다
3. partial regeneration result가 raw padded existing overlay id 때문에 stale overlay를 남기지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 109. 2026-07-04 preview renderer trimmed narration clip segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview read path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 `_effective_narration_source_uri(...)`는 narration clip `segment_id`를 raw 문자열로 읽고 있어 `" seg_001 "`처럼 whitespace stale clip id를 가진 timeline에서 trimmed TTS recommendation target과 매칭하지 못했다
- strict TDD로 `test_preview_renderer_matches_trimmed_narration_clip_segment_id_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML이 approved TTS asset이 아니라 original narration source URI를 계속 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer의 narration clip `segment_id`도 `strip()` 기준으로 맞춰, preview read path가 trimmed TTS recommendation target과 같은 기준으로 narration source를 고르게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview renderer narration source selection 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview renderer TTS 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview narration source selection의 segment-id canonicalization 한 점 수정이라 exact + preview 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 whitespace stale narration clip segment id도 canonical trimmed id 기준으로 approved TTS recommendation과 매칭한다
2. preview HTML이 raw padded clip id 때문에 original narration source를 잘못 노출하지 않는다
3. preview read path의 narration source selection 기준이 timeline builder / export 쪽 trimmed segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 110. 2026-07-04 capcut export trimmed narration clip segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 export read path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_clip_track(...)`는 narration clip `segment_id`를 raw 문자열로 비교하고 있어 `" seg_001 "`처럼 whitespace stale clip id를 가진 timeline에서 trimmed TTS recommendation target과 매칭하지 못했다
- strict TDD로 `test_capcut_export_adapter_matches_trimmed_narration_clip_segment_id_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover track 첫 segment가 approved TTS asset이 아니라 original narration source URI를 계속 사용하던 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 clip `segment_id`도 `strip()` 기준으로 맞춰, export read path가 trimmed TTS recommendation target과 같은 기준으로 narration source를 고르게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export voiceover source selection 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export TTS 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - export voiceover source selection의 segment-id canonicalization 한 점 수정이라 exact + export 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace stale narration clip segment id도 canonical trimmed id 기준으로 approved TTS recommendation과 매칭한다
2. export payload voiceover source가 raw padded clip id 때문에 original narration source로 잘못 남지 않는다
3. preview renderer와 CapCut export adapter가 approved narration source selection에서 같은 trimmed segment id 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 111. 2026-07-04 capcut export trimmed narration clip segment id surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 CapCut export payload surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_clip_track(...)`는 approved TTS voiceover source selection은 이미 trimmed clip id 기준으로 맞췄지만, returned segment payload의 `segment_id`는 raw 문자열 그대로 남겨 `" seg_001 "` 같은 whitespace stale shape를 export surface에 그대로 노출하고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_narration_clip_segment_id_surface_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover track segment id가 `[' seg_001 ']`로 남는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 voiceover segment payload도 `segment_id.strip()` 기준으로 맞춰, export read path가 canonical segment id를 유지하도록 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export segment-id surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export TTS 인접 exact
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - export voiceover segment-id surface canonicalization 한 점 수정이라 exact + export 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace stale narration clip segment id를 source selection뿐 아니라 returned payload surface에서도 canonical trimmed id로 유지한다
2. export payload voiceover segment metadata가 raw padded clip id를 그대로 노출하지 않는다
3. preview renderer와 CapCut export adapter가 approved narration source와 segment id surface에서 같은 trimmed 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 112. 2026-07-04 capcut export trimmed broll segment grouping closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 export payload 일관성에 가장 가까운 broll sequential-fill grouping 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_broll_track(...)`는 broll clip을 `segment_id` raw 문자열 기준으로 묶고 있어 `" seg_001 "`와 `"seg_001"`처럼 whitespace stale/raw id가 섞인 같은 세그먼트를 서로 다른 window로 취급하고 있었다
- strict TDD로 `test_capcut_export_adapter_groups_trimmed_broll_segment_ids_into_one_window` exact regression을 먼저 추가했고, 실제로 첫 broll segment id가 `[' seg_001 ', 'seg_001']`로 surface되는 RED를 확인했다
- 최소 수정으로 `_build_broll_track(...)`의 grouping key를 `segment_id.strip()` 기준으로 맞춰, 같은 세그먼트의 broll clips가 하나의 sequential-fill window와 canonical segment id surface를 공유하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export broll grouping 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export broll 인접 exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - broll sequential-fill grouping key canonicalization 한 점 수정이라 exact + export broll 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace stale/raw broll segment id가 섞여 있어도 같은 세그먼트를 하나의 sequential-fill window로 묶는다
2. broll export payload의 segment surface가 canonical trimmed id 기준으로 정리된다
3. voiceover와 broll 모두 export payload에서 같은 segment-id canonicalization 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 113. 2026-07-04 preview renderer trimmed narration clip segment id surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview HTML surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 narration sources HTML surface는 approved narration source selection은 이미 trimmed 기준으로 맞춰져 있어도, 목록에 보이는 `segment_id`는 raw 문자열 그대로 노출해 `" seg_001 "` 같은 whitespace stale shape를 preview surface에 남기고 있었다
- strict TDD로 `test_preview_renderer_trims_narration_clip_segment_id_surface_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML이 `<li> seg_001 : ...</li>`를 노출하는 RED를 확인했다
- 최소 수정으로 narration sources HTML surface의 `segment_id`도 `strip()` 기준으로 맞춰, preview read path가 approved narration source와 segment id surface를 같은 canonical 기준으로 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview renderer HTML surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview renderer TTS 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview HTML surface segment-id canonicalization 한 점 수정이라 exact + preview 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 whitespace stale narration clip segment id를 approved narration source selection뿐 아니라 HTML surface에서도 canonical trimmed id로 유지한다
2. preview HTML narration sources 목록이 raw padded clip id를 그대로 노출하지 않는다
3. preview renderer의 approved narration source와 visible segment surface가 같은 trimmed 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 114. 2026-07-04 partial regeneration segment refresh trimmed source segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 이어지는 partial regeneration `segment_refresh` runtime 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_segment_refresh_step(...)`는 source segment row의 `segment_id`를 raw 문자열로 비교하고 있어 `" seg_001 "`처럼 whitespace stale source row를 trimmed request/session segment id와 매칭하지 못하고 있었다
- strict TDD로 `test_editing_session_api_matches_trimmed_source_segment_ids_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 `result_payload["regenerated_segments"] == []` RED를 확인했다
- 최소 수정으로 `segment_refresh` step의 source segment id도 `strip()` 기준으로 맞추고, regenerated timeline segment surface에도 canonical trimmed id를 다시 써 주어 caption/cut-action rerun 결과가 같은 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration segment refresh의 source segment id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration segment-refresh 인접 exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - segment_refresh source segment-id canonicalization 한 점 수정이라 exact + runtime 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `segment_refresh`가 whitespace stale source segment id도 canonical trimmed id 기준으로 request/session target과 매칭한다
2. caption/cut-action rerun의 `regenerated_segments`와 downstream timeline segment surface가 raw padded source id 때문에 비어 있거나 어긋나지 않는다
3. partial regeneration runtime의 segment-refresh 기준이 source segment helper / session segment / downstream timeline 쪽 trimmed id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 115. 2026-07-04 partial regeneration segment refresh stale source cut action closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 이어지는 partial regeneration `segment_refresh` runtime의 stale source cut-action 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_segment_refresh_step(...)`는 source segment row의 `cleanup_decision`을 raw 문자열로 그대로 읽고 있어, segment DB에 `stale_invalid_value` 같은 legacy 값이 남아 있으면 caption-only rerun에서도 `regenerated_segments[].cut_action`에 그대로 새고 있었다
- strict TDD로 `test_editing_session_api_normalizes_invalid_source_cut_action_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 rerun 결과 `cut_action == "stale_invalid_value"` RED를 확인했다
- 최소 수정으로 `segment_refresh` step의 source cut-action도 `_normalize_runtime_cut_action(...)` 기준으로 맞춰, source stale cut state가 caption-only rerun 결과와 downstream timeline에 그대로 남지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration segment refresh의 source cut-action normalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration segment-refresh 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - source cut-action normalization 한 점 수정이라 exact + runtime 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `segment_refresh`가 stale source `cleanup_decision`을 canonical runtime cut-action 값으로 정리한다
2. caption-only rerun의 `regenerated_segments`와 downstream timeline이 legacy invalid source cut state를 그대로 유지하지 않는다
3. session fallback, target override, source segment runtime이 cut-action 처리에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 116. 2026-07-04 output gating mixed-case review approval status closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 explicit approval read-path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_ensure_timeline_ready_for_output(...)`는 explicit approval 여부를 `store.get_review_state(...)[\"status\"] == \"approved\"`로 직접 비교하고 있는데, `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_review_state(...)`는 DB의 `review_approvals.status`를 raw 문자열 그대로 반환하고 있었다
- 그래서 review DB에 legacy `" APPROVED "` 같은 mixed-case stale status가 남아 있으면 blocker가 없어도 preview output gating이 `Timeline requires explicit approval...`로 잘못 막히고 있었다
- strict TDD로 `test_preview_render_accepts_mixed_case_review_approval_state_without_blockers` exact regression을 먼저 추가했고, 실제로 preview render가 `400`을 반환하는 RED를 확인했다
- 최소 수정으로 `get_review_state(...)`의 returned `status`를 `strip().lower()` 기준으로 canonicalize해, output readiness read path가 stale approval casing 때문에 subtitle/preview/export를 다시 막지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review approval read path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - explicit approval / output gating 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review approval status read-path canonicalization 한 점 수정이라 exact + output gating 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output gating이 legacy mixed-case `review_approvals.status`도 canonical lowercase 승인 상태로 해석한다
2. blocker가 없는 timeline은 stale approval casing 때문에 preview/subtitle/export를 다시 막지 않는다
3. explicit approval read truth가 runtime output gating과 더 같은 canonical status 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 117. 2026-07-04 preview renderer mixed-case review status surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 preview visible status surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 preview HTML의 `Review status:` 문구에 `timeline["review_status"]`를 raw 문자열 그대로 넣고 있어, legacy `" APPROVED "` 같은 mixed-case stale shape가 visible output surface에 그대로 노출되고 있었다
- strict TDD로 `test_preview_renderer_canonicalizes_mixed_case_review_status_surface` exact regression을 먼저 추가했고, 실제로 preview HTML이 `Review status:  APPROVED `를 그대로 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer에 review status canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, preview HTML surface가 canonical lowercase status를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview visible status surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview renderer review/output 인접 exact
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview review-status surface canonicalization 한 점 수정이라 exact + preview 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy mixed-case `review_status`도 canonical lowercase 상태로 surface한다
2. preview HTML의 visible status 문구가 raw stale review status 문자열을 그대로 노출하지 않는다
3. preview visible status surface가 output gating/readiness의 canonical status 기준과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 131. 2026-07-04 review guidance mixed-case review flag code prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `review_flags.code` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `LocalFirstReviewGuidanceBuilder._build_prompt(...)`는 `review_flags`를 raw 리스트 그대로 prompt에 넣고 있어, legacy `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale `code`가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw mixed-case code를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 review guidance prompt 전용 `_prompt_review_flags(...)`와 `_canonical_review_flag_code(...)`를 추가해 `review_flags.code`를 `strip().lower()` 기준으로 canonicalize하고, prompt surface가 review/output gating 쪽 canonical review-flag truth와 같은 기준을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 review-flag code surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag code canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 legacy mixed-case `review_flags.code`도 canonical lowercase code로 surface한다
2. operator guidance prompt가 raw stale review-flag code 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 review-flag code surface가 review/output gating의 canonical blocker truth와 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 132. 2026-07-04 review guidance trimmed review flag segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `review_flags.segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 직전 slice에서 `review_flags.code`는 canonicalize했지만 `segment_id`는 raw 문자열 그대로 두고 있어, whitespace stale `segment_id`가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_review_flag_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'segment_id': ' seg_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_review_flags(...)` 안에서 `segment_id`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 review-flag segment surface가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 review-flag segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag segment-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `review_flags.segment_id`도 canonical trimmed segment id로 surface한다
2. operator guidance prompt가 raw padded review-flag segment id 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 review-flag segment-id surface가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 133. 2026-07-04 review guidance trimmed review flag message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `review_flags.message` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 `code`와 `segment_id`는 이미 canonicalize하고 있었지만 `message`는 raw 문자열 그대로 두고 있어, whitespace stale blocker message가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'message': ' Operator review still required. '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_review_flags(...)` 안에서 `message`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 review-flag message surface가 API response 쪽 canonical blocker message 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 review-flag message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag message trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `review_flags.message`도 trimmed message로 surface한다
2. operator guidance prompt가 raw padded blocker message 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 review-flag message surface가 API response 쪽 canonical blocker message 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 134. 2026-07-04 review guidance trimmed pending recommendation reason prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.reason` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`과 `target_segment_id`는 이미 canonicalize하고 있었지만 `reason`은 raw 문자열 그대로 두고 있어, whitespace stale recommendation reason이 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_reason_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'reason': ' Select narration asset '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `reason`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 recommendation reason surface가 API response 쪽 canonical recommendation reason 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation reason surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `8 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt recommendation reason trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.reason`도 trimmed reason으로 surface한다
2. operator guidance prompt가 raw padded recommendation reason 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 recommendation reason surface가 API response 쪽 canonical recommendation reason 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 135. 2026-07-04 review guidance pending recommendation decision state prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.decision_state` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`은 이미 canonicalize하고 있었지만 `decision_state`는 raw 문자열 그대로 두고 있어, legacy `" Approved "` 같은 mixed-case stale decision state가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_canonicalizes_pending_recommendation_decision_state_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'decision_state': ' Approved '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `decision_state`도 `str(...).strip().lower()` 기준으로 canonicalize하도록 맞춰, review guidance prompt의 decision-state surface가 API response 쪽 canonical decision-state 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation decision-state surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `9 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt recommendation decision-state canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 mixed-case 또는 whitespace stale `pending_recommendations.decision_state`도 canonical lowercase decision state로 surface한다
2. operator guidance prompt가 raw padded decision-state 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 recommendation decision-state surface가 API response 쪽 canonical decision-state 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 136. 2026-07-04 review guidance pending selected asset id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.selected_asset_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`, `decision_state`는 이미 canonicalize하고 있었지만 `selected_asset_id`는 raw 문자열 그대로 두고 있어, whitespace stale asset id가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_selected_asset_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_id': ' asset_tts_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `selected_asset_id`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 selected-asset-id surface가 API response 쪽 canonical selected asset id 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 selected-asset-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `10 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt selected-asset-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.selected_asset_id`도 trimmed asset id로 surface한다
2. operator guidance prompt가 raw padded selected asset id 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 selected-asset-id surface가 API response 쪽 canonical selected asset id 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 137. 2026-07-04 review guidance pending recommendation id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.recommendation_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`, `decision_state`, `selected_asset_id`는 이미 canonicalize하고 있었지만 `recommendation_id`는 raw 문자열 그대로 두고 있어, whitespace stale recommendation id가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'recommendation_id': ' rec_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `recommendation_id`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 recommendation-id surface가 approve/output 쪽 canonical recommendation identity 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `11 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt recommendation-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.recommendation_id`도 trimmed recommendation id로 surface한다
2. operator guidance prompt가 raw padded recommendation id 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 recommendation-id surface가 approve/output 쪽 canonical recommendation identity 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 138. 2026-07-04 review guidance pending created_at prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.created_at` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`, `decision_state`, `selected_asset_id`, `recommendation_id`는 이미 canonicalize하고 있었지만 `created_at`는 raw 문자열 그대로 두고 있어, whitespace stale created_at 값이 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_created_at_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'created_at': ' 2026-07-04T00:00:00+00:00 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `created_at`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 created-at surface가 approve/output 쪽 recommendation metadata truth와 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 created-at surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `12 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt created-at trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.created_at`도 trimmed timestamp로 surface한다
2. operator guidance prompt가 raw padded created_at 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 created-at surface가 approve/output 쪽 recommendation metadata 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 139. 2026-07-04 review guidance pending selected asset uri prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 review guidance prompt의 `pending_recommendations.payload.selected_asset_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 top-level `recommendation_type`, `target_segment_id`, `reason`, `decision_state`, `selected_asset_id`, `recommendation_id`, `created_at`는 이미 canonicalize하고 있었지만 nested `payload.selected_asset_uri`는 raw 문자열 그대로 두고 있어, whitespace stale asset uri가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_uri': ' local://projects/project_001/assets/generated/asset_tts_001.wav '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 dict `payload.selected_asset_uri`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 selected-asset-uri surface가 TTS approval/output 쪽 canonical selected asset uri 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 nested selected-asset-uri surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `13 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt nested selected-asset-uri trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.payload.selected_asset_uri`도 trimmed asset uri로 surface한다
2. operator guidance prompt가 raw padded selected asset uri 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 selected-asset-uri surface가 TTS approval/output 쪽 canonical asset uri 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 140. 2026-07-04 output operator copy pending recommendation type prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.recommendation_type` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `review_status`와 `track_type`는 이미 canonicalize하고 있었지만 `pending_recommendations`는 raw dict list를 그대로 프롬프트에 넣고 있어, legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale recommendation type이 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'recommendation_type': ' TTS_REPLACEMENT '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_build_prompt(...)` 안에서 prompt용 `pending_recommendations` summary를 따로 만들고 `recommendation_type`만 canonical lowercase로 정리하도록 맞춰, output operator copy prompt의 recommendation-type surface가 review guidance 및 output truth와 같은 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 recommendation-type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt recommendation-type canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 mixed-case stale `pending_recommendations.recommendation_type`도 canonical lowercase type으로 surface한다
2. preview/export guidance prompt가 raw padded recommendation type 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 recommendation-type surface가 review guidance 및 output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 141. 2026-07-04 output operator copy pending target segment prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.target_segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice에서 `pending_recommendations.recommendation_type`은 canonicalize하게 됐지만 `target_segment_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale segment id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_target_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'target_segment_id': ' seg_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `target_segment_id`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 segment-id surface가 review guidance 및 output truth와 같은 canonical segment id 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 target-segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt target-segment-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.target_segment_id`도 trimmed segment id로 surface한다
2. preview/export guidance prompt가 raw padded target segment id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 target-segment-id surface가 review guidance 및 output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 142. 2026-07-04 output operator copy pending reason prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.reason` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`과 `target_segment_id`는 정리됐지만 `reason`은 여전히 raw 문자열 그대로 넣고 있어, whitespace stale recommendation reason이 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_reason_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'reason': ' Select narration asset '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `reason`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 recommendation-reason surface가 review guidance 및 output truth와 같은 canonical reason 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 reason surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt reason trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.reason`도 trimmed reason으로 surface한다
2. preview/export guidance prompt가 raw padded recommendation reason 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 recommendation-reason surface가 review guidance 및 output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 143. 2026-07-04 output operator copy pending selected asset prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.selected_asset_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`은 정리됐지만 `selected_asset_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale asset id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_id': ' asset_tts_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `selected_asset_id`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 selected-asset-id surface가 review guidance 및 TTS/output truth와 같은 canonical asset id 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 selected-asset-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt selected-asset-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.selected_asset_id`도 trimmed asset id로 surface한다
2. preview/export guidance prompt가 raw padded selected asset id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 selected-asset-id surface가 review guidance 및 TTS/output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 144. 2026-07-04 output operator copy pending recommendation id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.recommendation_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`, `selected_asset_id`는 정리됐지만 `recommendation_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale recommendation id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'recommendation_id': ' rec_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `recommendation_id`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 recommendation-id surface가 approve/output 쪽 canonical recommendation identity 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 recommendation-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt recommendation-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.recommendation_id`도 trimmed recommendation id로 surface한다
2. preview/export guidance prompt가 raw padded recommendation id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 recommendation-id surface가 approve/output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 145. 2026-07-04 output operator copy pending created_at prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.created_at` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`, `selected_asset_id`, `recommendation_id`는 정리됐지만 `created_at`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale created_at 값이 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_created_at_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'created_at': ' 2026-07-04T00:00:00+00:00 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `created_at`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 created-at surface가 approve/output 쪽 recommendation metadata truth와 같은 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 created-at surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt created-at trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.created_at`도 trimmed timestamp로 surface한다
2. preview/export guidance prompt가 raw padded created_at 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 created-at surface가 approve/output metadata truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 146. 2026-07-04 output operator copy pending selected asset uri prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.payload.selected_asset_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 top-level pending recommendation fields는 대부분 정리됐지만 nested `payload.selected_asset_uri`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale asset uri가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_uri': ' local://projects/project_001/assets/generated/asset_tts_001.wav '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 dict `payload.selected_asset_uri`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 selected-asset-uri surface가 TTS approval/output 쪽 canonical selected asset uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 nested selected-asset-uri surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt nested selected-asset-uri trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.payload.selected_asset_uri`도 trimmed asset uri로 surface한다
2. preview/export guidance prompt가 raw padded selected asset uri 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 selected-asset-uri surface가 TTS approval/output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 147. 2026-07-05 review snapshot legacy blocked guidance reuse closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 `blocked` review snapshot guidance 재사용 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `get_review_snapshot(...)`는 persisted `operator_guidance`가 있고 canonical `review_status`만 같으면 그대로 재사용하고 있어, `blocked` 상태에서 blocker surface가 달라져도 legacy guidance를 그대로 노출하고 있었다
- strict TDD로 `test_review_snapshot_ignores_legacy_blocked_persisted_guidance_when_blocker_surface_changes` exact regression을 먼저 추가했고, 실제로 stale `"Legacy blocked guidance."`가 그대로 반환되는 RED를 확인했다
- 최소 수정으로 blocked snapshot에 한해 canonical `review_flags`/pending blocker surface 기반 hidden reuse key를 만들고, `packages/storage-abstractions/src/videobox_storage/local_project_store.py`에 `_operator_guidance_reuse_key`를 저장해 같은 blocked 상태라도 blocker surface가 바뀌면 guidance를 다시 계산하도록 맞췄다
- legacy blocked guidance처럼 reuse key가 없는 persisted guidance는 blocked 상태에서 더 이상 자동 재사용하지 않지만, 기존 `draft/approved` guidance 재사용 계약은 그대로 유지했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 blocked guidance 재사용 조건 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot blocked guidance 재사용 조건 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot이 legacy blocked persisted guidance를 blocker surface가 달라진 상태에서 그대로 재사용하지 않는다
2. blocked guidance 재사용은 같은 `review_status`뿐 아니라 같은 canonical blocker surface일 때만 허용된다
3. legacy no-key blocked guidance는 stale blocker truth를 덮어쓰지 않고 현재 `review_flags`/pending blocker 기준 guidance를 다시 만든다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 148. 2026-07-05 output operator copy ignores stale non-dict review flag prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale non-dict `review_flags` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `review_flags`를 모두 dict라고 가정하고 `dict(flag)`를 바로 호출하고 있어, stale 문자열 같은 non-dict review flag entry 하나만 있어도 preview/export operator copy prompt 생성이 `ValueError`로 깨지고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_non_dict_review_flags_in_prompt` exact regression을 먼저 추가했고, 실제로 `dictionary update sequence element #0 has length 1; 2 is required` RED를 확인했다
- 최소 수정으로 prompt `review_flags` 루프에서 dict가 아닌 entry를 건너뛰도록만 맞춰, valid review flag surface는 그대로 유지하면서 stale non-dict entry가 prompt 생성을 깨지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale review-flag input 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale non-dict review-flag input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 stale non-dict `review_flags` entry 하나 때문에 예외로 중단되지 않는다
2. preview/export guidance prompt는 valid review flag surface만 유지하고 junk input은 건너뛴다
3. review/output gating 인접 prompt surface가 preflight/runtime 쪽 stale-shape 방어 방향과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 149. 2026-07-05 output operator copy ignores stale non-dict pending recommendation prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale non-dict `pending_recommendations` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `pending_recommendations`를 모두 dict라고 가정하고 `dict(item)`를 바로 호출하고 있어, stale 문자열 같은 non-dict pending recommendation entry 하나만 있어도 preview/export operator copy prompt 생성이 `ValueError`로 깨지고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_non_dict_pending_recommendations_in_prompt` exact regression을 먼저 추가했고, 실제로 `dictionary update sequence element #0 has length 1; 2 is required` RED를 확인했다
- 최소 수정으로 prompt `pending_recommendations` 루프에서 dict가 아닌 entry를 건너뛰도록만 맞춰, valid recommendation surface는 그대로 유지하면서 stale non-dict entry가 prompt 생성을 깨지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale pending-recommendation input 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale non-dict pending-recommendation input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 stale non-dict `pending_recommendations` entry 하나 때문에 예외로 중단되지 않는다
2. preview/export guidance prompt는 valid recommendation surface만 유지하고 junk input은 건너뛴다
3. review/output gating 인접 prompt surface가 stale review-flag input 방어와 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 150. 2026-07-05 output operator copy ignores stale minimal pending recommendation prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale minimal-dict `pending_recommendations` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 dict 여부만 통과하면 prompt `pending_recommendations`에 그대로 올리고 있어, `recommendation_id`나 `target_segment_id`, canonical `recommendation_type` 없이 남은 stale minimal-dict entry도 valid recommendation처럼 operator prompt에 섞여 들어가고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `rec_stale_minimal` entry가 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 prompt `pending_recommendations` summary를 만들 때 canonical `recommendation_id`, `target_segment_id`, supported `recommendation_type`가 모두 있는 entry만 유지하도록 좁혀, stale minimal-dict input은 건너뛰고 valid recommendation surface만 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale minimal pending-recommendation 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale minimal pending-recommendation input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 `recommendation_id`나 `target_segment_id` 없이 남은 stale minimal-dict `pending_recommendations` entry를 valid recommendation처럼 노출하지 않는다
2. preview/export guidance prompt는 canonical recommendation identity와 supported type을 가진 valid pending recommendation surface만 유지한다
3. review/output gating 인접 prompt surface가 stale non-dict input 방어 다음 단계까지 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 151. 2026-07-05 output operator copy ignores stale minimal review flag prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale minimal-dict `review_flags` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 dict 여부만 통과하면 prompt `review_flags`에 그대로 올리고 있어, `segment_id` 없이 `code`만 남은 stale minimal-dict blocker도 valid review flag처럼 operator prompt에 섞여 들어가고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_minimal_dict_review_flags_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `segment_review_required` entry가 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 prompt `review_flags` summary를 만들 때 supported blocker `code`와 canonical `segment_id`가 모두 있는 entry만 유지하도록 좁혀, stale minimal-dict input은 건너뛰고 valid blocker surface만 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale minimal review-flag 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale minimal review-flag input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 `segment_id` 없이 남은 stale minimal-dict `review_flags` entry를 valid blocker처럼 노출하지 않는다
2. preview/export guidance prompt는 canonical blocker identity와 supported code를 가진 valid review flag surface만 유지한다
3. review/output gating 인접 prompt surface가 stale minimal pending-recommendation 입력 방어와 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 152. 2026-07-05 output operator copy ignores stale non-dict track prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale non-dict `tracks` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `tracks`를 모두 dict라고 가정한 list comprehension으로 summary를 만들고 있어, stale 문자열 같은 non-dict track entry 하나만 있어도 preview/export operator copy prompt 생성이 `AttributeError`로 깨지고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_non_dict_tracks_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `stale_track_entry` 때문에 `AttributeError: 'str' object has no attribute 'get'` RED를 확인했다
- 최소 수정으로 track summary loop에서 dict가 아닌 entry를 건너뛰도록만 맞춰, valid track summary surface는 그대로 유지하면서 stale non-dict track entry가 prompt 생성을 깨지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale track input 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale non-dict track input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 stale non-dict `tracks` entry 하나 때문에 예외로 중단되지 않는다
2. preview/export guidance prompt는 valid track summary surface만 유지하고 junk track input은 건너뛴다
3. review/output gating 인접 prompt surface가 track summary 입력면까지 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 153. 2026-07-05 output operator copy ignores stale minimal track prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale minimal-dict `tracks` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 dict인 `track`이면 모두 summary에 올리고 있어, `track_type` 없이 남은 stale minimal-dict entry도 빈 `track_type`과 `clip_count=0`인 track summary처럼 operator prompt에 섞여 들어가고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_minimal_dict_tracks_in_prompt` exact regression을 먼저 추가했고, 실제로 stale minimal track 때문에 `"'track_type': ''"`가 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 track summary loop에서 canonical `track_type`가 있는 entry만 유지하도록 좁혀, stale minimal-dict track은 건너뛰고 valid track summary surface만 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale minimal track 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale minimal track input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 `track_type` 없이 남은 stale minimal-dict `tracks` entry를 빈 track summary처럼 노출하지 않는다
2. preview/export guidance prompt는 canonical `track_type`를 가진 valid track summary surface만 유지한다
3. review/output gating 인접 prompt surface가 track summary의 non-dict 입력 방어 다음 단계까지 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 154. 2026-07-05 output operator copy ignores stale non-list track clips prompt entry closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 stale non-list `tracks[].clips` 입력 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 valid track이라면 `len(track.get("clips", []))`를 그대로 써서 summary를 만들고 있어, `clips`가 stale 문자열이면 실제 clip 개수 대신 문자열 길이만큼 `clip_count`를 잘못 노출하고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_non_list_track_clips_in_prompt` exact regression을 먼저 추가했고, 실제로 stale `"stale_clip_container"` 때문에 `"'clip_count': 20"`이 prompt 본문에 그대로 남는 RED를 확인했다
- 최소 수정으로 track summary loop에서 `clips`가 list인 entry만 유지하도록 좁혀, stale non-list clip container는 건너뛰고 valid track summary surface만 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 stale track-clips 입력 경계 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 stale non-list track-clips input 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 stale non-list `tracks[].clips` 값을 실제 clip count처럼 노출하지 않는다
2. preview/export guidance prompt는 list 기반으로 계산된 valid track summary surface만 유지한다
3. review/output gating 인접 prompt surface가 track summary의 non-dict/minimal-dict 방어 다음 단계까지 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 155. 2026-07-06 timeline summary ignores unknown review flag count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 persisted timeline summary의 stale unknown `review_flags` count 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)` / `update_timeline_run(...)`는 summary JSON의 `review_flag_count`를 raw list 길이로 저장하고 있어, unknown `review_flags.code`를 가진 junk entry도 valid blocker처럼 count를 부풀리고 있었다
- strict TDD로 `test_save_timeline_run_summary_ignores_unknown_review_flag_count` exact regression을 먼저 추가했고, 실제로 persisted summary의 `review_flag_count == 2` RED를 확인했다
- 최소 수정으로 `_timeline_summary_json(...)` helper를 추가해 summary `review_flag_count`도 canonical blocking review flag 기준으로 계산하도록 맞춰, valid blocker count만 persisted summary에 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline summary review-flag count 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - storage/read 인접 exact 묶음 `4 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline summary review-flag count 한 점 수정이라 exact + storage/read 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. persisted timeline summary가 unknown `review_flags.code` junk entry를 valid blocker count처럼 저장하지 않는다
2. summary `review_flag_count`가 actual blocking review flag 기준과 같은 방향을 사용한다
3. persistence summary count도 최근 review guidance prompt count hardening과 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 156. 2026-07-06 timeline summary ignores unknown pending recommendation count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 persisted timeline summary의 stale unknown `pending_recommendations` count 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_timeline_summary_json(...)`는 summary JSON의 `pending_recommendation_count`를 raw list 길이로 저장하고 있어, unknown `recommendation_type`를 가진 junk entry도 valid pending blocker처럼 count를 부풀리고 있었다
- strict TDD로 `test_save_timeline_run_summary_ignores_unknown_pending_recommendation_count` exact regression을 먼저 추가했고, 실제로 persisted summary의 `pending_recommendation_count == 1` RED를 확인했다
- 최소 수정으로 `_timeline_summary_json(...)` 안의 `pending_recommendation_count`도 canonical blocking pending recommendation 기준으로 계산하도록 맞춰, valid pending blocker count만 persisted summary에 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline summary pending-recommendation count 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - storage/read 인접 exact 묶음 `5 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline summary pending-recommendation count 한 점 수정이라 exact + storage/read 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. persisted timeline summary가 unknown `recommendation_type` junk entry를 valid pending blocker count처럼 저장하지 않는다
2. summary `pending_recommendation_count`가 actual blocking pending recommendation 기준과 같은 방향을 사용한다
3. persistence summary count도 최근 review flag count hardening과 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 157. 2026-07-06 review guidance broll review flag closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 canonical blocker allowlist 누락 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 canonical review-flag allowlist에는 `broll_review_required`가 빠져 있어, store/output gating이 blocker로 보는 B-roll review flag가 heuristic review guidance에서는 무시되고 approved guidance로 빠지고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_treats_broll_review_required_as_blocking` exact regression을 먼저 추가했고, 실제로 `Timeline review is approved and outputs can be generated.` RED를 확인했다
- 최소 수정으로 review guidance와 output operator copy prompt의 canonical review-flag allowlist에 `broll_review_required`를 추가해, B-roll review blocker도 다른 canonical blocker와 같은 기준으로 guidance에 반영되게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review/output consumer의 canonical review-flag allowlist 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / output operator copy 인접 exact 묶음 `7 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - canonical blocker allowlist 한 점 수정이라 exact + review guidance 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. canonical `broll_review_required` blocker가 heuristic review guidance에서 approved guidance로 잘못 빠지지 않는다
2. review guidance와 output operator copy prompt가 같은 canonical review-flag allowlist 기준을 사용한다
3. review/output gating 인접 guidance consumer가 store/output gating의 blocker truth와 더 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 158. 2026-07-06 timeline summary ignores unknown track count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 persisted timeline summary의 stale unknown `tracks` count 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_timeline_summary_json(...)`는 summary JSON의 `track_count`를 raw list 길이로 저장하고 있어, unknown `track_type`를 가진 junk entry도 valid runtime track처럼 count를 부풀리고 있었다
- strict TDD로 `test_save_timeline_run_summary_ignores_unknown_track_count` exact regression을 먼저 추가했고, 실제로 persisted summary의 `track_count == 2` RED를 확인했다
- 최소 수정으로 `_timeline_summary_json(...)` 안의 `track_count`도 canonical runtime `track_type` 기준으로 계산하도록 맞춰, valid runtime track count만 persisted summary에 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline summary track count 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - storage/read 인접 exact 묶음 `4 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline summary track count 한 점 수정이라 exact + storage/read 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. persisted timeline summary가 unknown `track_type` junk entry를 valid runtime track count처럼 저장하지 않는다
2. summary `track_count`가 actual runtime-supported track 기준과 같은 방향을 사용한다
3. persistence summary count도 최근 review flag / pending recommendation count hardening과 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 159. 2026-07-06 timeline summary ignores unknown applied recommendation count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 persisted timeline summary의 stale unknown `applied_recommendations` count 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_timeline_summary_json(...)`는 summary JSON의 `applied_recommendation_count`를 raw list 길이로 저장하고 있어, unknown `recommendation_type`를 가진 junk applied recommendation도 valid runtime recommendation처럼 count를 부풀리고 있었다
- strict TDD로 `test_save_timeline_run_summary_ignores_unknown_applied_recommendation_count` exact regression을 먼저 추가했고, 실제로 persisted summary의 `applied_recommendation_count == 2` RED를 확인했다
- 최소 수정으로 `_timeline_summary_json(...)` 안의 `applied_recommendation_count`도 canonical runtime recommendation type 기준으로 계산하도록 맞춰, valid runtime recommendation count만 persisted summary에 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline summary applied recommendation count 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - storage/read 인접 exact 묶음 `5 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline summary applied recommendation count 한 점 수정이라 exact + storage/read 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. persisted timeline summary가 unknown `recommendation_type` junk applied recommendation을 valid runtime recommendation count처럼 저장하지 않는다
2. summary `applied_recommendation_count`가 actual runtime-supported recommendation 기준과 같은 방향을 사용한다
3. persistence summary count도 최근 review flag / pending / track count hardening과 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 160. 2026-07-06 capcut export metadata ignores unknown track count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 CapCut export metadata의 stale unknown `tracks` count 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_capcut_export(...)`는 export metadata JSON의 `track_count`를 raw list 길이로 저장하고 있어, unknown `track_type`를 가진 junk entry도 valid runtime export track처럼 count를 부풀리고 있었다
- strict TDD로 `test_save_capcut_export_metadata_ignores_unknown_track_count` exact regression을 먼저 추가했고, 실제로 persisted export metadata의 `track_count == 2` RED를 확인했다
- 최소 수정으로 export metadata의 `track_count`도 canonical runtime `track_type` 기준으로 계산하도록 맞춰, valid runtime export track count만 persisted metadata에 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export metadata track count 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - storage/output 인접 exact 묶음 `4 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - export metadata track count 한 점 수정이라 exact + storage/output 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export metadata가 unknown `track_type` junk entry를 valid runtime export track count처럼 저장하지 않는다
2. export metadata `track_count`가 actual runtime-supported track 기준과 같은 방향을 사용한다
3. persisted export metadata count도 최근 timeline summary track count hardening과 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 161. 2026-07-06 preview summary ignores unknown track clip group count closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 preview summary의 stale unknown `clips` track-group count 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_preview_run(...)`는 preview summary JSON의 `clip_group_count`를 raw list 길이로 저장하고 있어, unknown `track_type`를 가진 junk clip-group entry도 valid runtime preview track-group처럼 count를 부풀리고 있었다
- strict TDD로 `test_save_preview_run_summary_ignores_unknown_track_clip_group_count` exact regression을 먼저 추가했고, 실제로 persisted preview summary의 `clip_group_count == 2` RED를 확인했다
- 최소 수정으로 preview summary의 `clip_group_count`도 canonical runtime `track_type` 기준으로 계산하도록 맞춰, valid runtime preview track-group count만 persisted summary에 남기게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview summary clip-group count 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - storage/output 인접 exact 묶음 `4 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview summary clip-group count 한 점 수정이라 exact + storage/output 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview summary가 unknown `track_type` junk clip-group entry를 valid runtime preview track-group count처럼 저장하지 않는다
2. preview summary `clip_group_count`가 actual runtime-supported track 기준과 같은 방향을 사용한다
3. persisted preview summary count도 최근 timeline/export track count hardening과 같은 stale-shape 방어 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 162. 2026-07-06 output operator copy ignores approved pending recommendation prompt entries closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 stale applied-like `pending_recommendations` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `pending_recommendations`를 canonical identity만 맞으면 그대로 prompt에 싣고 있어, `decision_state="approved"`이거나 `auto_apply_allowed=true` / `review_required=false`인 stale applied-like entry도 pending blocker처럼 노출하고 있었다
- strict TDD로 `test_output_operator_copy_builder_ignores_approved_decision_state_pending_recommendations_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt 안에 `rec_approved`가 남는 RED를 확인했다
- 최소 수정으로 `_is_prompt_blocking_pending_recommendation(...)` helper를 추가해 approved/applied-like stale entry를 prompt surface에서 걸러내고, 실제 pending blocker identity만 남기도록 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 pending blocker filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 pending blocker filtering 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 이미 승인된 stale pending recommendation entry를 pending blocker처럼 노출하지 않는다
2. output operator copy prompt가 legacy applied-like `auto_apply_allowed=true` / `review_required=false` entry도 pending blocker surface에서 제외한다
3. preview/export guidance prompt의 pending blocker 기준이 output job/read truth와 같은 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 163. 2026-07-06 heuristic review guidance ignores approved pending recommendation entries closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 heuristic review guidance의 stale applied-like `pending_recommendations` blocker 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder.build(...)`와 `_prompt_pending_recommendations(...)`는 `pending_recommendations`를 canonical identity만 맞으면 그대로 blocker로 취급하고 있어, `decision_state="approved"`이거나 `auto_apply_allowed=true` / `review_required=false`인 stale applied-like entry도 blocked guidance로 뒤집고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_ignores_approved_decision_state_pending_recommendation` exact regression을 먼저 추가했고, 실제로 summary가 `Review is blocked until the flagged items are resolved.`로 남는 RED를 확인했다
- 최소 수정으로 `_is_prompt_blocking_pending_recommendation(...)` helper를 추가해 approved/applied-like stale entry를 heuristic guidance와 prompt surface 양쪽에서 함께 걸러내고, 실제 pending blocker identity만 남기도록 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance의 pending blocker filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic review guidance의 pending blocker filtering 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance가 이미 승인된 stale pending recommendation entry 때문에 approved guidance를 blocked로 뒤집지 않는다
2. heuristic review guidance와 prompt surface가 legacy applied-like `auto_apply_allowed=true` / `review_required=false` entry도 pending blocker에서 제외한다
3. review guidance의 pending blocker 기준이 output job/read truth 및 output operator copy와 같은 방향으로 더 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 164. 2026-07-06 review guidance reuse key ignores approved pending recommendation entries closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance persisted reuse key의 stale applied-like `pending_recommendations` hidden blocker 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_build_review_guidance_reuse_key(...)`는 `pending_recommendations`를 canonical identity만 맞으면 hidden reuse key에 그대로 넣고 있어, `decision_state="approved"`이거나 `auto_apply_allowed=true` / `review_required=false`인 stale applied-like entry도 현재 blocker truth처럼 섞고 있었다
- strict TDD로 `test_review_guidance_reuse_key_ignores_approved_pending_recommendation_entries` exact regression을 먼저 추가했고, 실제로 stale snapshot reuse key가 canonical snapshot reuse key와 달라지는 RED를 확인했다
- 최소 수정으로 `_build_review_guidance_reuse_key(...)`가 hidden pending blocker key 구성에도 `_is_runtime_blocking_pending_recommendation(...)`를 재사용하도록 맞춰, approved/applied-like stale entry를 reuse key에서 제외하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance reuse key의 hidden pending blocker filtering 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance reuse key의 hidden blocker filtering 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance persisted reuse key가 이미 승인된 stale pending recommendation entry를 hidden blocker truth로 섞지 않는다
2. review guidance persisted reuse key가 legacy applied-like `auto_apply_allowed=true` / `review_required=false` entry도 hidden blocker surface에서 제외한다
3. persisted guidance reuse 조건이 current blocker truth와 heuristic/operator guidance filtering 기준에 더 맞게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 165. 2026-07-06 review guidance reuse key skips empty blocked blocker surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance persisted reuse key의 empty blocked blocker surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_build_review_guidance_reuse_key(...)`는 `review_status="blocked"`면 실제 blocker가 하나도 없어도 `{"review_flags":[],"pending_recommendations":[],"review_status":"blocked"}` 빈 hidden key를 만들고 있었다
- strict TDD로 `test_review_guidance_reuse_key_returns_none_when_blocked_status_has_no_actual_blockers` exact regression을 먼저 추가했고, 실제로 empty blocked key string이 반환되는 RED를 확인했다
- 최소 수정으로 `_build_review_guidance_reuse_key(...)`가 filtered blocker surface가 둘 다 비면 `None`을 반환하도록 맞춰, blocker 없는 stale blocked 상태가 예전 blocked guidance 재사용 키를 만들지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance reuse key의 empty blocked surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance reuse key의 empty blocked surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance persisted reuse key가 blocker 없는 stale blocked 상태에 대해 빈 blocked key를 만들지 않는다
2. blocker가 없는 상태에서 예전 blocked guidance를 재사용할 hidden key 조건이 더 줄었다
3. persisted guidance reuse 조건이 actual blocker surface 기준과 더 일치하게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 166. 2026-07-06 review guidance reuse key dedupes duplicate blocker entries closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance persisted reuse key의 duplicate blocker entry 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_build_review_guidance_reuse_key(...)`는 canonical blocker detail이 같은 duplicate `review_flags`/`pending_recommendations` entry도 그대로 hidden key에 넣고 있어, blocker truth는 같은데 stale duplicate entry 때문에 다른 reuse key를 만들고 있었다
- strict TDD로 `test_review_guidance_reuse_key_dedupes_duplicate_blocker_entries` exact regression을 먼저 추가했고, 실제로 stale snapshot reuse key가 canonical snapshot reuse key와 달라지는 RED를 확인했다
- 최소 수정으로 `_build_review_guidance_reuse_key(...)`가 canonicalized `review_flags`와 `pending_recommendations`를 각각 dedupe한 뒤 hidden blocker key를 만들도록 맞춰, duplicate stale entry를 reuse key에서 제외하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance reuse key의 duplicate blocker dedupe 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance reuse key의 duplicate blocker dedupe 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance persisted reuse key가 canonical blocker detail이 같은 duplicate `review_flags` entry를 hidden blocker truth에 중복 반영하지 않는다
2. review guidance persisted reuse key가 canonical blocker detail이 같은 duplicate `pending_recommendations` entry도 hidden blocker surface에서 한 번만 반영한다
3. persisted guidance reuse 조건이 actual blocker truth 기준 dedupe 방향과 더 일치하게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 167. 2026-07-06 review guidance reuse key fills default review-flag message closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance persisted reuse key의 message 없는 valid `review_flags` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_build_review_guidance_reuse_key(...)`는 valid `review_flags`의 `message`를 raw trim 결과로만 hidden key에 넣고 있어, canonical default blocker message가 채워진 snapshot과 message가 비어 있는 stale snapshot이 같은 blocker truth인데도 다른 reuse key를 만들고 있었다
- strict TDD로 `test_review_guidance_reuse_key_fills_default_review_flag_message` exact regression을 먼저 추가했고, 실제로 stale snapshot reuse key가 canonical snapshot reuse key와 달라지는 RED를 확인했다
- 최소 수정으로 `_build_review_guidance_reuse_key(...)`가 review-flag message를 canonical default blocker message 기준으로 정리한 뒤 hidden blocker key를 만들도록 맞춰, 빈 message stale entry도 reuse key에서 같은 blocker truth로 취급하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance reuse key의 review-flag default-message canonicalization 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance reuse key의 review-flag default-message canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance persisted reuse key가 message 없는 valid `review_flags`를 canonical default blocker message 기준으로 정리한다
2. review guidance persisted reuse key가 API/read-path와 같은 blocker truth인데 raw 빈 message 때문에 다른 hidden key를 만들지 않는다
3. persisted guidance reuse 조건이 review-flag default-message canonical surface와 더 일치하게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 168. 2026-07-06 review guidance reuse key fills default pending recommendation reason closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance persisted reuse key의 reason 없는 valid `pending_recommendations` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_build_review_guidance_reuse_key(...)`는 valid `pending_recommendations`의 `reason`을 raw trim 결과로만 hidden key에 넣고 있어, canonical default blocker message가 채워진 snapshot과 reason이 비어 있는 stale snapshot이 같은 blocker truth인데도 다른 reuse key를 만들고 있었다
- strict TDD로 `test_review_guidance_reuse_key_fills_default_pending_recommendation_reason` exact regression을 먼저 추가했고, 실제로 stale snapshot reuse key가 canonical snapshot reuse key와 달라지는 RED를 확인했다
- 최소 수정으로 `_build_review_guidance_reuse_key(...)`가 pending recommendation reason을 canonical default blocker message 기준으로 정리한 뒤 hidden blocker key를 만들도록 맞춰, 빈 reason stale entry도 reuse key에서 같은 blocker truth로 취급하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance reuse key의 pending-recommendation default-reason canonicalization 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance reuse key의 pending-recommendation default-reason canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance persisted reuse key가 reason 없는 valid `pending_recommendations`를 canonical default blocker message 기준으로 정리한다
2. review guidance persisted reuse key가 API/read-path와 같은 blocker truth인데 raw 빈 reason 때문에 다른 hidden key를 만들지 않는다
3. persisted guidance reuse 조건이 pending-recommendation default-reason canonical surface와 더 일치하게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 169. 2026-07-06 review guidance reuse key trims persisted stored key whitespace closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance persisted reuse key read-path의 stored whitespace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_operator_guidance_reuse_key(...)`는 stored `_operator_guidance_reuse_key`를 raw string 그대로 반환하고 있어, legacy 파일에 공백이 섞인 stale key가 남아 있으면 current blocker truth와 같은 key여도 persisted guidance를 재사용하지 못하고 다시 생성하고 있었다
- strict TDD로 `test_review_snapshot_reuses_persisted_guidance_when_stored_reuse_key_has_whitespace` exact regression을 먼저 추가했고, 실제로 두 번째 review snapshot이 persisted guidance 대신 새 guidance를 다시 생성하는 RED를 확인했다
- 최소 수정으로 `get_operator_guidance_reuse_key(...)`가 stored key도 `strip()` 기준으로 정리한 뒤 반환하도록 맞춰, whitespace-only drift가 있는 stale key도 current hidden key와 같은 기준으로 비교하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance persisted reuse key read-path trim 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance persisted reuse key read-path trim 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. persisted `_operator_guidance_reuse_key`에 공백이 섞인 stale 파일 shape도 trim 기준으로 읽힌다
2. blocker truth가 같은데 stored key whitespace 때문에 guidance를 다시 생성하던 경로가 줄었다
3. persisted guidance reuse read-path가 save-path와 같은 key normalization 기준으로 더 일치하게 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 170. 2026-07-06 recommendation response normalization trims payload selected asset uri closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 API response normalization의 nested `payload.selected_asset_uri` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 recommendation 바깥 필드만 trim/canonicalize하고 dict `payload.selected_asset_uri`는 raw 값 그대로 내보내고 있어, whitespace가 섞인 stale selected asset uri가 recommendation/timeline/review snapshot API response에서 그대로 노출되고 있었다
- strict TDD로 `test_recommendation_response_normalization_trims_payload_selected_asset_uri` exact regression을 먼저 추가했고, 실제로 normalized response의 `payload.selected_asset_uri`가 padded/raw 문자열 그대로 남는 RED를 확인했다
- 최소 수정으로 `_normalize_recommendations_for_response(...)`가 dict payload를 복사한 뒤 `selected_asset_uri`도 `strip()` 기준으로 정리하도록 맞춰, API response surface가 canonical selected asset uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation response normalization의 nested selected-asset-uri 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation response normalization의 nested selected-asset-uri 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation/timeline/review snapshot API response의 `payload.selected_asset_uri`가 whitespace stale shape여도 canonical trimmed uri를 유지한다
2. TTS approval/output read surface가 prompt/read-path 쪽 selected asset uri canonicalization 흐름과 더 일치하게 정렬됐다
3. nested payload field 하나 때문에 review/output read truth가 raw stale 문자열을 다시 노출하던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 171. 2026-07-06 preview renderer trims tts narration source uri surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 preview renderer의 narration source URI surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 `_effective_narration_source_uri(...)`는 approved TTS segment에 대해 clip `asset_uri`를 raw 문자열 그대로 내보내고 있어, whitespace가 섞인 stale selected narration asset uri가 preview HTML의 visible narration source surface에 그대로 노출되고 있었다
- strict TDD로 `test_preview_renderer_trims_tts_narration_source_uri_surface` exact regression을 먼저 추가했고, 실제로 preview HTML이 `seg_001:  local://...tts_selected.wav `처럼 padded/raw URI를 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer가 narration source URI도 `strip()` 기준으로 정리해 내보내도록 맞춰, preview visible surface가 canonical selected narration uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview renderer의 TTS narration source URI surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 TTS narration source URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved TTS preview visible surface가 whitespace stale `asset_uri`도 canonical trimmed narration source uri로 노출한다
2. TTS approval/output preview surface가 API/prompt 쪽 selected asset uri canonicalization 흐름과 더 일치하게 정렬됐다
3. 실제 approved narration source는 맞는데 visible preview URI만 raw stale 문자열로 보이던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 172. 2026-07-06 partial regeneration runtime fallback ignores non-dict session segments closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 인접한 partial regeneration runtime fallback의 stale non-dict `session segments` 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration(...)`는 source timeline에서 usable segment를 찾지 못해 session fallback으로 내려갈 때 `session["segments"]`의 모든 entry를 dict로 가정하고 `.get(...)`을 호출하고 있었다
- strict TDD로 `test_editing_session_api_ignores_non_dict_session_segments_in_partial_regeneration_fallback` exact regression을 먼저 추가했고, 실제로 partial regeneration start API가 `500 Internal Server Error`로 깨지는 RED를 확인했다
- 최소 수정으로 `_execute_partial_regeneration(...)`의 `session_segments` lookup과 fallback `source_segments` list comprehension이 `dict`가 아닌 stale entry를 먼저 건너뛰도록 맞춰, runtime fallback이 canonical session segment만 기준으로 계속 동작하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime fallback의 stale session-segment read path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration runtime adjacent slice `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime fallback의 stale non-dict session-segment read path 한 점 수정이라 exact + adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime이 source timeline에서 usable segment를 찾지 못해 session fallback으로 내려가도 stale non-dict `session["segments"]` entry 때문에 500으로 깨지지 않는다
2. runtime fallback source-segment 구성은 canonical dict session segment만 기준으로 계속 동작한다
3. preflight fallback과 runtime fallback이 stale non-dict session-segment 방어 기준에서 같은 방향으로 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 173. 2026-07-06 output operator copy prompt defaults missing pending recommendation reason closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 reason 없는 valid `pending_recommendations` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 valid pending recommendation을 prompt row로 옮길 때 `reason`이 있는 경우에만 trim했고, 비어 있거나 없는 경우에는 canonical default blocker message를 채우지 않고 있었다
- strict TDD로 `test_output_operator_copy_builder_defaults_missing_pending_recommendation_reason_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt의 pending recommendation row에 `reason` 필드가 빠진 RED를 확인했다
- 최소 수정으로 output operator copy prompt row가 pending recommendation의 `reason`도 `_canonical_review_flag_message(...)` 기준으로 정리하도록 맞춰, reason 없는 valid blocker도 canonical default blocker message를 surface하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 pending-recommendation default-reason 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - output operator copy prompt adjacent slice `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt의 pending-recommendation default-reason 한 점 수정이라 exact + adjacent focused evidence가 가장 직접적이다
    - `./scripts/dev-fast-path.ps1 -Mode output-gating`와 같은 pattern의 직접 `py -m pytest` broad command는 이번 환경에서 타임아웃이 나서, 이번 범위와 직접 맞닿은 prompt normalization slice로 focused evidence를 다시 확인했다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 reason 없는 valid `pending_recommendations`에도 canonical default blocker message를 surface한다
2. preview/export guidance prompt의 pending blocker reason surface가 review guidance 및 output truth와 같은 기본 blocker 문구 기준으로 정렬됐다
3. valid blocker인데 reason만 비어 있어 prompt surface가 덜 완성된 형태로 남던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 174. 2026-07-06 review guidance prompt defaults missing pending recommendation reason closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 reason 없는 valid `pending_recommendations` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 valid pending recommendation을 prompt row로 옮길 때 `reason`이 있는 경우에만 trim했고, 비어 있거나 없는 경우에는 canonical default blocker message를 채우지 않고 있었다
- strict TDD로 `test_review_guidance_builder_defaults_missing_pending_recommendation_reason_in_prompt` exact regression을 먼저 추가했고, 실제로 review guidance prompt의 pending recommendation row에 `reason` 필드가 빠진 RED를 확인했다
- 최소 수정으로 review guidance prompt row가 pending recommendation의 `reason`도 `_canonical_review_flag_message(...)` 기준으로 정리하도록 맞춰, reason 없는 valid blocker도 canonical default blocker message를 surface하게 정리했다
- focused verification 중 예전 `test_review_guidance_builder_canonicalizes_pending_recommendation_decision_state_in_prompt`가 현재 SSOT와 어긋나 있음을 같이 확인했고, 현재 계약인 applied-like approved entry non-blocking 규칙에 맞게 `test_review_guidance_builder_ignores_approved_decision_state_pending_recommendation_in_prompt`로 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 pending-recommendation default-reason surface와 인접 stale test mismatch 한 점만 좁게 정리했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt adjacent slice `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 pending-recommendation default-reason 한 점 수정이라 exact + adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 reason 없는 valid `pending_recommendations`에도 canonical default blocker message를 surface한다
2. operator guidance prompt의 pending blocker reason surface가 heuristic fallback 및 API response 쪽 default blocker 문구 기준과 더 일치하게 정렬됐다
3. stale approved-like pending entry를 blocker처럼 싣는 예전 test expectation도 현재 SSOT에 맞게 정리됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 175. 2026-07-06 recommendation response normalization filters missing recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 API response normalization의 missing `recommendation_type` stale recommendation surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 `recommendation_id`와 `target_segment_id`만 있으면 recommendation row를 그대로 응답 surface에 남기고 있어, `recommendation_type`이 비어 있는 stale `pending_recommendations`/`applied_recommendations` row도 valid recommendation처럼 recommendation/timeline/review snapshot API response에 그대로 노출되고 있었다
- strict TDD로 `test_recommendation_response_normalization_filters_missing_recommendation_type` exact regression을 먼저 추가했고, 실제로 normalized response helper가 `recommendation_type=""` recommendation row를 그대로 반환하는 RED를 확인했다
- 최소 수정으로 `_normalize_recommendations_for_response(...)`가 canonical lowercase `recommendation_type`를 먼저 계산한 뒤 supported recommendation type 집합에 없으면 row 자체를 건너뛰도록 맞춰, API response surface가 canonical recommendation identity/type/segment 기준만 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation response normalization의 missing recommendation-type filtering 한 점만 좁게 정리했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - recommendation response normalization adjacent slice `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation response normalization의 missing recommendation-type filtering 한 점 수정이라 exact + adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation/timeline/review snapshot API response가 `recommendation_type` 없는 stale recommendation row를 valid recommendation처럼 surface하지 않는다
2. review/output read surface의 valid recommendation 기준이 최근 prompt/decision/preflight 쪽 canonical recommendation identity/type/segment 규칙과 더 일치하게 정렬됐다
3. minimal stale recommendation row 하나 때문에 API read-path가 빈 type recommendation을 다시 노출하던 경로가 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 176. 2026-07-06 output operator copy pending decision-state stale test alignment and broader verification closeout

이번 후속 작업에서는 새 동작 변경을 더 넓히지 않고, `broader` 자동 검증에서 드러난 stale test expectation 1개를 현재 SSOT에 맞게 정리하고 전체 자동 검증 baseline을 다시 확인했다.

이번에 새로 확인된 사실은 아래와 같다.

- `pytest -q` broader 재실행 중 `tests/test_api.py::test_output_operator_copy_builder_canonicalizes_pending_recommendation_decision_state_in_prompt` 1건이 실패했는데, 원인은 현재 worktree의 output operator copy prompt가 `decision_state="approved"` stale pending recommendation을 blocker prompt에서 제외하도록 이미 정리돼 있는데도 예전 테스트가 여전히 `approved` row가 prompt 안에 남아야 한다고 기대하던 점이었다
- 이 경계는 이미 `test_output_operator_copy_builder_ignores_approved_decision_state_pending_recommendations_in_prompt`와 현재 SSOT가 설명하는 applied-like approved entry non-blocking 규칙과 충돌하고 있어, stale expectation을 mixed-case `pending` canonicalization 검증으로 좁혀 `test_output_operator_copy_builder_canonicalizes_pending_decision_state_in_prompt`로 정리했다
- 제품 코드 동작은 바꾸지 않았고, test expectation만 현재 SSOT와 같은 방향으로 맞춘 뒤 exact/focused/broader를 다시 통과시켰다
- 이로써 `current-focused-parallel`과 `broader`가 모두 현재 worktree 기준으로 다시 green이 되었고, Phase A 종료 판단 뒤 Phase B 자동 검증 진입 조건이 충족되는 쪽으로 진전됐다

이번 turn의 verification은 아래와 같다.

- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `59 passed`
  - frontend preflight `25 passed`
- exact regression
  - `test_output_operator_copy_builder_canonicalizes_pending_decision_state_in_prompt` -> `1 passed`
- focused verification
  - output operator copy pending decision-state adjacent slice `4 passed`
- broader verification
  - frontend build 성공
  - full backend regression `543 passed`

이 갱신으로 아래 범위는 현재 기준 정리됐다.

1. output operator copy prompt family의 pending decision-state test expectation이 stale approved-like pending blocker 비노출 SSOT와 같은 방향으로 맞춰졌다
2. 제품 동작을 건드리지 않고도 stale test mismatch 때문에 막히던 broader backend regression이 다시 green으로 돌아왔다
3. 현재 worktree 기준 자동 검증 baseline은 `current-focused-parallel green + frontend build green + full backend regression green`으로 다시 정렬됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 작은 stale-shape exact regression을 더 억지로 찾기보다, Phase B의 전체 동작 검증 / QA / 시스템 검증으로 넘어갈지 판단한다
- 필요하면 provider trace audit focused slice와 happy-path smoke evidence를 추가한다
- 그 뒤 문서 최신화 / 정리 리팩터링 / 찌꺼기 파일 정리 순서로 마감 정리를 진행한다

## 177. 2026-07-06 phase-b happy-path and provider-trace evidence closeout

이번 후속 작업에서는 새 stale-shape slice를 더 열지 않고, `Phase B` 전체 동작 검증과 시스템 검증에 바로 연결되는 대표 happy-path / provider trace audit evidence를 현재 worktree 기준으로 다시 확인했다.

이번에 새로 확인된 사실은 아래와 같다.

- review snapshot approve 흐름은 `test_review_snapshot_api_can_approve_pending_recommendation` 기준으로 계속 동작했고, approve 이후 review snapshot의 pending/applied split과 status 변화가 현재 SSOT와 같은 방향으로 유지됐다
- approved TTS replacement의 preview/export 반영 흐름은 `test_approved_tts_replacement_flows_through_preview_and_export_outputs` 기준으로 계속 동작했고, 승인된 narration asset이 preview/export 쪽 실제 output surface까지 이어지는 사실을 다시 확인했다
- editing session -> partial regeneration -> candidate result 흐름은 `test_editing_session_api_can_fetch_partial_regeneration_result`와 `test_review_snapshot_api_uses_partial_regeneration_job_id_for_candidate_timeline` 기준으로 계속 동작했고, candidate timeline lineage도 review snapshot read path에서 현재 truth를 유지했다
- provider trace audit의 candidate lineage는 `test_provider_trace_audit_timeline_filter_include_upstream_supports_partial_regeneration_candidate` 기준으로 계속 동작했고, partial regeneration candidate timeline에서도 upstream trace chain을 잃지 않는 사실을 다시 확인했다
- frontend/operator 관점에서도 `shows a blocked preflight warning before execution when the rerun preserves existing review blockers`와 `clears resumed candidate restore warnings when the operator changes the rerun target` 2개를 다시 확인해, blocked-warning surface와 resumed-warning cleanup이 현재 UI 기준으로 유지되는 사실을 같이 확인했다
- provider trace audit의 failed-output / fallback 쪽에서도 `failed segment analysis`, `gemini fallback recommendation`, `missing provider_trace default`, `failed preview render`, `authoritative failed run fallback` 대표 흐름 5개를 다시 확인해, 실패 상황에서도 trace read path가 현재 SSOT에 맞는 lineage와 fallback trace를 유지하는 사실을 같이 확인했다
- frontend/operator 관점에서 `disables preview and export controls until review blockers are cleared`와 `supports the thin editing flow with session load, regeneration preflight, and partial regeneration delta visibility`도 다시 확인해, 실제 사용 흐름에서 output gating과 thin editor progression이 현재 UI 기준으로 유지되는 사실을 확인했다
- editing session SSOT / persistence truth 쪽에서도 `caption 저장`, `latest session 복원`, `explanation+tts mutation 저장`, `music override clear` 대표 흐름 4개를 다시 확인해, 편집 세션 저장값과 최신 세션 read path가 현재 backend 기준으로 유지되는 사실을 같이 확인했다
- 이번 검증은 제품 코드를 더 바꾸지 않고도, 자동 baseline green 이후 실제 마감 검증에 필요한 핵심 흐름 증거를 한 번 더 좁게 확보한 단계다

이번 turn의 verification은 아래와 같다.

- phase-b representative backend verification
  - `test_review_snapshot_api_can_approve_pending_recommendation`
  - `test_approved_tts_replacement_flows_through_preview_and_export_outputs`
  - `test_editing_session_api_can_fetch_partial_regeneration_result`
  - `test_review_snapshot_api_uses_partial_regeneration_job_id_for_candidate_timeline`
  - `test_provider_trace_audit_timeline_filter_include_upstream_supports_partial_regeneration_candidate`
  - 결과: `5 passed`
- phase-b representative frontend QA verification
  - `shows a blocked preflight warning before execution when the rerun preserves existing review blockers`
  - `clears resumed candidate restore warnings when the operator changes the rerun target`
  - 결과: `2 passed`
- phase-b operator-flow frontend verification
  - `disables preview and export controls until review blockers are cleared`
  - `supports the thin editing flow with session load, regeneration preflight, and partial regeneration delta visibility`
  - 결과: `2 passed`
- phase-b editing-session persistence verification
  - `test_editing_session_api_can_create_and_patch_caption_override`
  - `test_editing_session_api_can_fetch_latest_session_by_updated_at`
  - `test_editing_session_api_can_patch_explanation_and_tts_mutations`
  - `test_editing_session_api_can_clear_music_override`
  - 결과: `4 passed`
- phase-b representative provider-trace failed/fallback verification
  - `test_provider_trace_audit_endpoint_includes_failed_segment_analysis_without_output_ref`
  - `test_provider_trace_audit_endpoint_includes_failed_gemini_fallback_recommendation_run`
  - `test_provider_trace_audit_endpoint_uses_default_trace_for_failed_provider_job_without_trace`
  - `test_provider_trace_audit_endpoint_includes_failed_preview_render_without_output_ref`
  - `test_provider_trace_audit_endpoint_uses_authoritative_failed_run_when_audit_log_append_fails`
  - 결과: `5 passed`

이 갱신으로 아래 범위는 현재 기준으로 근거가 더 확보됐다.

1. review snapshot approve -> approved output 흐름이 현재 backend 기준 happy-path로 다시 확인됐다
2. editing session -> partial regeneration -> candidate lineage 흐름이 현재 backend 기준으로 다시 확인됐다
3. provider trace audit이 candidate timeline upstream lineage를 계속 유지한다는 시스템 검증 근거가 추가됐다
4. blocked preflight warning과 resumed warning cleanup이 현재 frontend/operator surface 기준으로 다시 확인됐다
5. provider trace audit failed-output / fallback read path도 현재 backend 기준으로 다시 확인됐다
6. output gating과 thin editing flow가 현재 frontend/operator 흐름 기준으로 다시 확인됐다
7. editing session SSOT / persistence truth가 현재 backend 저장/복원 기준으로 다시 확인됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- frontend/operator 관점의 QA 근거를 조금 더 보강한다
- 필요하면 provider trace audit의 failed-output / fallback 쪽 대표 slice 1개를 더 확인한다
- 그 뒤 문서 최신화 / 정리 리팩터링 / 찌꺼기 파일 정리 순서로 마감 정리를 진행한다

## 179. 2026-07-06 Phase C 문서 최신화 기준 최신 상태

이번 후속 작업에서는 제품 동작을 더 바꾸지 않고, 이미 green으로 닫힌 자동 baseline과 representative evidence를 기준으로 상위 SSOT 문서의 현재 상태 표현을 `Phase C` 마감 정리 단계에 맞게 다시 정렬했다.

이번에 새로 확인된 사실은 아래와 같다.

- `current-focused-parallel`, `frontend build`, `full backend regression`, representative happy-path/provider-trace/operator/persistence evidence까지 이미 확보된 상태인데도 일부 상위 문서에는 여전히 `다음 exact stale-shape slice를 더 고른다`는 문구가 남아 있었다
- 이 차이는 구현 상태 자체의 문제라기보다 closeout 문구의 시차 문제였고, 실제 현재 단계는 `새 slice 추가`보다 `문서 최신화 -> 정리 리팩터링 판단 -> 찌꺼기 파일 정리 -> 최종 closeout` 순서가 더 맞다
- historical closeout 섹션은 그대로 보존하고, authoritative 포인터와 현재 next-step 문구만 최신 단계에 맞게 올리는 방식이 가장 안전했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않는 문서-only 변경이다

이번 turn의 verification은 아래와 같다.

- 상태 확인
  - `git status --short --branch`
  - `git log -5 --oneline`
- 문서 정합성 확인
  - `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업`
  - `docs/superpowers/plans/2026-07-05-finish-stabilization-and-closeout-plan.ko.md`의 `## 7. 지금 시점의 추천`
  - `docs/development-status-2026-06-29.ko.md`의 authoritative 포인터와 최신 closeout 섹션
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 코드나 테스트 동작이 아니라 현재 상태 표현 정렬만 다루는 문서-only 작업이다
    - 최신 자동 baseline은 직전 closeout 기준 `current-focused-parallel green`, `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. 구현 계획서와 상태 로그의 현재 next-step 표현이 실제 진행 단계인 `Phase C` 마감 정리와 다시 맞춰졌다
2. historical stale-shape closeout 기록은 그대로 보존하면서도, 지금 무엇을 해야 하는지 읽는 entry point는 최신 단계로 갱신됐다
3. 새 기능 추가나 추가 slice 개방 없이도, 최종 정리 턴에서 따라야 할 문서 기준이 더 단순해졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 문서 최신화 이후 실제 중복이 확인된 작은 정리 리팩터링 후보를 안전 범위에서만 다시 좁힌다
- dead helper, 임시 메모, 역할이 끝난 중복 파일 중 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 2026-07-19 offline provider qualification report closeout

- `[x] 완료 (done)`: fixed Korean 3-case shadow corpus, external SHA-256 pin, tamper rejection, captured CandidateResult revalidation, schema/grounded/policy/human-score/correction-time/95% CI report를 구현했다.
- `[x] 완료 (done)`: report는 perfect synthetic 20-case fixture에도 route를 승인하지 않고 항상 `needs_human_review`다. external provider, Hermes, DB/filesystem/router mutation은 0이다.
- `[ ] 미완료 (pending)`: actual captured GPT/Qwen output 비교, immutable audit persistence, authenticated Hermes bridge, OAuth는 아직 시작하지 않았다. Gemini provider call은 계속 0이다.
- 검증: 관련 focused `56 passed`, 전체 `1197 collected`, production image build 및 `--network none --read-only` reverse fixture load 통과. 전체 suite는 장기 E2E idle로 완료하지 않아 pass로 기록하지 않는다.

## 2026-07-19 유진 provider qualification 기반 closeout

- `[x] 완료 (done)`: LM Studio의 이전 `0.0.0.0:1234` listener를 중지하고 exact `127.0.0.1:1234`로 다시 bind했다. 이 확인은 direct LAN exposure closure일 뿐이며 Hermes host bridge 또는 Qwen qualification이 아니다.
- `[x] 완료 (done)`: `agent_quality_harness`는 GPT/Qwen 공통 frozen case를 JSON-compatible deep immutable fixture, strict object/schema allowlist, grounded claim, sensitive field/path/tool/approval rejection으로 판정한다. provider 호출·routing mutation 없이 통과 결과도 `shadow_only`에만 머문다.
- `[x] 완료 (done)`: 품질 리뷰는 보완 뒤 P0/P1 0이다. container production build와 `--network none --read-only` image reverse run에서 `shadow_only` 결과와 fixture identity 전달을 확인했다.
- `[ ] 미완료 (pending)`: actual authenticated pinned Hermes host bridge, Qwen task qualification corpus/metrics·사람 점수, Hermes OAuth/GPT 외부 호출은 시작하지 않았다. Gemini provider call은 계속 0이다.
- 검증: harness `7 passed`; LM Studio evidence/local media provider 관련 focused `47 passed`; 전체 suite는 `1188 tests collected`까지 통과했지만 실미디어/E2E 장기 실행이 종료 시간 안에 완료하지 않아 full-pass로 기록하지 않는다.

## 247. 2026-07-16 Local Media Director Slice 3 Task 15 closeout

- Director workspace는 대화 응답만으로 편집 session을 변경하지 않으며, immutable preflight와 명시적 `변경 적용`만 batch atomic apply를 호출한다.
- 비교 tray는 preflight diff와 selected-reference/B-roll/all scope를 표시한다. 후보 preview는 one-at-a-time, B-roll in/out, candidate audition gain, preview-only narration mute/solo를 제공하며 timeline gain을 바꾸지 않는다.
- batch journal은 Windows 장경로를 피하고, post-commit mirror write failure에서 DB-owned bytes를 보존한다. restart reconciliation은 허용된 project stage/assets 경로만 정리하고 unsafe manifest를 보존한다.
- 검증: focused frontend `36 passed`, focused backend `20 passed`, frontend full `137 passed`와 build, `git diff --check` 통과. backend full regression은 다음 Task 16의 첫 gate로 재실행한다.
- 누적 진행률: 15/18 (83.3%), 잔여 16.7%. 다음 작업은 Task 16 manual media library 추출과 AI 실패 독립성이다.

## 221. 2026-07-12 개인 음성 TTS 청취 승인 게이트 closeout

- `PATCH /api/projects/{project_id}/tts-candidates/{candidate_id}/listening-review`가 기술 검증 통과 후보의 `approved`/`rejected` 결정을 SQLite에 저장하고 후보 목록 재조회에 유지한다.
- `tts_candidate_*` ID는 세그먼트·자산 일치와 `technical_status=accepted`, `operator_review_status=approved`를 모두 만족해야 editing session의 TTS replacement가 된다. pending/rejected 후보는 기존 narration을 바꾸지 않는다.
- 편집 UI는 승인 전 선택을 비활성화하고, 승인/거부·실패 후 재시도·새로고침 복원 테스트를 갖췄다. legacy/imported 일반 TTS replacement는 개인 음성 후보가 아니므로 호환성을 유지한다.
- 검증: frontend 88 passed + build, backend 635 passed 분할(API 195+194, 기타 246), 600초 Korean smoke 14/14 true. `python-multipart` import의 known PendingDeprecationWarning만 남았다.
- 전체 milestone: 39개 중 38 완료, 1 부분. strict 97.4%, weighted 98.7%, weighted remaining 1.3%. 실제 사용자 청취 품질 판정과 다중 실제 프로젝트 CapCut UX QA는 계속 사람이 수행해야 한다.

## 220. 2026-07-12 personal voice file upload readiness

- 완료: 브라우저 file picker → multipart upload → `voice_sample_audio` 등록 → TTS candidate voice-sample ID 자동 반영을 구현했다. 기존 path 직접 등록은 유지한다.
- 안전성: 지원 확장자만 허용하고 empty file은 400으로 거부한다. 최대 128 MiB, 1 MiB chunk staging, 등록 뒤 임시 업로드 삭제를 적용했다.
- 복구: voice sample 목록 API로 최근 asset ID를 새로고침 후 복원하며 UI upload 실패 뒤 선택 파일명은 유지된다.
- 검증: frontend 86 passed/build success, backend Python 3.12 633 passed (API 389 + 기타 244), 600초 Korean smoke 13 checks true.
- 전체 milestone: 39개 중 38 완료, 1 부분. strict 97.4%, partial=0.5 weighted 98.7%, weighted remaining 1.3%. 실제 human listening approval 및 다중 프로젝트 CapCut UX QA는 남는다.

## 219. 2026-07-12 SFX real-asset recommendation/materialization acceptance

- 완료: assetless SFX 추천은 materialization하지 않으며, 실제 SFX asset 선택은 editing session → `sfx_refresh` → pending review → 개별 승인 → SFX timeline track으로 이어진다.
- 수정: review snapshot/API/storage canonical sets에 SFX를 추가했고, partial regeneration job의 embedded candidate timeline도 승인 결정으로 함께 갱신한다. 따라서 승인 직후 final renderer/real CapCut export가 같은 SFX track을 읽는다.
- UI: 편집 화면의 효과음 asset ID 저장·해제, default partial regeneration field, review/track label을 추가했다.
- 검증: frontend 83 passed/build success, backend Python 3.12 632 passed (API 388 + 기타 244), 600초 deterministic Korean smoke 12 checks true; final MP4 SHA-256 `036bc6ccfbcd5aba814e44aceb9b654f41ead6c9613d9ebfd4eb2dc8f672a93e`.
- 전체 milestone: 39개 중 38 완료, 1 부분. strict 97.4%, partial=0.5 weighted 98.7%, weighted remaining 1.3%.
- 남은 부분: 실제 사용자 음성 human listening approval, 다중 실제 프로젝트의 CapCut open/edit/export UX QA.

## 218. 2026-07-12 personal voice TTS acceptance

- 완료: technical acceptance, original-narration fallback, target duration, pending listening review UI/API, Korean 10-minute FFmpeg + real CapCut smoke.
- 검증: frontend 83 passed/build success, backend Python 3.12 `.venv` 628 passed, smoke final MP4 SHA-256 `6e257a604e05a15963a69554b1541107d999cb74a769b8d073747b81d1b46ba5`.
- 전체 milestone: 39개 중 37 완료, 2 부분. strict 94.9%, partial=0.5 weighted 97.4%, weighted remaining 2.6%.
- 남은 부분: 실제 사용자 녹음으로 수행하는 human listening approval, SFX materialization, 다중 프로젝트 human CapCut UX QA.

## 183. 2026-07-06 Phase C pending recommendation identity key refactor closeout

이번 후속 작업에서는 새 stale-shape 버그를 더 열지 않고, `Phase C` 정리 리팩터링 후보 중 가장 작은 범위였던 pending recommendation canonical identity key 중복을 `local_pipeline` 내부 helper 1개로 공통화했다.

이번에 새로 확인된 사실은 아래와 같다.

- output blocker read-path, blocking pending recommendation 판별, partial regeneration source merge가 같은 `recommendation_id + target_segment_id + canonical recommendation_type` identity를 각자 다시 만들고 있었다
- 현재 동작은 이미 맞았지만, trim/lower 기준이 나중에 한쪽만 바뀌면 output gating과 preflight dedupe가 다시 어긋날 수 있는 구조였다
- 그래서 동작을 바꾸지 않고 canonical identity key 생성만 helper로 묶어, 중복 기준 drift 가능성을 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_blockers_deduplicate_repeated_persisted_pending_recommendation_entries` -> `1 passed`
  - `test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - backend output-gating `24 passed`
  - backend preflight `59 passed`
  - frontend preflight `25 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 dedupe key 생성 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output blocker와 partial regeneration source merge가 보는 pending recommendation canonical identity 기준이 한 helper로 다시 모였다
2. mixed-case/trimmed recommendation type dedupe 기준이 흩어질 위험이 줄었다
3. 동작 변경 없이도 다음 정리 리팩터링 후보를 고를 때 비교 기준이 더 단순해졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review/output prompt normalization 중복과 stale-shape helper 중복 중 다음 최소 리팩터링 후보 1개를 다시 좁힌다
- dead helper, 임시 메모, 역할이 끝난 중복 파일의 정리 방식은 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 184. 2026-07-06 Phase C output operator copy pending row normalization refactor closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `Phase C` 정리 리팩터링 후보 중 가장 작은 범위였던 output operator copy prompt의 pending recommendation row canonicalization 중복을 helper 1개로 공통화했다.

이번에 새로 확인된 사실은 아래와 같다.

- `output_operator_copy.py` 안에서 blocking pending recommendation identity 판별과 prompt row canonicalization이 같은 파일 안에 따로 흩어져 있었다
- 현재 동작은 이미 맞았지만, `selected_asset_uri`, identity, reason, decision_state trim/lower/default 기준이 나중에 한쪽만 바뀌면 prompt surface가 다시 어긋날 수 있는 구조였다
- 그래서 동작을 바꾸지 않고 prompt row 정규화만 helper로 묶어, output guidance prompt surface의 canonicalization drift 가능성을 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 output operator copy prompt 내부 helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy prompt가 보는 pending recommendation canonical row 기준이 helper 1개로 다시 모였다
2. selected asset uri, identity, reason, decision state canonicalization 기준 drift 위험이 줄었다
3. 다음 정리 리팩터링 후보를 고를 때 review guidance prompt와 비교 기준이 더 단순해졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review guidance prompt의 pending recommendation row normalization 중복을 같은 방식으로 줄일지 판단한다
- dead helper, 임시 메모, 역할이 끝난 중복 파일의 정리 방식은 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 185. 2026-07-06 Phase C review guidance pending row normalization refactor closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `Phase C` 정리 리팩터링 후보 중 가장 작은 범위였던 review guidance prompt의 pending recommendation row canonicalization 중복을 helper 1개로 공통화했다.

이번에 새로 확인된 사실은 아래와 같다.

- `review_guidance.py` 안에서 blocking pending recommendation identity 판별과 prompt row canonicalization이 같은 파일 안에 따로 흩어져 있었다
- 현재 동작은 이미 맞았지만, `selected_asset_uri`, identity, reason, decision_state trim/lower/default 기준이 나중에 한쪽만 바뀌면 blocked guidance prompt surface가 다시 어긋날 수 있는 구조였다
- 그래서 동작을 바꾸지 않고 prompt row 정규화만 helper로 묶어, blocked guidance prompt surface의 canonicalization drift 가능성을 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_review_guidance_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 review guidance prompt 내부 helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. review guidance prompt가 보는 pending recommendation canonical row 기준이 helper 1개로 다시 모였다
2. selected asset uri, identity, reason, decision state canonicalization 기준 drift 위험이 줄었다
3. 남아 있는 review/output prompt normalization 중복 후보를 더 적게 비교해도 되게 됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review/output prompt normalization 중 남은 중복 후보가 더 있는지 다시 좁힌다
- dead helper, 임시 메모, 역할이 끝난 중복 파일의 정리 방식은 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 186. 2026-07-06 Phase C shared prompt pending row normalization helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, output operator copy와 review guidance가 각각 들고 있던 pending recommendation prompt row normalization helper를 공통 모듈로 묶었다.

이번에 새로 확인된 사실은 아래와 같다.

- 바로 앞 두 턴에서 파일 내부 중복은 줄였지만, 두 prompt 파일이 거의 같은 pending recommendation row normalization 본문을 각각 유지하고 있었다
- 현재 동작은 이미 맞았지만, `selected_asset_uri`, identity, reason, decision_state canonicalization 규칙을 나중에 조정할 때 두 파일이 다시 따로 움직일 수 있는 구조였다
- 그래서 판별 로직까지 넓히지 않고 row normalization helper만 공통 모듈로 분리해, review/output prompt surface의 canonicalization 규칙 drift 가능성을 더 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt pending recommendation row normalization helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 보는 pending recommendation row canonicalization 기준이 공통 모듈로 다시 모였다
2. selected asset uri, identity, reason, decision state canonicalization 규칙 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보를 고를 때 review/output prompt family의 중복은 더 많이 정리된 상태가 됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 210. 2026-07-06 operational readiness complete

이번 후속 작업에서는 운영 마감 blocker 1개를 실제로 복구하고, focused와 broader를 다시 돌려 현재 브랜치가 운영 마감 완료 상태인지 최신 증거로 재판정했다. 목적은 `개발 closeout은 끝났지만 운영 마감은 아직 아님`으로 남아 있던 상태를 실제 green 기준으로 닫는 것이었다.

이번에 새로 확인된 사실은 아래와 같다.

- exact blocker slice
  - `test_broll_recommendation_endpoint_preserves_heuristic_path_on_unexpected_runtime_failure`
  - 예상 밖 runtime 예외가 나와도 broll recommendation 단계가 heuristic fallback으로 내려가야 한다는 경계를 RED -> GREEN으로 복구했다
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused`
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - `npm run build` -> 성공
  - `pytest -q` -> `544 passed`

현재 authoritative 운영 판단은 아래처럼 정리한다.

- 현재 브랜치는 `개발 closeout 완료`이면서 동시에 `운영 마감 완료` 상태다
- focused, representative smoke, frontend build, full backend regression이 모두 최신 green으로 다시 확보됐다
- 현재 브랜치 기준 필수 blocker는 남아 있지 않다

historical / dead artifact 판단은 아래 기본값을 유지한다.

- 이번 턴에서도 즉시 삭제해야 할 명백한 dead artifact 후보는 확인하지 못했다
- historical closeout 문서는 reference로 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. 운영 마감 blocker 1개가 실제로 복구됐다
2. broader full backend regression이 다시 green으로 닫혔다
3. 현재 브랜치는 운영 마감 완료 상태로 봐도 되는 최신 증거가 다시 확보됐다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 현재 브랜치 범위에서 필수 남은 일은 없다
- 이후 새 요구가 생기면 새 goal로 열고, 실제 코드 변경인지부터 다시 판정한다

## 209. 2026-07-06 operational readiness check

이번 후속 작업에서는 개발 closeout 완료 상태와 운영 마감 완료 상태를 실제 검증 결과 기준으로 다시 분리해 점검했다. 목적은 `문서 closeout은 끝났지만 실제 운영 마감도 끝났는가`를 다시 증명하는 것이었다.

이번에 새로 확인된 사실은 아래와 같다.

- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused`
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - `./scripts/dev-fast-path.ps1 -Mode broader`
    - frontend production build는 성공했다
    - full backend regression은 `1 failed, 542 passed`로 red였다
  - failing test는 `test_editing_session_api_can_fetch_visual_overlay_and_music_updates`였다
- exact rerun
  - 같은 failing test를 단독으로 다시 돌리면 `1 passed`였다
- representative smoke / QA
  - backend happy-path / lineage / partial-regeneration / provider-trace representative `5 passed`
  - frontend operator QA representative `3 passed`

현재 authoritative 운영 판단은 아래처럼 정리한다.

- 현재 브랜치는 `개발 closeout 완료` 상태다
- 하지만 `운영 마감 완료` 상태는 아직 아니다
- 이유는 broader full backend regression에서 실제 red가 한 번 확인됐기 때문이다
- 현재 가장 가능성 높은 원인은 기능 단독 실패보다 full-suite 순서 의존 또는 테스트 간 상태 오염이다

historical / dead artifact 판단은 아래 기본값을 유지한다.

- 현재 범위에서 즉시 삭제해야 할 명백한 dead artifact 후보는 확인하지 못했다
- historical closeout 문서는 reference로 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. 개발 closeout 완료와 운영 마감 완료가 같은 말이 아니라는 점이 최신 증거 기준으로 다시 분리됐다
2. focused, build, representative smoke는 green이지만 broader backend regression은 아직 green이 아니다
3. 다음 실제 우선순위는 `test_editing_session_api_can_fetch_visual_overlay_and_music_updates`의 full-suite only red 원인을 좁히는 것이다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- full-suite에서만 보이는 `test_editing_session_api_can_fetch_visual_overlay_and_music_updates` red 원인을 좁힌다
- 필요하면 그 경계 1개만 minimal fix로 복구한다
- broader를 다시 돌려 운영 마감 가능 여부를 재판단한다

## 208. 2026-07-06 final closeout remote sync and record save

이번 후속 작업에서는 새 코드나 새 closeout judgment를 더 만들지 않고, 현재 브랜치의 closeout completion judgment가 원격까지 반영됐는지와 handoff 기록이 충분히 저장됐는지만 다시 확인했다. 목적은 사용자가 요청한 `워킹트리 정리`, `커밋/푸시`, `컨텍스트 저장`, `개발기록 저장`을 현재 상태 그대로 명확히 남기는 것이다.

이번에 다시 확인한 사실은 아래와 같다.

- worktree는 현재 clean이다
- latest pushed commit은 `905ae28 docs: confirm closeout completion judgment`다
- authoritative 상태 판단은 여전히 `final closeout completion judgment`를 유지한다
- 추가 코드 변경 없이, remote-synced handoff 메모만 개발기록으로 남기면 현재 저장 요청 범위는 닫힌다

현재 authoritative final judgment는 아래처럼 유지한다.

- 현재 브랜치 closeout 범위에서 필수 남은 일은 없다
- historical 문서와 역할 종료 메모는 기본적으로 historical reference로 유지한다
- 이후 새 코드 변경이나 새 운영 요구가 생길 때만 새 goal을 열어 다음 slice를 다시 정한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. 원격 반영 상태가 다시 확인됐다
2. 현재 authoritative 포인터와 handoff 문서가 한 번 더 저장됐다
3. 사용자 요청 기준 `컨텍스트 저장`과 `개발기록 저장`이 현재 브랜치 문서에 반영됐다

## 207. 2026-07-06 final closeout completion judgment

이번 후속 작업에서는 `final closeout` 본문이 적어 둔 마지막 3개 pending을 실제 증거로 다시 확인해, 현재 브랜치 기준 required closeout work가 사실상 모두 닫혔는지 판단했다. 목적은 `아직 남은 일처럼 적혀 있던 문장`과 실제 worktree 상태를 맞추는 것이다.

이번에 다시 확인한 사실은 아래와 같다.

- final closeout commit unit
  - `f12ab67 docs: write final closeout body`가 현재 closeout의 실제 docs-only 마감 커밋이다
- latest code-changing point
  - 마지막 코드 변경 커밋은 `56005dc fix: ignore nested target segment id runtime pending recommendations`다
  - 그 뒤 최근 커밋들은 모두 closeout 문서만 수정했다
- scoped cleanup check
  - 임시/실험/찌꺼기 파일 후보를 좁게 다시 스캔했지만, 현재 범위에서 즉시 삭제해야 할 명백한 dead artifact는 확인되지 않았다
- broader rerun judgment
  - 마지막 코드 변경 뒤 추가 코드 수정이 없으므로, broad 재검증을 지금 다시 돌릴 직접 사유는 현재 없다

현재 authoritative final judgment는 아래처럼 정리한다.

- automatic baseline, representative Phase B evidence, final closeout 문서화는 현재 기준으로 모두 확보됐다
- historical 문서와 역할 종료 메모는 기본적으로 historical reference로 유지한다
- 현재 브랜치의 required work는 새 exact regression 탐색이 아니라 final closeout/handoff 판단까지 닫힌 상태로 본다
- 이후 새 코드 변경이 다시 생길 때만 exact regression, focused verification, broader rerun 필요성을 다시 판단한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. final closeout commit 단위가 실제 커밋 기준으로 고정됐다
2. scoped 정리 점검에서 즉시 삭제가 필요한 찌꺼기 파일 후보는 현재 확인되지 않았다
3. broad 재검증을 다시 돌리지 않는 이유가 현재 코드 상태 기준으로 분명해졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 현재 브랜치 closeout 범위에서 필수 남은 일은 없다
- 이후 새 코드 변경이나 새 운영 요구가 생기면 그때 다음 slice를 다시 연다

## 206. 2026-07-06 final closeout

이번 후속 작업에서는 코드를 더 바꾸지 않고, `final closeout summary` 단계에서 모아 둔 current truth를 실제 final closeout 본문으로 한 번 더 고정했다. 목적은 이제 더 이상 `다음 exact regression`이나 `다음 cleanup`을 찾지 않고, 현재 브랜치를 어떤 검증 근거와 어떤 historical retention 판단으로 마감할지 한 자리에서 읽게 만드는 것이다.

현재 authoritative final closeout judgment는 아래와 같다.

- automatic baseline
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
  - `npm run build` -> 성공
  - `pytest -q` -> `543 passed`
- representative Phase B evidence
  - backend happy-path / lineage `5 passed`
  - provider trace audit failed-output / fallback `5 passed`
  - frontend operator QA `3 passed`
- current closeout judgment
  - 구현보다 closeout 문서화가 남은 실제 작업에 더 가깝다
  - editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 깨뜨리는 최신 회귀는 현재 baseline 기준으로 다시 확인되지 않았다

전체 동작 검증, QA, 시스템 검증 judgment는 아래처럼 요약한다.

- review snapshot -> editing session handoff 대표 경계는 최신 evidence 기준으로 정상이다
- preflight -> rerun -> candidate restore 대표 경계는 최신 evidence 기준으로 정상이다
- approve / reject / manual edit와 approved output 경계는 stale blocker/pending metadata가 current truth를 뒤집지 않도록 정리됐다
- provider trace audit failed-output / fallback과 candidate lineage 대표 경계는 최신 evidence 기준으로 정상이다
- TTS replacement approval -> preview / export 반영 대표 경계는 최신 baseline 기준으로 정상이다

historical retention judgment는 아래 기본값을 유지한다.

- closeout 기록과 역할 종료 메모는 기본적으로 삭제하지 않는다
- authoritative 포인터에서 밀려난 문서는 historical reference로 유지한다
- 실제 삭제는 임시 실험 파일이나 명백한 dead artifact가 있을 때만 별도 근거로 판단한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. final closeout 본문이 current truth 기준 문서로 실제 작성됐다
2. 이제 남은 일은 새 기능이나 새 exact regression이 아니라 final commit 단위 설계와 마지막 historical 정리 판단 쪽으로 더 좁혀졌다
3. 현재 가장 큰 리스크는 코드보다 final closeout 이후 무엇을 정말 끝으로 볼지에 대한 마감 판단이다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- final commit 단위를 설계한다
- historical 정리에서 실제 삭제 판단이 필요한 대상이 있는지 마지막으로만 확인한다
- broad 재검증을 다시 돌릴 이유가 실제로 남아 있는지 final commit 직전에만 판단한다

## 205. 2026-07-06 final closeout summary

이번 후속 작업에서는 코드를 더 바꾸지 않고, 현재 브랜치의 final closeout 본문을 작성할 수 있을 정도로 모인 최신 검증 근거와 정리 기준을 한 자리에서 다시 요약했다. 목적은 이제 더 이상 `다음 slice`를 찾지 않고, 현재 상태를 authoritative final-closeout-ready 상태로 읽게 만드는 것이다.

현재 authoritative summary는 아래와 같다.

- automatic baseline
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
  - `npm run build` -> 성공
  - `pytest -q` -> `543 passed`
- representative Phase B evidence
  - backend happy-path / lineage `5 passed`
  - provider trace failed-output / fallback `5 passed`
  - frontend operator QA `3 passed`
- latest broader recovery
  - nested `target_segment_id` stale pending recommendation runtime regression 1개를 복구했고, 그 뒤 full backend regression까지 다시 green을 확인했다
- historical retention policy
  - closeout 기록과 역할 종료 메모는 기본적으로 삭제보다 역할 명시를 우선한다

현재 QA/system verification judgment는 아래처럼 정리된다.

- QA judgment
  - blocked preflight warning, resumed candidate restore warning cleanup, mark for manual edit -> editing session 진입 대표 경계는 최신 frontend evidence로 다시 green이다
- system verification judgment
  - provider trace audit의 candidate lineage와 failed-output/fallback 대표 경계는 최신 backend evidence로 다시 green이다
  - editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 깨뜨리는 최신 회귀는 현재 baseline 기준으로 다시 확인되지 않았다

historical 문서와 찌꺼기 파일 판단은 아래 기본값을 유지한다.

- historical closeout 문서는 삭제하지 않고 historical reference로 남긴다
- 역할 종료 메모도 authoritative 포인터에서 밀려난 기록으로 유지한다
- 실제 삭제는 historical 가치가 없는 임시 실험 파일이나 명백한 dead artifact가 확인될 때만 별도 판단한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. current truth를 읽기 위한 authoritative final closeout summary가 SSOT에 반영됐다
2. 다음 턴은 새로운 cleanup이나 추가 검증보다, final closeout 문서를 실제로 작성하고 마지막 마감 커밋 단위를 정하는 데 집중하면 된다
3. 현재 남은 리스크는 코드보다 final closeout 문장을 얼마나 명확하게 쓰느냐 쪽으로 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- final closeout 본문을 실제로 작성한다
- 최종 마감 커밋 단위를 설계한다
- 필요하면 마지막 문서 정리만 더 수행한다

## 204. 2026-07-06 final closeout structure and historical retention policy confirmation

이번 후속 작업에서는 코드를 더 바꾸지 않고, final closeout 문서에 무엇을 반드시 넣을지와 historical 문서/역할 종료 메모를 어떤 기본 원칙으로 다룰지 먼저 확정했다. 목적은 다음 턴이 더 이상 cleanup 탐색으로 돌아가지 않고, 실제 final closeout 본문 작성으로 바로 이어지게 만드는 것이다.

이번에 새로 확인된 사실은 아래와 같다.

- 현재 상태에서 가장 부족한 것은 테스트가 아니라 final closeout 문서 구조의 고정이었다
- automatic baseline, broader baseline, representative Phase B evidence는 이미 최신 green이므로, 이제 남은 리스크는 `무엇을 final truth로 남길지`를 흐리게 쓰는 쪽이다
- historical 문서와 역할 종료 메모는 기본적으로 삭제보다 역할 명시가 더 안전하다
  - 이유:
    - 이 저장소는 closeout 기록이 누적 증거 역할도 한다
    - 지금 단계에서는 cleanup 기록 삭제보다 authoritative 포인터에서 밀려난 historical 기록임을 분명히 하는 편이 회귀 조사와 handoff에 더 유리하다
- 따라서 다음 final closeout 문서는 최소한 `현재 상태`, `automatic baseline`, `representative evidence`, `QA/system verification judgment`, `historical retention judgment`, `final commit/push 상태`를 한 문서 안에서 묶어야 한다

이번 turn의 verification 근거는 아래를 그대로 사용한다.

- current automatic baseline
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel` -> backend output-gating `24 passed`, backend preflight `59 passed`, frontend preflight `25 passed`
  - `npm run build` -> 성공
  - `pytest -q` -> `543 passed`
- representative Phase B evidence
  - backend happy-path / lineage `5 passed`
  - provider trace failed-output / fallback `5 passed`
  - frontend operator QA `3 passed`

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. final closeout 문서에 들어갈 최소 구조가 고정됐다
2. historical 문서/역할 종료 메모는 기본적으로 삭제보다 역할 명시를 우선한다는 정리 기준이 고정됐다
3. 다음 턴은 코드 수정 없이 final closeout 본문 작성과 최종 마감 판단에 바로 들어갈 수 있다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- final closeout 본문을 실제로 작성한다
- QA/system verification judgment를 최종 문장으로 고정한다
- 최종 마감 커밋 단위를 설계한다

## 203. 2026-07-06 final closeout prep stage confirmation

이번 후속 작업에서는 코드를 더 바꾸지 않고, 현재 SSOT의 next-step 표현을 실제 상태에 맞게 다시 정렬했다. automatic baseline, broader baseline, representative Phase B evidence가 모두 최신 green으로 확보된 지금 시점에서는 더 작은 cleanup 후보를 계속 여는 것보다 final closeout 준비 단계로 넘어가는 표현이 더 정확하다.

이번에 새로 확인된 사실은 아래와 같다.

- 현재 worktree는 이미 아래 근거를 모두 확보한 상태다
  - `current-focused-parallel` green
  - `frontend build` green
  - `full backend regression 543 passed`
  - representative backend happy-path / lineage evidence green
  - representative provider trace failed-output / fallback evidence green
  - representative frontend operator QA evidence green
- 따라서 남은 핵심 일은 stale-shape cleanup 1개를 더 고르는 것이 아니라, final closeout 문서 구조, QA/system verification judgment, historical 문서 역할 정리 기준을 확정하는 쪽이다
- 이 판단은 구현 상태를 과장하는 것이 아니라, 이미 확보된 최신 검증 근거에 맞춰 next-step 표현을 조정한 것이다

이번 turn의 verification 근거는 아래를 그대로 사용한다.

- current automatic baseline
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel` -> backend output-gating `24 passed`, backend preflight `59 passed`, frontend preflight `25 passed`
  - `npm run build` -> 성공
  - `pytest -q` -> `543 passed`
- representative Phase B evidence
  - backend happy-path / lineage `5 passed`
  - provider trace failed-output / fallback `5 passed`
  - frontend operator QA `3 passed`

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. SSOT의 next-step 표현이 실제 상태에 맞게 `final closeout 준비` 단계로 올라왔다
2. 다음 턴은 cleanup 탐색보다 final closeout 문서화, QA/system verification judgment, historical 정리 판단에 집중하면 된다
3. 현재 상태에서는 broad 재검증을 또 반복하기보다, 이미 확보된 최신 baseline을 어떤 형태로 최종 closeout에 고정할지가 더 중요하다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- final closeout 문서 구조를 확정한다
- historical 문서와 역할 종료 메모의 삭제/유지 기준을 정리한다
- 최종 마감 커밋 단위를 설계한다

## 202. 2026-07-06 phase b representative verification refreshed after broader recovery closeout

이번 후속 작업에서는 코드를 더 바꾸지 않고, broad 회귀 복구 직후의 최신 baseline 위에서 `Phase B` 대표 검증 근거를 다시 수집했다. 목적은 final closeout 전에 happy-path, frontend operator flow, provider trace failed-output/fallback evidence가 여전히 살아 있는지 최신 상태로 확인하는 것이었다.

이번에 새로 확인된 사실은 아래와 같다.

- backend representative happy-path 체인 5개가 모두 다시 green이었다
  - review snapshot approve
  - approved TTS replacement preview/export 반영
  - partial regeneration result fetch
  - candidate timeline job id lineage
  - provider trace audit candidate upstream lineage
- provider trace audit의 failed-output / fallback 대표 경계 5개도 모두 다시 green이었다
  - failed segment analysis without output ref
  - failed gemini fallback recommendation run
  - default trace for failed provider job without trace
  - failed preview render without output ref
  - authoritative failed run when audit log append fails
- frontend representative QA 경계 3개도 다시 green이었다
  - blocked preflight warning
  - resumed candidate restore warning cleanup
  - mark for manual edit -> editing session 진입
- 즉, 현재 최신 baseline은 자동 focused/broader green뿐 아니라 representative Phase B evidence까지 다시 최신 상태로 확보된 셈이다

이번 turn의 verification은 아래와 같다.

- representative backend happy-path / lineage evidence
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_can_approve_pending_recommendation or test_approved_tts_replacement_flows_through_preview_and_export_outputs or test_editing_session_api_can_fetch_partial_regeneration_result or test_review_snapshot_api_uses_partial_regeneration_job_id_for_candidate_timeline or test_provider_trace_audit_timeline_filter_include_upstream_supports_partial_regeneration_candidate" -vv` -> `5 passed`
- representative provider trace failed-output / fallback evidence
  - `py -m pytest tests/test_api.py -q -k "test_provider_trace_audit_endpoint_includes_failed_segment_analysis_without_output_ref or test_provider_trace_audit_endpoint_includes_failed_gemini_fallback_recommendation_run or test_provider_trace_audit_endpoint_uses_default_trace_for_failed_provider_job_without_trace or test_provider_trace_audit_endpoint_includes_failed_preview_render_without_output_ref or test_provider_trace_audit_endpoint_uses_authoritative_failed_run_when_audit_log_append_fails" -vv` -> `5 passed`
- representative frontend QA evidence
  - `npm test -- --run src/app.test.tsx -t "shows a blocked preflight warning before execution when the rerun preserves existing review blockers|clears resumed candidate restore warnings when the operator changes the rerun target|opens the actionable pending recommendation in the editing session when marked for manual edit"` -> `3 passed`
- current automatic baseline already verified in the immediately previous closeout
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel` -> backend output-gating `24 passed`, backend preflight `59 passed`, frontend preflight `25 passed`
  - `npm run build` -> 성공
  - `pytest -q` -> `543 passed`

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. final closeout 전에 필요한 representative Phase B evidence가 최신 baseline 위에서 다시 확보됐다
2. happy-path, frontend operator flow, provider trace failed-output/fallback 대표 근거가 모두 최신 green으로 맞춰졌다
3. 남은 일은 실제 final closeout용 전체 동작 검증 서술 정리, QA/system verification judgment, historical 문서/찌꺼기 정리 판단으로 더 좁혀졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- final closeout 문서에 전체 동작 검증, QA, 시스템 검증 결과를 어떤 단위로 묶을지 결정한다
- historical 문서와 역할 종료 메모의 삭제/유지 기준을 정리한다
- 최종 마감 커밋 단위를 설계한다

## 201. 2026-07-06 broader rerun recovered nested target_segment_id pending recommendation regression closeout

이번 후속 작업에서는 새 cleanup을 더 여는 대신 `Phase A`가 충분히 닫혔는지 확인하려고 `current-focused-parallel`과 `broader`를 다시 돌렸고, 그 과정에서 `partial regeneration` 런타임 read-path에 남아 있던 nested `target_segment_id` stale shape 회귀 1개를 발견해 최소 수정으로 복구했다.

이번에 새로 확인된 사실은 아래와 같다.

- `current-focused-parallel`은 그대로 green이었지만, full backend regression을 다시 돌리자 `test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration` 1개가 실패했다
- 원인은 `_runtime_pending_recommendation_identity_key(...)`가 `target_segment_id`를 무조건 `str(...).strip()`로 바꿔 nested dict stale shape도 유효한 pending recommendation identity처럼 살리던 점이었다
- `recommendation_id`와 `target_segment_id`를 실제 string 타입일 때만 identity로 인정하도록 최소 수정하자 exact RED가 바로 GREEN으로 복구됐고, 인접 preflight 경계와 full backend regression도 다시 green으로 돌아왔다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration" -vv` -> RED `1 failed`, GREEN `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_filters_nested_target_segment_id_source_pending_recommendation_from_preflight_prediction" -vv` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - backend output-gating `24 passed`
  - backend preflight `59 passed`
  - frontend preflight `25 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - `npm run build` -> 성공
  - `pytest -q` -> `543 passed`

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. broader rerun에서 실제로 남아 있던 nested `target_segment_id` stale shape 회귀 1개가 복구됐다
2. current-focused-parallel, frontend build, full backend regression 기준의 자동 baseline이 다시 최신 green으로 확인됐다
3. 이제 남은 일은 final closeout 직전의 전체 동작 검증, QA, 시스템 검증, historical 문서/찌꺼기 정리 판단 쪽으로 더 분명하게 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 전체 동작 검증, QA, 시스템 검증을 final closeout 순서로 실제 착수할지 판단한다
- historical 문서와 역할 종료 메모의 삭제/유지 기준을 정리한다
- 최종 closeout 문서와 정리 커밋 단위를 설계한다

## 200. 2026-07-06 Phase C shared operator review default text helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `prompt_pending_recommendation.py`, `review_guidance.py`, `local_pipeline.py`에 흩어져 있던 기본 operator review 문구 fallback 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- prompt review-flag row, blocked guidance fallback, runtime reuse key, source timeline restore path는 모두 `"Operator review required before approval or output."`를 기본 fallback 문구로 쓰고 있었지만, 구현은 파일별 local helper와 inline literal 중복으로 남아 있었다
- `canonical_operator_review_text.py`에 shared `canonical_operator_review_text(...)`와 `DEFAULT_OPERATOR_REVIEW_TEXT`를 추가하고 각 경로가 이를 직접 재사용하게 맞춰도 현재 blocked guidance, prompt surface, reuse key 동작은 그대로 유지됐다
- 이번 정리는 기본 안내 문구 fallback만 모은 cleanup이며, blocker 판단, recommendation truth, persistence semantics는 바꾸지 않았다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_fills_default_review_flag_message or test_review_guidance_reuse_key_fills_default_pending_recommendation_reason or test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason" -vv` -> `3 passed`
  - `py -m pytest tests/test_api.py -q -k "test_heuristic_review_guidance_builder_defaults_missing_review_flag_message" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_defaults_missing_pending_recommendation_reason_in_prompt" -vv` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 operator review default text helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. prompt/guidance/runtime read-path가 같은 기본 operator review 문구 fallback을 직접 공유한다
2. 기본 blocker 안내 문구 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 dead helper, historical 문서 역할 정리, broader 최종 판단 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 199. 2026-07-06 Phase C shared canonical source-uri helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `preview_renderer.py`, `review_action_mutations.py`, `timeline_builder.py`, `local_pipeline.py`에 흩어져 있던 source-uri trim helper 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- preview narration source surface, TTS approval apply path, timeline narration asset swap, runtime blocker reuse key는 모두 `selected_asset_uri` 또는 `asset_uri`를 `str(...).strip()` 기준으로 정리하고 있었지만, 구현은 파일별 local helper 또는 inline trim 중복으로 남아 있었다
- `canonical_source_uri.py`에 shared `canonical_source_uri(...)`를 추가하고 각 read-path가 이를 직접 재사용하게 맞춰도 현재 preview surface와 TTS approval/output 계약은 그대로 유지됐다
- 이번 정리는 URI canonicalization 규칙만 모은 cleanup이며, recommendation truth, approval semantics, persistence shape는 바꾸지 않았다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_trims_payload_selected_asset_uri" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_trims_tts_narration_source_uri_surface" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_rejects_tts_approval_without_selected_asset_uri" -vv` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 canonical source-uri helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. preview/review-action/runtime/timeline read-path가 같은 source-uri trim 기준을 직접 공유한다
2. selected_asset_uri와 narration source surface trim 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 dead helper, 문서 역할 정리, broader 최종 판단 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 198. 2026-07-06 Phase C shared strict boolish helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `preview_renderer.py`, `review_guidance.py`, `local_pipeline.py`에 흩어져 있던 strict boolish normalization helper 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- preview/output gating/review-guidance read-path는 `review_required`, `auto_apply_allowed` 같은 boolish 값을 문자열 false와 stale non-bool shape에 대해 같은 strict 규칙으로 해석하고 있었지만, 구현은 파일별 local helper 중복으로 남아 있었다
- `canonical_boolish.py`에 shared `normalize_strict_boolish(...)`를 추가하고 각 read-path가 이를 직접 재사용하게 맞춰도 현재 preview, blocked guidance, preflight normalization 동작은 그대로 유지됐다
- permissive `bool(value)` 의미를 쓰는 다른 helper와는 일부 의미가 달라 전역 일괄 통합은 하지 않았고, 현재 실제로 같은 strict semantics를 쓰는 경로만 묶었다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_string_false_segment_review_required" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_normalizes_stale_non_bool_review_required_to_false_in_preflight_targeted_segments" -vv` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 strict boolish helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. preview/review-guidance/runtime read-path가 같은 strict boolish normalization 기준을 직접 공유한다
2. string false와 stale non-bool review_required 해석 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 dead helper, 문서 역할 정리, broader 최종 판단 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 197. 2026-07-06 Phase C shared canonical review-status helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `output_operator_copy.py`, `preview_renderer.py`, `review_guidance.py`, `local_pipeline.py`에 흩어져 있던 review-status canonicalizer 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- preview/output/review-guidance/runtime read-path는 모두 `review_status`를 `trim/lower`로 canonicalize해 같은 조건 분기나 surface 문자열에 쓰고 있었지만, 구현은 파일별 local helper 중복으로 남아 있었다
- `canonical_review_status.py`에 shared `canonical_review_status(...)`를 추가하고 각 read-path가 이를 직접 재사용하게 맞춰도 현재 승인/차단/read surface 동작은 그대로 유지됐다
- 이번 정리 중 helper 호출 1곳이 기본값 없이 남아 output-gating에서 즉시 500 회귀가 드러났고, exact 1개 RED로 재현한 뒤 `local_pipeline.py`의 누락 호출만 최소 수정해 같은 slice를 다시 green으로 닫았다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_canonicalizes_mixed_case_review_status_surface" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries" -vv` -> `1 passed`
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_ignores_persisted_approved_guidance_when_synthetic_segment_blocker_makes_status_blocked" -vv` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 canonical review-status helper 공통화와 exact 회귀 복구만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. preview/output/review-guidance/runtime read-path가 같은 review-status canonicalization 기준을 직접 공유한다
2. mixed-case review-status surface와 blocked/draft/approved 판단 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 dead helper나 역할 종료 문서 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 196. 2026-07-06 Phase C shared canonical review-flag helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `prompt_pending_recommendation.py`, `review_action_mutations.py`, `local_pipeline.py`에 흩어져 있던 review-flag code canonicalizer와 valid review-flag set 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- mixed-case review-flag code, valid blocker code, stale unknown blocker filtering 경계는 이미 여러 exact test로 닫혀 있었지만, 구현은 prompt/runtime/review-action이 같은 `trim/lower` 함수와 같은 valid set 상수를 반복해서 들고 있었다
- `canonical_review_flag.py`에 shared `canonical_review_flag_code`와 `VALID_CANONICAL_REVIEW_FLAG_CODES`를 추가하고 각 read-path가 이를 직접 재사용하게 맞춰도 현재 prompt/output/runtime/review-action 동작은 그대로 유지됐다
- 이번 정리는 review/output prompt family, output gating blocker read-path, review guidance reuse key, recommendation approve mutation이 같은 review-flag truth를 더 직접 공유하게 만드는 code cleanup 성격의 수정이다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt` -> `1 passed`
  - `test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline` -> `1 passed`
  - `test_approving_last_pending_recommendation_removes_mixed_case_review_flag_code_for_same_segment` -> `1 passed`
  - `test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 canonical review-flag helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. prompt/output/runtime/review-action read-path가 같은 review-flag canonicalization 기준을 직접 공유한다
2. mixed-case review-flag code와 valid blocker code 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 더 작은 dead helper나 역할 종료 문서 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 195. 2026-07-06 Phase C shared canonical recommendation helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `prompt_pending_recommendation.py`, `preview_renderer.py`, `review_action_mutations.py`, `timeline_builder.py`, `local_pipeline.py`에 흩어져 있던 recommendation type canonicalizer와 valid recommendation set 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- mixed-case recommendation type, unknown recommendation type, approved TTS apply/read-path recommendation type truth는 이미 여러 exact test로 닫혀 있었지만, 구현은 파일별로 같은 `trim/lower` 함수와 같은 valid set 상수를 반복해서 들고 있었다
- `canonical_recommendation.py`에 shared `canonical_recommendation_type`과 `VALID_CANONICAL_RECOMMENDATION_TYPES`를 추가하고 각 read-path가 이를 직접 재사용하게 맞춰도 현재 prompt/output/runtime/timeline/TTS approval 동작은 그대로 유지됐다
- 이번 정리는 review/output prompt family, preview TTS source surface, timeline normalization, review action mutation, runtime restored recommendation read-path가 같은 recommendation truth를 더 직접 공유하게 만드는 code cleanup 성격의 수정이다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` -> `1 passed`
  - `test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source` -> `1 passed`
  - `test_segments_for_timeline_ignores_unknown_track_type` -> `1 passed`
  - `test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type` -> `1 passed`
  - `test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 canonical recommendation helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. prompt/output/runtime/timeline/TTS approval read-path가 같은 recommendation canonicalization 기준을 직접 공유한다
2. mixed-case recommendation type과 valid recommendation set 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 더 작은 dead helper나 역할 종료 문서 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 194. 2026-07-06 Phase C shared canonical track helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `preview_renderer.py`, `output_operator_copy.py`, `local_pipeline.py`, `review_action_mutations.py`에 흩어져 있던 track type canonicalizer와 valid track set 중복을 공통 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- mixed-case narration track type, unknown track type, valid track set 기준은 이미 여러 exact test로 닫혀 있었지만, 구현은 파일별로 같은 `trim/lower` 함수와 같은 set 상수를 반복해서 들고 있었다
- `canonical_track.py`에 shared `canonical_track_type`과 `VALID_CANONICAL_TRACK_TYPES`를 추가하고 각 read-path가 이를 직접 재사용하게 맞춰도 현재 preview/output/runtime/TTS apply 동작은 그대로 유지됐다
- 이번 정리는 review/output gating, TTS approval apply, preflight/runtime segment ordering read-path가 같은 track truth를 더 직접 공유하게 만드는 code cleanup 성격의 수정이다
- editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior는 바꾸지 않았다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source` -> `1 passed`
  - `test_preview_renderer_ignores_unknown_track_type_in_track_summary_surfaces` -> `1 passed`
  - `test_output_operator_copy_builder_canonicalizes_mixed_case_track_type_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_unknown_track_type_in_prompt` -> `1 passed`
  - `test_segments_for_timeline_ignores_unknown_track_type` -> `1 passed`
  - `test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - backend preflight `59 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 canonical track helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. preview, output prompt, runtime segment ordering, approved TTS apply가 같은 track canonicalization 기준을 직접 공유한다
2. mixed-case narration track type과 unknown track type 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 더 작은 dead helper나 역할 종료 문서 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 193. 2026-07-06 Phase C runtime review-required wrapper removal closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `local_pipeline.py`에서 `_normalize_runtime_boolish(...)`를 한 번 더 감싸기만 하던 `_normalize_runtime_review_required(...)` dead wrapper를 제거했다.

이번에 새로 확인된 사실은 아래와 같다.

- 이 wrapper는 별도 규칙을 추가하지 않고 boolish helper를 그대로 한 번 더 호출하기만 하고 있었다
- 실제 사용처도 segment review_required read-path 두 군데뿐이어서, wrapper를 제거해도 현재 runtime normalization 의미는 바뀌지 않았다
- output gating 쪽 `segment_review_required` 합성과 partial regeneration source segment read-path는 그대로 `_normalize_runtime_boolish(...)`를 직접 사용해 현재 동작을 유지했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_editing_session_api_normalizes_legacy_string_false_segment_review_required_from_store` -> `1 passed`
  - `test_editing_session_api_normalizes_string_false_review_required_when_running_partial_regeneration` -> `1 passed`
  - `test_output_jobs_ignore_stale_non_bool_segment_review_required_on_approved_timeline` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - exit code `0`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 runtime review_required dead wrapper 제거만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. local pipeline의 runtime review_required normalization 경로가 dead wrapper 없이 더 직접적인 형태가 됐다
2. output gating과 partial regeneration read-path이 같은 boolish helper를 직접 공유하게 됐다
3. 남아 있는 cleanup 후보는 더 작은 dead helper나 역할 종료 문서 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 192. 2026-07-06 Phase C shared prompt review-flag code helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `output_operator_copy.py`와 `review_guidance.py`에 각각 남아 있던 review-flag code canonicalizer local helper를 공통 모듈로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- 바로 앞 턴에 review-flag identity / row helper를 공통화했어도, 그 helper에 넘기던 `review flag code -> trim/lower` canonicalizer는 두 prompt 파일 안에 각각 남아 있었다
- 현재 동작은 이미 맞았지만, mixed-case review-flag code 기준이 나중에 파일별로 다시 갈라질 수 있는 마지막 local wrapper가 남아 있는 상태였다
- `prompt_pending_recommendation.py`에 shared review-flag code helper를 추가하고 두 prompt 파일이 이를 import alias로 직접 쓰게 맞춰도 현재 prompt surface는 그대로 유지됐다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_minimal_dict_review_flags_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt family review-flag code helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 review-flag code canonicalization 기준도 공통 helper를 직접 공유한다
2. mixed-case review-flag code 기준 drift 위험이 한 단계 더 줄었다
3. 남아 있는 cleanup 후보는 prompt family local helper보다 더 바깥의 dead helper, 역할 종료 문서, 최종 closeout 판단 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 191. 2026-07-06 Phase C shared prompt review-flag helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, `output_operator_copy.py`와 `review_guidance.py`가 각각 들고 있던 review-flag identity / prompt-row 정리 로직을 공통 모듈 helper로 다시 모았다.

이번에 새로 확인된 사실은 아래와 같다.

- pending recommendation 쪽 helper는 이미 공통화됐지만, review flag 쪽은 두 prompt 파일이 여전히 같은 identity 판정과 row 정리 로직을 각자 들고 있었다
- 현재 동작은 이미 맞았지만, valid blocker code / trimmed segment id / default message 기준이 나중에 파일별로 다시 갈라질 수 있는 구조였다
- `prompt_pending_recommendation.py`에 shared review-flag helper를 추가하고 두 prompt 파일이 이를 직접 재사용하게 맞춰도 현재 prompt surface는 그대로 유지됐다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_minimal_dict_review_flags_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt family review-flag helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 review-flag identity / prompt row 기준을 공통 helper로 직접 공유한다
2. valid blocker code, trimmed segment id, default blocker message 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 prompt family review-flag보다 더 바깥의 dead helper, 역할 종료 문서, 최종 closeout 판단 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 190. 2026-07-06 Phase C prompt canonical wrapper removal closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, 바로 앞 턴에 공통 모듈로 옮긴 canonical string helper를 감싸기만 하던 local wrapper 함수를 `output_operator_copy.py`와 `review_guidance.py`에서 제거했다.

이번에 새로 확인된 사실은 아래와 같다.

- `canonical_recommendation_type`, `canonical_decision_state`, `canonical_review_flag_message` 본체는 이미 공통 모듈에 있었지만, 두 prompt 파일 안에는 이름만 다시 감싼 thin wrapper가 그대로 남아 있었다
- 이 wrapper는 동작을 바꾸지 않지만, 앞으로 helper 위치를 읽을 때 탐색 경로를 늘리고 `Phase C` cleanup 관점에서는 dead indirection에 가깝다
- import alias로 직접 연결해도 현재 prompt surface와 blocker counting 동작은 그대로 유지됐다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt family local wrapper 제거만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 canonical string helper를 thin wrapper 없이 공통 모듈에 직접 연결한다
2. prompt family helper 탐색 경로와 dead indirection이 한 단계 줄었다
3. 남아 있는 cleanup 후보는 helper 본체보다 더 바깥의 dead code, 임시 메모, 역할 종료 파일 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 189. 2026-07-06 Phase C shared prompt canonical string helpers closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, output operator copy와 review guidance가 각각 들고 있던 `canonical_recommendation_type`, `canonical_decision_state`, `canonical_review_flag_message` helper를 공통 모듈로 묶었다.

이번에 새로 확인된 사실은 아래와 같다.

- valid set과 identity helper까지 공통화한 뒤에도, canonical string helper 3개는 여전히 두 prompt 파일 안에 같은 본문으로 각각 남아 있었다
- 현재 동작은 이미 맞았지만, mixed-case recommendation type, pending decision state, default review message 기준이 나중에 파일별로 다시 갈라질 수 있는 구조였다
- 그래서 canonical string helper 3개만 공통 모듈로 분리해, prompt family의 기본 string normalization 규칙 drift 가능성을 더 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt family canonical string helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 보는 canonical recommendation type / decision state / default review message 기준이 공통 모듈로 다시 모였다
2. mixed-case recommendation type, pending decision state, default blocker message 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 이전보다 더 작은 helper/파일 정리 쪽으로 더 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 189. 2026-07-06 Korean dashboard display policy closeout

이번 후속 작업에서는 웹 대시보드 한글 UX live smoke 결과를 기준으로, 남는 영어를 `서버 데이터 원문 / ID·URI / UI 고정 문구`로 분류하고 표시 정책을 최상위 계획서에 반영했다.

이번에 새로 확인된 사실은 아래와 같다.

- 로컬 커밋 2개(`fix: localize dashboard copy`, `fix: localize review dashboard notes`)는 원격 `codex/tts-approved-runtime`에 push 완료됐다
- 실제 브라우저 smoke에서 개요/타임라인/검수/편집/B롤 picker/import/제미나이 키 폼의 고정 UI 문구는 한글 단어 중심으로 확인됐다
- 화면에 남는 영어 중 `B-roll Smoke Test`, `Office overview.`, `Team meeting restart.`, `Office team smoke pan`, `smoke-office-pan`은 프로젝트/세그먼트/자산/파일명 원문 데이터다
- `transcription_job_001`, `timeline_002`, `asset_...`, `rec_...`, `local://...`는 추적용 ID/URI다
- 따라서 서버 데이터 원문과 ID/URI는 자동 번역하지 않고 기본 보존하는 것이 맞다
- UI 고정 문구와 상태/작업/검수 코드는 사용자 의미 기준 한글 라벨로 계속 매핑한다

이번 turn의 verification은 아래와 같다.

- push
  - `git push` -> `3c54dd3..4ed7e76 codex/tts-approved-runtime -> codex/tts-approved-runtime`
- policy update
  - `docs/implementation-plan.ko.md`에 `## 7.1. 웹 대시보드 표시 언어 기준` 추가
- judgment
  - 자동 번역은 기본값으로 사용하지 않음
  - 필요한 경우 후속 UX에서 `원문 유지 / 한글 요약 별도 표시 / 원문 보기 토글`을 검토한다

현재 이 단계에서 다음 핵심 남은 일은 아래로 정리된다.

- 문서화된 표시 정책에 맞춰 후속 UI 변경 시 서버 원문과 고정 UI 문구를 계속 구분한다
- 사용자가 실제 편집 중 원문 영어가 불편하다고 판단하면, 자동 번역보다 한글 요약 보조 표시를 먼저 검토한다

## 188. 2026-07-06 Phase C shared prompt valid sets closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, output operator copy와 review guidance가 각각 들고 있던 `VALID_PROMPT_RECOMMENDATION_TYPES`와 `VALID_PROMPT_REVIEW_FLAG_CODES`를 공통 모듈로 묶었다.

이번에 새로 확인된 사실은 아래와 같다.

- 바로 앞 턴에서 canonical identity helper는 공통화했지만, 그 helper가 참조하는 valid recommendation set과 valid blocker code set은 여전히 두 prompt 파일 안에 각각 남아 있었다
- 현재 동작은 이미 맞았지만, mixed-case type, unknown type, valid blocker code 기준이 나중에 파일별로 다시 갈라질 수 있는 구조였다
- 그래서 valid set 상수만 공통 모듈로 분리해, prompt family의 추천 type / blocker code 기준 drift 가능성을 더 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt family valid set 상수 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 보는 valid recommendation type / valid blocker code 기준이 공통 모듈로 다시 모였다
2. mixed-case type, unknown type, valid blocker code 기준 drift 위험이 더 줄었다
3. 남아 있는 cleanup 후보는 이전보다 더 작고 좁은 helper/파일 정리 쪽으로 수렴했다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다

## 187. 2026-07-06 Phase C shared prompt pending identity helper closeout

이번 후속 작업에서는 새 stale-shape 경계를 더 열지 않고, output operator copy와 review guidance가 각각 들고 있던 canonical pending recommendation identity helper를 공통 모듈로 묶었다.

이번에 새로 확인된 사실은 아래와 같다.

- 바로 앞 턴에서 row normalization helper는 공통화했지만, `recommendation_id + target_segment_id + canonical recommendation_type` identity 판별 helper는 여전히 두 prompt 파일 안에 각각 남아 있었다
- 현재 동작은 이미 맞았지만, minimal dict, mixed-case type, unknown type을 거르는 identity 기준이 나중에 파일별로 다시 갈라질 수 있는 구조였다
- 그래서 boolish 의미 차이처럼 실제 의미가 다른 부분은 그대로 두고, canonical identity 판별 helper만 공통 모듈로 분리해 review/output prompt family의 identity 규칙 drift 가능성을 더 줄이는 쪽이 현재 `Phase C`에 가장 맞는 최소 리팩터링이라고 판단했다
- 이번 정리는 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 바꾸지 않는 code cleanup 성격의 수정이다

이번 turn의 verification은 아래와 같다.

- exact verification
  - `test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
  - `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` -> `1 passed`
  - `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` -> `1 passed`
  - `test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - backend output-gating `24 passed`
- broader verification
  - 이번 turn에서는 재실행하지 않음
  - 판단:
    - 이번 변경은 prompt pending recommendation canonical identity helper 공통화만 다루는 `Phase C` 소규모 리팩터링이다
    - 현재 자동 baseline은 직전 closeout 기준 `frontend build 성공`, `full backend regression 543 passed`를 유지한다

이 갱신으로 아래 범위는 현재 기준으로 정리됐다.

1. output operator copy와 review guidance가 보는 pending recommendation canonical identity 기준이 공통 모듈로 다시 모였다
2. minimal dict, mixed-case type, unknown type filtering 기준 drift 위험이 더 줄었다
3. review/output prompt family에서 남은 cleanup 후보는 이전보다 더 작고 좁은 범위로 줄었다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힌다
- 역할이 끝난 중복 메모 문서는 삭제보다 역할 명시가 맞는지 먼저 판단한다
- 최종 closeout 직전 broad 재검증이 정말 필요한지 마지막으로 판단한다
