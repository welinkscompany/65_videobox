# Task 23C Owner Sample Edit Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자 영상 원본을 바꾸지 않고 격리 QA 프로젝트에 공개 API로 복사해 H264/HEVC 미리보기와 B-roll·BGM·SFX·자막·TTS·overlay·exact/final/SRT/CapCut 결과를 한 번에 재현하는 검토 패키지를 만든다.

**Architecture:** 새 편집 엔진을 만들지 않는다. `scripts/owner_sample_edit_package.py`가 사용자 샘플 inventory와 23A browser-preview API 증거를 소유하고, 기존 `verify-production-readiness-smoke.py`의 deterministic `audio_ducking` 흐름을 호출해 편집 결과를 만든다. 모든 산출물은 ignored `artifacts/owner-sample-edit-*` 아래에 두고, 상대경로+SHA reverse manifest와 사람용 한국어 체크리스트만 공개한다.

**Tech Stack:** Python 3.12, FastAPI TestClient public local API, existing LocalProjectStore/Task 23A preview service, FFmpeg/ffprobe, existing deterministic production-readiness smoke, pytest

---

## 실행 상태

- [x] Task 1 기존 편집 smoke의 exact preview·snapshot evidence 확장
- [x] Task 2 사용자 샘플 read-only inventory·공개 API ingest·H264/HEVC preview proof
- [ ] Task 3 bounded package·reverse manifest·한국어 review checklist
- [ ] Task 4 CLI·mutation guard·실제 사용자 샘플 검증
- [ ] Task 5 독립 review·관련 회귀·SSOT·commit/push

## 설계 결정

### 선택: 얇은 package runner + 기존 하네스 재사용

- 사용자 샘플과 preview proof는 새 runner가 담당한다.
- B-roll/BGM/SFX/caption/TTS/overlay/exact/final/SRT/CapCut 생성은 기존 production-readiness smoke가 담당한다.
- 기존 project/session mutation mode는 Task 23C에서 활성화하지 않는다. 관련 인자가 하나라도 들어오면 API나 파일 복사 전에 fail closed한다. 이는 master spec의 `IDs + explicit confirmation 없이는 변경 금지`보다 더 강한 기본 경계이며, 현재 owner dogfood 목표에는 격리 프로젝트만 필요하다.

### 제외한 방식

- `verify-production-readiness-smoke.py` 하나에 샘플 탐색·선택·owner checklist까지 넣지 않는다. 일반 회귀 하네스와 owner package 책임이 섞인다.
- PowerShell-only orchestration은 사용하지 않는다. nested JSON schema, source/copy SHA, reverse path 검증의 테스트 가능성이 낮다.
- 사용자 H264 494초 파일을 잘라 원본처럼 취급하지 않는다. 선택된 H264/HEVC 원본은 그대로 공개 API에 등록해 project-local copy를 만들고 source/copy SHA를 비교한다.

## 고정 경계

- 사용자 sample directory는 direct child supported video만 읽는다. 원본 create/write/rename/delete/touch는 0이다.
- source inventory에는 파일명, byte size, duration, container, video/audio codec, pixel format, SHA-256만 기록하고 sample directory 절대경로는 기록하지 않는다.
- H264와 HEVC는 각각 duration→size→filename 순으로 가장 작은 한 개만 선택한다. 두 codec 중 하나라도 없으면 복사 전에 `required_preview_codec_missing`으로 중단한다.
- 선택 파일은 `POST /api/projects/{project_id}/assets/broll-video` 공개 local API로만 격리 project에 복사한다. runner가 `shutil.copy*`로 사용자 샘플을 project에 직접 넣지 않는다.
- preview proof는 API start/status/content만 사용하고 Range `206`, output codec/pixel format, original-or-proxy 경로를 기록한다. 외부 URL/provider call은 0이다.
- deterministic QA 편집 선택은 disposable project 안에서만 허용한다. QA 승인·TTS listening approval은 test fixture의 명시 선택 증거이며 owner/human 승인, memory, UI auto-apply로 승격하지 않는다.
- 기존 project/session ID와 confirmation 인자는 Task 23C에서 모두 거부한다. 실제 owner project mutation은 0이다.
- manifest/checklist는 owner 승인·권리·최종 export 통과를 주장하지 않는다.

### Task 1: 기존 편집 smoke의 exact preview·snapshot evidence 확장

**Files:**
- Modify: `scripts/verify-production-readiness-smoke.py`
- Modify: `tests/test_production_readiness_smoke_script.py`

- [x] `tests/test_production_readiness_smoke_script.py`에 exact preview poll이 `ready`만 성공하고 `failed|stale|timeout`을 bounded error로 거부하는 실패 테스트를 작성한다.

```python
def test_smoke_exact_preview_poll_requires_ready_state():
    smoke = _load_smoke_module()
    client = SequenceClient([{"status": "running"}, {"status": "ready", "content_url": "/content"}])
    assert smoke._poll_exact_preview(client, project_id="p", generation_id="g", timeout_sec=1)["status"] == "ready"
```

- [x] JSON evidence writer가 timeline/editing-session payload를 UTF-8, stable key order로 쓰고 absolute path를 payload에 새로 넣지 않는 실패 테스트를 작성한다.

```python
def test_smoke_writes_timeline_and_session_snapshots(tmp_path):
    smoke = _load_smoke_module()
    paths = smoke._write_review_snapshots(tmp_path, timeline={"timeline_id": "t"}, session={"session_id": "s"})
    assert json.loads(paths["timeline"].read_text("utf-8"))["timeline_id"] == "t"
    assert json.loads(paths["editing_session"].read_text("utf-8"))["session_id"] == "s"
```

- [x] RED를 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_production_readiness_smoke_script.py -q`

Expected: `_poll_exact_preview`와 `_write_review_snapshots` 부재로 FAIL.

- [x] `verify-production-readiness-smoke.py`에 아래 helper를 구현한다.

```python
def _poll_exact_preview(client: TestClient, *, project_id: str, generation_id: str, timeout_sec: int) -> dict[str, Any]:
    """Poll until ready; failed/stale/timeout never becomes package evidence."""

def _write_review_snapshots(work_root: Path, *, timeline: dict[str, Any], session: dict[str, Any]) -> dict[str, Path]:
    """Write review/timeline.json and review/editing-session.json atomically."""

def _probe_media_summary(path: Path, *, ffprobe_binary: str) -> dict[str, Any]:
    """Return bounded duration/format/video/audio codec and pixel-format fields."""
```

- [x] `run_smoke()`에서 caption/overlay 편집 뒤 current session revision으로 `0..5초` exact preview를 시작·poll하고 Range `206`을 확인한다. candidate timeline과 current editing session snapshot, exact preview, final, SRT, CapCut draft, ffprobe summary 경로/SHA를 반환한다.
- [x] GREEN을 실행하고 기존 600초 계약이 깨지지 않았는지 확인한다.

완료 증거: focused 회귀 `114 passed`, spec/quality review `Critical 0 / Important 0 / Minor 0`. 실제 600초 end-to-end 실행은 Task 4의 사용자 샘플 검증 단계에서 별도로 수행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_production_readiness_smoke_script.py tests/test_exact_preview_artifact.py tests/test_api_exact_preview.py -q`

Expected: PASS.

### Task 2: 사용자 샘플 read-only inventory·공개 API ingest·H264/HEVC preview proof

**Files:**
- Create: `scripts/owner_sample_edit_package.py`
- Create: `tests/test_owner_sample_edit_package.py`

- [x] 실제 1초 H264/AAC와 HEVC/AAC fixture를 FFmpeg로 만들고, inventory가 파일명/size/duration/container/codec/pix_fmt/SHA만 반환하며 source stat/hash가 실행 전후 같은 실패 테스트를 작성한다.
- [x] sample direct child가 아니거나 symlink/reparse로 directory 밖을 가리키는 파일, 100개 초과, 2GiB 초과 파일, video stream 없는 media를 복사 전에 거부하는 테스트를 작성한다.
- [x] H264/HEVC 각각 duration→size→filename 순으로 한 개만 고르고 필수 codec이 없으면 `required_preview_codec_missing`인 실패 테스트를 작성한다.
- [x] public API import log가 project create 1회와 `/assets/broll-video` 2회만 포함하고, runner source에 사용자 샘플용 `shutil.copy`, `store.register_asset` 직접 호출이 없는 실패 테스트를 작성한다.
- [x] H264는 existing asset content URL, HEVC는 browser-preview proxy URL을 사용하며 둘 다 Range `206`, H264/yuv420p output, external provider call 0인 실패 테스트를 작성한다.
- [x] RED를 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_sample_edit_package.py -q`

Expected: module/file 부재로 FAIL.

- [x] 아래 typed core를 최소 구현한다.

```python
@dataclass(frozen=True)
class SampleRecord:
    name: str
    size_bytes: int
    duration_sec: float
    container: str
    video_codec: str
    audio_codec: str | None
    pixel_format: str | None
    sha256: str

def inventory_samples(sample_dir: Path, *, ffprobe_binary: str) -> list[SampleRecord]: ...
def select_preview_inputs(records: Sequence[SampleRecord]) -> dict[str, SampleRecord]: ...
def build_preview_proofs(*, sample_dir: Path, selected: dict[str, SampleRecord], projects_root: Path,
                         ffmpeg_binary: str, ffprobe_binary: str) -> dict[str, Any]: ...
```

- [x] `build_preview_proofs()`는 `create_app(projects_root=...)`의 TestClient와 public API만 사용한다. project copy의 SHA는 returned `storage_uri`를 read-only resolve해 source SHA와 비교하고 manifest에는 상대 logical ref만 기록한다.
- [x] source stat tuple `(size, mtime_ns, SHA)`를 preview 완료 뒤 다시 계산하고 하나라도 다르면 `source_changed_during_package`로 fail closed한다.
- [x] GREEN을 실행한다.

완료 증거: required focused `32 passed`, Task 23A verifier/API race 반복 `110/110 passed`, spec/quality review `Critical 0 / Important 0 / Minor 0`. Review gap으로 terminal job 상태와 proxy content를 결속하는 API fence도 함께 닫았다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_sample_edit_package.py tests/test_task23a_browser_preview_verifier.py tests/test_asset_browser_preview_api.py -q`

Expected: PASS.

### Task 3: bounded package·reverse manifest·한국어 review checklist

**Files:**
- Modify: `scripts/owner_sample_edit_package.py`
- Modify: `tests/test_owner_sample_edit_package.py`

- [ ] `write_review_checklist()`가 영상, 자막, 목소리, 음악, 효과음, 장면 전환, 권리, 최종 export의 unchecked 사람 항목과 `자동 통과 아님` 경고를 정확히 포함하는 실패 테스트를 작성한다.
- [ ] artifact path가 package root 밖이거나 없거나 SHA가 다르면 `validate_reverse_manifest()`가 거부하는 path traversal/tamper 실패 테스트를 작성한다.
- [ ] package manifest가 exact preview, final MP4, SRT, timeline, editing-session, CapCut draft, ffprobe summary, checklist를 모두 상대경로+SHA로 연결하고 각 upstream이 `editing_session → copied asset → source SHA`로 끝나는 실패 테스트를 작성한다.
- [ ] deterministic edit flow 호출이 exact `fixture_name="audio_ducking"`이고 결과 controls에 B-roll/BGM/SFX/caption/TTS/explanation overlay가 모두 true인 실패 테스트를 작성한다.
- [ ] owner approval, rights approval, desktop edit/export, auto apply, memory write, external provider call이 모두 false/0인 schema 실패 테스트를 작성한다.
- [ ] RED를 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_sample_edit_package.py -q`

Expected: package/checklist/reverse helper 부재로 FAIL.

- [ ] 아래 package builder를 구현한다.

```python
def build_owner_sample_package(*, sample_dir: Path, output_root: Path, narration: Path,
                               ffmpeg_binary: str, ffprobe_binary: str,
                               edit_flow_runner: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Inventory -> public API preview proof -> deterministic edit flow -> atomic manifest."""

def validate_reverse_manifest(package_root: Path, manifest: dict[str, Any]) -> None: ...
def write_review_checklist(package_root: Path) -> Path: ...
```

- [ ] narration은 먼저 package-local `inputs/qa-narration.wav`로 복사하고 source/copy SHA를 비교한다. 기본 narration artifact가 없을 때만 checked-in `New-ProductionReadinessKoreanSample.ps1`을 package root 대상으로 실행한다.
- [ ] manifest는 `.owner-sample-edit-package.json.tmp`에 쓴 뒤 same-directory replace로 게시한다. 실패 시 partial manifest를 노출하지 않으며 이미 생성한 project evidence는 삭제하지 않는다.
- [ ] GREEN을 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_sample_edit_package.py tests/test_production_readiness_smoke_script.py -q`

Expected: PASS.

### Task 4: CLI·mutation guard·실제 사용자 샘플 검증

**Files:**
- Modify: `scripts/owner_sample_edit_package.py`
- Modify: `tests/test_owner_sample_edit_package.py`

- [ ] CLI default output이 repo-local ignored `artifacts/owner-sample-edit-<UTC timestamp>`이고 existing destination을 덮어쓰지 않는 테스트를 작성한다.
- [ ] `--project-id`, `--session-id`, `--confirm-existing-project-mutation` 중 하나라도 주어지면 sample scan/API/file write 전에 `existing_project_mode_disabled`로 종료하는 테스트를 작성한다.
- [ ] CLI JSON/stdout과 manifest에 sample directory absolute path, credential, raw ffmpeg stderr, full command, `provider`, memory payload가 없는 테스트를 작성한다.
- [ ] `--sample-dir`, `--output-root`, `--narration`, `--ffmpeg`, `--ffprobe`, `--json` CLI를 구현한다. 성공 JSON은 `status`, package directory name, selected filenames, artifact count, `external_provider_calls=0`만 출력한다.
- [ ] focused GREEN을 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_sample_edit_package.py -q`

Expected: PASS.

- [ ] 실제 사용자 샘플을 read-only로 실행한다.

Run:

```powershell
.\.venv\Scripts\python.exe scripts/owner_sample_edit_package.py `
  --sample-dir 'C:\Users\atgro\OneDrive\바탕 화면\영상샘플' `
  --output-root artifacts\owner-sample-edit-20260803 `
  --narration artifacts\task5-korean-600.wav `
  --json
```

Expected: H264 1개+HEVC 1개 source/copy SHA match, both Range 206, HEVC proxy H264/yuv420p, edit controls 6종, exact/final/SRT/CapCut/reverse manifest present, original stat/SHA unchanged, provider call 0.

### Task 5: 독립 review·관련 회귀·SSOT·commit/push

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/superpowers/plans/2026-08-03-videobox-task23c-owner-sample-edit-package.md`
- Create: `docs/handoffs/2026-08-03-videobox-task23c-owner-sample-edit-package-closeout.ko.md`

- [ ] 독립 spec review에서 master spec의 inventory/copy hash/H264+HEVC preview/6 controls/exact+final+SRT+timeline+session+CapCut/checklist/mutation guard를 line-by-line 확인한다.
- [ ] code quality review에서 bounded subprocess, source read-only, path containment, atomic manifest, safe JSON, no external call을 확인한다.
- [ ] gap/reverse review에서 `manifest artifact → output → timeline/session → typed controls → project copy → source SHA`를 실제 package로 역추적한다. Critical/Important finding은 RED→GREEN 뒤 재리뷰한다.
- [ ] focused backend를 실행한다.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_owner_sample_edit_package.py `
  tests/test_production_readiness_smoke_script.py `
  tests/test_task23a_browser_preview_verifier.py `
  tests/test_asset_browser_preview_core.py `
  tests/test_asset_browser_preview_api.py `
  tests/test_exact_preview_artifact.py `
  tests/test_api_exact_preview.py `
  tests/test_preview_export.py `
  tests/test_local_pipeline_capcut_draft_export.py `
  tests/test_pycapcut_adapter.py -q
```

- [ ] Task 23 final full Python/frontend/build/E2E/provenance는 23D 뒤 final audit로 남기며 이번 slice에서 실행하지 않은 항목은 통과로 주장하지 않는다.
- [ ] `git diff --check`, branch/HEAD/upstream `0/0`, `git worktree list`, protected residue 3개, package artifact ignore를 확인한다.
- [ ] SSOT/handoff를 Task 23 **3/4 (75.0%)**, 잔여 **25.0%**, 다음 goal **23D Hermes readiness**로 갱신한다.
- [ ] 이번 범위만 commit하고 `origin/codex/videobox-container-compatibility`에 push한다.

## Acceptance matrix

| 경로 | 기대 결과 | 자동 근거 |
|---|---|---|
| inventory | direct supported video만, bounded metadata+SHA, 절대경로 없음 | synthetic media + traversal/count/size tests |
| selection | shortest H264 1 + shortest HEVC 1 | deterministic sort test |
| public ingest | API 2회, project copy SHA=source SHA | TestClient log + LocalProjectStore resolve |
| preview | H264 original, HEVC proxy, 둘 다 Range 206/H264 output | real FFmpeg/API focused test |
| source fence | before/after size+mtime_ns+SHA 동일 | mutation negative test + actual sample receipt |
| edit controls | B-roll/BGM/SFX/caption/TTS/overlay | existing audio_ducking smoke checks |
| outputs | exact/final/SRT/timeline/session/CapCut/ffprobe/checklist | manifest artifact schema + existence/SHA validation |
| reverse trace | 모든 artifact가 session/copy/source SHA까지 연결 | validate_reverse_manifest + actual package audit |
| mutation guard | existing project 관련 인자 즉시 fail closed | CLI preflight test |
| human boundary | taste/rights/export 모두 unchecked | Korean checklist exact copy test |
| network | in-process local API only, provider call 0 | manifest/CLI assertion |

## Reverse runtime trace

1. `owner-sample-edit-package.json`의 artifact row가 package-relative path와 SHA를 제공한다.
2. final/SRT/CapCut/ffprobe는 exact current candidate timeline과 editing-session snapshot을 가리킨다.
3. snapshot의 B-roll/BGM/SFX/caption/TTS/overlay typed control이 production-readiness smoke의 explicit API call로 역추적된다.
4. sample preview row는 public asset registration response와 project copy SHA로 역추적된다.
5. project copy SHA는 source inventory SHA와 같고, package 종료 후 source size/mtime/SHA도 시작 전과 같다.
6. checklist의 사람 판단 항목은 모두 unchecked이며 manifest의 owner approval/rights/export flags는 false다.

## Plan self-review

- spec coverage: 23C package와 mutation guard acceptance, owner-package reverse trace, cross-cutting source/network/apply/human 경계를 각 Task와 matrix에 연결했다.
- placeholders: TBD/TODO/나중에 구현 항목이 없다. 23D와 Task 23 final full audit만 명시적으로 다음 slice로 남긴다.
- type consistency: `SampleRecord`, `build_preview_proofs`, `build_owner_sample_package`, `validate_reverse_manifest` 이름과 입력을 모든 task에서 동일하게 사용한다.
- scope: production editor/UI/backend command를 새로 확장하지 않고 기존 public API와 deterministic output harness만 조합한다.
- 반대 검토: 전체 기존 owner project 자동 편집은 더 편할 수 있지만 실제 데이터 mutation·retry·approval 혼합 위험이 커서 Task 23C에는 포함하지 않는다.
