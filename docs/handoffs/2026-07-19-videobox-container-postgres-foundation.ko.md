# VideoBox 컨테이너·PostgreSQL 기반 인수인계

**날짜:** 2026-07-19
**브랜치:** `codex/videobox-container-compatibility`
**상태:** 컨테이너 호환 기반과 identified shared-store isolation hardening·실데이터 runtime 검증 완료. 모든 mutation/recovery/concurrency parity는 후속 audit.

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

## 2026-07-19 shared-store isolation 보완

- 기존 SQLite는 프로젝트별 파일이어서 deterministic ID가 파일 안에서만 고유했다. PostgreSQL 공유 DB에서는 동일 ID가 충돌하거나 미범위 query가 다른 프로젝트를 볼 수 있어, 해당 per-project table을 `(project_id, identifier)` composite key로 전환하고 CRUD/list/count query를 project scope로 제한했다.
- 대상은 timelines, review approvals, editing sessions, exports, transcripts, segment analysis runs, preview renders, subtitle renders, assets, segments, recommendations, jobs, TTS candidates, Gemini provider keys다.
- PG two-project regression은 동일 timeline/session/export/asset/job/TTS/key ID의 읽기·수정·삭제 격리를 확인한다. provider-key는 로컬 persistence만 다루며 Gemini provider/network call은 하지 않는다.
- 기존 파생 PostgreSQL volume은 정확히 `65_videobox_videobox_postgres_data`만 재생성해 immutable snapshot을 다시 import했다. 원본 source는 유지됐다. 재import 후 `b-roll-smoke-test` timeline 7개, `progress-bar-live-test` timeline 1개를 확인했다.
- 최신 API 컨테이너는 user/media library를 `/videobox-data/videobox-user-library`에 두므로 read-only root 밖에 쓰려던 이전 mount 결함도 없다.

## 검증 상태

- 통과: container config/migration/compose tests `10 passed`, PostgreSQL store/import integration `4 passed`, source-audio media controls `6 passed`, FFmpeg final renderer + playback delivery `18 passed`, web production build, Docker image build, runtime verifier.
- 최신 focused 검증: provenance, container data-root, PostgreSQL compatibility/store/import, media controls, user library/favorites/media library를 합쳐 `65 passed`다. PostgreSQL two-project suite는 `15 passed`다. full suite는 closeout 직전 최신 코드로 다시 실행해 기록한다.
- `npm audit`은 moderate 1, high 1, critical 1을 보고했다. 이번 전환 범위 밖의 기존 dependency 상태여서 자동 업그레이드는 하지 않았다.

## 재현 명령

`.env.container.example`을 `.env.container`로 복사하고 전용 빈 data root와 PostgreSQL 비밀번호를 설정한다. 원본을 직접 mount하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\migrate_container_data.py --source 'D:\AI_Workspace_louis_office_50\20_project\65_videobox-project' --target 'D:\AI_Workspace_louis_office_50\20_project\65_videobox-container-data'
docker compose --env-file .env.container up -d --build
docker compose --env-file .env.container exec -T videobox-api sh -c 'python scripts/import_sqlite_snapshot_to_postgres.py --source /videobox-data --database-url "$VIDEOBOX_DATABASE_URL"'
.\scripts\verify_container_stack.ps1 -DataRoot 'D:\AI_Workspace_louis_office_50\20_project\65_videobox-container-data'
```

## 아직 열어 둘 항목

- `PostgresProjectStore`는 기존 `LocalProjectStore`의 SQLite SQL surface를 명시적으로 변환한다. 위 identified deterministic-ID/shared-store path는 보완했지만, 모든 편집 mutation·복구·concurrency 경로를 PostgreSQL로 전면 검증한 것은 아니다.
- 이 parity hardening을 마친 뒤에만 Hermes agent를 추가한다. Hermes의 GPT OAuth·mem0는 별도 서비스/volume/승인 경계를 가진다.
- Task 9 사람/환경 acceptance 및 CapCut Desktop evidence는 이 작업으로 완료 처리하지 않는다.
