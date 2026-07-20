# VideoBox Hermes Dashboard Platform Mem0 handoff — 2026-07-20

## 현재 결과

- 작업 저장소: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility`
- 공식 Hermes Dashboard는 `nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787`으로 기동한다.
- 로컬 접근 주소는 `http://127.0.0.1:9119`이며, 2026-07-20 HTTP `200`과 `HERMES_DASHBOARD_READY`를 확인했다.
- 대시보드는 `videobox-hermes-provider-egress`만 사용하며 VideoBox DB·API·media·internal/edge network 및 local Ollama memory network에 연결하지 않는다.
- 실제 Docker Ollama container, model volume, image는 제거했다. source에는 과거 custom local-runtime/Ollama bootstrap 초안이 아직 남아 있으며 대시보드 실행 경로에는 연결되지 않는다.

## Mem0 설정 경로

Hermes Dashboard에서 다음만 수행한다.

1. `Memory Provider`를 연다.
2. `mem0`을 고른다.
3. `Platform`을 고른다.
4. Mem0 Platform API key를 **대시보드에만** 입력하고 연결 상태를 확인한다.

채팅·Git·문서에 API key를 기록하지 않는다. 이 handoff 시점에는 API key 입력, memory write, GPT provider request는 아직 증빙하지 않았다.

## 검증 결과

- `.venv\Scripts\python.exe -m pytest -q tests/test_compose_contract.py tests/test_hermes_runtime_foundation.py`: `14 passed`, 기존 multipart PendingDeprecationWarning 1건.
- `docker compose -p 65_videobox config --quiet`: 통과.
- `docker compose -p 65_videobox --profile hermes-dashboard up -d --force-recreate videobox-hermes-dashboard`: 통과.
- `http://127.0.0.1:9119/`: HTTP `200`.
- `git diff --check`: 통과.
- 전체 Python regression은 사용자 요청으로 종료했으므로 **미검증**이다.

## 다음 세션 첫 작업

1. `docker compose -p 65_videobox ps -a`와 `http://127.0.0.1:9119`를 다시 확인한다.
2. 사용자가 대시보드에서 Mem0 Platform API key를 입력한 뒤 provider 연결 상태만 확인한다. key, memory 내용, GPT request는 출력하지 않는다.
3. source에 남은 local Ollama/custom runtime bootstrap 초안을 Platform-only 결정을 기준으로 삭제할지, 추후 self-hosted 선택지로 보존할지 명시적으로 결정한다. 현재 요구에는 필요하지 않으므로 기본 권고는 삭제다.
4. Hermes Dashboard 설정과 별개로 공식 계획서의 다음 VideoBox 편집기 goal을 재개한다. Task 9 수동 acceptance는 실제 장면 MP4와 사람 승인 증빙 전까지 **9/22 (40.9%)**를 유지한다.
