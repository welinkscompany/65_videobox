# VideoBox Container Compatibility Migration Design

**Date:** 2026-07-19  
**Status:** user-approved design; implementation plan pending  
**Scope:** 현재 VideoBox를 Docker Compose 프로젝트 `65_videobox`로 비파괴 이전하는 1단계

## 1. Decision

현재 호스트에서 직접 실행하는 VideoBox web/API/FFmpeg 경로를 먼저 Compose로 옮긴다. 기존 프로젝트 데이터는 새 host-managed data root로 **복사**하고, 원본 데이터는 삭제하거나 이동하지 않는다.

이 단계는 Hermes, GPT OAuth, mem0, host bridge, egress proxy, 별도 render worker를 구현하지 않는다. 이들은 컨테이너화된 VideoBox 호환 경로가 검증된 뒤 별도 단계로 도입한다.

## 2. Architecture

```text
Browser
  -> videobox-web (loopback only)
  -> videobox-api (internal only; compatibility FFmpeg renderer included)
  -> /videobox-data (host-managed copied data root)
```

- Compose project name is exactly `65_videobox`.
- `videobox-web` is the only loopback host port. API remains internal.
- `videobox-api` runs the existing API plus current FFmpeg render path. This is a compatibility boundary, not the final isolated render-worker design.
- Data inside containers uses `/videobox-data`; durable records keep project-relative storage URIs, never container paths.
- API images run non-root with a read-only root filesystem where current dependencies allow it. No Docker socket, user home, arbitrary media library, Hermes state, or OAuth secret is mounted.

## 3. Data Migration Contract

The existing default root is `D:\AI_Workspace_louis_office_50\20_project\65_videobox-project`. The new container root is a separately configured host directory (`VIDEOBOX_CONTAINER_DATA_ROOT`).

1. A migration command requires explicit source and target roots.
2. It refuses source=target, missing source, target inside source, and a non-empty unrecognized target.
3. It copies project files to staging, computes streaming SHA-256 for copied files, verifies SQLite/project metadata, then atomically publishes the target project directory.
4. It records a migration manifest with source path, target path, file count, hashes, timestamp, and source-preserved status.
5. It never deletes, renames, or mutates the source root.
6. Re-running with the same verified manifest is idempotent; mismatched content fails closed.

The first container launch refuses to use an empty target root unless the migration command has completed successfully.

## 4. Runtime Configuration

- `VIDEOBOX_DATA_ROOT` becomes the authoritative runtime data-root override. The current path remains the host-development default only.
- Compose resolves its bind mount from `VIDEOBOX_CONTAINER_DATA_ROOT` and passes `/videobox-data` as `VIDEOBOX_DATA_ROOT` to the API.
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

1. Compose project name is `65_videobox` and the API has no host port.
2. Migration copies a fixture project, preserves source bytes, rejects unsafe targets, and is idempotent.
3. API resolves the mounted `/videobox-data` root from configuration rather than the hard-coded Windows default.
4. The Compose stack starts from copied data, exposes the web service only on loopback, and returns API health through the proxy.
5. Existing focused API/render tests still pass; container-specific tests run without Gemini, OAuth, Hermes, or external HTTP calls.

## 7. Later Stages

After this stage is verified, a second design/plan will split the render worker. Only then does the Hermes stage add `videobox-hermes-agent`, its isolated state volume, and user-initiated GPT OAuth device/PKCE login.
