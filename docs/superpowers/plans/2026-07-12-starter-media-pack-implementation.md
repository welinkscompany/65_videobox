# VideoBox Starter Media Pack Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Ship an optional, verifiable starter pack of commercially usable music and SFX that can be searched, favorited, and safely materialized into projects for real FFmpeg and CapCut output.

**Architecture:** A pack is external content, never repository source. Verify manifest/files before activation, keep global library data separate from projects, and copy a chosen library asset through existing project registration before it can enter a timeline. Assetless recommendations remain non-applicable.

**Tech Stack:** Python 3.12, SQLite, SHA-256, FFmpeg/ffprobe, FastAPI, React/TypeScript, pytest, Vitest.

---

## Decision locks

- User-library default is <projects_root>/../videobox-user-library; installs are <user-library-root>/packs/<pack_id>/<version>.
- Music is MP3 CBR 320kbps; SFX is WAV PCM 48kHz mono. Manifest declares exact pack bytes within 300–500MB.
- Library identity is pack:<pack_id>:<asset_id>.
- Apply first calls LocalProjectStore.register_asset as BGM/SFX. Timeline stores only project local URI plus source library metadata.
- Only active, checksum-verified assets with official evidence explicitly allowing commercial use and redistribution are visible.
- Actual curation is a research gate: retrieve official license page on selection date and store URL, page-text hash, timestamp, creator, attribution. Search snippets/community summaries are never evidence.

## File structure

- Create: packages/domain-models/src/videobox_domain_models/media_pack.py — manifest/license invariants.
- Create: packages/storage-abstractions/src/videobox_storage/media_library_store.py — global SQLite library.
- Create: packages/core-engine/src/videobox_core_engine/media_pack_service.py — install/verify/materialize.
- Create: scripts/build-starter-media-pack.py and scripts/verify-starter-media-pack.py.
- Modify: services/api/src/videobox_api/main.py and models.py — library endpoints.
- Modify: apps/web/src/api.ts, App.tsx, styles.css — library/favorites/apply UI.
- Create: tests/test_media_pack.py, tests/test_media_library_store.py, tests/test_media_pack_service.py, tests/test_api_media_library.py.
- Modify: editing/output tests, apps/web/src/app.test.tsx, .gitignore, SSOT status docs.

### Task 1: Lock manifest and license validation

**Files:** media_pack.py and tests/test_media_pack.py.

- [x] Step 1 — Write RED validation tests.

~~~
def test_manifest_rejects_asset_without_redistribution_right() -> None:
    with pytest.raises(ValueError, match="redistribution"):
        MediaPackAsset.from_dict({"license": {"commercial_use": True, "redistribution": False}})

def test_manifest_requires_namespaced_unique_ids_and_sha256() -> None:
    manifest = MediaPackManifest.from_dict(valid_manifest())
    assert manifest.assets[0].library_asset_id == "pack:starter-001:music-001"
~~~

- [x] Step 2 — Run RED: .venv\Scripts\python.exe -m pytest tests/test_media_pack.py -q. Expected: import failure.
- [x] Step 3 — Require pack ID, semantic version, bytes, SHA-256, media type/duration, source, creator, official license URL, evidence timestamp/hash, commercial_use true, redistribution true. Reject duplicates/unknown license status.
- [x] Step 4 — Verify and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_media_pack.py -q
Expected: PASS.

~~~
git add packages/domain-models tests
git commit -m "feat: validate starter media manifests"
~~~

### Task 2: Installer, integrity check and library index

**Files:** media_library_store.py, media_pack_service.py, scripts/verify-starter-media-pack.py, tests/test_media_library_store.py, tests/test_media_pack_service.py.

- [x] Step 1 — Write RED tests for interrupted staged install, checksum mismatch/no activation, idempotent reinstall, inactive-only removal, unavailable library DB not blocking project edit.
- [x] Step 2 — Run RED: .venv\Scripts\python.exe -m pytest tests/test_media_library_store.py tests/test_media_pack_service.py -q. Expected: import failure.
- [x] Step 3 — Extract to <version>.staging, validate SHA-256 and ffprobe duration, transactionally index, atomically rename, then activate. Failure deletes only staging and returns structured error.
- [x] Step 4 — Store packs, assets, favorites, recent usage, immutable license evidence. Search returns active/verified/non-missing only.
- [x] Step 5 — Verify and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_media_library_store.py tests/test_media_pack_service.py -q
Expected: PASS.

~~~
git add packages/storage-abstractions packages/core-engine scripts tests
git commit -m "feat: install and verify starter media packs"
~~~

### Task 3: Materialize media before timeline use

**Files:** editing_session_and_regeneration.py, API files, test_api_media_library.py, test_editing_session.py, test_api.py, test_pycapcut_adapter.py, test_ffmpeg_final_renderer.py.

- [x] Step 1 — Write RED E2E: install synthetic pack, materialize pack:starter-001:music-001, apply music override, assert timeline/FFmpeg/CapCut use only local://projects/<id>/assets URI. Assert assetless recommendation returns 422 and changes no timeline.
- [x] Step 2 — Run RED: .venv\Scripts\python.exe -m pytest tests/test_api_media_library.py tests/test_editing_session.py -q. Expected: missing endpoint/service.
- [x] Step 3 — Implement POST /media-library/assets/{library_asset_id}/materialize. Infer only BGM/SFX, call LocalProjectStore.register_asset, persist source ID/pack/version/license snapshot, update recent/favorite only after success.
- [x] Step 4 — Require project asset_id and resolvable URI for automatic application; return asset_missing blocker; never substitute external pack path.
- [x] Step 5 — Verify reverse output and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_api_media_library.py tests/test_editing_session.py tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py -q
Expected: PASS.

~~~
git add packages/core-engine services/api tests
git commit -m "feat: materialize library media into projects"
~~~

### Task 4: Library, preview and favorites UI

**Files:** apps/web/src/api.ts, App.tsx, styles.css, app.test.tsx.

- [x] Step 1 — Write RED Vitest cases for install state, BGM/SFX/tag/duration search, preview, favorite after reload, disabled apply for missing/unverified item, successful materialize-then-apply.
- [x] Step 2 — Implement separate BGM/SFX drawer with license/attribution/version, favorites/recent filters, preview without mutation, one Apply waiting for materialization before existing override mutation.
- [x] Step 3 — Global DB unavailability is non-blocking notice; missing pack asset cannot preview/apply; project editor stays usable.
- [x] Step 4 — Verify and commit.

Run: npm --prefix apps/web test; npm --prefix apps/web run build
Expected: PASS.

~~~
git add apps/web
git commit -m "feat: add starter media library UI"
~~~

### Task 5: Curate and release first pack

**Files:** starter-media-pack/manifest.json, starter-media-pack/LICENSES.md, scripts/build-starter-media-pack.py, .gitignore, docs/implementation-plan.ko.md, docs/development-status-2026-06-29.ko.md.

- [x] Step 1 — Complete official-license research for every candidate. Store all Task 1 facts; reject unclear/non-commercial/non-redistributable terms and conversion-prohibited terms. 2026-07-14: `docs/starter-media-pack-license-research.ko.md` records 30 music/100 SFX with creator, official page, direct file, CC0 evidence hash and attribution. 130 direct asset URLs and 36 official asset pages returned HTTPS 200. This marks the research gate only; source-byte/hash/transcode/manifest build remain the next gate.
- [x] Step 2 — Write RED verifier tests for wrong music codec/bitrate, wrong SFX format, pack size outside 300–500MB, missing evidence. 2026-07-14: core service gate regression also covers missing/tampered evidence, wrong codec, average-320kbps VBR, source-before-staging rejection, and ID3v2.3/v2.4 CBR parser boundaries.
- [ ] Step 3 — Build manifest/checksums/LICENSES reproducibly. Put archive/media only in ignored dist/starter-media-pack; never track binaries.
- [ ] Step 4 — Release verify.

Run: .venv\Scripts\python.exe scripts\verify-starter-media-pack.py dist\starter-media-pack
Run: .venv\Scripts\python.exe -m pytest -q
Run: npm --prefix apps/web test
Run: npm --prefix apps/web run build
Expected: PASS. Run one 600-second Korean ingest → materialize BGM/SFX → edit → SRT → MP4 → real CapCut draft smoke.

- [ ] Step 5 — Update SSOT with source/evidence dates, pack hash/size, test totals, smoke paths, attribution; inspect git status and diff; commit feat: ship verified starter media pack.

## Coverage self-review

Tasks 1–5 cover license/manifest, installer recovery, project materialization, assetless blocking, search/favorites, distribution constraints, real output and SSOT closeout. No asset is approved until Task 5 completes official license verification.
