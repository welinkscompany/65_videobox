# VideoBox Container Compatibility Migration Design

**Date:** 2026-07-19  
**Status:** user-approved design; implementation plan pending  
**Scope:** 현재 VideoBox를 Docker Compose 프로젝트 `65_videobox`로 비파괴 이전하는 1단계

## 1. Decision

현재 호스트에서 직접 실행하는 VideoBox web/API/FFmpeg 경로를 Compose로 옮기고, 컨테이너의 운영 데이터베이스는 PostgreSQL로 사용한다. 기존 프로젝트 SQLite 데이터와 자산은 새 host-managed data root로 **복사**한 뒤 PostgreSQL 이관의 입력으로 사용하며, 원본 데이터는 삭제·이동·변환하지 않는다.

이 단계는 Hermes, GPT OAuth, mem0, host bridge, egress proxy, 별도 render worker를 구현하지 않는다. 이들은 컨테이너화된 VideoBox 호환 경로가 검증된 뒤 별도 단계로 도입한다. mem0는 이후에도 Hermes 에이전트의 보조기억일 뿐이며 VideoBox의 프로젝트·편집·자산·대화 SSOT를 대체하지 않는다.

## 2. Architecture

```text
Browser
  -> videobox-web (loopback only)
  -> videobox-api (internal only; compatibility FFmpeg renderer included)
  -> videobox-postgres (internal only; VideoBox operational records)
  -> /videobox-data (writable runtime copy)
  -> /videobox-snapshot (read-only verified SQLite preservation snapshot)
```

- Compose project name is exactly `65_videobox`.
- `videobox-web` is the only loopback host port. API remains internal.
- `videobox-postgres` is internal only. It is the operational database for the container runtime; publishing PostgreSQL to the host is prohibited.
- `videobox-api` runs the existing API plus current FFmpeg render path. This is a compatibility boundary, not the final isolated render-worker design.
- API bind mounts are exact: `${VIDEOBOX_CONTAINER_DATA_ROOT}/runtime:/videobox-data` is writable and `${VIDEOBOX_CONTAINER_DATA_ROOT}/snapshot:/videobox-snapshot:ro` is read-only. The API receives `VIDEOBOX_DATA_ROOT=/videobox-data` and `VIDEOBOX_SNAPSHOT_ROOT=/videobox-snapshot`; it must not mount the parent data root or source root.
- Durable records keep project-relative storage URIs, never container paths.
- API images run non-root with a read-only root filesystem where current dependencies allow it. No Docker socket, user home, arbitrary media library, Hermes state, or OAuth secret is mounted.

## 3. Data Migration Contract

The existing default root is `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`. The new container root is a separately configured host directory (`VIDEOBOX_CONTAINER_DATA_ROOT`).

1. A snapshot command requires explicit source and target roots.
2. It refuses source=target, missing source, target inside source, and a non-empty unrecognized target.
3. It copies project files to a sibling staging root, computes streaming SHA-256 for copied files, verifies SQLite/project metadata, then atomically publishes `snapshot/` and an initial writable `runtime/` copy.
4. The manifest is inside `snapshot/` and records source path, final target path, snapshot/runtime layout version, hashes, and source-preserved status. Runtime mutations never change snapshot verification.
5. A legacy flat target is upgraded only after its legacy manifest and file hashes verify. A crash is resumable only for proven states (`.staging` completed layout and/or `.legacy-backup` verified legacy copy). Unknown or incomplete recovery artifacts fail closed and are retained. A backup is removed only after the published target verifies completely.
6. A separate PostgreSQL import command reads only `/videobox-snapshot`, records a source-SQLite hash and import revision, then commits one project atomically. Re-running the identical verified snapshot is idempotent; a changed source requires an explicit new import revision.
7. It never deletes, renames, or mutates the source root.
8. Re-running with the same verified manifest is idempotent; mismatched content fails closed.

The first container launch refuses to use an empty target root unless the migration command has completed successfully.

## 4. Runtime Configuration

- `VIDEOBOX_DATABASE_URL` is required for the container API and points only to the internal PostgreSQL service. SQLite is not an operational container database.
- `VIDEOBOX_DATA_ROOT=/videobox-data` is the writable runtime root for mounted project assets. `VIDEOBOX_SNAPSHOT_ROOT=/videobox-snapshot` is the separately mounted, read-only verified SQLite snapshot root. The current host path remains the host-development default only.
- Compose resolves both bind mounts from `VIDEOBOX_CONTAINER_DATA_ROOT` and passes the runtime root, snapshot root, and internal PostgreSQL URL to the API.
- The web service proxies `/api` to the internal API service. It does not call an external provider.
- A health command verifies Compose service health, API readiness, the mounted root, and a project inventory count.

## 5. Explicit Exclusions

- No Gemini provider or fallback route.
- No Hermes agent, GPT OAuth bootstrap, mem0, host bridge, or external egress service.
- No Docker Desktop socket mount or host-wide media-directory mount.
- No source-data deletion, replacement, or automatic rollback by deletion.
- No change to Task 9 acceptance status.

## 6. Verification

The implementation must prove:

1. Compose project name is `65_videobox`; API and PostgreSQL have no host ports.
2. Snapshot migration copies a fixture project, preserves source bytes, rejects unsafe targets, and is idempotent.
3. PostgreSQL import proves the imported project records and asset references match the verified SQLite snapshot without using the SQLite file as the running database.
4. API resolves the mounted `/videobox-data` root and its internal PostgreSQL URL from configuration rather than hard-coded host paths.
5. The Compose stack starts from imported data, exposes the web service only on loopback, and returns API health through the proxy.
6. Existing focused API/render tests still pass; container-specific tests run without Gemini, OAuth, Hermes, or external HTTP calls.

## 7. Later Stages

After this stage is verified, a second design/plan will split the render worker. Only then does the Hermes stage add `videobox-hermes-agent`, its isolated state volume, user-initiated GPT OAuth device/PKCE login, and an isolated mem0 auxiliary-memory store. VideoBox's project/editing/asset/conversation databases remain authoritative.
