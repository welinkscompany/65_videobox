# VideoBox 데이터 경로 전수조사 (2026-08-08)

2026-08-08 핸드오프 `다음 세션에서 바로 할 일 §0`(owner 지시)의 1번 항목이다.
계획서 `2026-08-05-videobox-owner-usable-recovery.md`의 공식 Task는 아니다.

**이 문서는 조사 결과만 담는다.** 영상 데이터는 옮기거나 지우지 않았고, 코드도 고치지
않았다. 아래 §5의 결정이 나오기 전에는 손대지 않는다.

## 1. 한 줄 요약

데이터 폴더는 **두 벌이 아니라 세 벌**이다. 그리고 owner가 모아 둔 촬영본 **725MB가
컨테이너에서 보이지 않는다** — 실제 작업선인 컨테이너의 라이브러리는 비어 있고,
725MB는 로컬 실행 쪽 폴더에 있다.

## 2. 경로를 정하는 곳은 한 군데다

`packages/core-engine/src/videobox_core_engine/settings.py`가 전부다. 8개 파일에
흩어져 있다는 인상은 사실이 아니었다 — 나머지는 이 함수들을 부르기만 한다.

| 결정 대상 | 함수 | 환경변수 | 없을 때 기본값 |
|---|---|---|---|
| 프로젝트 루트 | `resolve_projects_root()` | `VIDEOBOX_DATA_ROOT` | `20_project\65_videobox-project` |
| 사용자 라이브러리 | `resolve_user_library_root()` | `VIDEOBOX_DATA_ROOT` | `20_project\videobox-user-library` |
| 가져오기 라이브러리 | `resolve_media_inbox_library_root()` | `VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT` | 위 라이브러리 `/media-inbox` |
| 감시 폴더 | `resolve_media_inbox_watch_path()` | `VIDEOBOX_MEDIA_INBOX_WATCH_PATH` | `G:\내 드라이브\100_videobox` |
| 감시 켬/끔 | `resolve_media_inbox_watch_enabled()` | `VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED` | **꺼짐** |
| 스냅샷 | `resolve_container_snapshot_root()` | `VIDEOBOX_SNAPSHOT_ROOT` | 없음 |
| 프로젝트 기록 저장소 | `resolve_database_url()` | `VIDEOBOX_DATABASE_URL` | 파일(SQLite) |
| 모델 가중치 | — | `HF_HOME` / `XDG_CACHE_HOME` | 사용자 프로필 캐시 |

**주의할 비대칭이 하나 있다.** `VIDEOBOX_DATA_ROOT`가 있으면 라이브러리는 그 **안**에
들어가고(`<root>/videobox-user-library`), 없으면 프로젝트 루트의 **형제**가 된다
(`65_videobox-project`의 옆). 그래서 컨테이너와 로컬의 폴더 모양이 다르다.
§4-①이 여기서 나온다.

## 3. 실행 방식별로 어디를 보는가

`.env.container`의 `VIDEOBOX_CONTAINER_DATA_ROOT=...\20_project\65_videobox-container-data-v2`,
compose가 그 아래 `runtime`을 `/videobox-data`에 붙인다.

| | 컨테이너 (`127.0.0.1:5173`) | 로컬 (web 5199 / api 8000) |
|---|---|---|
| 프로젝트 기록 | **Postgres** | 파일(SQLite) |
| 프로젝트 파일 | `container-data-v2\runtime\projects` | `65_videobox-project\projects` |
| 사용자 라이브러리 | `container-data-v2\runtime\videobox-user-library` | `20_project\videobox-user-library` |
| 가져오기 폴더 | 위 `\media-inbox` (**없음**) | 위 `\media-inbox` (**725MB**) |
| 감시 폴더 | 설정 없음 → `G:\...`(컨테이너 안에 없는 경로) | `G:\내 드라이브\100_videobox` |
| 스냅샷 | `container-data-v2\snapshot` (읽기 전용) | 없음 |
| 모델 가중치 | 도커 볼륨 `videobox_model_cache` | 사용자 프로필 |

**"저장소가 갈라져서 합치기 어렵다"는 앞선 판단은 절반만 맞다.**
`PostgresProjectStore`는 `LocalProjectStore`를 상속하고 같은 생성자 인자를 그대로
넘긴다(`postgres_project_store.py:112`). **영상·오디오 같은 실제 파일은 두 방식 모두
같은 디스크 레이아웃에 쓴다.** Postgres에 따로 들어가는 것은 프로젝트 **기록**뿐이다.
따라서 루트를 맞추면 미디어 파일은 실제로 한자리에 모인다.

## 4. 실측 (읽기 전용, 2026-08-08)

세 트리의 용량이다. 컨테이너 스택 5개가 healthy인 상태에서 쟀다.

| 위치 | 파일 | 크기 |
|---|---|---|
| `container-data-v2\runtime\projects` | 55 | 156.1 MB |
| `container-data-v2\runtime\videobox-user-library` | 1 | ~0 MB |
| `container-data-v2\snapshot` | 50 | 204.9 MB |
| `65_videobox-project\projects` | 47 | 95.3 MB |
| `20_project\videobox-user-library\media-inbox` | **9** | **725.0 MB** |

`b-roll-smoke-test`와 `progress-bar-live-test`는 세 곳 모두에 있다. 컨테이너 쪽이 가장 크다
(122.9MB 대 92.4MB) — 컨테이너에서 작업이 더 진행됐다는 뜻이다.

### ① 가장 큰 것 — owner의 촬영본 725MB가 컨테이너에서 안 보인다

`20_project\videobox-user-library\media-inbox`에 실제 촬영본 9개가 있다.

```
20250827_유튜브영상.mp4          520.8 MB   2025-08-27
20260323_152848.mp4              30.4 MB   2026-03-23
20260323_152916.mp4              19.4 MB   2026-03-23
20260323_153258.mp4              17.7 MB   2026-03-23
가로_FHD_20260319_203503.mp4     18.8 MB   2026-03-19
20260612_091959.mp4              17.2 MB   2026-07-18
20260612_092018.mp4              28.4 MB   2026-07-18
20260626_163224.mp4              48.2 MB   2026-07-18
20260628_165922.mp4              24.3 MB   2026-07-18
```

이 폴더는 **로컬 실행**의 라이브러리 경로다. 컨테이너의 라이브러리
(`runtime\videobox-user-library`)에는 `media_library.sqlite` 하나뿐이고 `media-inbox`
폴더는 아예 없다.

**실행 중인 앱에서 확인한 결과:**

```
GET http://127.0.0.1:5173/api/media-inbox/assets
{"assets":[]}
```

owner의 실제 작업 방식이 폰 촬영 → Drive → B-roll이므로, **컨테이너에서는 이 흐름의
출발점이 비어 있다.**

### ② 감시 폴더가 컨테이너에서 동작할 수 없다

실행 중인 컨테이너의 환경변수에 `VIDEOBOX_MEDIA_INBOX_*`가 **하나도 없다.**
compose.yaml에도 없다. 그래서:

- 감시 스레드가 **꺼져 있다**(기본값 꺼짐)
- 감시 경로 기본값이 `G:\내 드라이브\100_videobox`인데, 이건 윈도우 경로이고
  리눅스 컨테이너 안에 마운트되지도 않았다

즉 컨테이너에서는 `media-inbox` 폴더를 **채워 줄 주체가 없다.** 호스트에서 손으로
파일을 넣지 않는 한 §4-①의 목록은 계속 비어 있다.

### ③ B-roll 분석이 컨테이너에서 꺼져 있다

`VIDEOBOX_MEDIA_ANALYSIS_ENABLED`도 실행 중인 컨테이너에 없다.
`main.py:530-565`가 이 경우 `_UnavailableMediaAnalysisService`를 붙인다.

**실행 중인 앱에서 확인한 결과:**

```
GET .../api/projects/b-roll-smoke-test/media-analysis
"status":"blocked","error_code":"MEDIA_ANALYSIS_WORKER_UNAVAILABLE"
```

(이 기록 자체는 2026-07-18자 옛것이지만, 지금 뜬 컨테이너도 같은 서비스로 배선돼 있다.)
경로 문제는 아니지만 같은 원인 — **compose에 환경변수가 빠져 있다** — 이라 함께 적는다.

### ④ 중첩 잔재의 출처를 밝혔다

`runtime\projects\projects\b-roll-smoke-test\assets\imported\_intake_probe.mp4` (30.4MB).

**내용은 확정했다.** SHA-256이
`F3A063B574A18FCB77979F30AF6941B3D3158D15E2E4B45C5B8EE77E24DF0DA6`로,
owner의 촬영본 `20260323_152848.mp4`와 **바이트 단위로 같다.** 같은 파일이 컨테이너
트리 안에 두 벌 있다 — 제자리 하나, 한 겹 더 들어간 자리 하나. 둘 다 생성 시각이
`2026-08-05 19:23:51`로 초 단위까지 같다.

**중첩이 생기는 구조도 확정했다.** `LocalProjectStore`가 생성자로 받은 루트에
스스로 `"projects"`를 붙인다(`local_project_store.py:523`, `:631`). 그래서
`LocalProjectStore(x / "projects")`로 만들면 `x/projects/projects/<프로젝트>`가 된다.
저장소 안에 이 모양이 두 군데 있다.

| 위치 | 위험 |
|---|---|
| `scripts/measure_exact_preview_performance.py:57` | 없음 — `TemporaryDirectory` |
| `scripts/verify_owner_path.py:129` | **있음** — `--work-root`를 argv로 받는다 |

**다만 이 파일을 쓴 실행이 무엇인지는 확정하지 못했다.** `verify_owner_path.py`는
프로젝트를 `bootstrap_project(name="owner-path-verify")`로 새로 만들므로
`b-roll-smoke-test`라는 이름을 쓰지 않는다. `_intake_probe.mp4`라는 이름도 저장소의
코드·git 이력 어디에도 없다. **구조는 밝혔고 범인은 못 밝혔다.**

**두 벌 중 어느 쪽이 살아 있는지는 확정했다.** 실행 중인 앱이 이 자산을 등록된
B-roll로 들고 있다.

```
GET .../api/projects/b-roll-smoke-test/assets/broll-video
asset_6edcf5c1ed00  local://projects/b-roll-smoke-test/assets/imported/_intake_probe.mp4
```

이 주소가 가리키는 것은 **제자리 쪽**(`runtime\projects\b-roll-smoke-test\...`)이다.
**중첩된 쪽을 가리키는 자산은 하나도 없다** — 그쪽 30.4MB는 고아다.

곁가지로 하나 더 보였다. 같은 목록에서 `smoke-office-pan.mp4` **한 파일을 자산 7개가
가리키고 있다.** 경로 문제는 아니고 이번 범위 밖이라 적어만 둔다.

### ⑤ 코드가 전혀 모르는 폴더가 둘 있다

| 폴더 | 어디에 | 코드 참조 |
|---|---|---|
| `비롤_라이브러리\{수집함,보류,검수완료}` | 세 트리 전부 | **0건** |
| `65_videobox-project\tts-sample` (0.7MB) | 로컬만 | **0건** |

`.py`, `.ps1`, `.ts`, `.tsx` 어디에서도 이 이름들을 만들지 않는다. 문서에서도
2026-08-08 핸드오프의 조사 후보 목록에만 나온다. 과거 수동 작업의 잔재로 보이지만
**확정하지 않았다.**

참고로 `smoke_sources`(109.9MB)는 세 트리에 같은 것이 세 벌 있으나, 이건 QA 픽스처이고
`§10.12`의 `preserve-evidence` 대상이다. 재생성 스크립트도 있다.

## 5. owner 결정이 필요한 것

전부 owner의 영상 데이터에 대한 결정이라 내가 임의로 하지 않았다.

1. **725MB를 어디로 둘 것인가.** 컨테이너를 계속 쓸 거라면 이 폴더가
   `container-data-v2\runtime\videobox-user-library\media-inbox`로 가야 한다.
   복사할지 옮길지, 아니면 감시 폴더 설정으로 다시 채울지.
2. **로컬 실행 경로를 유지할 것인가.** 접으면 `65_videobox-project` 트리(95MB)와
   `.claude/launch.json`, `DEFAULT_PROJECTS_ROOT`의 역할을 다시 정해야 한다.
   남기면 두 벌 데이터를 계속 안고 간다.
3. **중첩된 `_intake_probe.mp4` 한 벌(30.4MB)을 지울 것인가.** 이쪽은 어떤 자산도
   가리키지 않는 고아로 확인됐다(§4-④). 제자리 쪽은 등록된 자산이므로 **건드리지
   않는다.** 원본 `20260323_152848.mp4`도 라이브러리에 그대로 있다.
4. **`비롤_라이브러리`와 `tts-sample`을 지울 것인가.** 안이 거의 비어 있고 코드가
   모르는 폴더다.

## 6. 확인하지 못한 것

- `_intake_probe.mp4`를 실제로 쓴 실행이 무엇인지 (구조만 밝혔다)
- `비롤_라이브러리` / `tts-sample`을 만든 주체
- 화면(브라우저)에서 가져오기 목록이 비어 보이는 것까지는 확인하지 않았다.
  API 응답 `{"assets":[]}`까지만 봤다 — `CLAUDE.md §4` 기준으로는 화면 확인이 아니다

## 7. 다시 재는 명령

```powershell
curl.exe -s http://127.0.0.1:5173/health
```

```powershell
curl.exe -s http://127.0.0.1:5173/api/media-inbox/assets
```

```powershell
docker exec 65_videobox-videobox-workspace-1 sh -c "env | grep VIDEOBOX_ | sort"
```
