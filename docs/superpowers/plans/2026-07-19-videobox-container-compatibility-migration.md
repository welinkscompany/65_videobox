# VideoBox Container Compatibility Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the current VideoBox web/API/FFmpeg compatibility runtime into Compose project `65_videobox`, run operational data on internal PostgreSQL, and preserve existing SQLite project data as a non-mutated migration source.

**Architecture:** Add an environment-resolved runtime-data boundary, a separately mounted read-only verified SQLite snapshot, and a PostgreSQL storage adapter/import path. Build a three-service Compose compatibility stack: loopback-only web reverse proxy, internal API containing the existing renderer, and internal PostgreSQL. The API mount contract is exact: `${VIDEOBOX_CONTAINER_DATA_ROOT}/runtime:/videobox-data` (writable) and `${VIDEOBOX_CONTAINER_DATA_ROOT}/snapshot:/videobox-snapshot:ro` (read-only). Hermes, OAuth, mem0, host bridge, and a split render worker remain later work; mem0 is Hermes auxiliary memory only.

**Tech Stack:** Python 3.12, FastAPI/Uvicorn, PostgreSQL, psycopg, pytest, Node/Vite production build, Nginx, Docker Compose.

---

### Task 1: Data-root configuration

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/settings.py`
- Create: `tests/test_container_data_root.py`

- [ ] **Step 1: Write failing tests**

```python
def test_projects_root_uses_videobox_data_root_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "managed"))
    assert resolve_projects_root() == tmp_path / "managed"

def test_projects_root_keeps_host_default_without_override(monkeypatch):
    monkeypatch.delenv("VIDEOBOX_DATA_ROOT", raising=False)
    assert resolve_projects_root() == DEFAULT_PROJECTS_ROOT
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\pytest.exe tests/test_container_data_root.py -q`  
Expected: failure because `resolve_projects_root` does not exist.

- [ ] **Step 3: Implement the minimal resolver**

```python
def resolve_projects_root() -> Path:
    configured = os.environ.get("VIDEOBOX_DATA_ROOT", "").strip()
    return Path(configured) if configured else DEFAULT_PROJECTS_ROOT
```

Use it from `create_app` instead of reading the default constant directly.

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\pytest.exe tests/test_container_data_root.py -q`  
Commit: `feat: configure VideoBox data root`

### Task 2: Non-destructive migration command

**Files:**
- Create: `scripts/migrate_container_data.py`
- Create: `tests/test_container_data_migration.py`

- [ ] **Step 1: Write failing fixture tests**

```python
def test_migration_copies_project_and_preserves_source(tmp_path):
    result = migrate_container_data(source_root, target_root)
    assert (target_root / "projects" / "demo" / "db" / "project.sqlite").is_file()
    assert source_file.read_bytes() == b"source"
    assert result["source_preserved"] is True

def test_migration_rejects_source_equal_target(tmp_path):
    with pytest.raises(MigrationError, match="source and target"):
        migrate_container_data(tmp_path, tmp_path)
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\pytest.exe tests/test_container_data_migration.py -q`  
Expected: import failure for `migrate_container_data`.

- [ ] **Step 3: Implement staging-copy and manifest verification**

Copy into a sibling staging directory, compute SHA-256 per file, require a `projects/*/db/project.sqlite` tree, write `snapshot/container-migration-manifest.json`, initialize `runtime/` from that snapshot, and rename staging only after verification. Legacy flat targets must resume only proven `.staging`/`.legacy-backup` states; preserve unknown recovery artifacts and delete a verified backup only after the published snapshot/runtime layout verifies. Refuse unsafe/nonempty targets and never call delete/move on source.

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\pytest.exe tests/test_container_data_migration.py -q`  
Commit: `feat: add non-destructive container data migration`

### Task 3: PostgreSQL operational-store migration

**Files:**
- Create: `packages/storage-abstractions/src/videobox_storage/postgres_project_store.py`
- Create: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Create: `scripts/import_sqlite_snapshot_to_postgres.py`
- Create: focused PostgreSQL store/import tests

- [ ] **Step 1: Define the storage boundary and write failing contract tests**

The container runtime must select PostgreSQL only when `VIDEOBOX_DATABASE_URL` is configured. Existing host-development tests retain SQLite until the PostgreSQL store has parity.

- [ ] **Step 2: Implement schema, repository compatibility, and SQLite snapshot importer**

Keep project asset files in `/videobox-data`, but import every operational record needed by the current web/API flow into PostgreSQL. Record source SQLite SHA-256 and import revision. Never write the source or snapshot SQLite files.

- [ ] **Step 3: Run PostgreSQL integration tests**

Run against an ephemeral local Compose PostgreSQL service. Prove idempotent import and reject a source hash mismatch.

- [ ] **Step 4: Commit**

Commit: `feat: add PostgreSQL operational store migration`

### Task 4: Compose compatibility stack

**Files:**
- Create: `compose.yaml`
- Create: `docker/api.Dockerfile`
- Create: `docker/web.Dockerfile`
- Create: `docker/nginx.conf`
- Create: `.dockerignore`
- Create: `.env.container.example`
- Create: `tests/test_compose_contract.py`

- [ ] **Step 1: Write failing Compose contract tests**

```python
def test_compose_uses_exact_project_name_and_only_web_loopback_port():
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    assert compose["name"] == "65_videobox"
    assert compose["services"]["videobox-api"].get("ports") is None
    assert compose["services"]["videobox-web"]["ports"] == ["127.0.0.1:${VIDEOBOX_WEB_PORT:-5173}:8080"]
```

- [ ] **Step 2: Run RED**

Run: `\.venv\Scripts\pytest.exe tests/test_compose_contract.py -q`  
Expected: failure because `compose.yaml` is absent.

- [ ] **Step 3: Implement images and Compose**

`videobox-postgres` has a named data volume and no host port. `videobox-api` installs Python dependencies plus FFmpeg, runs non-root Uvicorn, mounts exactly `${VIDEOBOX_CONTAINER_DATA_ROOT}/runtime:/videobox-data` and `${VIDEOBOX_CONTAINER_DATA_ROOT}/snapshot:/videobox-snapshot:ro`, and sets `VIDEOBOX_DATA_ROOT=/videobox-data`, `VIDEOBOX_SNAPSHOT_ROOT=/videobox-snapshot`, and an internal `VIDEOBOX_DATABASE_URL`. `videobox-web` builds the Vite app and proxies `/api` to `videobox-api:8000`. Apply `read_only`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, tmpfs, and loopback-only web publication.

- [ ] **Step 4: Run GREEN and Compose validation**

Run: `\.venv\Scripts\pytest.exe tests/test_compose_contract.py -q`  
Run: `docker compose -f compose.yaml config --quiet`  
Commit: `feat: add VideoBox Compose compatibility stack`

### Task 5: Runtime migration and smoke verification

**Files:**
- Create: `scripts/verify_container_stack.ps1`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-19-videobox-container-compatibility-migration.ko.md`

- [ ] **Step 1: Write a failing PowerShell verifier test/fixture**

Verify the script rejects a target without a migration manifest and treats an API host port as a contract violation.

- [ ] **Step 2: Migrate a copy and start Compose**

Run: `\.venv\Scripts\python.exe scripts/migrate_container_data.py --source <existing-root> --target <new-root>`  
Run: `docker compose -p 65_videobox up -d --build`

- [ ] **Step 3: Verify actual runtime**

Confirm `docker compose -p 65_videobox ps`, web loopback health, proxied API health, target project inventory, source manifest hashes, and no API host listener. Stop the Compose stack only after evidence is captured; preserve copied data.

- [ ] **Step 4: Run affected/full tests, build, review, and commit**

Run focused migration/config/compose tests, current renderer tests, relevant API tests, frontend production build, `git diff --check`, and source→runtime inspection. Update SSOT/handoff without marking Task 9 complete. Commit and push the closed container-migration unit.

## 2026-07-19 implementation record

- [x] Task 1: `VIDEOBOX_DATA_ROOT`와 opt-in `VIDEOBOX_DATABASE_URL` 경계를 추가했다.
- [x] Task 2: 원본을 변경하지 않는 staging snapshot 복사기를 추가했다. 실행 중인 SQLite는 read-only backup API로 복사한다.
- [x] Task 3 (foundation): PostgreSQL schema, SQLite SQL compatibility surface, read-only SQLite snapshot importer, API store 선택 경계를 구현했다.
- [x] Task 4: Compose 프로젝트 이름 `65_videobox`, internal PostgreSQL/API, loopback-only web edge, non-root/read-only runtime을 구현했다.
- [x] Task 5 (runtime): 실제 데이터 snapshot 2개 프로젝트를 PostgreSQL에 import하고, `/api/projects`와 current-revision MP4 delivery를 `127.0.0.1:5173`에서 확인했다.
- [x] Recovery hardening: legacy flat copy를 `snapshot/` + `runtime/` layout으로 올릴 때, verified staging/backup crash state만 재개하고 불명확한 recovery artifact는 보존한 채 fail-closed한다. Compose contract은 runtime writable / snapshot read-only 두 bind mount로 고정한다.
- [ ] PostgreSQL store의 모든 편집 mutation/복구 경로에 대한 전면 parity suite는 Hermes 도입 전 별도 hardening slice로 계속 검증한다. 이번 단계에서 검증한 것은 실제 데이터 import, project listing, proxied playback 및 새 project 생성 API다.

Task 9 사람/환경 acceptance 상태는 이 컨테이너 이전으로 변경하지 않는다.

## 다음 통합 slice: Hermes (새 계획서 생성 금지)

Hermes는 이 계획과 최상위 `docs/implementation-plan.ko.md`의 §23을 이어서 구현한다. 시작 순서는 GPT OAuth device/PKCE 경계, internal-only Hermes service와 VideoBox typed-handler allowlist, read-only status/승인 요청 vertical slice, mem0 보조기억 경계, OAuth/logout·restart·Gemini 0 runtime gate다. VideoBox PostgreSQL/snapshot/runtime media direct mount와 편집 mutation·CapCut host bridge는 이 첫 Hermes slice 범위 밖이다.
