# VideoBox Container Compatibility Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the current VideoBox web/API/FFmpeg compatibility runtime into Compose project `65_videobox` while copying existing project data without mutating its source.

**Architecture:** Add an environment-resolved data-root boundary and a standalone migration command. Build a two-service Compose compatibility stack: loopback-only web reverse proxy and internal API containing the existing renderer. Hermes, OAuth, mem0, host bridge, and a split render worker remain later work; mem0 is Hermes auxiliary memory only.

**Tech Stack:** Python 3.12, FastAPI/Uvicorn, pytest, Node/Vite production build, Nginx, Docker Compose.

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

Copy into a sibling staging directory, compute SHA-256 per file, require a `projects/*/db/project.sqlite` tree, write `container-migration-manifest.json`, and rename staging only after verification. Refuse unsafe/nonempty targets and never call delete/move on source.

- [ ] **Step 4: Run GREEN and commit**

Run: `\.venv\Scripts\pytest.exe tests/test_container_data_migration.py -q`  
Commit: `feat: add non-destructive container data migration`

### Task 3: Compose compatibility stack

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

`videobox-api` installs Python dependencies plus FFmpeg, runs non-root Uvicorn, mounts only `${VIDEOBOX_CONTAINER_DATA_ROOT}:/videobox-data`, and sets `VIDEOBOX_DATA_ROOT=/videobox-data`. `videobox-web` builds the Vite app and proxies `/api` to `videobox-api:8000`. Apply `read_only`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, tmpfs, and loopback-only web publication.

- [ ] **Step 4: Run GREEN and Compose validation**

Run: `\.venv\Scripts\pytest.exe tests/test_compose_contract.py -q`  
Run: `docker compose -f compose.yaml config --quiet`  
Commit: `feat: add VideoBox Compose compatibility stack`

### Task 4: Runtime migration and smoke verification

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
