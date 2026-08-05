# VideoBox 실사용 복구 구현 계획

> **작업자에게:** 이 계획은 Task 단위로 실행한다. 각 Step은 `- [ ]` 체크박스로 추적한다.
> 착수 전 `CLAUDE.md` → `docs/development-fast-path.ko.md` §10 → 해당 Task의 근거 문서를 읽는다.
> 각 Task는 `implementation-plan.ko.md` §8.1 재사용 게이트를 먼저 통과하고,
> §10.2 TDD를 기본으로 하며, §8.3 완료 보고 항목을 남긴다.

**Goal:** owner가 실제로 쓸 수 있는 제품을 만든다. 최종 상태는 아래 셋을 모두 만족한다.

1. 실제 음성·영상으로 자동 초안이 만들어지고, 사람이 보고 고칠 수 있다
2. 대시보드가 깔끔하고 직관적이어서 설명 없이 쓸 수 있다
3. 유진이 로컬 LLM으로 대화하며, provider 어댑터로 GPT-5.4 / 5.4-mini 전환이 쉽다

1번은 이미 만들어졌으나 꺼져 있거나 가짜로 동작하는 경로를 실제 동작으로 바꾸는 일이다.
2번과 3번은 현재 계획서 조항과 충돌하므로 **owner 승인으로 조항을 먼저 바꿔야** 착수할 수 있다.

**Architecture:** 진실 확정 → 즉시 체감 개선 → 문서 정합 → 잔여 결함 순으로 진행한다.
런타임 실측을 먼저 하는 이유는 코드와 최상위 계획서(`implementation-plan.ko.md` §23)가
서로 다른 상태를 주장하고 있어, 실측 없이는 어떤 계획도 추측 위에 서기 때문이다.

**Tech Stack:** Python 3.12 / FastAPI / pytest, React 19 / Vite / vitest, FFmpeg, Docker Compose.

**근거 문서:** `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`
(결함 9건, 결정 4건, 아키텍처 발견 2건, 범위 충돌 3건, 각 항목 근거 등급 포함)

**역방향 검증으로 확인한 전제:** `artifacts/.../r4`의 `transcript_001.json`을 소스까지 역추적한 결과,
r4는 `deterministic_korean_smoke_stt`로 만들어졌다. 이 stub은 오디오를 버리고 대본 문장과
고정 시간(`0–300`, `300–600`)을 반환한다. TTS stub은 일정한 톤을 쓴다.
**따라서 r4로는 사람이 품질을 판정할 수 없다.** Task 2의 기준선은 r4 재사용이 아니라
실제 provider로 새로 만들어야 한다.

---

## Slice 0 — 진실 확정

### Task 1: 컨테이너 provider 활성화 — 음성 인식·목소리·CapCut

owner가 쓰는 컨테이너에서 제품 핵심 기능 셋이 비활성이다. 컨테이너 런타임에서 직접 확인했다.

| Provider | 컨테이너 기본값 | 비활성 시 실제 동작 |
|---|---|---|
| 음성 인식 (STT) | `enabled=False` | `MockSTTProvider` — 오디오와 무관한 고정 두 줄 |
| 본인 목소리 (TTS) | `enabled=False` | `None` — provider 자체가 없음 |
| CapCut 내보내기 | `enabled=False` | `None` — exporter 자체가 없음 |
| 로컬 LLM | `enabled=True` | 활성. 다만 미디어 분석은 `D-2`로 별도 차단 |

`scripts/run_api.py`(개발 서버)는 STT만 켜고 TTS·CapCut은 켜지 않는다.
즉 어느 실행 경로에서도 TTS와 CapCut export는 동작하지 않는다.

음성 인식 비활성 체인은 아래로 확인했다.

1. `docker/workspace-supervisor.py:48`이 `uvicorn videobox_api.main:create_app --factory`를 인자 없이 실행한다
2. `create_app`의 `whisper_stt_config` 기본값은 `WhisperSTTConfig(enabled=False)`다
3. `provider_factories._build_stt_provider`가 `MockSTTProvider()`를 반환한다
4. `MockSTTProvider`는 오디오 내용과 무관하게 `"Line one."`과
   `"Line two with restart from {파일명}."` 두 줄을 고정 반환한다
5. 컨테이너에 whisper 관련 환경변수가 없고 `faster_whisper` 패키지도 설치되어 있지 않다

반면 `scripts/run_api.py:25`는 `WhisperSTTConfig(enabled=True)`를 넘긴다.
즉 개발 서버 경로와 컨테이너 경로가 서로 다른 STT를 쓴다.

이 상태에서는 자막·세그먼트·B-roll 텍스트 매칭·타임라인이 모두 가짜 전사 위에 만들어진다.
다른 어떤 개선보다 먼저 닫아야 한다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `FasterWhisperSTTProvider` | `adopt as-is` | 이미 구현돼 있다. 새로 만들지 않는다 |
| `scripts/run_api.py`의 활성화 방식 | `partial port` | 같은 설정을 컨테이너 팩토리 경로에도 적용한다 |
| 새 STT provider 작성 | `exclude` | 기존 provider로 충분하다 |

**Files:**
- Modify: `services/api/src/videobox_api/main.py` (환경변수 기반 STT 설정 해석)
- Modify: `packages/core-engine/src/videobox_core_engine/settings.py` (설정 해석 함수)
- Modify: `docker/workspace.Dockerfile` (faster-whisper 설치)
- Modify: `compose.yaml` (STT 환경변수)
- Create: `tests/test_stt_runtime_config.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_app_factory_without_arguments_uses_real_stt_when_enabled(monkeypatch):
    monkeypatch.setenv("VIDEOBOX_STT_ENABLED", "1")
    assert resolve_whisper_stt_config().enabled is True

def test_app_factory_defaults_to_mock_when_not_configured(monkeypatch):
    monkeypatch.delenv("VIDEOBOX_STT_ENABLED", raising=False)
    assert resolve_whisper_stt_config().enabled is False
```

- [ ] **Step 2: RED 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_stt_runtime_config.py -q`
Expected: `resolve_whisper_stt_config`가 없어 import 실패.

- [ ] **Step 3: 최소 구현**

`settings.py`에 환경변수 기반 해석 함수를 추가하고, `create_app`이 인자 없이 호출될 때
이 함수를 쓰도록 바꾼다. 기본값은 계속 `False`로 두어 기존 테스트 스위트의
가짜 오디오 fixture가 실제 모델을 부르지 않게 유지한다.

`workspace.Dockerfile`에 `faster-whisper`를 설치하고, `compose.yaml`의
`videobox-workspace`에 `VIDEOBOX_STT_ENABLED=1`과 모델 크기·device 환경변수를 추가한다.

- [ ] **Step 4: GREEN 및 실제 전사 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_stt_runtime_config.py -q`
Run: `.venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "stt or transcription"`
실제 확인: 컨테이너 재빌드 후 owner의 실제 나레이션 파일을 넣고,
전사 결과가 `"Line one."`이 아니라 실제 발화 내용인지 확인한다.

- [ ] **Step 5: 전체 회귀 및 커밋**

Run: `.venv\Scripts\python.exe -m pytest -q`
Commit: `fix: use the real transcriber in the container`

- [ ] **Step 6: CapCut exporter 활성화**

`CapCutDraftExportConfig(enabled=False)`면 `_build_pycapcut_exporter`가 `None`을 반환한다.
같은 환경변수 방식으로 켜고, 실제 draft JSON이 생성되는지 확인한다.
CapCut Desktop 실행은 이 Task 범위가 아니다.

Commit: `fix: enable the CapCut draft exporter in the container`

- [ ] **Step 7: TTS 엔진 결정 및 활성화**

`TTSEngineConfig(enabled=False)`면 `_build_tts_provider`가 `None`을 반환한다.
엔진 선택은 owner 결정 사항이다.

| 엔진 | 필요 조건 |
|---|---|
| `local_xtts` | 모델 다운로드 약 2GB, Coqui 라이선스 동의 |
| `elevenlabs` | API key와 owner 동의된 voice ID. 외부 전송 발생 |
| `gtts` | 본인 목소리가 아님. 음성 클로닝 용도로 부적합 |

**owner 결정 (2026-08-05): TTS는 보류한다.** 음성 인식과 CapCut 내보내기를 먼저 켜고
실제 동작을 확인한 뒤 별도로 정한다. 한 번에 여러 개를 켜면 실패 원인 구분이 어렵다.
따라서 Step 7은 이번 Slice에서 실행하지 않고 열어둔다.

`product-plan.ko.md` §6.4와 `architecture-plan.ko.md` §13.7이
"TTS는 자동 전면 대체가 아니라 review 기반으로만 적용"을 요구하므로 그 경계를 유지한다.

Commit: `feat: enable the chosen voice engine`

**승인 필요:** STT 모델 다운로드, TTS 엔진 선택과 그에 따른 다운로드 또는 외부 전송은
착수 전 owner 승인을 받는다. 크기·저장 위치·외부 전송 여부를 먼저 알린다.

### Task 2: 런타임 진실 기준선 확보

backlog 각 항목을 실제 동작으로 확인해 근거 등급을 `관측`으로 승격하거나 반증한다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `scripts/verify-production-readiness-smoke.py` | `partial port` | work-root/artifact/ffprobe 구조만 재사용한다. `DeterministicKoreanSTTProvider`와 `DeterministicWaveTTSProvider`는 **반입하지 않는다** |
| `scripts/owner_sample_edit_package.py` | `partial port` | 실제 샘플 ingest와 package 조립 흐름만 재사용한다. **주의:** 이 스크립트의 `create_app` 호출(472행)에 provider 인자가 없어 기본 mock STT로 돌아간다. 재사용 시 실제 provider 설정을 반드시 주입한다 |
| `scripts/owner-ready.ps1 -Mode Smoke` | `exclude` | static/non-live verifier라 실제 파이프라인을 돌리지 않는다 |
| r4 산출물 재사용 | `exclude` | stub으로 만들어져 품질 판정 근거가 될 수 없다 |

**이 Task의 핵심 제약:** 어떤 stub provider도 주입하지 않는다.
기존 검증 스크립트가 실제 AI 경로를 우회한 것이 지금 문제의 원인이므로,
같은 방식을 재사용하면 같은 결과가 나온다.

**Files:**
- Create: `scripts/verify_owner_path.py`
- Create: `tests/test_owner_path_verifier.py`
- Modify: `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md` (등급 갱신)

- [ ] **Step 1: 실패 테스트 작성** — verifier가 각 단계의 pass/fail과 근거를 구조화해 남기는지 검사한다
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 실제 나레이션과 실제 B-roll로 ingest → STT → 세그먼트 → 추천 → timeline
      → preview → 자막 → export를 순서대로 실행하고 각 단계 결과를 JSON으로 기록한다.
      provider를 대체하지 않는다. 실패해도 중단하지 않고 실패 지점을 기록한다.
- [ ] **Step 4: GREEN 및 실제 실행**
- [ ] **Step 5: backlog 등급 갱신 및 커밋**

Commit: `feat: verify the owner path end to end`

---

## Slice 1 — 즉시 체감 개선

### Task 3: 편집기 자산 카드에 썸네일 연결 (F-2)

생성·저장·API·프론트 헬퍼가 모두 존재하지만 편집기 UI가 호출하지 않는다.
`api.assetThumbnailUrl`을 호출하는 코드가 프론트엔드 전체에 없다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `api.assetThumbnailUrl` | `adopt as-is` | 이미 있다. 호출만 하면 된다 |
| `thumbnail_generator` / `/assets/{id}/thumbnail` | `adopt as-is` | 백엔드 변경 불필요 |
| 새 이미지 컴포넌트 | `exclude` | 기존 카드 마크업에 `img` 추가로 충분하다 |

**Files:**
- Modify: `apps/web/src/features/editor/assets/editorAssetProjection.ts`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`
- Modify: `apps/web/src/features/editor/assets/editorAssetProjection.test.ts`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`

- [ ] **Step 1: 실패 테스트** — 카드가 썸네일 이미지를 렌더하고, 없으면 기존 텍스트로 폴백하는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 썸네일 유무를 projection에 넣고 카드에 렌더한다. `alt`는 §10.13 창작자 언어를 따른다
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

Run: `npm --prefix apps/web test -- src/features/editor/assets`
Commit: `feat: show thumbnails in the editor asset list`

### Task 4: 편집 화면 데드엔드 제거 (F-1)

초안이 없는 프로젝트에서 `/projects/{id}/editor` 진입 시
사이드바·헤더 없는 흰 화면에 문장 한 줄만 나오고 돌아갈 수단이 없다.
근거: `apps/web/src/app/AppRouter.tsx`의 `CanonicalEditorEntry`가
`<main><p>{message}</p></main>`만 렌더한다.

**Files:**
- Modify: `apps/web/src/app/AppRouter.tsx`
- Modify: `apps/web/src/app/AppRouter.test.tsx`

- [ ] **Step 1: 실패 테스트** — 초안 없는 프로젝트의 편집 진입에서 셸과 이동 수단이 보이는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — `ProductShell`을 유지하고 `새 영상 만들기`로 유도한다. §10.13 어휘를 따른다
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

Commit: `fix: keep the workspace shell when no draft exists`

---

## Slice 2 — 문서 정합

### Task 5: 계획서를 실측 상태에 맞추기

Task 1·2의 실측 결과로 어긋난 문서를 갱신한다. 최소 대상은 아래다.

- `implementation-plan.ko.md` §23: gateway·signer·OAuth·편집 mutation의 실제 상태
- `development-status`: 새 authoritative 항목 추가
- backlog 문서: 근거 등급 최종 갱신

코드 동작을 바꾸지 않으므로 §10.2.1에 따라 TDD를 강제하지 않는다.

- [ ] **Step 1: Task 1·2 결과와 §23 각 항목 대조**
- [ ] **Step 2: 갱신 및 커밋**

Commit: `docs: reconcile the plan with measured runtime state`

---

## Slice 3 — 잔여 결함

Task 2 실측이 세부를 조정할 수 있으나, 각 항목의 결함 자체는 이미 화면에서 직접 관측했으므로
Step을 지금 확정한다. 실측으로 전제가 바뀌면 갱신 규칙에 따라 해당 Task를 수정한다.

### Task 6: 미리보기 자동 갱신 (F-4)

편집 후 `미리보기 새로 만들기`를 수동으로 눌러야 한다. `stale` 상태가 화면에 그대로 노출된다.
편집 → 확인 왕복이 끊겨 체감 속도를 떨어뜨린다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `exact-preview-state.ts` | `adopt as-is` | freshness 판정 로직이 이미 있다. 상태 계산을 새로 만들지 않는다 |
| `EditorWorkbenchRoute.tsx`의 기존 polling | `partial port` | 이미 pending preview를 polling한다. 트리거 조건만 확장한다 |
| 새 상태 머신 | `exclude` | 기존 revision·freshness 계약으로 충분하다 |

**Files:**
- Modify: `apps/web/src/features/editor/preview/exact-preview-state.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx`
- Modify: 각 대응 테스트 파일

- [ ] **Step 1: 실패 테스트** — 편집 mutation 뒤 미리보기가 자동으로 갱신 요청되는지,
      갱신 중 상태 문구가 `§10.13` 창작자 언어인지(`stale` 같은 내부 용어 금지),
      연속 편집 시 요청이 중복되지 않는지
- [ ] **Step 2: RED 확인**

Run: `npm --prefix apps/web test -- src/features/editor/preview`

- [ ] **Step 3: 구현** — mutation 성공 후 현재 revision 기준으로 갱신을 트리거한다.
      진행 중 재편집이 오면 최신 요청만 유효하게 유지한다(기존 latest-request 규칙 재사용).
      자동 갱신 실패 시 기존 수동 버튼을 폴백으로 남긴다
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

Commit: `feat: refresh the preview after an edit`

### Task 7: 타임라인 클립 이름을 사람이 읽는 말로 (F-3)

클립 접근성 이름이 `broll:session-broll-segment_draft_1726b9574a-0 클립 선택` 형태다.
근거: `apps/web/src/features/editor/timeline/TimelineDock.tsx:536`의
`aria-label={`${rect.clipId} 클립 선택`}`이 내부 ID를 그대로 쓴다.
`§10.13.3`의 내부 용어 노출 금지 취지에 어긋난다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| 기존 트랙 이름(`내레이션`, `B-roll`, `BGM`, `효과음`, `오버레이`, `자막`) | `adopt as-is` | 이미 창작자 언어다. 라벨 구성에 재사용한다 |
| 새 명명 체계 | `rewrite` | 트랙 이름 + 순번 + 시간으로 조합하는 최소 포맷터 |

**Files:**
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.test.tsx`

- [ ] **Step 1: 실패 테스트** — 클립 접근성 이름에 내부 ID가 없고
      트랙 이름과 순번으로 사람이 읽을 수 있는지 (예: `B-roll 2번째 장면, 3초부터`)
- [ ] **Step 2: RED 확인**

Run: `npm --prefix apps/web test -- src/features/editor/timeline`

- [ ] **Step 3: 구현** — 라벨 포맷터를 추가한다. 선택·조작 로직은 계속 `clipId`를 쓰고
      **표시용 이름만** 바꾼다. 식별자와 표시명을 섞지 않는다
- [ ] **Step 4: GREEN + 커밋**

Commit: `feat: name timeline clips in plain language`

### Task 8: 프로젝트 삭제 경로 (F-5)

API와 UI 모두 없다. `local_project_store.py`에 삭제·보관 함수 자체가 없다.
이번 세션에서 만든 `my-project`가 목록에 영구 잔존 중이다.

**선행 결정 — owner 확인 필요:** 삭제 방식을 먼저 정해야 한다.

| 방식 | 결과 |
|---|---|
| 완전 삭제 | 프로젝트 폴더와 DB 레코드를 지운다. 되돌릴 수 없다 |
| 보관 처리 | 목록에서 숨기고 데이터는 남긴다. 되돌릴 수 있고 용량은 그대로 |

`§10.12.3`이 QA 증거에 `preserve-evidence`를 요구하는 취지를 고려하면 **보관 처리가 기본값**으로 적절하고,
완전 삭제는 별도 확인 절차를 두는 것이 안전하다.

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `services/api/src/videobox_api/routers/projects.py`
- Modify: `apps/web/src/app/AppRouter.tsx`, `apps/web/src/api.ts`
- Create: `tests/test_project_archive.py`

- [ ] **Step 1: 실패 테스트** — 보관 처리 후 목록에서 빠지는지, 데이터가 남는지,
      존재하지 않는 프로젝트 요청이 안전하게 실패하는지, 되돌리기가 되는지
- [ ] **Step 2: RED 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_project_archive.py -q`

- [ ] **Step 3: 구현** — store에 보관 상태를 추가하고 라우터와 UI를 연결한다.
      UI는 확인 단계를 거치며 `§10.13` 창작자 언어를 쓴다
- [ ] **Step 4: GREEN + 전체 회귀 + 커밋**

Commit: `feat: let the owner put a project away`

### Task 9: 중복 진입점 정리 (F-7)

`새 영상 만들기`가 사이드바(`ProductShell.tsx:41`), 헤더 버튼(`ProductShell.tsx:56`),
그리고 홈 화면 카드에 동시에 있다. 같은 동작이 세 번 보인다.

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx`
- Modify: `apps/web/src/app/ProductShell.test.tsx`

- [ ] **Step 1: 실패 테스트** — 같은 화면에서 동일 동작 진입점이 중복 노출되지 않는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 사이드바 항목을 주 진입점으로 두고, 헤더 버튼은
      해당 화면이 아닐 때만 보이게 하거나 제거한다. 홈 카드는 맥락 안내로 유지한다
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

Commit: `refactor: keep one way into video creation`

**이 Task는 Slice 4 디자인 재승인과 겹칠 수 있다.** Task 10 승인 내용에 진입점 구조가 포함되면
이 Task를 Slice 4로 흡수하고 여기서는 제외한다.

---

---

## Slice 4 — 대시보드 완성도 (선행: 승인 조항 개정)

owner 요구: "어설픈 기능 말고 깔끔한 디자인으로 직관적이고 쉽게".

**선행 조건 — 승인 게이트:** 승인된 시각 결정이 두 건 있다.

- `docs/decisions/creator-workspace-visual-approval.ko.md` (2026-07-17, 팔레트)
- `docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md` (2026-07-22, 편집 작업판 5개 viewport)

두 문서 모두 artifact aggregate SHA 변경 시 재승인을 요구하며
`scripts/build_ui_prototype_artifacts.py --require-approved`가 이를 검증한다.
따라서 디자인을 바꾸려면 **프로토타입 재생성 → 새 SHA → owner 재승인 기록**이 선행이다.

### Task 10: 시각 방향 재승인

- [ ] **Step 1:** 현재 화면의 실제 문제를 목록화한다. 취향이 아니라 사용성 근거로 적는다
- [ ] **Step 2:** 새 방향 프로토타입을 5개 viewport로 생성한다
- [ ] **Step 3:** owner 검토와 명시 승인을 `docs/decisions/`에 기록한다
- [ ] **Step 4:** `--require-approved` 검증 통과 확인

### Task 11: 색상 토큰 일원화 (F-6) — Task 10과 병행 가능

`apps/web/src/styles/product-shell.css`에 하드코딩 색상 19종이 있고 CSS 변수를 참조하지 않는다.
실측: `--primary`를 바꿔도 기본 버튼은 `rgb(91,74,200)`을 유지한다.
**이걸 먼저 고쳐야 어떤 디자인 승인도 실제 화면에 반영된다.**

이 Task는 승인 내용과 무관하다. 색을 바꾸는 것이 아니라 **색을 바꿀 수 있게** 만드는 작업이므로
Task 10 승인 전에 착수할 수 있다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `ui-system.css`의 기존 변수 세트 | `adopt as-is` | 이미 승인된 팔레트 값이 변수로 정의돼 있다 |
| `product-shell.css` 하드코딩 19종 | `rewrite` | 같은 값을 변수 참조로 바꾼다. **색상값 자체는 바꾸지 않는다** |
| 새 디자인 토큰 체계 | `exclude` | 기존 변수 이름을 그대로 쓴다 |

**Files:**
- Modify: `apps/web/src/styles/product-shell.css`
- Modify: `apps/web/src/styles/editor-workbench.css` (하드코딩 `#08090b` 확인)
- Create: `apps/web/src/styles/theme-tokens.test.ts`

- [ ] **Step 1: 실패 테스트** — 셸 CSS에 하드코딩 hex가 남아 있지 않은지,
      `--primary`를 바꾸면 기본 버튼 색이 실제로 따라 바뀌는지
- [ ] **Step 2: RED 확인**

Run: `npm --prefix apps/web test -- src/styles`

- [ ] **Step 3: 구현** — 하드코딩 19종을 대응 변수로 치환한다.
      **현재 승인된 색상값과 시각적으로 동일해야 한다.** 이 Task는 리팩터링이지 디자인 변경이 아니다
- [ ] **Step 4: GREEN + 브라우저에서 변수 변경이 반영되는지 실측 + 커밋**

Commit: `refactor: drive shell colours from theme tokens`

### Task 11A: 승인된 디자인을 화면에 반영

> **Step은 Task 10 승인 결과가 나온 뒤 채운다.** 무엇을 승인받는지 정해지기 전에는
> 구현 Step을 쓸 수 없다. Task 11이 선행이다.

확정된 범위: 승인된 팔레트를 변수에 반영하고 대비(4.5:1) 회귀 테스트를 추가한다.

---

## Slice 5 — 유진 대화와 provider 전환 (선행: 조항 개정)

owner 요구: "로컬 LLM 물려서 동작하게, 어댑터로 GPT-5.4 / 5.4-mini 전환 쉽게".

**선행 조건 — 조항 충돌:** `implementation-plan.ko.md` §23.3A.4가 명시한다.

> 유진의 자유 대화·콘셉트/대본 창작·권한/승인 판단·tool selection을 Qwen으로 대체하지 않는다.

로컬 LLM의 허용 범위는 현재 "대화 압축·명시된 정형 요약"뿐이고,
자유 대화는 `disabled`다. §23.3A.5는 qualification 전까지 `shadow_only` 유지를 요구한다.

또한 §23.1은 egress allowlist gateway 통과 전 `hermes model` 실행을 금지하고,
§23.2.6은 capability signer가 어떤 route에도 배포되지 않았다고 기록한다.

**따라서 이 Slice는 §23 개정이 선행되어야 한다.** owner가 승인권자이므로 개정할 수 있으나,
개정 없이 구현하면 최상위 계획서 위반이다.

### Task 12: §23 조항 개정과 새 경계 확정 — **완료 (2026-08-05)**

- [x] **Step 1:** 유지할 안전 경계를 확정했다.
      DB·filesystem·shell·renderer·CapCut·raw HTTP·credential 접근 금지,
      편집 mutation은 사람 승인 게이트 유지, 대화의 "네"는 승인 아님,
      모델 출력은 untrusted proposal, VideoBox DB가 SSOT,
      provider 전환은 명시적·기록됨. 대본·썸네일·추천 영상 생성은 계속 범위 밖
- [x] **Step 2:** `implementation-plan.ko.md`에 `§23.3B`를 신설해 `§23.3A.4`의
      "유진의 자유 대화를 Qwen으로 대체하지 않는다"를 로컬 우선 방침으로 대체했다.
      개정 근거는 `docs/decisions/2026-08-05-local-first-assistant-decision.ko.md`
- [x] **Step 3:** 로컬 호출은 외부 전송이 없어 `§23.1` egress allowlist gate 대상이 아님을
      `§23.3B`에 명시했다. 다만 컨테이너→호스트 경로는 네트워크 경계 변경이므로
      `§10.14`에 따라 별도 기록한다는 조건도 함께 고정했다

커밋: `d503ce2`

### Task 13: 로컬 LLM으로 유진 대화 실제 동작

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `LocalOpenAICompatibleRuntimeConfig` | `adopt as-is` | 이미 `enabled=True`이고 LM Studio 연동 코드가 있다 |
| `packages/provider-interfaces/.../lm_studio.py` | `adopt as-is` | 기존 클라이언트를 쓴다 |
| `yujin_profile_contract`, `agent_gateway_contract` | `adopt as-is` | 프로필·정책 계약을 유지한다 |
| Hermes 컨테이너 OAuth 경로 | `exclude` | 이 Task는 로컬 전용이다. OAuth는 Task 14 |

- [ ] **Step 1: 실패 테스트** — 유진 대화 요청이 로컬 LLM 응답으로 채워지는지, 정책 위반 요청은 `blocked`인지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 컨테이너에서 호스트 LM Studio(`127.0.0.1:1234`)로 가는 경로를 연다.
      `architecture-plan` §11이 GPU 로컬 모델 컨테이너화를 비권장하므로,
      모델은 호스트에 두고 컨테이너가 호출만 하는 구조를 유지한다
- [ ] **Step 4: GREEN + 실제 대화 확인 + 커밋**

Commit: `feat: run the assistant on the local model`

### Task 14: provider 어댑터와 전환

- [ ] **Step 1: 실패 테스트** — 설정으로 provider를 바꾸면 실제 호출 대상이 바뀌고,
      전환 이력이 기록되며, 미설정 provider 선택은 `blocked`로 끝나는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 로컬 / GPT-5.4 / GPT-5.4-mini를 같은 인터페이스 뒤에 둔다.
      §23.3A.3의 "조용히 대체하지 않는다"를 지켜, 전환은 항상 명시적이고 기록된다
- [ ] **Step 4: GREEN + 커밋**

Commit: `feat: switch assistant providers through one adapter`

GPT 경로 실제 사용은 §23.1 egress gate와 OAuth 로그인이 선행이다.
어댑터 구현과 실제 GPT 호출은 별개이며, 이 Task는 어댑터까지만 닫는다.

---

---

## 계획서 완성도

Task 14개 중 상세 Step까지 완성된 것과 개요만 있는 것을 구분한다.
"계획서 완성"이라고 뭉뚱그리지 않기 위해 명시한다.

| Task | 상태 |
|---|---|
| 1–4, 6–11, 13, 14 | 상세 Step·Files·재사용 게이트 완성 |
| 5 | 간략하지만 실행 가능 |
| 12 | **완료** (2026-08-05, 커밋 `d503ce2`) |
| 11A | **개요만.** Task 10 승인 결과가 나와야 쓸 수 있다 |

Task 11A만 비워둔다. 무엇을 승인받는지 정해지기 전에 구현 Step을 쓰면 순서가 뒤바뀐다.

처음에는 Task 6–9도 "실측 전이라 못 쓴다"고 미뤄뒀으나, 각 결함을 이미 화면에서
직접 관측했으므로 그 판단은 틀렸다. owner 지적으로 바로잡고 Step을 채웠다.
실측이 전제를 바꾸면 갱신 규칙에 따라 수정한다.

**owner 결정이 필요한 항목:** Task 8의 삭제 방식(완전 삭제 vs 보관 처리).

## 이 계획서의 갱신 규칙

이 계획서는 확정본이 아니라 **실측에 따라 갱신되는 문서**다.
작성 근거 중 일부는 이미 역방향 검증으로 뒤집혔다.

- 실측이 계획서의 전제를 반증하면 **해당 Task를 즉시 수정한다.** 그대로 진행하지 않는다.
- 정정할 때는 이전 내용을 조용히 덮어쓰지 않고 무엇이 왜 틀렸는지 남긴다.
  근거 기록은 `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`가 맡는다.
- 정정이 다른 Task의 전제에 영향을 주는지 매번 확인한다.
  실제로 `F-0` 정정이 Task 2의 재사용 분류를 바꿨다.

**이미 발생한 정정 이력:**

| 시점 | 최초 판단 | 정정 후 | 계기 |
|---|---|---|---|
| 초기 | 편집기 디자인이 엉망이다 | 2026-07-22 owner가 5개 viewport로 승인한 디자인이다 | `docs/decisions/` 확인 |
| 초기 | 색상 시스템 충돌은 구조적 결함이다 | 변수만 오렌지로 바꾼 내 변경이 만든 충돌이다 | 승인 팔레트 확인 |
| 초기 | B-roll 자동 분류 차단은 치명 버그다 | 의도적 fail-closed 설계이며 구성 공백이다 | 코드 확인 |
| 중반 | Hermes는 로그인만 하면 동작한다 | §23이 gateway·signer·OAuth·mutation을 미완료로 표기한다 | 최상위 계획서 §23 |
| 후반 | 모든 산출물이 `MockSTTProvider`의 가짜 두 줄 위에 있다 | r4는 `deterministic_korean_smoke_stt`로 만들어졌고 자막 텍스트는 대본에서 왔다 | **역방향 검증** |

정정 다섯 건 중 네 건이 "확인 없이 단정"에서 나왔다.
그래서 이 계획의 Task 2(런타임 기준선)를 다른 구현보다 앞에 둔다.

## 이 계획에 넣지 않은 것

아래는 owner의 별도 승인 또는 선행 결정이 필요하다. 승인 없이 착수하지 않는다.

| 항목 | 필요한 선행 조건 |
|---|---|
| `D-2` 미디어 분석 worker | `§10.14` 네트워크 경계 결정. Task 13에서 컨테이너→호스트 LM Studio 경로를 열면 함께 해결될 수 있다 |
| `S-3` 대본 생성 | `implementation-plan` §23.3이 제품 범위 밖으로 차단 중. 조항 개정이 선행 |
| TTS 활성화 | owner가 2026-08-05에 보류 결정. 음성 인식 확인 후 재논의 |

`D-1` 팔레트와 `F-6` 하드코딩은 Slice 4로, `D-4` Hermes는 Slice 5로 각각 편입했다.
둘 다 owner 요구가 명확해졌으므로 "넣지 않은 것"에서 계획 본문으로 옮겼다.

## 완료 기준

이 계획은 아래가 모두 성립할 때 닫는다.

1. owner의 실제 나레이션에서 실제 전사가 나온다
2. `verify_owner_path.py`가 각 단계의 실제 동작을 기록하고 backlog 등급이 갱신됐다
3. 편집기에서 영상을 썸네일로 보고 고를 수 있다
4. 초안 없는 프로젝트에서도 편집 진입이 막히지 않는다
5. `implementation-plan` §23이 실측 상태와 일치한다
6. 대시보드 시각 방향이 재승인되고 하드코딩 색상이 변수로 일원화됐다
7. 유진이 로컬 LLM으로 실제 대화하고, provider 어댑터로 전환이 가능하다
8. 전체 Python·frontend 회귀와 production build가 통과한다

**최종 인수 기준:** owner가 설명 없이 대시보드를 열어 대본을 넣고,
자동 초안을 받고, 썸네일로 자산을 고르고, 유진과 대화하며 고친 뒤 내보낼 수 있다.
이 흐름 중 어디서도 막히지 않아야 한다.

사람의 시각·청취·취향 판정, 저작권·게시 승인, CapCut Desktop 실제 편집·export는
이 계획의 완료 기준에 포함하지 않는다. 계속 별도 human gate다.
