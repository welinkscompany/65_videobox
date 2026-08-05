# VideoBox 실사용 복구 구현 계획

> **작업자에게:** 이 계획은 Task 단위로 실행한다. 각 Step은 `- [ ]` 체크박스로 추적한다.
> 착수 전 `CLAUDE.md` → `docs/development-fast-path.ko.md` §10 → 해당 Task의 근거 문서를 읽는다.
> 각 Task는 `implementation-plan.ko.md` §8.1 재사용 게이트를 먼저 통과하고,
> §10.2 TDD를 기본으로 하며, §8.3 완료 보고 항목을 남긴다.

**Goal:** 문서가 주장하는 "Task 23 4/4 100%"와 owner가 실제로 쓸 수 있는 상태 사이의 간극을 닫는다.
새 기능을 늘리지 않고, 이미 만들어졌으나 연결되지 않았거나 가짜로 동작하는 경로를 실제 동작으로 바꾼다.

**Architecture:** 진실 확정 → 즉시 체감 개선 → 문서 정합 → 잔여 결함 순으로 진행한다.
런타임 실측을 먼저 하는 이유는 코드와 최상위 계획서(`implementation-plan.ko.md` §23)가
서로 다른 상태를 주장하고 있어, 실측 없이는 어떤 계획도 추측 위에 서기 때문이다.

**Tech Stack:** Python 3.12 / FastAPI / pytest, React 19 / Vite / vitest, FFmpeg, Docker Compose.

**근거 문서:** `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`
(결함 8건, 결정 4건, 아키텍처 발견 2건, 범위 충돌 3건, 각 항목 근거 등급 포함)

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
| `scripts/verify-production-readiness-smoke.py` | `partial port` | work-root/artifact/ffprobe 구조는 재사용한다. 다만 이 스크립트는 LLM·STT·TTS를 deterministic으로 대체하므로 그 부분은 쓰지 않는다 |
| `scripts/owner_sample_edit_package.py` | `partial port` | owner 실제 샘플로 edit package를 만드는 흐름을 재사용한다 |
| `scripts/owner-ready.ps1 -Mode Smoke` | `exclude` | static/non-live verifier라 실제 파이프라인을 돌리지 않는다 |

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

### Task 6: 미리보기 자동 갱신 (F-4)

편집 후 `미리보기 새로 만들기`를 수동으로 눌러야 하고 `stale` 상태가 그대로 노출된다.
자동 갱신 정책과 §10.13 문구를 함께 정한다.

### Task 7: 타임라인 내부 식별자를 사람이 읽는 라벨로 (F-3)

`broll:session-broll-segment_draft_1726b9574a-0` 형태의 접근성 이름을 교체한다.

### Task 8: 프로젝트 삭제 경로 (F-5)

API와 UI 모두 없다. 데이터 보존 정책과 확인 절차를 함께 설계한다.

### Task 9: 중복 액션 정리 (F-7)

`새 영상 만들기`가 3곳에 있다. 주 진입점을 하나로 정한다.

---

## 이 계획에 넣지 않은 것

아래는 owner의 별도 승인 또는 선행 결정이 필요하다. 승인 없이 착수하지 않는다.

| 항목 | 필요한 선행 조건 |
|---|---|
| `D-1` 오렌지 팔레트 | 승인된 팔레트 2건이 있다. 프로토타입 재생성 → 새 SHA → owner 재승인 |
| `D-2` 미디어 분석 worker | `§10.14` 네트워크 경계 결정. `architecture-plan` §11이 GPU 로컬 모델 컨테이너화를 비권장 |
| `D-4` Hermes 대화 편집 | Task 2 실측으로 코드·계획서 불일치를 먼저 확정 |
| `S-3` 대본 생성 | `implementation-plan` §23.3이 제품 범위 밖으로 차단 중. 조항 개정이 선행 |
| `F-6` 테마 하드코딩 | `D-1`과 함께 처리 |

## 완료 기준

이 계획은 아래가 모두 성립할 때 닫는다.

1. owner의 실제 나레이션에서 실제 전사가 나온다
2. `verify_owner_path.py`가 각 단계의 실제 동작을 기록하고 backlog 등급이 갱신됐다
3. 편집기에서 영상을 썸네일로 보고 고를 수 있다
4. 초안 없는 프로젝트에서도 편집 진입이 막히지 않는다
5. `implementation-plan` §23이 실측 상태와 일치한다
6. 전체 Python·frontend 회귀와 production build가 통과한다

사람의 시각·청취·취향 판정, 저작권·게시 승인, CapCut Desktop 실제 편집·export는
이 계획의 완료 기준에 포함하지 않는다. 계속 별도 human gate다.
