# VideoBox 컨테이너·PostgreSQL 기반 인수인계

**날짜:** 2026-07-19
**브랜치:** `codex/videobox-container-compatibility`
**상태:** 컨테이너 호환 기반 구현·실데이터 runtime 검증 완료. PostgreSQL 전체 mutation parity hardening은 후속 slice.

## 확정된 경계

- Compose project name은 정확히 `65_videobox`이다.
- `videobox-web`만 `127.0.0.1:5173`에 공개한다. API와 PostgreSQL은 host port가 없다.
- 기존 데이터 원본 `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`는 수정·이동·삭제하지 않았다.
- 새 복사본은 `D:\AI_Workspace_louis_office_50\20_project\65_videobox-container-data`다.
- 복사본은 SQLite read-only backup API로 생성한 일관된 snapshot이며 `container-migration-manifest.json`의 49개 파일 SHA-256으로 검증한다.
- 컨테이너 API의 운영 store는 `VIDEOBOX_DATABASE_URL`이 있을 때 PostgreSQL을 사용한다. SQLite는 snapshot·자산 경로와 이전 입력으로만 남는다.
- Hermes, GPT OAuth, mem0, host bridge, OpenCut, SaaS auth/billing은 이번 변경에 넣지 않았다. mem0는 이후 Hermes 보조기억일 뿐 VideoBox SSOT가 아니다.
- Gemini provider call은 0이다.

## 실측 runtime 증거

1. snapshot에서 `b-roll-smoke-test`, `progress-bar-live-test` 두 프로젝트를 PostgreSQL에 import했다.
2. `http://127.0.0.1:5173/api/projects`가 2개 프로젝트를 반환했다.
3. `b-roll-smoke-test`의 `final_render_job_009/content`가 프록시를 통해 `200`, `video/mp4`, `841742` bytes로 전달됐다.
4. `scripts/verify_container_stack.ps1`은 snapshot hash 49개, 프로젝트 2개, source preserved, API/PostgreSQL host-port 미공개를 확인했다.

## 재현 명령

`.env.container.example`을 `.env.container`로 복사하고 전용 빈 data root와 PostgreSQL 비밀번호를 설정한다. 원본을 직접 mount하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\migrate_container_data.py --source 'D:\AI_Workspace_louis_office_50\20_project\65_videobox-project' --target 'D:\AI_Workspace_louis_office_50\20_project\65_videobox-container-data'
docker compose --env-file .env.container up -d --build
docker compose --env-file .env.container exec -T videobox-api sh -c 'python scripts/import_sqlite_snapshot_to_postgres.py --source /videobox-data --database-url "$VIDEOBOX_DATABASE_URL"'
.\scripts\verify_container_stack.ps1 -DataRoot 'D:\AI_Workspace_louis_office_50\20_project\65_videobox-container-data'
```

## 아직 열어 둘 항목

- `PostgresProjectStore`는 기존 `LocalProjectStore`의 SQLite SQL surface를 명시적으로 변환한다. 실데이터 project listing, playback, 새 project 생성과 snapshot import는 확인했지만, 모든 편집 mutation·복구·concurrency 경로를 PostgreSQL로 전면 검증한 것은 아니다.
- 이 parity hardening을 마친 뒤에만 Hermes agent를 추가한다. Hermes의 GPT OAuth·mem0는 별도 서비스/volume/승인 경계를 가진다.
- Task 9 사람/환경 acceptance 및 CapCut Desktop evidence는 이 작업으로 완료 처리하지 않는다.
