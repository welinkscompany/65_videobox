# 한글 이름이 한 글자가 되던 문제 — 진짜 위험은 "조용히 섞인다"였다

- 작성: 2026-08-22 (작업은 2026-08-21 밤부터, 실측 날짜는 본문에 그대로 적는다)
- 앞 문서: `2026-08-21-videobox-yujin-writes-the-first-draft.ko.md`
- 개발선: `codex/videobox-container-compatibility`

## 한 줄

프로젝트 이름을 한글로 지으면 `project_id`가 한 글자가 되던 것을 고쳤다.
그런데 재 보니 **더 중요한 건 그 다음이었다 — 식별자가 겹치면 거절되는 게 아니라
먼저 있던 프로젝트를 조용히 삼켰다.**

## 무엇이 어떻게 되고 있었나 (실측)

`packages/domain-models/src/videobox_domain_models/projects.py`의 `_slugify`가
`[^a-z0-9]`를 전부 버렸다. 한글은 한 글자도 남지 않는다.

| 이름 | 옛 `project_id` |
|---|---|
| `관리화면 점검 A` | `a` |
| `테스트 A` | `a` |
| `샘플 A` | `a` |
| `다른 이름 A` | `a` |
| `제주도 여행 브이로그 2` | `2` |
| `여행 2` | `2` |
| `요리 2` | `2` |
| `그림 만들기 확인` | `project-2f0cca18` |
| `My First Video` | `my-first-video` |

**갈래가 둘이었다.**

- **한글만 있는 이름**은 남는 게 아예 없어서 `project-<무작위 8자리>`로 떨어졌다.
  우연히 안 겹쳤다. owner 컨테이너의 16개 중 11개가 이 모양이다.
- **한글에 영문·숫자가 한 글자라도 섞인 이름**은 그 한 글자만 남았다. 여기가 겹친다.

**한글만의 문제가 아니었다.** `My First Video`를 두 번 만들어도 둘 다
`my-first-video`였다. 같은 이름을 두 번 쓰면 언제나 겹쳤고, 한글은 서로 다른
이름까지 같은 자리로 몰아넣어 그 확률을 크게 올렸을 뿐이다.

## 겹치면 어떻게 됐나 — 이게 가장 중요한 물음이었다

**거절하지 않는다. 덮어쓰지도 않는다. 조용히 섞는다.**

`bootstrap_project`가 하는 일이 둘인데 둘 다 이미 있는 것을 그냥 받아들였다.

- `_create_project_layout` → `mkdir(parents=True, exist_ok=True)` — 남의 폴더를 그대로 재사용
- `_bootstrap_database` → `INSERT OR REPLACE INTO projects` — 남의 행을 덮어씀

실측으로 확인한 결과다. `테스트 A`를 만들고 그 안에 촬영본을 넣은 뒤 `샘플 A`를 만들면:

- 폴더는 `a` 하나뿐이다.
- 목록에는 `샘플 A`만 나온다. **`테스트 A`는 사라진다.**
- 그런데 `테스트 A`의 촬영본 파일은 그 안에 그대로 있다.
- `assets` 표의 행도 그대로 남아 **새 프로젝트 것이 된다.**

즉 owner 입장에서는 **프로젝트 하나가 소리 없이 없어지고, 그 안의 영상이 엉뚱한
프로젝트에 붙는다.** 오류도 경고도 없다. 셋 중 최악이다.

**컨테이너(Postgres)도 똑같다.** `PostgresProjectStore._bootstrap_database`는
`ON CONFLICT (project_id) DO UPDATE SET name = EXCLUDED.name ...`라, sqlite의
`INSERT OR REPLACE`와 같은 자리에서 같은 일을 한다. 로컬만의 문제가 아니었다.
식별자를 만드는 곳은 두 저장소가 공유하는 `ProjectRecord.create` 한 곳이라,
거기를 고치면 둘 다 고쳐진다(`PostgresProjectStore`는 `LocalProjectStore`를 상속한다).

## 고친 방향

`_slugify`를 `_name_stem` + `_new_project_id` 둘로 나누고, **이름에서 뽑은 부분 뒤에
짧은 무작위(uuid4 앞 8자리)를 항상 붙인다.**

```
관리화면 점검 A  ->  a-4f21c9be
샘플 A          ->  a-08d3117a
그림 만들기 확인 ->  project-9b2ee410
My First Video  ->  my-first-video-1c77a05d
```

**왜 항상 붙이나.** 디스크를 먼저 뒤져 빈 이름을 고르는 방법도 있지만 그러지 않았다.
확인과 생성 사이가 벌어져 같은 순간에 들어온 두 요청은 여전히 겹치고, 식별자를 만드는
일이 저장소 상태를 알아야 하는 일로 커진다. 항상 붙이면 **옛 프로젝트가 쓰던 짧은
식별자(`a`, `my-first-video`)와도 저절로 어긋난다** — 그래서 새 프로젝트가 옛
프로젝트를 삼킬 수 없다.

**왜 한글을 식별자에 넣지 않았나.** 넣으면 읽기는 좋아진다. 하지만 식별자는 저장
경로이자 DB 키이고 HTTP 경로 조각이다. 글자 범위를 넓히면 nginx·ffmpeg 인자·CapCut
draft JSON·Windows 경로까지 한꺼번에 영향을 받는데, 그 전부를 이 범위에서 확인할 수
없다. **owner에게 보이는 한국어 제목은 `name` 칸에 그대로 남는다** — 사람이 읽을
이름과 기계가 쓸 주소를 분리해 두는 쪽을 골랐다. 넓히고 싶으면 별도 작업으로 하되,
렌더·내보내기까지 실제로 밟아 보고 판단해야 한다.

**길이도 같이 막았다.** 이름에서 뽑는 부분을 40자로 자른다. 프로젝트 폴더 밑으로
`analysis/partial_regenerations` 같은 깊은 경로가 더 붙어서, 긴 제목 하나가 경로
길이를 다 먹으면 안 된다.

덤으로 `CON` 같은 Windows 예약 장치 이름도 뒤에 무작위가 붙어 저절로 풀린다.

## 옛 프로젝트는 건드리지 않았다

식별자를 만드는 규칙만 바꿨다. **이미 있는 프로젝트의 식별자·폴더·DB는 그대로다.**
`ProjectRecord.create`에 `project_id`를 명시해 주는 경로는 예전과 똑같이 그 값을 쓴다.

owner 컨테이너의 16개(`project-04180302` 등)는 전부 옛 모양 그대로 남아 있고,
목록·열기·이름 바꾸기가 된다. `tests/test_project_id_never_collides.py`의
`test_projects_made_before_this_fix_still_open`이 옛 모양(`a`, `my-first-video`,
`project-2f0cca18`)을 디스크에 그대로 놓고 그것을 지킨다.

## 남긴 시험

`tests/test_project_id_never_collides.py` (새 파일, 9개)

- 옛날에 `a`로 뭉치던 한글 이름 넷이 서로 다른가
- 옛날에 `2`로 뭉치던 이름 셋이 서로 다른가
- 같은 이름을 두 번 만들면 둘이 되는가 (영문·한글 각각)
- **새 프로젝트가 남의 촬영본을 물려받지 않는가** — 조용한 병합을 막는 시험
- 식별자가 폴더 이름으로 안전한가 (경로 구분자·예약 이름·길이)
- **옛 프로젝트가 여전히 열리는가**
- 새 프로젝트가 옛 식별자(`a`)를 뺏지 않는가

`tests/test_domain_models.py`는 옛 모양(`local://projects/demo-project`)을 그대로
박아 두고 있어 같이 고쳤다.

## 검증

### 실제 HTTP 경로로 밟았다

단위 테스트만으로 끝내지 않았다(§4). 이 worktree의 FastAPI 앱을 임시 데이터 폴더로
띄우고 `POST /api/projects` → `GET /api/projects/{id}` → `GET /api/projects` →
`DELETE`까지 owner가 지나는 순서 그대로 지났다. 결과:

```
'점검용 한글 이름 A'   -> a-235a2174
'다른 한글 이름 A'     -> a-633c6933
'또 다른 한글 이름 A'  -> a-27281d9b        <- 옛 규칙이면 셋 다 'a'
'그림 만들기 확인'     -> project-b6d397c2
'빈 편집판 점검'       -> project-99fbc55c
'빈 편집판 점검'       -> project-59d155b6  <- 같은 이름 두 번도 둘로 갈린다
```

- 만든 6개, 서로 다른 식별자 6개. **안 겹친다.**
- 여섯 개 전부 `GET`으로 열리고 이름도 맞다.
- 목록에 여섯 개가 다 나온다 — **삼켜진 것이 없다.**
- 디스크에도 폴더가 여섯 개 따로 생겼다.
- `DELETE`로 여섯 개 다 지워졌고 남은 것은 0개.

### owner 컨테이너는 재빌드하지 않았다 — 이유를 밝힌다

지시는 `scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`였으나
**그렇게 하지 않았다.** `owner-ready.ps1 -Rebuild`는 주석 그대로 "이 worktree에서"
workspace 이미지를 다시 만들어 **공유 스택을 갈아끼운다.** 그런데 지금
`65_videobox-videobox-workspace-1`은 **8분 전에 다른 작업이 새로 띄운 것**이었고,
장면 전환·대본 쓰기 두 작업이 같은 스택을 쓰고 있다. 내 브랜치로 다시 만들면
그쪽 검증 환경을 덮어쓴다.

대신 위처럼 실제 API를 그대로 밟았다. **컨테이너에서 다시 확인하고 싶다면**
다른 두 작업이 끝난 뒤 같은 이름으로 프로젝트를 두세 개 만들어 보면 된다.
컨테이너는 Postgres 저장소를 쓰지만 **식별자를 만드는 곳은 두 저장소가 공유하는
`ProjectRecord.create` 한 곳**이라 결과는 같아야 한다.

### 백엔드 pytest

- 새 시험 파일 + 직접 영향받는 파일 **40개 통과**
  (`test_project_id_never_collides.py`, `test_domain_models.py`,
  `test_handoff_entry_point.py`, `test_project_rename.py`, `test_project_archive.py`)
- 넓힌 범위 **410개 통과, 43개 건너뜀** (12분 55초)
  (`test_api.py` 전체 + `test_cross_project_job_dashboard.py` +
  `test_postgres_project_store.py`) — API 표면 전체와 두 저장소를 다 지난다
- 개발선을 병합한 뒤 다시 **17개 통과** (진입점·식별자·도메인 모델)

**전체 pytest는 단독으로 돌리지 못했다. 이건 확인하지 못한 채로 남는다.**

돌리려고 했는데 **다른 작업 둘이 이미 전체 pytest를 돌리고 있었다.** 프로세스를
직접 확인한 결과다 — 하나는 `-q --tb=short`(내 명령에는 `--tb=short`가 없다),
다른 하나는 `agent-a4f0a82fffa50322c` worktree의 venv에서 돌고 있었다. 셋이 같이
도니 20분에 12%밖에 못 갔다. 규정이 단독을 요구하는데 **기계를 나 혼자 쓸 수가
없었다.** 남의 실행은 죽이지 않았고, 내 것만 멈췄다.

**다음 세션이 알아 둘 것:** 에이전트 여럿이 같이 돌면 "전체 pytest 단독"은 규정만으로는
지켜지지 않는다. 돌리기 전에 `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`로
남이 돌리고 있는지 먼저 보는 편이 낫다. 안 보고 띄우면 서로를 느리게 만들고
**둘 다 근거로 쓸 수 없는 값**이 나온다.

대신 **넓힌 범위를 410개까지 돌려 놨다**(위). 다음 세션에서 기계가 한가할 때
`.venv\Scripts\python.exe -m pytest`를 단독으로 한 번 돌려 주면 이 칸이 닫힌다.
다만 이번 변경이 건드리는 것은 문자열 하나를 만드는 순수 함수 하나이고, 옛 모양을
그대로 박아 둔 곳은 `tests/test_domain_models.py` 하나뿐이라(전체 grep으로 확인)
남은 위험은 작다고 본다.

## 안 한 것 / 확인하지 못한 것

- **마이그레이션은 하지 않았다.** 이 작업의 범위가 아니다. 옛 프로젝트의 짧은
  식별자(`a` 같은 것)는 그대로 남는다. owner 자료에는 지금 그런 것이 없다.
- **`bootstrap_project`의 조용한 병합 자체는 그대로 있다.** 무작위 8자리 덕에
  실제로는 닿을 수 없는 길이 됐지만(16개 기준 충돌 확률은 사실상 0), 폴더가 이미
  있으면 소리 내어 거절하도록 막는 것은 넣지 않았다. 넣으면 더 안전하지만 이번
  범위 밖이고, 기존 흐름 중 재-bootstrap에 기대는 것이 있는지 확인이 필요하다.
- **렌더·내보내기까지 밟아 보지는 않았다.** 새 식별자는 옛 식별자와 같은 글자
  범위(`[a-z0-9-]`)라 경로에서 달라지는 건 길이뿐이다.
