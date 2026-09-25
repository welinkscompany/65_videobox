# 결재함 큐 연결 서버 상시 실행 — AK-Hermes 정책 충돌로 등록 보류 (2026-09-26)

**대체됨 표시 대상:** `2026-09-25-hermes-approval-queue-live-verification-and-index-fix.ko.md`가
이 문서로 이어진다.

## 배경

`2026-09-25-hermes-approval-queue-live-verification-and-index-fix.ko.md`가 남긴 숙제 —
AK-System Hermes 결재함 큐 연결 서버(`scripts/videobox-mcp-connector-server.js`,
`100_ak-system-hermes` 저장소, 127.0.0.1:19680)가 사람이 터미널을 열어 두지
않아도 항상 떠 있게 만드는 일 — 을 이어받았다.

owner-ready.ps1의 두 번째 결함(`-Rebuild`가 `videobox-agent-gateway`를 절대
다시 안 만드는 것)은 완전히 고쳤다. **결재함 큐 연결 서버 상시 실행은
AK-System Hermes 쪽의 같은 날(2026-09-25) 다른 결정과 충돌한다는 것을
뒤늦게 발견해서 실제 등록은 하지 않았다** — 아래 "무엇이 막혔나" 절 참고.

## 1. `owner-ready.ps1` 재빌드 결함 — 고침, 커밋·푸시 완료

`-Rebuild`를 줘도 `videobox-agent-gateway`는 절대 다시 만들지 않던 문제.
`-WithYujinMemory`일 때만 그 이미지가 존재하므로, 그 스위치가 있을 때만
빌드 대상에 추가하도록 고쳤다. 관련 테스트 123개 통과.

- 커밋: `3fa7ad92c fix: owner-ready.ps1이 -Rebuild에서 agent-gateway도 같이 다시 만들게 함`
- `git push origin main` 완료.

## 2. 결재함 큐 연결 서버 상시 실행 — 대표님 지시 (2026-09-25, VideoBox 세션)

> "2번은 상시로 해야되. 왜냐면 ak 직원들이 영상 생성할때마다 자동으로
> 비디오박스를 불러와서 편집을 할거거든."

이어서 반복 주기는 "5분은 너무 짧고 3시간마다 한번씩 해"로 확정.

### 한 것 (AK-System Hermes 저장소, `100_ak-system-hermes`)

AK-System Hermes 자체가 "선언(JSON) → `reconcile-ak-system-scheduled-tasks.ps1`
→ 실제 Windows 예약 작업" 파이프라인을 이미 갖고 있어서, 그 방식을 그대로
따랐다.

1. **`scripts/restart-videobox-approval-connector-if-down.ps1` 신설** —
   `restart-founder-dashboard-if-stale.ps1`과 같은 모양. `127.0.0.1:19680/health`를
   확인하고, 죽어 있으면 `Start-Process -WindowStyle Hidden`으로 분리해서
   `node scripts/videobox-mcp-connector-server.js`를 다시 띄우고 정상
   종료한다(예약 작업이 "Running"으로 영원히 안 걸리게).
2. **`docs/ak-system/data/ak-system-scheduled-task-registry.json`에 새 행
   추가** — `task_id: videobox-approval-connector-watchdog`, `provider-failover-health-probe`를
   genesis 씨앗으로, `s4u`/headless, `repetition_interval: PT3H`,
   `execution_time_limit: PT5M`, `desired_state: enabled`(대표님 승인이
   등록 그 자체라는 선례를 따름).
3. **찾은 진짜 버그 — `scripts/ak-system-scheduled-tasks.ps1`의
   `$expectedGovernedSurfaceCount`가 48로 박혀 있었다.** 새 작업을
   추가하면 49개가 되는데 이 숫자를 안 맞추면
   `build-ak-system-scheduled-task-projection.ps1`이 "tasks must contain
   exactly 48 governed surfaces but contains 49"로 즉시 죽는다. 48→49로
   고치고 주석에 근거를 남겼다(이 저장소가 이미 40여 회 반복해 온 패턴 —
   "등록 개수를 세는 안전장치를 같이 안 옮기면 다음 추가가 막힌다").
4. **실물로 확인** — `build-ak-system-scheduled-task-projection.ps1`을
   직접 돌려(Register-ScheduledTask는 안 부르는, 순수 XML 변환 단계)
   정상적인 Task XML이 나오는 것까지 확인했다: `TimeTrigger` 반복
   `PT3H`, `ExecutionTimeLimit PT5M`, `LogonType S4U`,
   `-WindowStyle Hidden`, `WorkingDirectory`가 정확히 이 저장소 루트.

세 파일을 로컬 커밋했다(`5d57ca81`). **`git push`는 안 했다** — 아래
이유 때문이다.

### 실제 등록(Windows 예약 작업 생성)은 못 했다 — 이유 둘

**(a) 관리자 권한 UAC 승인은 대표님이 물리적으로 그 컴퓨터 앞에 계셔야
한다.** `register-ak-system-scheduled-task-as-admin.cmd
videobox-approval-connector-watchdog -Yes`를 이 세션이 대신 실행해도,
Windows 보안 승인 창은 사람이 그 화면 앞에서 클릭해야만 넘어간다.
대표님이 이번 세션 동안 모바일이라 이 창을 누를 수 없어서 여러 번
"사용자가 취소함"으로 실패했다.

**(b) 이보다 더 중요한 발견 — 같은 날 AK-System Hermes 세션에서 대표님이
이미 "이번 세션에서는 새 예약 작업 등록을 보류하라"고 지시하신 기록을
찾았다.** `docs/superpowers/plans/2026-09-25-01-data-and-execution-layer-python-postgres-migration.md`
(그 저장소, Task 3 Step 5)에 이렇게 적혀 있다:

> "검증되면 파이썬 버전을 실제 예약작업으로 등록... **아직 착수 안 함** —
> 대표님 지시(2026-09-25, W1137)로 이 세션에서는 새 예약작업(윈도우든
> 파이썬 스케줄러든) 실제 등록·전환은 보류하고 시범 사례의 파이썬 버전
> 완성·검증까지만 한다. 다음 세션에서 진행 여부 재판단."

배경: AK-System 전체가 예약작업 49개를 전부 파이썬(APScheduler 추천)
기반으로 옮기고 **윈도우 작업 스케줄러 의존을 0으로 만들기로** 같은 날
확정했다(파도 단위 점진 전환, 시범 사례 하나로 검증 중). 그 계획 문서의
Task 3 비교표에 `videobox-approval-connector-watchdog`(이번에 내가 만든
바로 그 작업)가 **이미 후보로 이름이 올라 있었다** — 즉 그쪽 세션도
이 파일을 이미 읽었다는 뜻이다. 이게 아마 내 등록 파일 편집이 두 번이나
"흔적도 없이 사라진" 이유였을 것이다(그쪽 세션이 같은 파일을 동시에
다시 쓰고 있었을 가능성이 크다 — 확실하지 않으니 짐작으로만 남긴다).

**그래서 실제 `Register-ScheduledTask` 반영은 이 세션이 의도적으로
진행하지 않았다.** VideoBox 쪽 요청(3항 상시 실행)과 AK-Hermes 쪽 요청
(새 예약작업 등록 보류)이 같은 날 서로 다른 세션에서 나온 대표님의
지시라 충돌한다 — 어느 쪽을 우선할지는 대표님 판단이 필요하다.

### 지금 상태 (정확히)

- `100_ak-system-hermes`: 세 파일(감시 스크립트·레지스트리 선언·개수
  가드) **로컬 커밋만 됨, push 안 함**. Windows에는 아직 아무 예약
  작업도 실제로 없다(`schtasks /query`로 직접 확인 완료).
- `65_videobox`: 관련 없음, 이미 깨끗하게 커밋·푸시됨.
- 결재함 큐 연결 서버(`node scripts/videobox-mcp-connector-server.js`)는
  **지금 이 컴퓨터에서 계속 떠 있다** — 이전 세션이 수동으로 띄운 채로,
  아직 안 죽었을 것이다(재부팅하면 죽는다, 상시 실행 문제 자체는
  여전히 안 풀림).

## 다음 세션이 할 일

**먼저 대표님께 확인**: AK-Hermes 쪽 "새 예약작업 보류" 지시(W1137)와
VideoBox 쪽 "결재함 다리는 상시로" 지시가 충돌한다 — 어느 쪽을
우선할지 여쭤봐라. 가능한 선택지:

1. **예외로 지금 등록한다** — VideoBox 다리는 20명 직원 업무 로직을
   전혀 안 건드리는 격리된 로컬 프로세스라(127.0.0.1 루프백만) 회사
   전체 파이썬 전환과 무관하게 지금 예외로 처리해도 안전하다고 볼 수
   있다. 이 경우 대표님이 컴퓨터 앞에서
   `register-ak-system-scheduled-task-as-admin.cmd
   videobox-approval-connector-watchdog -Yes`를 실행하고 Windows 승인
   창에 "예"만 누르면 끝난다(준비는 전부 끝나 있다, XML까지 검증
   완료).
2. **AK-Hermes 파이썬 전환을 기다린다** — `2026-09-25-01-data-and-execution-layer-python-postgres-migration.md`의
   Task 3(시범 사례 `founder-dashboard-recovery`)이 끝나고 다음 파도가
   열리면, `videobox-approval-connector-watchdog`도 처음부터 파이썬
   (APScheduler)으로 등록한다. 이미 만든 윈도우용
   `restart-videobox-approval-connector-if-down.ps1`은 그때 참고용
   PowerShell 원본으로만 남긴다.

결정이 나면:
- (1번을 고르면) 위 명령 실행 → `schtasks /query /tn "AK-System Hermes
  VideoBox Approval Connector Watchdog"`로 실제 등록 확인 → 로컬 커밋
  `5d57ca81`을 그때 `git push`.
- (2번을 고르면) 로컬 커밋은 그대로 두거나(참고용) 되돌리고, AK-Hermes
  마이그레이션 계획의 다음 파도 Task로 이 작업을 등록해 달라고 그쪽
  세션에 전달한다.

## 검증한 것 / 못한 것

- 검증함: `owner-ready.ps1` 재빌드 로직(테스트 123개), 새 워치독
  스크립트의 XML 투영 결과(TimeTrigger·ExecutionTimeLimit·LogonType·
  WindowStyle·WorkingDirectory 전부 의도대로).
- 못 함: 실제 Windows 예약 작업 등록(위 이유 둘 다), 등록 후 3시간
  주기로 실제 재시작이 동작하는지의 실물 확인(등록 자체가 안 됐으므로).
