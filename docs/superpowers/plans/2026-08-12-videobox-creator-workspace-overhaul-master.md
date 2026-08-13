# VideoBox Creator Workspace Overhaul Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로젝트 선택부터 개인 자산 등록, 촬영본 정리, 자체 편집, 유진 보조, 가로·세로 검토와 출력까지 VideoBox 안에서 끝내는 데스크톱 제작 작업실을 단계적으로 구축한다.

**Architecture:** 기존 프로젝트 편집 세션을 마스터 편집본으로 유지하고, 전역 사용자 미디어 라이브러리와 출력 변형을 별도 경계로 추가한다. 기존 자동 장면 감지, 의미 색인, 편집 명령, 유진 승인, 검토 lineage와 독립 렌더 작업은 확장하고, 기존 URL·프로젝트 데이터는 호환 어댑터와 lazy migration으로 보존한다.

**Tech Stack:** React 19, TypeScript, Vite, Radix, react-resizable-panels, FastAPI, Pydantic, SQLite global library, SQLite/PostgreSQL project stores, FFmpeg/FFprobe, LM Studio OpenAI-compatible local endpoints, Vitest, Playwright.

---

## Authority and non-negotiable rules

- Worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- Branch: `codex/videobox-container-compatibility`; never start from `main`.
- Design authority: `docs/superpowers/specs/2026-08-12-videobox-creator-workspace-overhaul-design.ko.md`.
- Decision authority: `docs/decisions/2026-08-12-creator-workspace-overhaul-direction.ko.md` and retained decisions named there.
- Backend tests must use the absolute `.venv\Scripts\python.exe -m pytest` command written in each wave.
- Containers must be operated only with `scripts/owner-ready.ps1`; never call Docker Compose directly.
- Do not touch `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`, owner source samples, or existing runtime project `videobox-pc-qa-20260811153350`.
- Dashboard copy must obey `docs/development-fast-path.ko.md §10.13`: no runtime, provider, model, API, job, revision, pipeline language on creator surfaces.
- Every mutation is RED → focused GREEN → broader verification. Every visual completion claim requires real-browser proof.
- Do not add mobile work. Supported acceptance viewports are `1920×1080`, `1440×900`, `1366×768`, and minimum `1280×800`.

## Scope reconciliation

The approved 2026-08-12 decision replaces the older “CapCut is the normal finish” boundary, but not the exclusions for professional color grading, complex masks/keyframes, multicam, or advanced motion graphics. Wave 0 updates `CLAUDE.md` and `docs/implementation-plan.ko.md` before feature code so later workers cannot follow the stale boundary.

## Reuse decisions

| Existing unit | Decision | Use |
|---|---|---|
| `MediaLibraryStore` | partial port | Retain verified packs, descriptors, semantic search; add a separate user-asset lifecycle schema in the same global SQLite authority. |
| `media_inbox.py` | partial port | Reuse settled-file and hash logic; replace move/delete semantics with copy-only ingest service. |
| `library_audio_indexer.py`, `library_footage_indexer.py` | adopt | Make new user assets automatically eligible through content hash and description version. |
| `AutoCutPlanner`, `FfmpegAutoCutExecutor` | adopt | Convert output into persisted footage proposals; never mutate editor segments directly. |
| editing session commands | adopt | Keep master timeline, optimistic revision, immediate save, undo/redo and invalidation. |
| `YujinProposal` validation | extend | Add variant-scoped operations and identity; preserve fail-closed attestation. |
| review/output lineage | extend | Bind derived variant timeline and variant revision; reuse independent render jobs. |
| existing `MediaWorkspacePage` | compatibility adapter | Keep project-specific asset reference screen; do not turn it into the global library SSOT. |
| `PreviewStage` | exclude from footage organizer | It is editing-session/exact-preview coupled. Build a bounded footage preview controller around native media and existing asset preview patterns. |

## Wave order and hard gates

| Wave | Plan | Depends on | Current status (2026-08-13) | Gate before next wave |
|---|---|---|---|---|
| 0 | [Workspace and SSOT](2026-08-12-videobox-wave0-workspace-ssot.md) | none | **core implemented, visual gate partial**; official `1280×800` pass exists, exact four-viewport official capture/reverse action remains | Old routes work, new IA is browser-usable, docs no longer contradict. |
| 1 | [Personal media library](2026-08-12-videobox-wave1-personal-media-library.md) | Wave 0 | **core implemented, gate partial**; starter B-roll pack and dedicated destructive real-browser flow remain open | B-roll/music/SFX drag/drop, copy, dedupe, search, preview, trash/restore and delete guard work in browser. |
| 2 | [Footage organizer](2026-08-12-videobox-wave2-footage-organizer.md) | Wave 1 | **implementation gate complete**; human owner acceptance separate | Long footage proposal and virtual sequence approval create searchable derived B-roll without changing originals. |
| 3 | [Creator editor and output variants](2026-08-12-videobox-wave3-editor-output-variants.md) | Waves 0–2 | **implementation gate complete**; server variant runtime/browser evidence recorded, human acceptance separate | Direct editor operations and linked horizontal/vertical variants persist and recover in browser. |
| 4 | [Yujin, review and multi-output](2026-08-12-videobox-wave4-yujin-review-output.md) | Wave 3 | **open**; fixed four-chip starter baseline only, variant proposal/review/multi-output implementation remains | Proposal/cancel/apply/undo, current-variant review, independent horizontal/vertical outputs work. |
| 5 | [Owner acceptance and closeout](2026-08-12-videobox-wave5-owner-acceptance.md) | Waves 0–4 | **open**; current runtime preflight complete, dedicated project/full flow/artifact watch/human acceptance remain | Owner can complete and watch a dedicated real project; evidence, review, gap and reverse checks are pinned. |

This table records current repository truth, including work that historically advanced before every earlier checklist was reconciled. Close the remaining Wave 0/1 gates and Wave 4 implementation before final Wave 5 acceptance; do not reinterpret completed Wave 2/3 slices as satisfying those residual gates.

Do not start the next wave because unit tests pass. The wave’s 실제 브라우저 gate must be completed on the exact committed source. If a gate exposes a defect, fix it within the same wave and rerun the affected reverse/failure path.

## Cross-wave data ownership

```text
global user library (media_library.sqlite)
  library_user_assets -> derivatives -> ingest records -> trash state
          | project reference/materialization
project store (SQLite or PostgreSQL)
  project assets -> master editing session -> output variants -> derived timelines
                                         -> current review -> independent render jobs
```

- Global library remains local SQLite because this is a single-owner local product. 콘텐츠 해시를 중복·파생물 identity의 기준으로 삼고, `BEGIN IMMEDIATE`, bounded transactions and migration-concurrency tests를 사용한다.
- Project state retains SQLite/PostgreSQL parity. New project-scoped variant tables must update both `sqlite_schema.py` and `postgres_schema.py` compatibility identifiers/tests.
- Starter-pack rows stay immutable pack assets. User assets have their own lifecycle and provenance; do not fake them as a synthetic verified pack.
- Project materialization records an explicit global-library reference. Metadata strings alone are not a referential-integrity mechanism.

## Design coverage matrix

| Design section | Implementing tasks | Acceptance evidence |
|---|---|---|
| §2 existing decisions | Wave 0 Task 0 | documentation contract and retained palette browser proof |
| §§3–4 goals and information architecture | Wave 0 Tasks 1–3 | canonical/legacy route tests and real project navigation |
| §5 desktop layout/buttons | Wave 0 Task 3 | four viewport captures, internal scroll and reverse collapse |
| §6 personal library | Wave 1 Tasks 1–7 | three media types ingest/search/preview/delete lifecycle |
| §7 footage organizer | Wave 2 Tasks 1–5 | proposal cancel/apply and unchanged source hashes |
| §8 creator editor | Wave 3 Task 4 | direct commands, reload recovery and undo/redo |
| §9 linked variants | Wave 3 Tasks 1–6 | lock/rebase/conflict and horizontal/vertical materialization |
| §10 Yujin | Wave 4 Tasks 1–3 | starter fill-only, preview/cancel/apply/undo and strict rejection |
| §11 review/output | Wave 4 Tasks 4–7 | exact lineage and independent sibling render recovery |
| §12 starter pack/licenses | Wave 1 Tasks 1, 3, 7 | immutable builtin lifecycle and provenance display |
| §13 failure/recovery | Every wave gate; Wave 5 Task 6 | authoritative reconciliation and enumerated reverse paths |
| §14 construction order | This master wave order | each browser gate closes before its dependent wave |
| §15 completion | Wave 5 Tasks 1–7 | automated, official browser, artifact and owner acceptance separated |

## New file ownership map

- `library_assets.py` owns global user-media identity and lifecycle vocabulary.
- `library_user_asset_store.py` owns user-asset SQLite persistence; `MediaLibraryStore` remains the facade used by API/bootstrap.
- `library_ingest.py` owns durable copy and idempotency; routers never implement filesystem copy rules.
- `footage_organizer.py` domain/core/store files own proposal and derived-source semantics; editor split commands remain unrelated.
- `output_variants.py` domain/core/store files own inheritance, locks, conflicts and derived materialization.
- `starterRegistry.ts` owns contextual starter selection; chat and workbench only render the selection.
- `variantOutputState.ts` owns independent output-card reconciliation; `OutputsPage.tsx` remains page composition, not another state machine.

## Commit and review policy

- Each numbered Task ends with one logical commit using the message in its wave plan.
- Before each commit: focused tests, `git diff --check`, `git status --short`, and staged-file inspection.
- After each wave: run a read-only code review focused on P0/P1 functional regressions, then a spec gap table and one real reverse/failure browser flow.
- Push only after the wave gate is closed and HEAD is clean. Pin the exact SHA in the wave closeout note.
- `ProductShell.tsx` changes require `docs/oss/editor-ui-source-map.json` hash refresh and `tests/test_editor_ui_source_provenance.py`.

## Global completion criteria

- A dedicated QA project is created through the browser.
- B-roll, music and SFX are dragged into the global library, copied byte-for-byte, automatically indexed and previewed.
- A long source is split through a proposal and short sources are combined virtually; originals remain unchanged.
- The owner performs direct timeline editing and applies one Yujin proposal after preview; cancel and undo are proven.
- Reload preserves the same master revision, selected variant and playhead.
- Horizontal and vertical-full reviews bind the current master and variant revisions.
- Horizontal and vertical MP4 jobs are independently recoverable; both files pass FFprobe and play in VideoBox.
- Optional vertical highlight does not exist until explicitly created.
- Full watch/listen and caption timing are accepted by the owner. Tests and FFprobe do not substitute for this.

## Plan self-review result

- Spec coverage: every design section maps to an implementing wave and an acceptance gate in the matrix above.
- Missing-scope repair: added verified CC0 B-roll pack work and strict Yujin footage-plan interpretation after the first pass exposed those gaps.
- Type consistency: global identity is always `library_asset_id`; project edits use `session_id/session_revision`; output changes add `variant_id/variant_revision`; derived review/render artifacts carry all four identities.
- Compatibility: existing project URLs, pack assets, session JSON, timelines and legacy artifacts are read-compatible. New behavior uses additive tables, lazy seeding and explicit compatibility branches.
- Failure semantics: response loss reconciles authoritative state; sibling output jobs are independent; user locks and approved metadata are never silently overwritten.
- Scope check: the work is intentionally split into six independently gated plans so no Luna execution turn owns unrelated storage, UI, editing and rendering changes at once.
