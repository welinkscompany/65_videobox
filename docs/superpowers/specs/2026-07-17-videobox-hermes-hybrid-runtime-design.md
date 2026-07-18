# VideoBox Hermes Hybrid Runtime and Local Container Design

**Date:** 2026-07-17
**Status:** direction approved; execution boundary is superseded by `docs/implementation-plan.ko.md` §23 (2026-07-19)
**Scope:** 유진 대화형 영상 제작, 전용 Hermes 실행 경계, mem0 보조 기억, 로컬 Qwen/BGE 역할 분리, 향후 SaaS 전환 경계

## 1. 결정

VideoBox의 사용자 대화와 영상 기획을 담당하는 에이전트는 `유진`이다. 유진의 주 창작·대화 추론은 VideoBox 전용 Hermes profile인 `yujin-video-director`가 맡는다. 현재 로컬 Qwen은 제거하지 않고, 원본 미디어를 외부로 보내지 않는 저비용 배경 분석과 제한된 구조화 보조 작업에 사용한다.

로컬 배포는 VideoBox와 Hermes를 하나의 container process에 섞지 않고, 하나의 `65_videobox` Docker Compose 제품 스택 안에서 독립 서비스로 운영한다. release-local profile은 VideoBox web/API/render worker, Hermes, mem0와 보안 gateway를 함께 시작한다. 개발 중 hot reload profile은 web/API를 호스트에서 실행할 수 있지만 최종 로컬 사용자 실행 단위는 Compose 스택이다.

Windows GPU와 desktop integration이 필요한 다음 두 경계만 호스트에 남긴다.

- LM Studio `127.0.0.1:1234`: Qwen Vision/Text와 BGE-M3 실행
- `videobox-host-bridge`: container가 직접 Windows 전체를 보지 않고 LM Studio와 CapCut Desktop 진단·등록만 요청하는 최소 권한 helper

FFmpeg/ffprobe는 network와 application secret이 없는 `videobox-render-worker` image에 포함한다. VideoBox API는 편집 truth와 job orchestration을 맡고 untrusted media parsing은 worker에 넘긴다. CapCut Desktop 자체와 LM Studio를 Linux container에 억지로 넣지 않는다.

AK-System Hermes, 직원 identity, mem0 database, volume, credential은 재사용하지 않는다. 재사용 대상은 검증된 Hermes image와 배포 패턴뿐이다.

## 2. 판단 근거와 기각한 대안

### 2.1 Qwen 단독

비용과 개인정보 측면에서는 가장 유리하지만, 인터뷰·콘셉트·대본·장면 구성·최종 비평처럼 모호성이 큰 작업의 영상 품질을 현재 테스트가 보장하지 않는다. 기존 테스트는 구조화 JSON, 로컬 vision tag, embedding 동작을 증명할 뿐 실제 한국어 유튜브 초안의 창작 품질을 증명하지 않는다. 따라서 주 창작 두뇌로 고정하지 않는다.

### 2.2 Hermes 단독

대화 품질은 기대할 수 있지만, 모든 프레임 태깅과 대량 분류까지 외부 모델에 맡기면 OAuth quota, 네트워크 의존, 개인정보 노출과 지연이 커진다. 로컬 GPU와 이미 동작하는 Qwen/BGE 자산도 낭비한다. 따라서 고영향 판단에 집중한다.

### 2.3 계층형 하이브리드

Hermes는 사용자 대화와 창작 결정을, Qwen은 검증된 저위험 배경 작업을, BGE와 deterministic code는 검색·검증·편집 실행을 담당한다. 품질과 비용을 분리 측정할 수 있고 향후 SaaS fork에서도 provider adapter만 교체할 수 있으므로 이 방식을 채택한다.

## 3. 목표와 비목표

### 목표

1. 사용자가 VideoBox 안에서 유진과 대화하며 영상 목적과 스타일을 인터뷰한다.
2. 유진은 실제 프로젝트·자산·편집 상태를 typed tool로 조회하고 적용 가능한 초안을 제안한다.
3. 모든 편집 변경은 기존 proposal, preflight, explicit approval, atomic revision mutation을 거친다.
4. Qwen 사용 범위를 품질 근거에 따라 제한하고 paid Hermes 호출을 줄인다.
5. mem0는 취향과 반복 작업 선호만 보조 기억하고 VideoBox의 사실 저장소를 대체하지 않는다.
6. 이후 SaaS fork에서 고객별 OAuth/provider와 tenant storage로 교체할 수 있는 경계를 만든다.

### 비목표

- 이번 설계 단계에서 컨테이너나 Hermes 연동 코드를 생성·실행하는 것
- 사용자의 승인 없이 유진이 timeline 또는 output을 변경하는 것
- AK-System Hermes identity, session 또는 mem0 data를 VideoBox와 공유하는 것
- 현재 로컬 버전에서 multi-tenant SaaS auth, billing, team 기능을 구현하는 것
- owner 한 명의 OAuth를 여러 SaaS 고객에게 공유하는 것
- CapCut을 주 편집기로 바꾸는 것
- LM Studio GPU runtime 또는 CapCut Desktop 자체를 Linux container로 옮기는 것

## 4. 전체 구조

```text
Browser
  │  loopback HTTP/SSE
  ▼
videobox-web container
  │  internal network
  ▼
videobox-api container
  ├─ Agent Gateway ───────────────> videobox-hermes-agent
  │    ├─ durable run/event log          │
  │    ├─ host-mediated tool loop        ▼
  │    └─ typed proposal validator   videobox-hermes-egress ──> approved OAuth provider
  ├─ MemoryPolicyAdapter ──> videobox-memory-gateway ──> videobox-mem0-api ──> mem0-postgres
  ├─ Editing-session / asset / conversation SSOT
  ├─ signed render job spool ─────> videobox-render-worker
  ├─ host-visible managed data root
  └─ HostIntegrationPort ──> videobox-host-bridge-egress ──> videobox-host-bridge on Windows
                                          ├─ exact LM Studio loopback
                                          ├─ user-initiated import picker/staging
                                          └─ CapCut diagnostics/registration
```

브라우저는 Hermes나 mem0를 직접 호출하지 않는다. 브라우저가 보는 대화 protocol은 VideoBox API의 project-scoped SSE다. VideoBox backend는 Hermes 응답이 native streaming인지 완성 응답인지와 무관하게 같은 event contract를 제공한다.

Hermes는 VideoBox database나 media directory에 직접 접근하지 않는다. Hermes가 반환한 tool-call event를 Agent Gateway가 검증하고 같은 `videobox-api` process 안의 typed handler를 실행한 뒤 결과만 Hermes에 돌려준다. 따라서 container→Windows API callback이나 Hermes용 bearer endpoint를 만들지 않는다. editing mutation의 최종 권한은 계속 VideoBox backend에 있다.

## 5. 로컬 컨테이너 토폴로지

release Compose project 이름은 `65_videobox`로 고정한다. dev/test는 `65_videobox-dev-<worktree-hash>`와 `65_videobox-test-<run-id>`처럼 충돌 없는 ephemeral suffix를 사용하고 release external volume을 연결하지 않으며 test 종료 때 자체 volume/network를 제거한다.

| Service | 역할 | host 노출 | 영속 데이터 |
|---|---|---|---|
| `videobox-web` | production frontend와 `/api` reverse proxy | `127.0.0.1:${VIDEOBOX_WEB_PORT:-5173}` | 없음 |
| `videobox-api` | API, durable jobs, editing/output domain과 artifact 검증·승격 | internal only; debug profile만 loopback | host-visible managed `VIDEOBOX_DATA_ROOT` bind |
| `videobox-render-worker` | FFmpeg/ffprobe, thumbnail/waveform/preview/final media job | host/network 미노출 | read-only managed input, isolated staging output와 signed job spool |
| `videobox-hermes-agent` | 유진 agent runtime과 OAuth-backed creative reasoning | internal only; debug profile만 loopback | `videobox-hermes-state`, read-only pinned skill bundle |
| `videobox-hermes-egress` | Hermes OAuth/provider 전용 egress | host 미노출 | versioned provider allowlist/log policy |
| `videobox-host-bridge-egress` | VideoBox API→Windows host bridge 전용 egress | host 미노출 | pinned bridge address/certificate policy |
| `videobox-memory-gateway` | API의 approved memory operation만 mem0로 전달 | host 미노출 | versioned schema/budget policy |
| `videobox-mem0-api` | 선택적 기억 저장·검색 | internal only | 없음 |
| `videobox-mem0-postgres` | mem0 전용 PostgreSQL/pgvector | host 미노출 | `videobox-mem0-postgres-data` |

Hermes와 mem0를 포함한 모든 image는 `latest`가 아니라 검증한 version 또는 digest로 pin한다. OAuth credential은 repository, compose YAML, 일반 `.env`에 넣지 않는다. Hermes가 요구하는 `auth.json`은 전용 `videobox-hermes-state`에 container UID 소유와 mode `0600`으로 저장하고, 암호화된 host disk 사용 여부를 startup에서 확인하며 backup/export에서 제외한다. OAuth logout/revoke는 이 사본과 Hermes session을 함께 삭제한다.

OAuth 연결은 launcher가 `docker compose --profile auth run --rm hermes-auth-bootstrap`으로 실행하는 공식 Hermes device/PKCE login flow만 사용한다. bootstrap service는 전용 state volume만 mount하고 inbound debug port 없이 verification URL/code를 launcher에 반환한다. AK-System, Codex 또는 다른 Hermes의 `auth.json`을 복사·공유하지 않는다. logout/revoke verifier는 bootstrap container 종료 뒤 state volume의 active token과 session이 0임을 확인한다.

`videobox-web`만 기본 host port를 loopback에 bind한다. API, worker, Hermes, mem0와 PostgreSQL은 host에 노출하지 않는다. `app-internal`, `memory-api-side`, `memory-store-side`, `hermes-provider-egress`, `api-host-bridge-egress` network를 분리한다. 각 egress service는 서로 다른 network/listener와 workload mTLS identity를 사용하므로 Hermes가 API의 host-bridge route를 사용할 수 없다. PostgreSQL은 memory-store network에서 mem0 API만 접근한다. Hermes에는 mem0 credential과 direct service route를 주지 않고, VideoBox의 `MemoryPolicyAdapter`가 검색·승인된 write를 중개한다.

mem0는 별도 `app_id=videobox-yujin`, secret file, network와 volume key를 사용한다. `AUTH_DISABLED=false`, strong local service credential, telemetry off, 모든 model/cloud key absent를 fail-start 조건으로 둔다. VideoBox가 승인된 memory text와 BGE vector를 먼저 만들고 `MemoryStorePort`가 add/search/update/delete만 호출한다. mem0는 model inference, extraction과 embedding을 하지 않는 storage-only sidecar이며 direct external egress가 없다. 현재 mem0 distribution이 raw text/vector storage를 지원하지 않으면 narrow VideoBox wrapper에서 그 기능만 구현하고 일반 mem0 model endpoint는 노출하지 않는다.

`videobox-hermes-egress`는 pinned OAuth/provider host manifest만, `videobox-host-bridge-egress`는 정확한 bridge address/port만 허용한다. application client는 redirect 자동 추적을 끄고 각 `Location`을 allowlist로 다시 검증해 새 연결을 요청한다. egress는 새 목적지 연결을 별도로 검사하고 unknown DNS/redirect, IP literal, loopback, RFC1918, link-local, metadata, Docker socket과 다른 local service를 차단한다. host bridge의 단일 private-address 예외는 resolved address, port와 mTLS certificate를 startup manifest에 pin한다.

모든 container는 non-root, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, bounded CPU/memory/PID/log, tmpfs 임시공간을 기본으로 한다. Docker socket, repository 전체, Windows home, CapCut root와 media library 전체를 mount하지 않는다. `%LOCALAPPDATA%\VideoBox\data`를 기본 `VIDEOBOX_DATA_ROOT`로 만들고 API에는 관리 root만 `/videobox-data`에 read-write bind한다. render worker는 project input을 read-only로, job별 staging output만 read-write로 받으며 application DB, OAuth, mem0와 host-bridge secret에 접근하지 않는다. API는 worker result manifest, content SHA와 media probe를 검증한 뒤에만 artifact를 canonical root로 승격한다.

호스트의 `videobox-host-bridge`는 Docker Desktop gateway interface에만 listen하고 Windows Firewall로 LAN 접근을 거부한다. 정확한 LM Studio `127.0.0.1:1234` proxy, 사용자 앞에서 여는 native import picker/staging, CapCut diagnostics/registration command만 제공하며 shell, container가 문자열로 지정한 임의 path와 일반 HTTP proxy 기능은 없다. bridge request는 짧은 TTL, audience, nonce와 operation allowlist를 가진 서명 token을 요구하고 replay를 거부한다.

`VideoBox 시작` launcher는 host bridge를 hidden process로 시작하고, `docker compose up -d`, aggregate health check와 브라우저 열기를 한 번에 수행한다. `VideoBox 종료`는 bridge와 Compose를 정상 종료하되 persistent volume은 보존한다.

### 5.1 로컬 파일 ingest

release-local profile은 기존 API의 raw Windows `source_path/source_paths`를 browser나 agent 입력으로 받지 않는다. 기본 ingest는 API가 one-time import grant를 만들고 host bridge가 native Windows file/folder picker를 사용자에게 보여주는 방식이다. 사용자가 직접 선택한 항목만 bridge가 관리 root의 `imports/staging/<import_id>`로 복사한다. headless recovery를 위해 browser chunk upload도 같은 staging contract로 들어오게 하며 두 경로의 authoritative 결과는 동일하다.

staging은 허용 extension/MIME, file count와 total byte limit, reparse point/symlink, traversal, duplicate name과 free-space를 먼저 검사한다. 원본을 열기 전 identity/size/mtime을 기록하고 temporary copy의 streaming SHA-256을 계산한 뒤 원본을 다시 확인한다. 원본이 바뀌었거나 copy SHA가 맞지 않으면 폐기한다. 성공한 파일만 project-local asset root로 atomic rename하고 기존 asset registration/provenance contract를 실행한다. container가 사용자의 임의 host 폴더를 runtime에 새로 mount하지 않는다.

### 5.2 Container와 Windows path 계약

모든 durable media reference는 project-relative storage URI와 content SHA를 canonical truth로 사용한다. `/videobox-data/...` Linux path나 `C:\...` Windows path를 DB/timeline truth로 저장하지 않는다.

- FFmpeg와 API file IO: `ContainerPathResolver`가 storage URI를 `/videobox-data/projects/...`로 해석한다.
- CapCut draft material: `HostPathResolver`가 같은 URI를 `%LOCALAPPDATA%\VideoBox\data\projects\...` Windows path로 해석한다.
- host bridge registration: host-visible export tree와 material path가 관리 root 안에 있고 SHA가 current source와 일치하는지 다시 확인한 뒤 CapCut project root로 copy한다.

PyCapCut output에는 container absolute path가 한 건도 없어야 한다. path mapping은 draft JSON의 사후 문자열 치환이 아니라 export adapter의 typed resolver에서 수행한다. bridge는 canonical source draft를 임의 수정하지 않고 verified registered copy만 만든다.

CapCut registration request는 Windows path 문자열 대신 VideoBox DB에 등록된 opaque artifact ID만 보낸다. 짧은 수명의 bridge token은 operation, artifact ID, request body hash, audience, nonce와 expiry를 묶고 bridge가 ID를 managed root의 canonical path로 직접 해석한다. UNC/device path, `..`, root 밖 absolute path, junction/reparse point와 copy 전후 file identity/SHA 불일치는 거부한다. TOCTOU fixture는 검증 직후 source가 바뀌면 registration을 fail-closed하게 만든다.

## 6. Identity와 session 경계

- 사용자 표시명: `유진`
- 내부 profile ID: `yujin-video-director`
- compose project: `65_videobox`
- local tenant ID: `local`
- 대화 scope: `tenant_id + user_id + project_id + conversation_id`
- tool authorization scope: authoritative run의 `tenant_id + user_id + project_id + conversation_id + allowed_action_family`

AK-System의 `ai-louis` 또는 다른 직원 profile을 사용하지 않는다. 동일한 공식 Hermes code/image를 쓰더라도 home volume, OAuth session, skill directory, mem0 namespace와 audit log는 분리한다.

`/videobox-data/system/installation.sqlite`가 installation identity와 project ownership registry의 authoritative store다. 첫 실행에서 installation UUID, `tenant_id=local`과 stable owner user UUID를 한 번 생성한다. 개별 프로젝트의 `projects/<project_id>/db/project.sqlite`는 계속 해당 project의 editing/conversation truth다.

관리 root 안의 기존 owner 없는 project는 migration audit를 남기고 현재 installation owner에 한 번 bind한다. 외부에서 가져온 project는 먼저 새 managed root로 복사·검증하고 embedded owner를 신뢰하지 않으며 사용자의 명시적 import 확인 뒤 현재 owner에 bind한다. project ID 충돌은 자동 덮어쓰지 않는다. 각 project conversation은 migration에서 `tenant_id=local`과 registry owner user ID로 backfill한다. raw internal ID는 외부 모델에 전달하지 않고 run-scoped opaque handle로 바꾼다.

## 7. Agent Gateway 계약

VideoBox backend에 provider-neutral `CreativeDirectorPort`를 둔다.

```python
class CreativeDirectorPort(Protocol):
    def capabilities(self) -> DirectorCapabilities: ...
    def start(self, request: DirectorRequest) -> DirectorRunHandle: ...
    def events(self, run_id: str, after_cursor: int) -> Iterable[DirectorEvent]: ...
    def continue_with_tool_result(self, run_id: str, tool_call_id: str, result: ToolResult) -> None: ...
    def cancel(self, run_id: str) -> None: ...

class LocalAnalysisPort(Protocol):
    def analyze_media(self, request: MediaAnalysisRequest) -> MediaAnalysisResult: ...
    def propose_keywords(self, request: KeywordRequest) -> KeywordResult: ...
```

`DirectorRequest`에는 raw database object 대신 다음 최소 문맥만 포함한다.

- run-scoped opaque user/project/conversation handle
- 현재 대본 또는 선택한 대본 구간
- 영상 목적, 시청자, 길이, 분위기와 output profile
- run-scoped opaque editing-session/segment/placement handle과 base revision
- tool로 다시 조회할 수 있는 proposal/asset stable reference
- 프로젝트의 cloud-media policy

`DirectorResponse`는 자유 텍스트만 반환하지 않는다. 사용자 설명과 함께 typed `question`, `proposal_request`, `action_intent`, `no_action`, `blocked` 중 하나를 반환한다. schema가 맞지 않거나 존재하지 않는 asset/reference를 가리키면 저장 가능한 제안으로 승격하지 않는다.

VideoBox DB의 `director_agent_runs`가 remote 실행의 authoritative ledger다. 최소 필드는 `run_id`, tenant/user/project/conversation, immutable user message ID와 input hash, base editing-session revision, Hermes session/run mapping, status, lease/finalize fence, event cursor, consent/audit reference, final response ID와 error code다. status는 `queued`, `running`, `waiting_tool`, `succeeded`, `blocked`, `failed`, `cancelled`를 사용한다.

`conversation_id + user_message_id`는 unique다. Hermes session은 재개를 위한 projection/cache일 뿐 transcript truth가 아니다. container restart 뒤 completed run은 저장된 결과를 재사용하고, expired running lease는 Hermes가 같은 run을 resume할 수 있을 때만 이어간다. resume을 증명할 수 없으면 `interrupted` 성격의 blocked/failed 상태로 전환해 사용자 재시도를 요구하며 paid request를 몰래 다시 보내지 않는다.

각 Hermes tool-call은 `run_id + tool_call_id` unique result를 가진다. Agent Gateway는 run ledger의 project/revision/allowed-tool scope로 handler를 선택하고 모델이 보낸 raw ID나 scope를 권한 근거로 사용하지 않는다. 같은 tool-call retry는 저장된 result를 반환한다.

Browser SSE event는 최소한 `message_delta`, `tool_started`, `tool_finished`, `proposal_ready`, `blocked`, `completed`, `failed`를 구분한다. event는 브라우저 전송 전에 VideoBox DB에 cursor와 함께 저장한다. reconnect는 cursor와 immutable user message ID로 이미 확정된 event/result를 복구하며 같은 user message를 다시 실행하지 않는다. 중간에 끊긴 stream이나 schema-invalid final frame은 proposal로 승격하지 않는다.

## 8. 대화에서 편집까지

1. 사용자가 유진에게 대본이나 요청을 보낸다.
2. Agent Gateway가 VideoBox project truth와 허용된 mem0 preference만 조합한다.
3. routing policy가 Hermes creative route 또는 local helper background route를 결정하고 근거를 run ledger에 기록한다.
4. Hermes가 자산 검색, 현재 편집 상태, output readiness 같은 read-only `tool_request` event를 반환한다.
5. Agent Gateway가 같은 `videobox-api` process의 allowlisted handler를 실행하고 opaque result를 Hermes run에 돌려준다. container→host callback은 없다.
6. 완전하고 schema-valid한 Hermes final response만 immutable proposal 또는 action intent 후보로 정확히 한 번 저장된다. 이 시점의 editing mutation은 0이다.
7. VideoBox backend가 asset 존재, rights warning, source SHA, session revision, placement collision과 output 영향을 deterministic preflight로 검증한다.
8. 사용자가 화면에서 변경 범위와 미리보기를 확인하고 명시적으로 승인한다.
9. 승인 endpoint만 하나의 revisioned atomic mutation을 실행한다. 실패하면 부분 적용하지 않는다.
10. 성공한 결과는 undo/redo history에 남고 review/output freshness를 기존 규칙대로 갱신한다.

Hermes는 최종 renderer, filesystem copy, database write 또는 CapCut registration tool을 직접 가지지 않는다. export는 기존 VideoBox output flow에서 별도 사용자 승인으로만 실행한다.

## 9. 허용 tool surface

초기 embedded-Yujin tool allowlist는 다음으로 제한한다. 이 surface는 network MCP server가 아니라 Agent Gateway 내부 handler registry다.

### Read-only

- 현재 프로젝트 목적·대본·output profile 조회
- 현재 editing-session/revision/selection 조회
- project-local asset 검색과 candidate preview metadata 조회
- proposal, gap slot, review/output readiness 조회
- B-roll/BGM/SFX availability와 rights status 조회

### Finalization-only

- 완전한 final response에서 인터뷰 project brief candidate를 idempotent하게 저장
- 완전한 final response에서 B-roll/BGM/SFX/caption/overlay proposal을 idempotent하게 생성
- draft generation deterministic preflight 실행

### 금지

- 임의 SQL, shell, filesystem browse/write
- media 원본 upload 또는 외부 전송
- timeline direct mutation
- review 자동 승인, final render 자동 실행, CapCut 자동 등록
- credential, environment variable, 다른 project/conversation 조회

향후 새 tool은 threat review, project isolation test, idempotency test와 explicit approval semantics가 없으면 allowlist에 추가하지 않는다.

기존 외부 자동화용 MCP surface는 별도 제품 경계다. embedded Yujin은 그 network endpoint와 coarse-grained create/render/export tool을 사용하지 않는다. 두 경계가 재사용하는 것은 pure request validator와 domain service뿐이다. 향후 remote MCP를 다시 열 경우 `tenant/user/project/conversation/run/base_revision/allowed_tools/audience/nonce/exp`를 묶은 짧은 수명의 서명 capability와 replay 방지를 별도로 설계한다.

## 10. Hermes, Qwen, BGE, deterministic code 역할

| 작업 | 기본 실행자 | Qwen 허용 | 적용 규칙 |
|---|---|---|---|
| 유진 인터뷰와 자유 대화 | Hermes | 자동 대체 금지 | Hermes unavailable이면 명시적 offline 상태 |
| 콘셉트, hook, 구성, 대본 개선 | Hermes | shadow 비교만 | 결과는 사용자 선택 전 draft |
| 장면 계획과 부족 자산 설명 | Hermes | first-pass 후보 생성 가능 | 실제 asset grounding과 preflight 필수 |
| B-roll/BGM/SFX 최종 top-N rerank | Hermes + deterministic eligibility | 1차 후보 확장 가능 | 사용자 explicit apply 필수 |
| 대표 프레임 태그·설명 | local Qwen Vision | 실행·파생결과 저장 허용 | provenance/confidence 저장, qualification 전 review-only |
| 대량 구조화 분류·키워드 후보 | local Qwen | qualification 뒤 허용 | ranking signal일 뿐 placement truth 아님 |
| embedding | BGE-M3 | 해당 없음 | vector + lexical fallback, deterministic tie-break |
| duration/SHA/codec/scene 추출 | FFmpeg/deterministic code | 금지 | authoritative technical metadata |
| rights/availability/revision 검사 | deterministic code | 금지 | fail-closed |
| timeline mutation/render/export | VideoBox domain code | 금지 | 승인·revision·freshness gate 유지 |

Qwen은 Hermes OAuth 장애 시 사용자에게 알리지 않고 유진인 것처럼 답하지 않는다. 반대로 Qwen이 꺼져도 Hermes 대화, lexical search와 수동 편집은 계속 가능해야 한다.

현재 Qwen이 연결된 B-roll keyword expansion처럼 실제 자산 선택에 영향을 주는 경로는 새 routing policy 아래 `candidate signal`로 강등한다. Qwen 결과만으로 timeline에 자동 적용하는 경로는 두지 않는다.

Qwen task가 qualification을 통과하기 전에는 실행과 provenance-bearing 파생결과 저장만 허용한다. free-text summary와 keyword는 Hermes prompt, 검색 ranking 또는 자동 eligibility 판단에 사용하지 않는다. 사람에게 승인된 structured tag와 deterministic technical metadata만 사용할 수 있다. qualification은 task별로 열며 한 task의 통과를 다른 Qwen route에 확대 적용하지 않는다.

## 11. Media privacy policy

기본값은 `cloud_media_policy=text_only`다. 이는 binary media를 보내지 않는다는 뜻이지 개인정보가 없다는 뜻은 아니다. 프로젝트에서 Hermes를 처음 켤 때 대본·brief·승인된 asset tag가 외부 provider로 전송됨을 설명하고 project-scoped consent를 먼저 저장한다. consent/audit 저장이 실패하면 외부 요청을 보내지 않는다.

cloud payload는 허용 필드 schema를 사용한다. 대본과 사용자가 입력한 brief, 사람 승인 또는 qualification을 통과한 tag/summary, 필요한 기술 metadata만 허용한다. local path, filename, EXIF, credential, raw database ID와 불필요한 인물·위치 metadata는 제거하고 stable reference는 run-scoped opaque handle로 바꾼다. 사용자는 전송 전 payload category를 확인할 수 있고 project 설정에서 consent를 철회할 수 있다.

`selected_previews` cloud 전송은 초기 구현에서 제외하고 별도 후속 설계로 둔다. 구현할 때도 loopback URL을 외부 provider에 넘기지 않고, 사용자가 선택한 저해상도 payload만 egress를 통해 bounded direct upload한다. 전송 대상, content hash, 목적, provider 보관·삭제 증거와 consent 시각을 audit에 남기며 전체 media library 일괄 전송은 허용하지 않는다.

대본, asset metadata, mem0 text와 model output은 모두 신뢰할 수 없는 data로 취급한다. system/tool instruction과 분리된 typed field로 전달하고, 그 안의 명령문이 tool scope나 routing policy를 바꾸지 못하도록 prompt-injection fixture를 둔다.

## 12. mem0의 역할과 별도 database

mem0는 Hermes의 보조 기억장치이며 VideoBox SSOT가 아니다.

### 저장 가능한 기억

- 사용자가 명시적으로 기억해 달라고 한 채널·톤·길이·금지 요소
- 여러 프로젝트에서 반복 확인된 편집 선호
- 사용자가 승인한 고정 브랜드 표현과 작업 습관
- 기억의 source conversation, 생성 시각, 마지막 확인 시각

### 저장하지 않는 정보

- current timeline, session revision, proposal 또는 output readiness
- asset catalog, source path, SHA, rights truth
- 전체 대본·원본 미디어·음성 파일
- OAuth token, API key, credential
- 시스템 prompt, 내부 tool response 전체

memory write는 명시적 `기억해줘` 또는 정책상 허용된 성공 행동 뒤의 후보 생성으로 나뉜다. 자동 후보는 먼저 VideoBox DB의 검토 가능한 candidate로 저장하고 사용자 또는 명시된 promotion policy가 승인한 뒤에만 mem0에 기록한다. 사용자는 candidate와 실제 memory를 삭제·수정·전체 초기화할 수 있어야 한다. 삭제는 vector, history index와 retention 대상 backup/tombstone 정책까지 같은 memory ID로 추적한다. memory read 결과는 preference hint로만 사용하며 현재 project truth와 충돌하면 VideoBox DB가 이긴다.

자산 태그와 의도 검색도 database가 필요하지만 mem0 database를 사용하지 않는다. asset metadata, embedding, provenance와 index revision은 VideoBox asset/search store에 둔다. editing-session과 output은 기존 VideoBox durable store가 authoritative하다.

| 정보 | authoritative store |
|---|---|
| installation/tenant/local owner와 project ownership registry | `/videobox-data/system/installation.sqlite` |
| 프로젝트, 대본, editing session, revision | VideoBox DB |
| asset 등록, 태그, SHA, rights, embedding, index revision | VideoBox asset/search store |
| 원본·preview·render artifact | managed `VIDEOBOX_DATA_ROOT`의 project-local storage |
| 대화 transcript와 proposal/action intent | VideoBox DB |
| 사용자 장기 선호 | VideoBox 전용 mem0 |
| Hermes OAuth/session runtime state | `videobox-hermes-state` |
| Yujin skill/prompt/policy source | repository의 versioned bundle + manifest |

mem0 장애는 편집과 대화를 막지 않는다. 해당 요청에서는 project context만 사용하고 `장기 기억 사용 불가` 상태를 audit에 남긴다.

## 13. Skill 학습 구조

유진이 매 작업마다 자신의 실행 code를 자동 변경하는 구조는 사용하지 않는다. 학습은 세 층으로 나눈다.

1. **Preference memory:** mem0에 저장되는 사용자 선호
2. **Evidence log:** proposal, 사용자 선택·거절, 수정량, undo, output 승인 결과
3. **Versioned skill:** 반복 근거를 사람이 검토해 repository의 versioned skill/prompt/policy로 승격

새 skill version은 fixture replay, 안전성 검사, quality benchmark를 통과한 뒤 활성화한다. 실패하면 이전 version으로 rollback한다. 사용자 행동 한 번을 일반 규칙으로 즉시 승격하지 않는다.

repository의 versioned bundle과 manifest SHA가 skill SSOT다. Hermes container에는 검증한 bundle을 read-only mount하고 writable state volume의 skill copy는 authoritative하게 읽지 않는다. startup capability probe는 shell, filesystem, browser, Docker와 승인되지 않은 built-in tool이 로드되지 않았음을 검사하며 allowlist 밖 capability가 보이면 fail-start한다. AK-System compose의 `latest`, `AUTH_DISABLED=true`, static password, workspace/vault broad mount 패턴은 복사하지 않는다.

## 14. 품질·비용 qualification gate

Qwen의 역할 확대는 느낌이 아니라 같은 입력에 대한 shadow evaluation으로 결정한다.

### 평가 corpus

- 한국어 segment-level microtask 80개: 인터뷰, 장면 계획, B-roll 검색어/후보, 음악/SFX 선택, 최종 초안 비평을 균형 있게 포함
- tutorial, 제품 설명, 사실형 해설, story형 실제 3–5분 프로젝트 각 3개, 총 12개
- model/profile, prompt/schema, skill, asset pool과 renderer version을 freeze한 A/B/C fixture
- 한국어 평가자 3명의 blind rubric과 25% 반복 표본

### 기록 지표

- schema-valid rate와 bounded retry 수
- 존재하지 않는 asset/reference 생성 건수
- B-roll top-5 usable hit rate와 반복률
- 사용자 채택, 교체, undo, correction time
- blind human score: 관련성, 자연스러움, 일관성, publishability
- p50/p95 latency, provider call 수, token/quota, retry, 로컬 처리 시간
- 원본 media 또는 credential 외부 전송 여부
- GPU 전력, OAuth 구독 배분, 실패/재시도와 사람 correction time을 포함한 총 유효비용

### Qwen route 활성화 조건

- 평가 corpus에서 critical defect 미관측: fabricated asset/URI, rights 우회, cross-project reference, 승인 없는 mutation
- fixed schema success 98% 이상 after at most one bounded retry
- grounding precision 95% 이상
- 평균 human score가 같은 task의 Hermes 기준 대비 0.5/5점 이상 낮지 않음
- correction time이 Hermes 기준보다 10% 이상 악화되지 않음
- 해당 저위험 task의 paid Hermes call을 25% 이상 줄임

각 metric은 task별 표본 수와 95% confidence interval을 함께 보고한다. OAuth subscription의 call 감소를 현금 절감으로 단정하지 않고 quota 여유와 총 유효비용을 따로 표시한다.

조건을 만족하지 못하면 Qwen은 local tag/summary의 `needs_review` 또는 shadow-only 상태로 유지한다. 조건을 만족해도 timeline, review와 output의 auto-apply 권한은 주지 않는다.

## 15. Network, secret, permission 정책

- 일반 unit/API/E2E는 deterministic fake providers와 socket guard를 사용하고 external HTTP(S), Gemini, Hermes OAuth call이 모두 0이어야 한다.
- LM Studio live smoke는 host bridge가 exact host loopback `127.0.0.1:1234`만 호출하는 별도 opt-in profile에서 허용한다.
- Hermes OAuth live smoke는 명시적 opt-in test/profile에서만 실행하고 provider route와 call count를 audit한다.
- Gemini는 기본, fallback, test 어느 경로에서도 사용하지 않는다.
- Hermes direct egress는 network에서 제거하고 pinned egress proxy만 사용한다. proxy는 매 DNS 결과와 redirect를 다시 검증한다.
- OAuth bootstrap은 전용 one-shot Hermes device/PKCE login/refresh flow만 사용한다. 다른 runtime의 credential import는 금지하며 token file permission, encrypted disk, backup exclusion을 검증하지 못하면 Hermes route를 fail-start한다.
- mem0는 인증 없이 기동하지 않고 OpenAI/Gemini provider, cloud key와 telemetry가 감지되면 fail-start한다.
- service/DB/host-bridge secret은 generated Docker secret 또는 ACL-protected gitignored secret file로 주입하고 일반 environment dump에 포함하지 않는다.
- 기본 Hermes budget은 connect 10초, first event 60초, total 300초, text context 1MiB, 개별 tool result 256KiB와 read-only tool 15초다. 더 작은 task budget은 versioned manifest로만 줄일 수 있다. model transport retry는 첫 event 전에 같은 run/idempotency key로 최대 1회, read-only tool retry만 허용하며 proposal/apply mutation은 자동 retry하지 않는다. rate limit과 첫 event 뒤 단절은 자동 재호출하지 않는다.
- 한 run은 model turn 8회, tool-call 12회, durable event 256개, 누적 assistant output 2MiB와 누적 tool result 2MiB를 넘지 못한다. conversation당 active run 1개, local user 전체 active run 2개와 기본 OAuth creative run 100회/일 hard cap을 둔다. 사용자는 설정에서 더 낮출 수 있고 상향은 quota 경고와 재인증을 요구한다. 어느 cap이든 초과하면 run을 `blocked`로 finalize하고 mutation은 0이다.
- log에는 OAuth token, Authorization header, raw environment와 원본 media binary를 남기지 않는다.
- image/version, prompt schema, skill version과 tool contract는 pin하고 변경을 audit한다.

OAuth refresh 실패, rate limit, 중간 stream 단절 또는 audit store 실패 시 incomplete response는 proposal로 승격하지 않는다. consent/audit를 먼저 durable하게 쓰지 못하면 외부 호출 자체를 막는다. apply는 agent run과 분리된 사용자 endpoint이므로 agent retry가 적용을 반복할 수 없다.

새 설계는 기존 `external/Gemini call 0` 증명을 폐기하지 않는다. **일반 테스트와 local helper runtime은 계속 0**이며, 사용자가 실행한 Hermes creative request만 별도 승인된 외부 route다.

## 16. 장애와 degraded mode

| 장애 | 사용자에게 보이는 상태 | 유지되는 기능 |
|---|---|---|
| Hermes/OAuth unavailable | `유진 온라인 대화 사용 불가`와 재연결 안내 | 수동 편집, local analysis/search, render/output |
| 인터넷 unavailable | cloud creative route offline | Qwen/BGE/deterministic local 기능 |
| Qwen/LM Studio unavailable | `로컬 미디어 분석 대기` | Hermes text chat, lexical search, 수동 tag/edit |
| BGE unavailable | 의미 검색 성능 저하 안내 | normalized tag/lexical matching |
| mem0 unavailable | 장기 선호를 불러오지 못했다는 비차단 상태 | project conversation과 모든 편집 기능 |
| tool request rejected | proposal 생성 실패와 scope/retry 안내 | current session은 변경되지 않음 |
| host bridge unavailable | 로컬 분석 또는 CapCut 연결 상태별 복구 안내 | Hermes text chat과 container 내부 편집 기능 |
| audit/consent store unavailable | cloud 요청 차단과 저장소 복구 안내 | manual/local-only 기능 |
| stale session/revision | 새 preflight 요구 | current session 보존, 재조회 가능 |

Hermes unavailable일 때 Qwen으로 몰래 자동 fallback하지 않는다. 사용자가 명시적으로 `로컬 보조 모드로 계속`을 선택하더라도 그 응답은 `로컬 Qwen`으로 표시하고 창작 품질 보장 범위를 설명한다.

## 17. Observability와 증거

각 agent/model 실행은 다음 metadata를 남긴다.

- request, conversation, project stable ID
- tenant/user/run ID, durable event cursor와 consent/audit reference
- routing decision과 reason
- provider/runtime/model/profile/skill/prompt-schema version
- input context hash와 cloud-media policy
- tool name, scope, success/failure, duration
- schema validation, retry, latency, token/quota 가능 범위
- proposal ID, base session revision, 사용자 apply/reject/undo 결과
- external/Gemini/local call counter

대화 transcript와 final message/proposal은 사용자 기능을 위해 project DB에 저장하고 사용자가 conversation 또는 project를 삭제할 때 함께 삭제한다. 사용자는 삭제 전 JSON export를 만들 수 있다. raw streaming event/delta는 run finalize 후 30일, model/tool audit metadata는 90일 뒤 prune하며 보안 거부 event는 payload 없이 180일 보존한다. input fingerprint는 단순 SHA가 아니라 installation secret 기반 HMAC으로 저장해 짧은 대본의 사전 대입을 어렵게 한다.

memory는 사용자가 지우거나 180일 재확인에서 폐기할 때 vector/history까지 삭제한다. 삭제 tombstone은 offline backup 복원으로 되살아나는 것을 막기 위해 30일 보존한 뒤 제거하고, backup policy도 tombstone 적용 뒤 다음 rotation에서 원문을 purge한다. OAuth token, raw prompt/media와 secret은 backup 대상이 아니다.

## 18. 검증 계약

1. fake Hermes, fake Qwen, fake mem0로 interview → tool search → typed proposal → preflight → explicit apply E2E를 RED-first로 고정한다.
2. 승인 전 editing-session mutation 0, 승인 뒤 정확히 한 번의 atomic mutation과 undo를 증명한다.
3. normal suite socket guard가 external HTTP(S), Gemini, OAuth, real LM Studio와 host bridge call 0을 증명한다.
4. compose/config contract가 web/API/render worker/Hermes/memory gateway/mem0/분리 egress service, pinned image, read-only skill, isolated profile/volume/app ID, auth enabled와 AK-System 비공유를 검사한다.
5. model이 만든 raw ID나 prompt-injected instruction으로 다른 project, 일반 API, filesystem, SQL 또는 금지 tool에 접근할 수 없음을 opaque-handle/registry negative test로 검증한다.
6. mem0가 없는 상태에서도 project 대화와 편집이 동작하고 mem0 결과가 project truth를 덮지 못함을 검증한다.
7. OAuth/Qwen/BGE/host bridge 각각의 장애와 reconnect/retry가 silent fallback 없이 표기되는지 contract/E2E로 확인한다.
8. source → adapter → gateway → runtime과 runtime trace → route → source의 양방향 검증으로 우회 provider가 없음을 확인한다.
9. host bridge test는 Docker gateway에서 성공하고 LAN/문자열 지정 임의 path/임의 URL/replay/expired token에서 실패한다. picker import와 opaque CapCut artifact만 허용하며 UNC/device/reparse/traversal/TOCTOU를 거부하고 실제 outbound가 LM Studio loopback 또는 허용된 CapCut operation뿐임을 확인한다.
10. 별도 opt-in local product smoke는 한 번의 launcher로 web reverse proxy, API/SQLite restart persistence, isolated FFmpeg worker render, Hermes health/auth/profile, storage-only mem0, 한 번의 conversation과 read-only tool을 확인하고 fake editing mutation counter 0을 증명한다.
11. egress integration은 별도 network/listener/mTLS identity 때문에 Hermes만 pinned OAuth/provider destination에, API만 pinned host bridge에 도달하고 mem0/render worker의 external destination은 0임을 증명한다.
12. skill capability probe는 shell/filesystem/browser/Docker와 allowlist 밖 built-in tool이 0임을 runtime에서 확인한다.
13. 별도 quality harness가 frozen corpus, routing evidence, blind human score, confidence interval과 총 유효비용/latency report를 재현 가능하게 만든다.
14. one-shot OAuth bootstrap은 새 VideoBox state volume만 쓰고 AK/Codex/다른 Hermes auth file read 0, logout/revoke 뒤 active token/session 0을 증명한다.
15. ingest E2E는 native picker와 browser chunk upload가 같은 project-local URI/SHA를 만들고 source mutation, collision, disk full과 restart에서 partial asset을 남기지 않음을 검증한다.
16. FFmpeg/CapCut path E2E는 Linux absolute path가 draft에 0이고 동일 storage URI가 container render와 Windows CapCut material로 올바르게 해석되며 registration 전 SHA를 다시 확인함을 증명한다.
17. retention verifier는 event/audit/memory prune, conversation export/delete, HMAC fingerprint와 backup tombstone lifecycle을 fake clock으로 확인한다.

## 19. 단계별 도입 경계

이 설계는 기존 OSS dashboard/editor 22개 Task에 조용히 섞지 않고 별도 implementation plan으로 실행한다.

1. **Governance and provider boundary:** 기존 local-only 문서 충돌 정리, provider-neutral port, durable run/event와 network policy
2. **Local product stack:** `65_videobox` web/API/render worker/Hermes/memory gateway/mem0/분리 egress compose, host bridge, data root, identity와 aggregate health; 편집 mutation 없음
3. **Read-only Yujin chat:** project context, conversation persistence, read-only asset/session tools
4. **Proposal and approval:** typed intent, deterministic preflight, explicit atomic apply/undo
5. **Selective mem0:** preference write/read/delete와 SSOT conflict policy
6. **Qwen qualification:** shadow corpus, quality/cost report, 허용 route enablement
7. **Editor integration:** OSS editor Task 20이 실제 Gateway의 우측 유진 패널과 inline candidate interaction을 소비
8. **SaaS fork later:** tenant/user OAuth, managed storage, billing와 isolation을 별도 설계

각 단계는 focused test, full relevant suite, code review, 계획 gap 검증, source→runtime 역방향 검증 후 논리적으로 닫힌 단위로 commit/push한다.

중복 UI와 interview contract 재작성을 피하기 위해 실행 순서는 다음으로 고정한다.

1. 현재 미커밋 Yujin copy를 OSS 계획 Task 1로 먼저 closeout한다.
2. OSS 계획 Task 2–7로 visual direction, app shell, routing과 provider-neutral creation brief/interview를 만든다.
3. 이 설계의 Stage 1–3으로 전체 local product stack과 read-only Hermes chat을 연결한다.
4. OSS 계획 Task 8–9로 deterministic draft plan과 atomic real draft를 완성한다.
5. 이 설계의 Stage 4–6으로 Hermes proposal, mem0와 Qwen qualification을 연결한다.
6. OSS 계획 Task 10–22를 진행하고 Task 20에서 이미 검증한 Gateway를 editor에 통합한다.

## 20. 기존 SSOT와의 충돌 정리

이 문서를 사용자가 승인하면 다음 계획 갱신에서 충돌을 명시적으로 해소한다.

- `docs/superpowers/specs/2026-07-14-local-media-director-design.md`의 LM Studio-only 창작 경로는 **media analysis/local helper 기본값**으로 범위를 좁힌다. Gemini 자동 fallback 금지는 유지한다.
- host 개발 profile의 `LocalOnlyStructuredRuntime`은 exact `127.0.0.1:1234`를 유지한다. container release profile은 인증된 `HostBridgedLocalRuntime`을 추가하되, host bridge의 유일한 model outbound가 exact `127.0.0.1:1234`임을 양방향 trace로 증명한다.
- `docs/implementation-plan.ko.md`의 오래된 `Local Qwen -> Gemini fallback` 문장은 폐기 대상으로 표시한다.
- `docs/llm-provider-strategy.ko.md`의 `Qwen -> Gemini -> OpenAI` 자동 fallback 전략은 현재 local-only 구현 및 이 설계와 충돌한다. `docs/implementation-plan.ko.md` §23이 Hermes 범위에서 이를 우선하며, 첫 Hermes 작업은 Gemini disabled·unwired와 OAuth provider contract를 그 문서에도 반영한다.
- 같은 문서의 external/Gemini 0 계약은 normal test/local runtime에는 유지하되, explicit Hermes OAuth creative route를 별도 capability로 추가한다.
- `docs/videobox-mcp-scope.ko.md`의 외부 orchestration용 coarse-grained create/render/export tool 목록은 유진의 in-product allowlist로 재사용하지 않는다. 독립 VideoBox 엔진이라는 원칙은 유지하되, 유진 surface는 read/proposal-only와 별도 사용자 승인 endpoint로 좁힌다.
- `docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md`와 22개 Task의 `Hermes agent/container 제외`는 해당 22개 Task 범위에만 유지한다. Hermes 작업은 새 계획을 만들지 않고 최상위 `docs/implementation-plan.ko.md` §23으로 추적한다.
- VideoBox 자체 editor/FFmpeg output이 주력이며 CapCut은 optional handoff라는 최신 결정을 상위 계획에 반영한다.

문서 충돌을 고치기 전에는 기존 local-only production runtime을 임의로 바꾸지 않는다.

## 21. SaaS 전환 경계

현재 로컬 버전은 한 명의 사용자 OAuth를 전용 `videobox-hermes-state`에 보관한다. SaaS fork에서는 다음이 필수다.

- 고객마다 자신의 OAuth/provider account를 연결하고 owner credential을 공유하지 않는다.
- tenant/user/project가 conversation, memory, asset, audit과 tool authorization의 복합 경계가 된다.
- provider token은 중앙 secret store와 rotation/revocation을 사용한다.
- customer media의 cloud 전송 동의, 보관, 삭제와 지역 정책을 별도로 설계한다.
- OAuth/provider 약관이 상업적 multi-user proxy를 허용하는지 출시 전에 법무·약관 검토한다.
- provider 장애와 quota에 대비해 provider adapter를 교체할 수 있게 유지한다.

현재 작업은 이 경계를 코드 interface와 stable identity에만 반영하며 SaaS 운영 완료를 주장하지 않는다.

## 22. 설계 완료 조건

- 유진/Hermes/Qwen/BGE/deterministic code의 역할이 겹치지 않는다.
- 하나의 `65_videobox` 제품 스택 안에서 VideoBox와 Hermes가 별도 container로 분리되고, volume, identity, port와 credential 경계가 정의돼 있다.
- mem0와 VideoBox asset/editing DB의 책임이 분리돼 있다.
- 대화가 직접 mutation하지 않고 proposal/preflight/approval을 거친다.
- Qwen 역할 확대에 재현 가능한 품질·비용 gate가 있다.
- normal test external/Gemini/OAuth call 0과 opt-in Hermes route가 동시에 설명된다.
- FFmpeg는 무네트워크 VideoBox render-worker container에 있고 Windows host에는 LM Studio, CapCut Desktop과 최소 host bridge만 남는 경계가 명확하다.
- 기존 설계/계획의 충돌과 후속 갱신 대상이 식별돼 있다.
- SaaS는 customer-owned OAuth와 tenant isolation을 전제로 나중 단계로 분리돼 있다.

이 문서는 컨테이너가 생성됐거나 Hermes가 VideoBox에 연결됐다는 완료 증거가 아니다. 사용자 서면 리뷰 뒤 별도 구현 계획을 작성하고, 그 계획의 RED-first Task부터 실행한다.
