# 격리 스택 실브라우저 전체 흐름 검증 (2026-09-19)

## 요청과 배경

2026-09-18에 FIX/INVEST 항목이 거의 다 닫혔지만 가장 중요한 항목 하나만
의도적으로 미뤄졌다: **격리된 Postgres+파일 저장소로 실제 브라우저에서
전체 흐름을 끝까지 검증하는 것**(컨테이너 충돌 사고 때문에 피했다고
`docs/handoffs/2026-09-18-mem0-removed-native-memory-librarian.ko.md`에
명시돼 있었다). 이 세션이 그 항목을 채운다. `.claude/worktrees/agent-a10b5c621aeadbfde`
격리 worktree에서 작업했고, 공용 스택(포트 5173, 원본 `videobox-hermes-yujin` 등)은
건드리지 않았다.

## 격리 방법

- `docker compose -p videobox-wt-agent-a10b5c621aeadbfde`로 완전히 분리된 프로젝트.
- 웹 포트 5273(`VIDEOBOX_WEB_PORT`), 별도 데이터 루트
  (`D:/AI_Workspace_louis_office_50/20_project/65_videobox-agent-a10b5c6-data`,
  `scripts/migrate_container_data.py`로 최소 시드 소스에서 정식 snapshot/runtime
  레이아웃을 만들었다), 별도 `owner-drop`(같은 20_project 트리의
  `65_videobox-agent-a10b5c6-isolated/owner-drop`).
- `videobox-hermes-yujin`은 **고정 `container_name`이라 프로젝트 격리로 안 갈라진다**
  (GPU/LM Studio 공유 설계 의도로 보인다). scratchpad에 임시 override 컴포즈 파일
  (`services.videobox-hermes-yujin.container_name`만 재정의)을 만들어
  `videobox-hermes-yujin-agent-a10b5c6`라는 별도 컨테이너로 띄웠다 — 운영
  `videobox-hermes-yujin`은 계속 그대로 떠 있었다(안 건드림). 이 override 파일은
  저장소 밖(스크래치패드)에만 있고 커밋 대상이 아니다.
- `scripts/install-hermes-yujin-profile.ps1`은 `-p` 프로젝트 이름을 안 넘겨서
  기본적으로 **운영 프로젝트 이름(`65_videobox`)의 볼륨에 프로필을 설치한다** —
  이번 세션 초반에 owner-ready.ps1 Start를 한 번 그대로 돌렸다가 이 경로로
  운영 볼륨에 조용히 닿았다(`hermes profile install --force`는 멱등이라 실질
  피해는 없어 보이지만, 격리가 완전하지 않다는 뜻이라 아래 "발견한 문제"에
  남긴다). 이후로는 `-p videobox-wt-agent-a10b5c621aeadbfde`를 명시해 직접
  `docker compose run`으로 다시 설치했다.
- `.env.container`는 이 worktree에만 있고(gitignore 대상, 커밋 안 됨) 전부
  새로 만든 값(Postgres 비밀번호, Hermes capability 키, 게이트웨이 토큰)이다
  `scripts/new-hermes-yujin-secrets.ps1`로 생성. `VIDEOBOX_LOCAL_MODEL_NAME`은
  지금 LM Studio에 실제로 로드된 모델(`qwen/qwen3.8-27b`)로 맞췄다 — 기본값
  `qwen3-35b`와 다르다(§"발견한 문제" 참고).
- **끝나면 이 worktree의 컨테이너·이미지·볼륨만 정리한다**(아래 "정리" 절).

## 실제로 밟은 흐름 (브라우저, 포트 5273)

1. `/projects` 빈 상태 → `+ 새로 만들기` → 자동 이름 프로젝트가 바로 편집기로 열림.
2. 자료실에서 가져오기 → 실제 owner 영상(`videobox-user-library/media-inbox`의
   `20260612_091959.mp4`, 18MB, read-only 원본에서 **복사**해 격리 owner-drop에
   넣음 — 원본은 안 건드림)이 owner-drop 감시로 **자동 색인**되어 자료실에 떴다.
   타임라인에 적용 → 실제 영상 프레임(공항 라운지 네온사인)이 미리보기에 그려짐.
3. 텍스트 탭에서 본문 자막 추가 → 미리보기에 "본문" 자막이 실제로 얹혀 보임.
4. 새로고침 + `/projects`로 갔다가 다시 편집기 재진입 → 클립·자막 그대로 남아
   있음(저장·재접속 정상).
5. 확인과 내보내기 → 검토본 재생성 → 검토 승인 → 가로·세로 출력 만들기(마스터
   재조정 충돌까지 실제로 뜨고 눌러서 해소) → 자막 만들기 → **완성본 만들기 →
   실제 mp4 생성 성공** → CapCut 초안 만들기까지 전부 성공(job 테이블에
   `succeeded` 3개: timeline_build, final_render, capcut_draft_export).
6. 완성본을 역추적: `exports` 테이블 `export_001` → `source_session_id
   editing_session_001` · `source_session_revision 4` → `editing_sessions`의
   실제 `session_revision 4`와 **일치**. `output_variants` 두 개도
   `source_session_revision 4`로 일치. 다운로드 엔드포인트
   (`/api/projects/.../final-renders/final_render_job_002/content`)로 받은
   파일이 디스크 파일과 바이트 동일(1,489,834바이트). `ffprobe`로
   1920x1080/h264/aac/5.0초 확인, 프레임 추출로 **실제 영상 내용**(공항 라운지
   네온사인 + "본문" 자막)과 `volumedetect`로 무음이 아님(mean -39.1dB, max
   -20.4dB)을 확인했다 — 합성 영상이 아니라 owner 실촬영본이 최종 mp4까지
   그대로 이어졌다.
7. 프로젝트 없는 주소(`/projects/does-not-exist/home`)로 직접 진입 →
   `RecoveryPage`가 깨지지 않고 "프로젝트를 찾을 수 없어요" + 실제 프로젝트로
   돌아가는 단추를 보여줌(실패 경로 정상).

## 발견한 문제

### 1. (고침) `scripts/run_memory_librarian.py`가 컨테이너 안에서 항상 실패했다

owner가 손으로 돌리는 유일한 사서 진입점인데, `_default_runtime()`이
`LocalOpenAICompatibleRuntimeConfig(timeout_seconds=120)`을 인자 없이 새로
만들어 `base_url`이 dataclass 리터럴 기본값(`http://127.0.0.1:1234/v1`)으로
고정됐다. 이 스크립트는 `/app/scripts/`에 들어가 **컨테이너 안에서 돌리는
것이 유일한 실사용 경로**인데, 컨테이너 안에서 127.0.0.1은 컨테이너 자신이라
호스트의 LM Studio에 안 닿는다 — 실측(2026-09-19)으로
`ConnectionRefusedError: [Errno 111] Connection refused`가 났다. 컨테이너에는
이미 `VIDEOBOX_LOCAL_RUNTIME_BASE_URL=http://host.docker.internal:1234/v1`이
올바르게 설정돼 있었는데 이 스크립트만 그 값을 안 읽었다.

**원인은 이번 세션 이전부터 있던 결함이다** — Mem0 제거·INVEST-04와 무관하게,
사서 스크립트가 처음 만들어질 때부터 컨테이너 실행 경로가 한 번도 검증 안 된
채였다(기존 시험 `tests/test_run_memory_librarian_script.py`은 전부
`runtime_factory`를 주입해 `_default_runtime()`을 건너뛴다 — 실사용 기본
경로는 커버리지 0%였다).

**고침**: `_default_runtime()`이 이제 `resolve_local_runtime_config()`로 환경을
먼저 읽고(`base_url`이 컨테이너/로컬을 자동으로 맞춘다) `timeout_seconds`만
120초로 올린다(`dataclasses.replace`). 새 시험 파일
`tests/test_run_memory_librarian_default_runtime_uses_env_base_url.py`(시험 2개)로
RED→GREEN 확인, 기존 `tests/test_run_memory_librarian_script.py`(시험 2개)도
같이 통과. 실물로도 재확인 — 고친 스크립트를 컨테이너 안에서(`docker exec -i
... python - < scripts/run_memory_librarian.py`) 다시 돌리니 더는
`ConnectionRefusedError`가 아니라 실제로 LM Studio에 요청을 보내고 120초
상한까지 기다렸다(아래 §2와 같은 이유로 결국 타임아웃했지만, **닿기는
했다** — 연결 문제는 확실히 없어졌다).

### 2. (보고만, 안 고침) 로컬 모델 실측 지연이 대화·사서 양쪽의 기본 타임아웃을 넘는다

이 컴퓨터에 지금 로드된 모델은 `qwen/qwen3.8-27b`(reasoning 기본값 `xhigh`,
LM Studio `/api/v1/models`로 확인 — GPU 경합은 없었다, 로드된 인스턴스는
이거 하나뿐이었다). 이 모델로:

- 유진 채팅 직접 편집(`YujinEditingProposalService.create`, 전역 기본
  60초 사용, 별도 `wait_seconds` 안 줌) — 화면에서 실측 **약 105초**까지
  기다리다 "유진의 답을 받지 못했어요"로 종료. 백엔드 로그의 실제 원인은
  `local_qwen: Local Qwen request timed out.`(30초가 아니라 60초 — 코드의
  전역 기본값은 2026-09-18에 이미 60초로 올라 있었다). **자막이 실제로는
  안 바뀌었다** — "말하면 바로 적용된다"(2026-09-01 결정)가 이 모델 조건에서는
  깨진다.
- `scripts/run_memory_librarian.py`(자체 상한 120초) — §1 고친 뒤 재실행하니
  120초를 다 채우고 `local_qwen: Local Qwen request timed out.`.
- `review-snapshots` 조회는 **타임아웃 뒤 정상적으로 heuristic
  fallback으로 내려간다**(`provider_trace.final_provider:
  "heuristic_fallback"`, `fallback_reasons: ["local_provider_error"]`) —
  이 경로는 안 죽고 우아하게 떨어진다. 유진 채팅과 사서는 fallback이
  없어 그대로 실패로 보인다.

**판단 근거 없음(owner 결정 필요)**: 이게 "이 모델(27B, xhigh)이 그냥
느리다"인지 "지금 로드된 모델 자체가 잘못됐다"(설정 기본값은 `qwen3-35b`인데
LM Studio는 다른 모델을 올려 뒀다 — `owner-ready.ps1 -Mode Check`가 이걸
BLOCKED로 잡는다, 이번 세션도 그 경고를 봤다)인지 실측으로 못 갈랐다.
`qwen3-35b`는 다른 프로젝트가 쓰고 있어 안 내렸다(기존 메모리 규칙:
"35b는 내리지 마라"). 타임아웃 상한을 올리는 것은 "대화·자막처럼 짧아야 하는
일까지 같이 느려진다"는 트레이드오프가 이미 코드 주석에 명시돼 있어(
`local_only_runtime.py`) 그 판단을 코드만 보고 대신 내리지 않았다.

**고치지 않은 이유**: (1) 두 가지 원인(모델 선택 vs 상한 값) 중 어느 쪽을
바꿀지는 제품 판단이라 넓다. (2) `qwen3-35b`를 로드해 같은 실측을 해 볼
권한/여유가 이번 세션엔 없었다(다른 프로젝트가 씀).

### 3. (환경 아티팩트, 실제 결함 아님) CSRF Origin 화이트리스트가 5173 하나만 신뢰한다

`services/api/src/videobox_api/csrf_guard.py`의 `TRUSTED_ORIGINS`는 의도적으로
`http://127.0.0.1:5173`/`http://localhost:5173`만 넣는다(승인 문 다섯 개용
최소 CSRF 방어, 2026-09-07 결정). 격리 스택을 5273으로 띄운 이번 세션에서는
브라우저로 "검토 승인" 버튼을 누르면 403이 났다 — **이건 내 테스트 포트
선택 때문이지 제품 결함이 아니다**(운영은 항상 5173 하나만 쓴다). 코드를
바꿔 우회하려다 자동 승인 분류기가 "보안 완화"로 막았고, 그게 맞는
판단이었다 — 대신 Origin 헤더 없는 curl 호출(코드 주석이 명시한 의도된
우회 경로, 스모크 스크립트용과 동일)로 검토 승인 엔드포인트 자체가 정상
동작함을 확인했다. **코드는 안 건드렸다** — 편집했던 임시 라인은 rebuild가
막힌 즉시 되돌렸고 `git status`로 깨끗함을 재확인했다.

## 검증하지 못한 채 남은 것

- **목소리 더빙·목소리 복제**: `start-voice.ps1`(chatterbox 컨테이너)를 이번
  격리 스택에 같이 못 띄웠다(범위 밖으로 판단 — 별도 GPU 서비스라 시간
  예산 안에서 추가 격리까지는 못했다). 화면의 "내레이션" 탭 존재만 확인,
  실제 합성 음성 생성은 안 밟았다.
- **취소 시나리오**: 이 테스트 영상이 5초짜리라 렌더가 1초 안에 끝나서
  진행 중 취소 버튼을 실제로 눌러볼 타이밍을 못 잡았다. 실패 시나리오는
  §2의 유진 채팅 타임아웃으로 대신 확인됐다(실패가 화면에 안전하게
  보고되는 것까지 확인).
- **다른 프로젝트로 이동 중 렌더 완료 도착** 같은 실제 경쟁 상태는
  강제로 재현하지 않았다. `is_current`/`source_session_revision` 필드가
  구조적으로 방어하고 있음은 실측(§"실제로 밟은 흐름" 6번)으로 확인했지만,
  경쟁을 직접 유발하지는 않았다.
- **frontend 전체 테스트(vitest)는 이번 세션에서 안 돌렸다** — 코드 변경이
  `scripts/run_memory_librarian.py`(backend 전용 스크립트) 하나뿐이라 frontend
  파일을 전혀 안 건드렸다. 백엔드 전체 pytest만 독립 실행했다(아래).
- **`scripts/install-hermes-yujin-profile.ps1`의 `-p` 미전달 문제**는 이번
  세션 범위 밖으로 판단해 코드를 안 고쳤다 — 별도 확인이 필요하면 §"발견한
  문제" 서두를 참고.

## 최종 판정

**owner가 화면에서 이 기능을 실제로 쓸 수 있는가** 기준:

- **프로젝트 생성 → 자료 가져오기 → 컷/자막 편집 → 저장 → 재접속 →
  검토 승인 → 완성본(MP4) → CapCut 초안까지는 그대로 된다.** 실제
  owner 영상으로, 실제 브라우저로, 격리된 Postgres+파일 저장소에서
  끝까지 재생 가능한 결과물을 만들었고 픽셀·음량·다운로드 바이트까지 다
  쟀다.
- **유진에게 말해서 바로 적용되는 편집(2026-09-01 결정)은 지금 이
  컴퓨터에 로드된 로컬 모델 조건에서 실패한다.** 화면은 안전하게
  "답을 받지 못했어요"라고 말하지만(거짓 긍정은 아님 — 2026-09-17
  마무리된 그 결함은 재발 안 함), 실제로 요청한 편집은 안 걸린다.
  이게 이번 세션 발견 중 **가장 owner 판단이 필요한 항목**이다.
- **Mem0 제거·사서 전환은 배관(스키마·상태 기계)은 그대로였지만, 컨테이너
  실행 경로 자체가 막혀 있었다** — 오늘 고쳐서 최소한 "LM Studio에 닿는다"까지는
  됐다. 승인 대기열에 실제로 기억 후보가 쌓이는 것까지는 이번 세션에서
  로컬 모델 지연 때문에 못 봤다(§2).

## 배경 검증

- `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_mcp_server.py`
  (독립 실행, 50분 52초): **5082 passed, 56 skipped, 1 xfailed, 7 failed.**
  - 5개는 `tests/test_editor_ui_source_provenance.py` — `apps/web/src/app/ProductShell.tsx`
    provenance 해시 어긋남. `git log`로 확인: 이 파일은 이번 세션에서 전혀
    안 건드렸고(`git status --short`도 빈 출력), 마지막 커밋도 이번 작업과
    무관한 옛 커밋(`ca3565bb6`)이다. 2026-09-18 인계 문서가 이미 같은 결함을
    "내 변경과 무관"으로 플래그해 뒀다(`task_a923ef55`) — 재확인만 하고
    범위 밖으로 둔다.
  - 2개(`test_owner_ready_script.py`의 크레덴셜 분류기 시험 하나,
    `test_start_hermes_yujin_script.py`의 파이프 데드락 시험 하나)는
    subprocess 기반 시간 상한 시험이다. 이 세션은 전체 pytest를 돌리는
    동안에도 격리 도커 스택(postgres·workspace·agent-gateway·hermes-yujin)을
    계속 띄워 둔 채였다 — CPU 부하가 큰 상황에서만 흔들린다는 기존 메모리
    (`videobox-audit-subagents-die-on-rate-limit`,
    `videobox-full-pytest-must-run-alone`)와 일치한다. 두 시험만 따로
    독립 실행(2분 30초)하니 **31개 전부 통과** — 내 변경과 무관한 부하성
    플레이키임을 확인했다.
  - `scripts/run_memory_librarian.py`를 바꾼 데 대한 직접 시험
    (`tests/test_run_memory_librarian_default_runtime_uses_env_base_url.py`
    2개, `tests/test_run_memory_librarian_script.py` 2개)은 전체 실행에도
    포함돼 전부 통과했다.
- frontend 전체 테스트(vitest): 안 돌림 — 이번 변경이 backend 스크립트
  하나뿐이고 frontend 파일은 전혀 안 건드렸다(위 "검증하지 못한 채 남은 것"
  참고).

## SSOT 갱신

- `CLAUDE.md` §2 표의 "최신 세션 인계" → 이 문서.
- 이전 인계(`docs/handoffs/2026-09-18-mem0-removed-native-memory-librarian.ko.md`)에
  **대체됨** 포인터 추가(아래 참고).
