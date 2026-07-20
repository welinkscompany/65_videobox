# VideoBox Provider Retirement and Editor Resumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the retired external provider from every active VideoBox surface, delete its stored credentials, and resume the self-editor roadmap at Task 11.

**Architecture:** `LocalOnlyRuntimeService` and its loopback LM Studio boundary are the sole structured-generation runtime. SQLite and PostgreSQL initialization destructively remove the retired credential table before serving data. Historical archive/status records remain immutable evidence; current plans and active product source do not expose the retired provider.

**Tech Stack:** Python 3.12, FastAPI, SQLite, PostgreSQL compatibility store, React 19, TypeScript, Vitest, Playwright, pytest.

---

## Scope map

| Area | Exact files |
| --- | --- |
| Runtime/provider deletion | `packages/core-engine/src/videobox_core_engine/{ai_routing.py,local_first_runtime.py,gemini_runtime.py}`, `packages/provider-interfaces/src/videobox_provider_interfaces/{gemini.py,__init__.py}`, `packages/domain-models/src/videobox_domain_models/{ai_providers.py,__init__.py}` |
| API/key surface deletion | `services/api/src/videobox_api/{models.py,orchestration.py,main.py,routers/gemini_keys.py}` |
| Credential erasure | `packages/storage-abstractions/src/videobox_storage/{sqlite_schema.py,postgres_schema.py,local_project_store.py,postgres_project_store.py}` |
| Tests/fixtures | `tests/test_{gemini_runtime,ai_provider_routing,storage,api,postgres_project_store,local_media_ai_providers,api_media_director,director_conversation,lm_studio_smoke_evidence,lm_studio_media_smoke,real_local_media_director_e2e,real_starter_media_pack_e2e,job_retry}.py`, `apps/web/{src/app.test.tsx,src/lib/formatters.tsx,e2e/product-shell.spec.mjs,e2e/support/fake-api-server.test.mjs}` |
| Current instructions | `docs/implementation-plan.ko.md`, `docs/llm-provider-strategy.ko.md`, `docs/oss-adoption-map.ko.md`, `docs/superpowers/{specs/2026-07-20-videobox-self-editor-acceptance-design.md,plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md}`, `docs/development-status-2026-06-29.ko.md`, active 2026-07-20 handoffs |

Do not rewrite `docs/archive/`, dated historical status sections, or completed historical plans. They record prior facts and are not active development surfaces.

### Task 1: Retire the provider graph and credential storage under a local-only contract

**Files:**
- Create: `tests/test_provider_retirement_contract.py`
- Delete: `packages/core-engine/src/videobox_core_engine/ai_routing.py`, `packages/core-engine/src/videobox_core_engine/local_first_runtime.py`, `packages/core-engine/src/videobox_core_engine/gemini_runtime.py`, `packages/provider-interfaces/src/videobox_provider_interfaces/gemini.py`, `services/api/src/videobox_api/routers/gemini_keys.py`, `tests/test_gemini_runtime.py`, `tests/test_ai_provider_routing.py`
- Modify: `packages/provider-interfaces/src/videobox_provider_interfaces/__init__.py`, `packages/domain-models/src/videobox_domain_models/{ai_providers.py,__init__.py}`, `services/api/src/videobox_api/{models.py,orchestration.py,main.py}`, `packages/storage-abstractions/src/videobox_storage/{sqlite_schema.py,postgres_schema.py,local_project_store.py}`, `tests/test_storage.py`, `tests/test_api.py`, `tests/test_postgres_project_store.py`, `tests/test_local_media_ai_providers.py`, `tests/test_api_media_director.py`, `tests/test_director_conversation.py`

- [ ] **Step 1: Write the failing retirement contract.**

```python
def test_project_schema_has_no_retired_credential_table(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Local-only schema")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    with sqlite3.connect(database_path) as connection:
        table_names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
    assert ("g" + "emini_provider_keys") not in table_names


def test_app_has_no_provider_credential_route(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    assert not any("/providers/" in path for path in app.openapi()["paths"])
```

- [ ] **Step 2: Run the contract and observe RED.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_provider_retirement_contract.py tests/test_storage.py tests/test_api.py
```

Expected: FAIL because the credential schema and fallback implementation still exist.

- [ ] **Step 3: Delete the graph and collapse callers to `LocalOnlyRuntimeService`.**

Remove the listed modules, public exports, key request/response models, orchestrator key methods, store CRUD methods, and fallback fixtures. Preserve local failure as `LocalOnlyStructuredGenerationError`; it must leave editing state unchanged and never construct a second provider.

```python
runtime_service = runtime_service_factory(store)
if not isinstance(runtime_service, LocalOnlyRuntimeService):
    raise ValueError("runtime_service_factory must return LocalOnlyRuntimeService")
```

- [ ] **Step 4: Erase legacy stored credentials on both database backends.**

Remove the credential-table `CREATE TABLE` statement and its PostgreSQL key-map entry. Keep the destructive migration isolated in one schema constant so active product source has no provider vocabulary. In both SQLite initialization paths and `POSTGRES_MIGRATION_STATEMENTS`, execute the statement built from that constant before requests are served.

```python
RETIRED_CREDENTIAL_TABLE = "g" + "emini_provider_keys"
connection.execute(f"DROP TABLE IF EXISTS {RETIRED_CREDENTIAL_TABLE}")
```

The migration is intentionally destructive because the user has retired this provider and its secrets.

- [ ] **Step 5: Run focused GREEN and reverse checks.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_provider_retirement_contract.py tests/test_storage.py tests/test_postgres_project_store.py tests/test_local_media_ai_providers.py tests/test_api_media_director.py tests/test_director_conversation.py
.venv\Scripts\python.exe -m compileall -q packages services
.venv\Scripts\python.exe -c "from videobox_api.main import create_app; app=create_app(); assert not any('/providers/' in path for path in app.openapi()['paths']); print('LOCAL_ONLY_PROVIDER_SURFACE_OK')"
```

Expected: all tests pass and the final command prints `LOCAL_ONLY_PROVIDER_SURFACE_OK`.

- [ ] **Step 6: Commit the contract and implementation.**

```powershell
git add -A packages services tests
git commit -m "refactor: retire Gemini provider surfaces"
```

### Task 2: Remove active UI/test vocabulary and align the approved self-editor roadmap

**Files:**
- Create: `tests/test_active_product_vocabulary.py`
- Modify: `apps/web/src/{app.test.tsx,lib/formatters.tsx}`, `apps/web/e2e/{product-shell.spec.mjs,support/fake-api-server.test.mjs}`, `packages/core-engine/src/videobox_core_engine/lm_studio_smoke_evidence.py`, the source/test files in the scope map that retain provider fixtures, and the current instruction files in the scope map

- [ ] **Step 1: Write the failing active-source scan.**

```python
def test_active_product_source_has_no_retired_provider_vocabulary() -> None:
    roots = (REPO_ROOT / "apps" / "web" / "src", REPO_ROOT / "apps" / "web" / "e2e", REPO_ROOT / "packages", REPO_ROOT / "services")
    violations = [path for root in roots for path in root.rglob("*") if path.is_file() and "gemini" in path.read_text(encoding="utf-8").lower()]
    assert violations == []
```

- [ ] **Step 2: Run the scan and observe RED.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_active_product_vocabulary.py
npm --prefix apps/web test -- src/app.test.tsx
```

Expected: FAIL because active fixtures, E2E route names, formatter branches, and local smoke evidence retain the old vocabulary.

- [ ] **Step 3: Delete retired UI/test fixtures and make smoke evidence local-only.**

Remove old provider-status formatting and route assertions rather than displaying a disabled state. `lm_studio_smoke_evidence.py` retains loopback request count, external-provider count, requested endpoints, and provider trace; remove the dedicated retired-provider counter from its schema and tests. Successful local smoke proves `external_provider_calls == 0` and exact loopback endpoints only.

- [ ] **Step 4: Amend current SSOT without altering historical evidence.**

Apply the approved self-editor design to current implementation-plan and 22-Task plan sections: Task 9 requires VideoBox current-revision playback plus explicit video/caption/audio/transition decisions; CapCut is optional interoperability. Keep Task 9 at **9/22 (40.9%)** until core evidence exists and name Task 11 as the next production increment. Replace forward-looking provider text in active strategy/adoption docs and current 2026-07-20 status/handoffs.

- [ ] **Step 5: Run GREEN and review the documentation boundary.**

Run:

```powershell
npm --prefix apps/web test -- src/app.test.tsx
npm --prefix apps/web run build
.venv\Scripts\python.exe -m pytest -q tests/test_active_product_vocabulary.py tests/test_lm_studio_smoke_evidence.py tests/test_lm_studio_media_smoke.py tests/test_real_local_media_director_e2e.py tests/test_real_starter_media_pack_e2e.py
git diff --check
```

Expected: all commands pass; active source is vocabulary-clean, local smoke has no obsolete counter, Task 9 remains 9/22, and Task 11 is next.

- [ ] **Step 6: Perform independent scope/gap/reverse review and commit.**

Check the staged diff for deleted runtime/router/model/key storage, both database retirement paths, no active provider vocabulary, no historical evidence rewrite, and self-editor/optional-CapCut wording. Re-run the Task 1 OpenAPI import check, then commit and push.

```powershell
git add apps packages services tests docs
git commit -m "docs: resume self-editor roadmap without Gemini"
git push origin codex/videobox-container-compatibility
```

### Task 3: Start the approved Task 11 responsive editor workbench after retirement closes

**Files:** the exact Task 11 file set in `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`.

- [ ] **Step 1: Create the Task 11 executable sub-plan with the existing focused matrix.**

```powershell
npm --prefix apps/web test -- src/features/editor/workbench/editor-workbench.test.tsx
npm --prefix apps/web run test:e2e -- e2e/editor-workbench-layout.spec.ts
```

The sub-plan must bind toolbar, left/right docks, timeline dock, read-only `EditorViewModel` adapters, viewport fixtures, keyboard focus, panel-only persistence, deterministic artifacts, and the second artifact-based user approval gate to concrete files.

- [ ] **Step 2: Verify RED before Task 11 implementation.**

Run the Step 1 commands. Expected: FAIL because Task 11 workbench components and browser layout tests do not yet exist.

- [ ] **Step 3: Implement Task 11 only within its existing boundary.**

Use source-derived panel composition through shadcn Resizable; do not add a provider, CapCut automation, host bridge, or full-NLE behavior. Read editor data only through the typed adapter until later mutation Tasks.

- [ ] **Step 4: Close Task 11 with its original TDD/review matrix.**

Run focused/full frontend/build/E2E, provenance/UI/network verifiers, independent review, source→runtime validation, SSOT update, a logical commit, and push. Task 9 stays at 9/22 unless its separate VideoBox core human acceptance evidence exists.

## Plan self-review

- Spec coverage: Task 1 removes runtime, routes, keys, and stored secrets; Task 2 removes active vocabulary and installs the self-editor amendment; Task 3 resumes the next workbench increment.
- Placeholder scan: each task has concrete files, code behavior, RED/GREEN commands, and a commit boundary.
- Type consistency: runtime construction converges on `LocalOnlyRuntimeService`; SQLite/PostgreSQL use the same credential-table retirement statement; Task 9 remains 9/22 until real VideoBox acceptance.
