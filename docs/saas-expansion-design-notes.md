# VideoBox SaaS Expansion Design Notes

## Product Direction

VideoBox is implemented as a local-first application in the early phase, but its core engine, data model, job model, and provider interfaces must be designed so the product can later expand into a SaaS-backed model without a full rewrite.

This does not mean building full SaaS features now.
It means avoiding local-only assumptions in the engine and data boundaries.

## Design Rule

- Implementation priority: local-first
- Architecture priority: SaaS-expandable
- Core engine must be reusable across local desktop execution and future cloud worker execution
- Storage, auth, provider credentials, and delivery must stay outside the core engine

## Required Changes To The Existing Plan

### 1. Separate the core engine from the app shell

Keep these concerns isolated from UI, auth, billing, and deployment concerns:

- media ingest
- transcription
- speech cleanup analysis
- scene and topic analysis
- edit intent processing
- B-roll matching
- rough cut planning
- visual support planning
- audio planning
- timeline building
- preview planning
- CapCut export
- shortform extraction

The engine should accept structured inputs and emit structured outputs.
It should not depend on a specific desktop UI or direct cloud services.

### 2. Replace path-first thinking with identity-first thinking

Use records such as:

- `project_id`
- `asset_id`
- `job_id`
- `timeline_id`
- `provider_id`

Paths still exist, but they should be attached as storage metadata rather than treated as the primary identity.

This is important because local disk paths can later become cloud object URIs.

### 3. Introduce a storage abstraction

The engine should not assume every asset lives on a local filesystem forever.

Suggested concepts:

- `storage_provider`
- `asset_uri`
- `preview_uri`
- `export_uri`
- `storage_kind` such as `local`, `network`, `object`

In early local builds, these can all map to local files.

### 4. Treat long-running work as jobs

The plan should formalize background work as jobs:

- ingest job
- transcription job
- analysis job
- preview render job
- export job

Suggested statuses:

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

This helps both local orchestration and future cloud workers.

### 5. Add provider abstraction from day one

LLM, STT, and TTS should all go behind provider interfaces.

Examples:

- `LLMProvider`
- `STTProvider`
- `TTSProvider`

This allows:

- user-provided API keys
- platform-managed providers later
- local model execution later

### 6. Keep user assets and system assets separate

The data model should distinguish:

- user-owned B-roll
- user project inputs
- system starter assets
- licensed default assets

This becomes important later for sync, access control, packaging, and business rules.

### 7. Project-centric schema must be preserved

Each project should own:

- media inputs
- assets used
- edit intent
- segments
- timeline versions
- jobs
- previews
- exports
- shortform candidates

This structure works for both local and SaaS evolution.

### 8. Add identity boundaries even before auth exists

Even in local-first mode, records should be compatible with future ownership boundaries such as:

- `owner_id`
- `workspace_id`

These fields can be optional early on, but the schema should anticipate them.

### 9. Separate configuration layers

Do not mix all settings into one flat file.

Keep distinct configuration domains:

- app settings
- project settings
- provider settings
- render settings
- asset library settings

### 10. Capability flags are preferable to hard-coded assumptions

Examples:

- `allow_byo_llm`
- `enable_cloud_auth`
- `enable_default_broll_pack`
- `enable_managed_ai`

This lets the product evolve without rewriting major control flow.

## What Should Not Be Built Now

The following are compatible with future SaaS, but should not be built in the first implementation phase:

- billing
- multi-user collaboration
- browser-based full editor
- cloud render farm
- real-time synchronization
- full server-side project storage

These are expansion layers, not MVP requirements.

## Recommended MVP Interpretation

For the first implementation phase, the plan should narrow to:

1. local project creation
2. local media ingest
3. STT and segment analysis
4. rough cut planning
5. timeline JSON generation
6. preview render output
7. CapCut export
8. basic local-first operator dashboard / lightweight editing UI

This still fits the long-term SaaS-capable architecture if the boundaries above are respected.
