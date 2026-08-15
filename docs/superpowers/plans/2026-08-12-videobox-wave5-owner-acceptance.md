# VideoBox Wave 5 Owner Acceptance and Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정확한 커밋의 공식 런타임에서 owner가 실제 제작 전 과정을 수행하고 가로·세로 결과를 시청할 수 있음을 증명한 뒤 코드리뷰·갭·역방향 검증과 Git closeout을 완료한다.

**Architecture:** Automated regression, fake isolated browser, official real browser, artifact inspection and human media acceptance are separate gates. Use a new dedicated QA project and copy-isolated inputs; preserve all evidence and never treat old mixed-lane manifests as current proof.

**Tech Stack:** owner-ready PowerShell wrapper, real Chromium, existing Playwright isolated harness, FFprobe, VideoBox players, Git.

---

## Current gate audit (2026-08-13)

| Task | Current state | Evidence / remaining boundary |
| --- | --- | --- |
| 1. Final-SHA regression | open | Earlier full regression exists, and current Wave 3 focused regression passed, but the full frontend/backend/E2E matrix has not run after the remaining Wave 4 implementation because Wave 4 is still open. |
| 2. Official runtime | completed for current implementation HEAD | `70d5c09d9`: clean/synced Check, current-worktree rebuild, initial 502 settle, final VideoBox/Hermes HTTP 200, official `127.0.0.1:5173` browser. Rerun after any functional Wave 4 commit. |
| 3. Dedicated owner QA project | open | Owner-approved copied inputs and a new preserved `VideoBox Creator QA <timestamp>` project do not exist for this gate. |
| 4. Complete production flow | open | Wave 2 and Wave 3 slices were proven separately; they were not executed as one dedicated Wave 5 owner project. Contextual variant proposal/review/multi-output steps depend on open Wave 4 work. |
| 5. Watch outputs | open | No paired horizontal/vertical artifacts with hashes/FFprobe and no complete owner watch/listen confirmation. |
| 6. Final review/gap/reverse | partial | Wave 2/3 scoped review and reverse checks exist; final Wave 0–4 range review and Wave 4 sibling-render failure proof remain open. |
| 7. Acceptance closeout | open | A QA closeout records automated/runtime limits, but human acceptance and the final post-Wave-4 SHA closeout are not complete. |

Do not convert prior isolated/runtime evidence into completion of Tasks 3–7. Human owner acceptance remains a separate gate.

### Task 1: Pin exact source and run automated regression

- [ ] Verify `git status --short` is clean, branch is `codex/videobox-container-compatibility`, upstream counts are `0 0`, and record `git rev-parse HEAD`.
- [ ] Run full frontend: `npm --prefix apps/web test`, `npm --prefix apps/web run build`, `npm --prefix apps/web run test:e2e`, `npm --prefix apps/web run test:e2e:editor-workbench`.
- [ ] Run full backend: `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider`.
- [ ] Run provenance and owner wrapper tests with the same absolute Python: `tests/test_editor_ui_source_provenance.py tests/test_owner_ready_script.py`.
- [ ] Do not call this owner-ready if any full suite is skipped because of a new failure. Record environment skips separately.

### Task 2: Rebuild the official runtime

- [x] Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\owner-ready.ps1 -Mode Check -Json` and record branch/upstream/data preflight.
- [x] Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\owner-ready.ps1 -Mode Start -Rebuild -Json` only after Check confirms the exact source; then rerun Check.
- [x] A blocked unrelated Hermes dashboard is recorded separately and must not be described as a VideoBox failure or success.
- [x] Open the official runtime with the wrapper-supported route. Do not use direct Vite or fake API as real-runtime proof.

### Task 3: Prepare a dedicated owner QA project safely

- [ ] Obtain or identify owner-approved input files. Copy them read-only into ignored `artifacts/qa/creator-workspace-overhaul/wave5/inputs/`; record source path, copy path, SHA-256 and byte count. Never edit/delete the source.
- [ ] Create through UI a new project named `VideoBox Creator QA <YYYYMMDD-HHmmss>`; record display name and project ID. Never reuse or alter `videobox-pc-qa-20260811153350`.
- [ ] Preserve all runtime project data and outputs until owner acceptance; no cleanup in this plan.

### Task 4: Execute the complete real-browser production flow

- [ ] Create/approve a plan or script through the UI.
- [ ] Drag one B-roll, music and SFX file into the global library; verify copy, analysis, preview and semantic search.
- [ ] Import a long source, accept a modified split proposal; combine short clips virtually; verify derived B-roll search.
- [ ] Add assets to the project and directly trim/split/reorder, place B-roll/music/SFX, edit captions and audio; reload and verify same revision/selection/playhead.
- [ ] Use a contextual starter, edit the prompt, preview/cancel, then preview/apply; undo and reapply.
- [ ] Adjust and lock one vertical crop/caption layout; edit master and resolve the resulting conflict.
- [ ] Review horizontal and vertical current variants; fix or explicitly exclude each issue.
- [ ] Generate horizontal and vertical MP4 together. Optional vertical highlight is tested only after explicit creation. CapCut compatibility is optional and cannot block MP4 completion.

### Task 5: Inspect and watch outputs

- [ ] For every output, record path, SHA-256, byte count and FFprobe JSON containing codec, pixel size, duration and audio stream. Expected default dimensions are 1920×1080 and 1080×1920.
- [ ] Play each output inside VideoBox. Seek to start, middle and end; verify captions, audio, crop, safe area and synchronization.
- [ ] Owner watches/listens to the complete horizontal and vertical files and chooses `결과 확인 완료`. This human gate cannot be replaced by frame screenshots or FFprobe.
- [ ] If owner rejects a result, record exact timestamp and reason, return to the owning wave, fix, recommit/rebuild and repeat Tasks 1–5 on the new HEAD.

### Task 6: Code review, gap and reverse verification

- [ ] Read-only code review the complete range from Wave 0 base to final HEAD. Report P0/P1/P2 with file/impact/evidence; fix all P0/P1 before closeout.
- [ ] Build a design-coverage table for every section of `2026-08-12-videobox-creator-workspace-overhaul-design.ko.md` with code owner, automated evidence, browser evidence and owner evidence.
- [ ] Reverse/failure proof: project-summary failure does not create; upload response loss dedupes; invalid file preserves batch; referenced delete blocks then restore works; stale footage proposal cannot apply; variant lock survives rebase; Yujin cancel has zero effects; master edit stales review; vertical render failure keeps horizontal success.
- [ ] Re-run all affected focused tests after review fixes, then full frontend/backend regression and real-browser acceptance on the final SHA.

### Task 7: Closeout, commit and push

**Files:**
- Create: `docs/handoffs/2026-08-12-videobox-creator-workspace-overhaul-closeout.ko.md`
- Modify: `CLAUDE.md` latest handoff pointer
- Modify: `docs/development-status-2026-06-29.ko.md`

- [ ] Write separate gate results for automated, isolated browser, official browser, artifact inspection and human acceptance. Include exact SHA and evidence paths; do not collapse them into a test count.
- [ ] Record reuse decisions, exclusions, boundary preservation, data migration and any remaining non-blocking P2.
- [ ] Run incomplete-marker scan (`rg -n -i "TBD|TODO|FIXME"` on the closeout files) and `git diff --check`; stage only handoff/status/pointer files and commit `docs: close creator workspace overhaul acceptance`.
- [ ] Verify clean status and upstream divergence, push `codex/videobox-container-compatibility`, then rerun `git status -sb` to prove synchronization.
