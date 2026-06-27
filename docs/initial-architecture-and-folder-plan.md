# VideoBox Initial Architecture And Folder Plan

## Goal

Set up VideoBox as a local-first application with a SaaS-expandable architecture.

## Recommended Top-Level Structure

```text
65_videobox/
  docs/
  apps/
    desktop/
    web/
  services/
    api/
    worker/
  packages/
    core-engine/
    domain-models/
    provider-interfaces/
    storage-abstractions/
    timeline-schema/
    capcut-export/
  infra/
    local/
    containers/
  scripts/
  tests/
```

## Responsibility By Area

### `apps/desktop`

Local-first operator application.

Responsibilities:

- project creation
- asset library browsing
- review workflow
- preview launching
- local settings and provider key entry

### `apps/web`

Optional future web surface.

Not required for the first implementation, but the folder can exist to prevent desktop-specific assumptions from leaking into the rest of the system.

### `services/api`

Thin service layer for:

- local API process in desktop mode
- future remote API reuse
- auth integration later
- project/job coordination

This should not contain editing intelligence itself.

### `services/worker`

Job execution layer for:

- transcription
- analysis
- render
- export

In local-first mode this can run on the same machine.
Later it can be split into remote workers if needed.

### `packages/core-engine`

Pure application logic for:

- ingest orchestration
- analysis orchestration
- rough cut planning
- timeline generation
- shortform candidate selection

This is the most important package to keep deployment-agnostic.

### `packages/domain-models`

Shared models for:

- project
- asset
- segment
- timeline
- job
- export

### `packages/provider-interfaces`

Abstractions for:

- LLM providers
- STT providers
- TTS providers

The interfaces live here, while actual provider bindings can live elsewhere.

### `packages/storage-abstractions`

Abstractions for:

- reading media
- writing previews
- locating exports
- resolving URIs

### `packages/timeline-schema`

The internal source of truth for edit decisions.

All preview, review, rendering, and export steps should depend on this shared schema.

### `packages/capcut-export`

Isolated adapter layer.

CapCut schema drift should be absorbed here rather than leaking into the engine.

### `infra/local`

Local setup helpers such as:

- ffmpeg bootstrap notes
- local database setup
- local asset path conventions

### `infra/containers`

Container definitions for optional reproducibility and service packaging.

These should not become a hard blocker for early iteration.

## Suggested Data Boundaries

### Project

- `project_id`
- `owner_id`
- `workspace_id`
- `status`
- `settings`

### Asset

- `asset_id`
- `project_id`
- `asset_type`
- `storage_uri`
- `source_kind`
- `metadata`

### Job

- `job_id`
- `project_id`
- `job_type`
- `status`
- `input_ref`
- `output_ref`
- `error_message`

### Timeline

- `timeline_id`
- `project_id`
- `version`
- `output_mode`
- `tracks`

## Container Recommendation

Containers should be treated as a support tool, not the starting point of the product.

### What to containerize early if useful

- API service
- worker service
- local database if one is introduced

### What not to force into containers early

- FFmpeg-heavy media workflows that depend on desktop file access
- GPU-dependent local model execution
- the full desktop application

### Practical recommendation

Start with native local development first.
Add containers after the first working pipeline exists, mainly for:

- reproducible backend setup
- worker isolation
- future deployment alignment

If containers are introduced too early, they can slow down video tooling work, file path debugging, and GPU integration.

## Immediate Build Order

1. define shared domain models
2. define timeline schema
3. define provider interfaces
4. implement a local storage adapter
5. implement a local job runner
6. build the first ingest to preview pipeline
7. add CapCut export adapter
8. add a thin review UI
