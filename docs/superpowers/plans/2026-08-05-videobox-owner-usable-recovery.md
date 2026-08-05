# VideoBox 실사용 복구 구현 계획

> **작업자에게:** 이 계획은 Task 단위로 실행한다. 각 Step은 `- [ ]` 체크박스로 추적한다.
> 착수 전 `CLAUDE.md` → `docs/development-fast-path.ko.md` §10 → 해당 Task의 근거 문서를 읽는다.
> 각 Task는 `implementation-plan.ko.md` §8.1 재사용 게이트를 먼저 통과하고,
> §10.2 TDD를 기본으로 하며, §8.3 완료 보고 항목을 남긴다.

**Goal:** owner가 실제로 쓸 수 있는 제품을 만든다. 최종 상태는 아래 셋을 모두 만족한다.

1. 실제 음성·영상으로 자동 초안이 만들어지고, 사람이 보고 고칠 수 있다
2. 대시보드가 깔끔하고 직관적이어서 설명 없이 쓸 수 있다
3. 유진이 로컬 LLM으로 대화하며, provider 어댑터로 GPT-5.4 / 5.4-mini 전환이 쉽다

4. 촬영한 B-roll이 자동으로 분류되고 의미로 검색된다
5. Drive에 올린 영상이 자동으로 반입되고, 세로 영상은 숏폼으로 편집할 수 있다

1번·4번·5번은 이미 만들어졌으나 꺼져 있거나 연결되지 않은 경로를 실제 동작으로 바꾸는 일이다.
2번과 3번은 계획서 조항과 충돌했으나 **2026-08-05에 둘 다 해소했다.**
디자인은 `2026-08-05-dashboard-white-orange-direction.ko.md`로 승인했고,
로컬 LLM 제약은 `implementation-plan.ko.md` §23.3B로 개정했다.

**Architecture:** 아래 8개 Slice로 나눈다.

| Slice | 내용 | Task |
|---|---|---|
| 0 | 진실 확정 — provider 활성화와 런타임 기준선 | 1–2 |
| 1 | 즉시 체감 개선 — 썸네일, 데드엔드 | 3–4 |
| 2 | 문서 정합 | 5 |
| 3 | 잔여 결함 | 6–9 |
| 4 | 대시보드 | 10–11A |
| 5 | 유진 대화와 provider 전환 | 12–14 |
| 6 | 영상 반입과 숏폼 | 15–18 |
| 7 | B-roll 자동 분류와 의미 검색 | 19–21 |

Slice 번호는 분류일 뿐 실행 순서가 아니다. 실행 순서는 아래 `## 실행 순서`를 따른다.

런타임 실측(Task 2)을 앞에 두는 이유는 코드와 최상위 계획서가 서로 다른 상태를 주장하고 있어,
실측 없이는 어떤 계획도 추측 위에 서기 때문이다.

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

### Task 2: 런타임 진실 기준선 확보 — **완료 (2026-08-05)**

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

**품질 기준선 — owner의 수작업 결과물 (2026-08-05 제공):**

`G:\내 드라이브\100_videobox\20250827_유튜브영상.mp4`

owner가 Vrew로 **약 24시간에 걸쳐 하나하나 수작업**으로 만든 영상이다.
`1920×1080`, `30fps`, H.264/AAC, **8분 15초**, 546MB.

**이것이 VideoBox가 따라가야 할 목표다.** 자동 초안의 품질을 판정할 때
"기술적으로 렌더가 됐는가"가 아니라 **"이 수준에 얼마나 가까운가"**로 본다.

이 영상은 read-only 참고 자료다. 반입·수정·삭제하지 않는다.
Task 2 기준선을 만들 때 같은 길이대(8~10분) 실제 나레이션을 쓰면 비교가 쉬워진다.

**Files:**
- Create: `scripts/verify_owner_path.py`
- Create: `tests/test_owner_path_verifier.py`
- Modify: `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md` (등급 갱신)

- [x] **Step 1: 실패 테스트 작성** — stub provider 거부, 실패해도 중단 없이 9단계 전부 기록되는지 검사
- [x] **Step 2: RED 확인** — `ModuleNotFoundError: No module named 'scripts.verify_owner_path'`
- [x] **Step 3: 구현** — `run_owner_path()`가 ingest→STT→세그먼트→추천→timeline→preview→
      자막→최종렌더→CapCut을 순서대로 실행하고, 실패해도 나머지를 `skipped`로 계속 기록한다.
      `STUB_PROVIDER_NAMES`에 `mock_stt`와 `deterministic_korean_smoke_stt`를 등록해 거부
- [x] **Step 4: GREEN(4/4) 및 실제 실행** — owner의 실제 영상에서 나레이션 60초와 B-roll 2개를
      뽑아 실제 provider(`faster_whisper`, 스텁 없음)로 end-to-end 실행.
      전사 정확히 성공(14개 세그먼트). `timeline_build`에서 실패 — `S-4`로 별도 기록
- [x] **Step 5: backlog 등급 갱신 및 커밋**

Commit: `feat: verify the owner path end to end`

**결과 요약:** `F-0`(provider 비활성)는 Task 1로 해소되어 실사용 확인까지 승격했다.
그런데 실제로 돌려보니 **`S-4`라는 새 차단 지점**을 찾았다 — 세그먼트 14개 전부가
review 필수로 자동 차단되어 timeline 승인이 거부되고 preview 이후 전 단계가 스킵됐다.
이건 이번 실측이 아니었다면 몰랐을 문제다. Task 21이 이제 이 원인 규명부터 시작한다.

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
- Modify: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`

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

### Task 10: 시각 방향 재승인 — **완료 (2026-08-05)**

- [x] **Step 1:** 현재 화면의 실제 문제를 사용성 근거로 정리했다.
      썸네일 없음, 데드엔드, 내부 ID 노출, 진입점 중복, 자산 세로 나열, 무음 상태 비노출
- [x] **Step 2:** 시안을 만들어 owner에게 보여주고 화이트톤으로 한 차례 수정했다.
      `docs/prototypes/2026-08-05-dashboard-direction/editor-workbench.html`
- [x] **Step 3:** owner 승인을 기록했다.
      `docs/decisions/2026-08-05-dashboard-white-orange-direction.ko.md`
- [x] **Step 4:** 대비를 직접 계산해 확인했다.
      본문 17.01:1, 보조 5.07:1, 희미 4.77:1, 강조 5.18:1 — 전부 4.5:1 이상

**승인 방식이 이전과 다르다.** owner가 "나중에 개발하면서 조금씩 바뀔 것"이라고 명시했으므로
artifact SHA를 고정하지 않고 **방향을 승인**했다. 여백·모서리·문구 조정은 재승인 없이 진행하고,
색 값·"배경 흰색, 오렌지는 강조만" 원칙·3분할 구조·자산 그리드를 바꿀 때만 재승인한다.

따라서 `scripts/build_ui_prototype_artifacts.py --require-approved`는
이 방향 승인에 적용하지 않는다. 기존 두 승인 기록의 SHA 게이트는 그대로 두되,
색 팔레트는 이번 결정이 대체한다.

### Task 11: 색상 토큰 일원화 (F-6) — **완료 (2026-08-05)**

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

- [x] **Step 1: 실패 테스트** — `theme-tokens.test.ts`: 셸 CSS에 하드코딩 hex가 남아 있지 않은지,
      기본 버튼 rule이 `var(--primary)`/`var(--primary-foreground)`를 쓰는지,
      `editor-workbench.css`의 preview shell도 `var(--vb-preview)`를 쓰는지 (4개 테스트)
- [x] **Step 2: RED 확인** — 4/4 실패 (하드코딩 hex·rgba 다수 검출)

Run: `npm --prefix apps/web test -- src/styles`

- [x] **Step 3: 구현** — `product-shell.css`의 하드코딩 색·rgba 전부와
      `editor-workbench.css`의 `#08090b`를 기존 토큰(`--vb-canvas`/`--vb-panel`/`--vb-border`/
      `--vb-text`/`--vb-muted`/`--vb-accent`/`--vb-preview`, `--primary`/`--primary-foreground`,
      `--accent`)으로 치환했다. 새 토큰 체계는 만들지 않았다.
      **재실측 결과, 실제로는 승인된 값과 다른 값(색상 드리프트)이 하드코딩돼 있었다** —
      기본 버튼 `#5b4ac8`은 승인된 accent `#4F46E5`와 다른 값이었다. 이 Task로 승인값과
      일치시켰다. 값을 새로 정한 게 아니라 이미 승인된 값에 맞춘 것이므로 "색상값을 바꾸지
      않는다"는 원칙과 충돌하지 않는다
- [x] **Step 4: GREEN(4/4) + 브라우저 실측 + 커밋** — 프론트 전체 회귀 749/749 통과.
      실제 실행 중인 앱(`b-roll-smoke-test` 프로젝트 홈)에서 `--primary`를 JS로 바꾸면
      기본 버튼(`새 영상 만들기`)의 `background-color`가 실제로 따라 바뀌는 것을 확인했다
      (`rgb(79,70,229)` → `rgb(255,0,0)` → 원복). 셸 배경·사이드바 배경·테두리 색도
      승인 팔레트 값(`#FFFFFF`/`#292524`/`#FAFAF9`/`#E7E5E4`)과 일치함을 계산된 스타일로 확인

Commit: `refactor: drive shell colours from theme tokens`

### Task 11A: 승인된 디자인을 화면에 반영 — **완료 (2026-08-05)**

승인 **내용**은 Task 10에서 정해지지만 **작업 절차**는 지금 정할 수 있다.
승인된 값은 이 Task의 입력이지 Step의 구조를 바꾸지 않는다.

**선행:** Task 11(색상 토큰 일원화). 토큰이 안 통하면 어떤 승인값도 화면에 안 나온다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| Task 11이 만든 변수 체계 | `adopt as-is` | 값만 교체한다 |
| `scripts/build_ui_prototype_artifacts.py` | `adopt as-is` | 승인 SHA 검증에 기존 스크립트를 쓴다 |
| 새 디자인 시스템 | `exclude` | 기존 토큰 이름을 유지한다 |

**Files:**
- Modify: `apps/web/src/ui-system.css` (승인된 값으로 토큰 교체)
- Modify: `apps/web/src/styles/product-shell.css` (Task 11에서 변수화된 상태)
- Create: `apps/web/src/styles/contrast.test.ts`

- [x] **Step 1: 실패 테스트** — `contrast.test.ts`: 토큰 hex가 `2026-08-05-dashboard-
      white-orange-direction.ko.md`의 승인값과 정확히 일치하는지, 본문/보조/희미/강조
      텍스트가 패널 배경에서 4.5:1 이상인지, 성공 상태 텍스트가 자기 배경에서 4.5:1
      이상인지 (6개 테스트). 기준값은 승인 문서가 이미 계산해 명시한 17.01/5.07/4.77/
      5.18:1을 그대로 재확인하는 것이지 새로 정하는 것이 아니다
- [x] **Step 2: RED 확인** — 토큰 값 불일치 1건 검출 (`--vb-canvas`가 구 승인값 `#FAFAF9`)

Run: `npm --prefix apps/web test -- src/styles`

- [x] **Step 3: 승인된 값 적용** — `ui-system.css`의 `:root`를 백색·오렌지 승인 표로 교체했다.
      기존 승인에 없던 역할(진한 테두리·희미 텍스트·강조 배경/테두리·성공 상태)은
      승인 문서의 값 그대로 새 변수(`--vb-border-strong`, `--vb-faint`, `--vb-accent-bg`,
      `--vb-accent-border`, `--vb-success`, `--vb-success-bg`)로 추가했다.
      shadcn 계열 변수(`--primary`, `--accent`, `--ring` 등)도 같은 값으로 맞췄다
- [x] **Step 4: GREEN(6/6) + 브라우저에서 실제 대비 측정** — 프론트 전체 회귀 755/755 통과.
      실행 중인 앱에서 계산된 스타일로 확인: 기본 버튼 `rgb(194,65,12)`(`#C2410C`),
      셸 텍스트 `rgb(28,28,30)`(`#1C1C1E`), 사이드바 배경 `rgb(250,250,250)`(`#FAFAFA`) —
      전부 승인값과 정확히 일치
- [ ] **Step 5: GREEN + 브라우저 실측 + 커밋**

Commit: `feat: apply the approved visual direction`

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
| `packages/provider-interfaces/src/videobox_provider_interfaces/lm_studio.py` | `adopt as-is` | 기존 클라이언트를 쓴다 |
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

## Slice 6 — 영상 반입과 숏폼 (2026-08-05 owner 추가 요구)

owner 추가 요구 4건을 조사한 결과다.

| 요구 | 현재 상태 |
|---|---|
| 업로드 영역 | **부분만 존재** |
| B-roll 자동 무음 | **이미 구현됨** |
| 가로/세로 판별 | **미구현** |
| 숏폼 편집기 | **미구현** |

### B-roll 자동 무음은 이미 동작한다 — 새 작업 없음

`media_controls.py:50`의 `preserve_source_audio` 기본값이 `False`이고,
`ffmpeg_final_renderer.py:222`가 `if not controls["preserve_source_audio"]: continue`로
B-roll 오디오를 건너뛴다. 즉 **B-roll은 기본 무음이고 명시적으로 켤 때만 소리가 살아난다.**
나레이션·원본 영상은 B-roll 트랙이 아니므로 영향받지 않는다.

요구사항이 이미 충족되므로 구현 Task를 만들지 않는다.
다만 **사용자가 이 상태를 화면에서 볼 수 없다.** 자산 카드가 오디오 유무를 표시하지 않는다.
이 노출은 Task 15에서 함께 처리한다.

### Task 15: 자산 반입 시 실제 정보 저장 (F-2와 같은 뿌리)

현재 B-roll 등록은 `metadata={"title", "tags"}`만 저장한다(`local_pipeline.py:494`).
실제 API 응답에서도 `title`, `tags`, `thumbnail_uri` 세 키뿐이다.

**크기·길이·오디오 유무를 버리고 있다.** `media_probe.probe()`가 이미
`duration_sec`, `width`, `height`, 코덱, 대표 프레임을 반환하는데 저장하지 않는다.
자산 카드의 `길이 정보 없음`, `오디오 정보 확인 중`이 여기서 나온다.

이 Task 하나로 owner 요구 3번(가로/세로)과 `F-2`의 나머지 절반이 함께 해결된다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `media_probe.MediaProbe.probe()` | `adopt as-is` | 필요한 값을 이미 전부 반환한다 |
| `_try_generate_broll_thumbnail` | `partial port` | 같은 등록 시점에 probe 결과도 함께 저장하도록 확장한다 |
| 새 probe 구현 | `exclude` | 기존 ffprobe 경로로 충분하다 |

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `apps/web/src/features/editor/assets/editorAssetProjection.ts`
- Create: `tests/test_asset_intake_metadata.py`

**저장 위치 — 태그가 아니라 별도 필드다.**

가로/세로는 사용자가 정하는 값이 아니라 영상 파일에서 계산되는 사실이므로
`tags` 배열이 아니라 독립 metadata 필드에 넣는다.

| 구분 | 저장 위치 | 예 |
|---|---|---|
| 기계가 계산한 사실 | metadata 필드 | `orientation`, `duration_sec`, `width`, `height`, `has_audio` |
| 사용자가 붙인 의미 | `tags` 배열 | `카페`, `야외`, `타이핑` |

`tags`에 넣으면 사용자가 태그를 정리하다 지우거나 오타를 내면 분류가 깨진다.
`tags`는 사용자의 의미 태그 전용으로 비워둔다.

화면에서는 편집기 자산 목록의 기존 필터(`전체`/`B-roll`/`BGM`/`SFX`) 옆에
`가로`/`세로` 필터를 추가해 노출한다. 숏폼 작업 시 세로 소재만 걸러 보기 위한 것이다.

- [ ] **Step 1: 실패 테스트** — 등록된 B-roll의 metadata에
      `duration_sec`, `width`, `height`, `orientation`, `has_audio`가 있는지.
      `orientation`은 `가로`/`세로`/`정사각`으로 분류되는지.
      `tags` 배열이 이 값들로 오염되지 않는지
- [ ] **Step 2: RED 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_asset_intake_metadata.py -q`

- [ ] **Step 3: 구현** — 등록 시 probe 결과를 metadata에 저장한다.
      `orientation`은 width/height 비교로 판정한다. probe 실패는 등록을 막지 않고
      해당 필드만 비운다(기존 썸네일 실패 처리와 동일한 폴백)
- [ ] **Step 4: 프론트 표시 연결** — 자산 카드에 길이와 오디오 유무를 실제 값으로 표시하고,
      자산 목록에 `가로`/`세로` 필터를 추가한다. `§10.13` 창작자 언어를 쓴다
- [ ] **Step 5: GREEN + 브라우저 실측 + 커밋**

Commit: `feat: keep size, length, and audio when media is added`

### Task 16: 자산 업로드 영역

현재 파일 업로드는 `DraftGapMedia.tsx`에만 있고, "초안 준비 중 자산 부족" 경로에서
`return_to` 파라미터를 달고 들어갈 때만 열린다. 자산 화면(`MediaWorkspacePage`)에는 파일 입력이 없다.
즉 **평소에 B-roll을 쌓아두는 경로가 UI에 없다.**

owner의 실제 사용 방식("평소에 다양한 B-roll을 녹화해서 저장")에 이 경로가 필요하다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `api.uploadDraftBroll` | `adopt as-is` | 업로드 엔드포인트가 이미 있다 |
| `DraftGapMedia`의 업로드 UI | `partial port` | 파일 선택·상태 표시 패턴을 재사용한다 |
| `MediaWorkspacePage` | `partial port` | 기존 자산 화면에 업로드 영역을 추가한다. 새 화면을 만들지 않는다 |

**Files:**
- Modify: `apps/web/src/features/media/MediaWorkspacePage.tsx`
- Modify: 대응 테스트 파일

- [ ] **Step 1: 실패 테스트** — 자산 화면에서 파일을 여러 개 올릴 수 있고,
      진행·성공·실패 상태가 창작자 언어로 보이는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 자산 화면에 업로드 영역을 추가한다.
      Task 15가 선행이면 업로드 직후 길이·방향·썸네일이 바로 보인다
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

Commit: `feat: add media from the asset screen`

### Task 17: 숏폼 편집 — 세로 캔버스로 기존 편집기 재사용

**owner 결정 (2026-08-05):** "지금 편집기를 세로화면으로 쓰면 되."

따라서 숏폼 전용 편집기를 새로 만들지 않는다. 기존 편집 작업판을 세로 캔버스로 쓴다.
`implementation-plan.ko.md` §4의 `풀 자체 편집기` 제외 조항에 걸리지 않으므로 **조항 개정이 불필요하다.**

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| 기존 편집 작업판과 14개 조작 | `adopt as-is` | 새 편집 기능을 만들지 않는다 |
| `composition_plan`의 canvas width/height | `partial port` | 출력 규격만 세로로 바꾼다 |
| `ffmpeg_final_renderer`의 `force_original_aspect_ratio=increase,crop` | `adopt as-is` | 가로 소재를 세로로 채우는 변환이 이미 있다 |
| 숏폼 전용 새 편집기 | `exclude` | owner 결정으로 범위 밖 |

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/composition_plan.py`
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx`
- Create: `tests/test_vertical_composition.py`

- [ ] **Step 1: 실패 테스트** — 세로 출력 규격을 고르면 canvas가 세로가 되고,
      가로 소재가 잘림 없이 채워지며, 자막이 세로 화면 안에 들어오는지
- [ ] **Step 2: RED 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_vertical_composition.py -q`

- [ ] **Step 3: 구현** — 프로젝트 또는 출력 단위로 세로 규격을 고를 수 있게 한다.
      미리보기도 같은 비율로 보여준다. Task 15의 `orientation`을 써서
      세로 소재를 우선 추천할 수 있으나, 그 랭킹 조정은 별도 Task로 둔다
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

Commit: `feat: compose vertical videos in the same editor`

**선행:** Task 15(`orientation` 저장).

### Task 18: 촬영본 반입 경로 — Drive 폴더 감시

owner의 실제 작업 방식: 외부에서 촬영 → 폰에서 구글 드라이브로 전송 → PC에서 사용.
요구: Drive 폴더에 올리면 자동으로 로컬로 옮기고, 태그를 붙이고, Drive에서는 정리되기.

**계획서 충돌:** 아래 세 조항이 Google Drive 결합을 금지한다.

- `implementation-plan.ko.md:265` "Google Sheets/Drive 구조는 버림"
- `implementation-plan.ko.md:286` "`Google Sheets/Drive 결합`은 반입 금지"
- `architecture-plan.ko.md:446` "Google Sheets/Drive 의존은 제거"

이 조항은 BrollBox가 Drive를 저장소 backend로 쓰던 결합을 버리기 위한 것이다.

**API를 쓰지 않는 대안이 조항과 충돌하지 않는다.**

Drive 데스크톱 앱이 폴더를 로컬로 동기화하면, VideoBox 입장에서는 그냥 로컬 폴더다.
VideoBox가 그 폴더를 감시하다가 파일을 라이브러리로 **이동**하면 동기화 폴더에서 사라지고,
결과적으로 Drive에서도 정리된다. OAuth·API key·외부 호출이 전혀 없다.

- Drive API 직접 호출 방식: **조항 개정 선행 필요**
- 로컬 동기화 폴더 감시 방식: **조항과 충돌 없음.** 권장

**확인이 필요한 전제:**

1. ~~이 PC에 Drive 데스크톱 앱이 설치되어 있지 않다~~ → **owner가 설치하기로 함 (2026-08-05).**
   설치 후 동기화 폴더 경로를 확인해 감시 대상으로 설정한다
2. 동기화 폴더에서 파일을 옮겼을 때 Drive에서 실제로 지워지는지는
   앱 동작 모드(미러/스트림)에 따라 다를 수 있다. **실제로 확인해야 한다**

**owner 결정 (2026-08-05): 로컬 동기화 폴더 감시 방식으로 진행한다.**
Drive API를 쓰지 않으므로 `implementation-plan.ko.md` §8·§8.1과
`architecture-plan.ko.md` §12의 Drive 결합 금지 조항을 개정할 필요가 없다.
감시 대상은 설정 가능한 로컬 경로이며, VideoBox는 그것이 어떤 클라우드의
동기화 폴더인지 알지 못한다. 이 무지가 조항 준수의 근거다.

**감시 경로 (2026-08-05 확인):** `G:\내 드라이브\100_videobox`

실측한 현재 내용:

| 항목 | 상태 |
|---|---|
| 최상위 mp4 | 8개. 전부 `1920×1080` 가로 |
| `가로/FHD/` | mp4 1개 |
| `thumbnails/` | jpg 1개 |
| `voiceover/` | 비어 있음 |
| `desktop.ini` | Windows 폴더 설정 파일. 반입 대상에서 제외한다 |

**기존 폴더를 지우지 않는다.** owner가 방향별로 수동 정리하던 흔적(`가로`)이 있으나,
Task 15가 `orientation`을 자동 판정하므로 **수동 분류 폴더는 앞으로 불필요하다.**
반입 후 자연스럽게 비워진다. 강제로 정리하지 않는다.

**감시 규칙:**

- 최상위와 하위 폴더를 모두 훑되 `desktop.ini`와 숨김 파일은 무시한다
- 동영상 확장자만 대상으로 한다
- Drive가 아직 내려받는 중인 파일(스트림 모드 placeholder)은 건너뛰고 다음 주기에 다시 본다

**전제 확인 완료 (2026-08-05) — 더미 파일 실측:**

더미 파일 `_videobox_synctest.txt`를 동기화 폴더에 만들고 라이브러리로 **이동**한 뒤,
owner가 Drive에서 확인했다. 결과:

| 확인 항목 | 결과 |
|---|---|
| 이동 후 동기화 폴더에서 사라지는가 | **그렇다** |
| 로컬 라이브러리에 내용이 온전한가 | **그렇다** |
| Drive에서도 제거되는가 | **그렇다. 휴지통으로 이동됨** |
| Drive 모드 | 미러 모드. `du` 726MB ≈ 논리 합계 706MB로 파일이 실제 로컬에 존재 |

**핵심 단서 — 휴지통은 용량을 계속 차지한다.**

Google Drive 휴지통의 항목은 30일 뒤 자동 삭제되기 전까지 저장 용량에 포함된다.
따라서 "옮기면 즉시 용량이 빈다"가 아니라 **"옮기면 휴지통으로 가고 30일 뒤 자동으로 빠진다"**가 정확하다.
즉시 비우려면 owner가 Drive 휴지통을 직접 비워야 한다.

이 동작은 **안전장치로 활용한다.** 로컬 반입이 잘못돼도 30일 안에는 Drive 휴지통에서 복구할 수 있다.
VideoBox가 별도 유예 기간을 구현할 필요가 없다. Drive의 휴지통이 그 역할을 한다.

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/media_inbox.py`
- Create: `tests/test_media_inbox.py`
- Modify: `packages/core-engine/src/videobox_core_engine/settings.py` (감시 경로 설정)

- [ ] **Step 1: 실패 테스트** — 감시 폴더의 동영상만 반입 대상으로 잡는지,
      `desktop.ini`·숨김 파일·비동영상을 건너뛰는지,
      해시가 일치할 때만 원본을 옮기는지, 불일치면 원본을 건드리지 않고 실패로 남기는지,
      아직 내려받는 중인 파일을 건너뛰고 다음 주기에 다시 보는지
- [ ] **Step 2: RED 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_media_inbox.py -q`

- [ ] **Step 3: 구현** — 감시 → 해시 검증 → 라이브러리로 이동 순서를 지킨다.
      **복사 후 삭제가 아니라 검증 후 이동이다.** 검증 실패 시 원본은 그대로 둔다.
      Task 15의 반입 metadata 저장과 같은 경로를 쓴다
- [ ] **Step 4: GREEN + 실제 Drive 폴더로 확인 + 커밋**

Commit: `feat: take in footage from the watched folder`

**owner에게 안내할 것:** 반입된 파일은 Drive 휴지통에 30일간 남는다.
용량을 바로 비우려면 휴지통을 직접 비워야 한다.

**안전 요건 — 데이터 손실 방지:**

- 원본을 옮기기 전에 해시로 무결성을 확인한다
- 확인 실패 시 원본을 건드리지 않고 실패로 남긴다
- 즉시 삭제하지 않는다. 로컬 반입이 검증된 뒤 일정 기간이 지난 것만 정리한다
- 사용자 원본은 read-only로 취급한다는 기존 경계를 유지한다

Step은 위 전제 확인과 방식 결정 뒤에 채운다.

**현재 미구현이다.** 코드에 숏폼 관련 구현이 없다.

다만 문서에는 이미 자리가 있다.

- `product-plan.ko.md` §9.3: "롱폼 초안 또는 전사 결과를 기반으로 shortform 후보를 추천한다"
- `architecture-plan.ko.md` §2.2: `shortform extractor`가 timeline JSON 소비자로 명시
- `architecture-plan.ko.md` §4.4: Recommendation Layer에 `shortform 후보 scoring` 포함

**범위 충돌 확인 필요:** 문서가 규정한 것은 **후보 추출·추천**이고,
owner가 요구한 것은 **편집기**다. `implementation-plan.ko.md` §4 제외 목록에
`실시간 멀티트랙 편집 UI`와 `풀 자체 편집기`가 있으므로, 숏폼 편집기가
기존 편집기 재사용인지 새 편집기인지에 따라 판정이 갈린다.

- 세로 캔버스와 기존 14개 조작을 재사용하는 방식이면 **범위 안**이다
- 숏폼 전용 새 편집 기능이 필요하면 **§4 개정이 선행**이다

Step은 이 판정 뒤에 채운다. 판정에 필요한 입력은 owner의 숏폼 작업 방식이다.
Task 15의 `orientation`이 선행 조건이므로 그 뒤에 다룬다.

---

## Slice 7 — B-roll 자동 분류와 의미 검색 (owner 핵심 요구)

> **2026-08-05 갭 검증으로 추가.** 이 Slice는 원래 "계획에 넣지 않은 것"에 있었다.
> owner가 가장 강조한 요구인데 계획서에서 빠져 있었다. 갭 검증이 잡았다.
>
> owner 발언: "내가 평소에 다양한 비롤을 녹화해서 내 컴퓨터에 저장할거야.
> 이건 내가 직접 녹화해서 넣는거라 진짜 내 자산인거야."
> "메타검색(의미 연관검색)이 필요했던 거야. 왜냐면 100% 똑같은 형태의 영상을 만들수가 없잖아."

### Task 19: 미디어 분석 worker 연결 (D-2, A-1)

현재 컨테이너는 `_UnavailableMediaAnalysisService` 스텁을 써서 모든 분석 요청을
즉시 `MEDIA_ANALYSIS_WORKER_UNAVAILABLE`로 차단한다. 그 결과 태그·설명·임베딩이
생성되지 않고, `media_ranking.py`의 1순위 점수인 `semantic_similarity`를 계산할 재료가 없다.

`A-1`에서 확인했듯 **랭킹 구조는 이미 완성돼 있다.** 점수 항목에
`semantic_similarity`, `lexical_fallback`, `structured_tag_match`, `repetition`, `diversity`가 있고,
`MediaLibraryStore`는 `project_id`를 받지 않는 전역 저장소이며
`ProjectAssetMaterializer`가 프로젝트로 복사한다. 여러 채널에서 같은 B-roll을 쓰는 경로가 이것이다.

**즉 이 Task는 새 설계가 아니라 이미 설계된 자리를 채우는 일이다.**

**선행:** Task 13(컨테이너→호스트 LM Studio 경로). 같은 경로를 vision 분석이 재사용한다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `media_ranking.rank_candidates` | `adopt as-is` | 점수 체계를 바꾸지 않는다 |
| `EmbeddingProvider` 프로토콜 | `adopt as-is` | 인터페이스가 이미 있다 |
| `lm_studio.py` 클라이언트 | `adopt as-is` | Task 13이 연 경로를 재사용한다 |
| `_UnavailableMediaAnalysisService` | `rewrite` | 실제 worker로 교체한다. fail-closed 동작은 worker 부재 시 폴백으로 유지 |
| `architecture-plan.ko.md` §7 Vision Provider | `adopt as-is` | 역할이 이미 규정돼 있다 |

**Files:**
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `packages/core-engine/src/videobox_core_engine/media_analysis.py`
- Create: `tests/test_media_analysis_worker.py`

- [ ] **Step 1: 실패 테스트** — worker가 구성되면 분석이 `blocked`가 아니라 실제 결과를 내는지,
      태그 4축(찍힌 대상 / 장소·배경 / 분위기·톤 / 구도·움직임)이 채워지는지,
      worker 부재 시 기존 fail-closed 동작이 유지되는지
- [ ] **Step 2: RED 확인**

Run: `.venv\Scripts\python.exe -m pytest tests/test_media_analysis_worker.py -q`

- [ ] **Step 3: 구현** — vision 분석 결과를 자산 metadata에 저장하고 임베딩을 생성한다.
      Task 15가 저장 구조를 이미 열어놨으므로 같은 자리에 넣는다.
      분석 실패는 등록을 막지 않고 해당 필드만 비운다
- [ ] **Step 4: GREEN + 실제 B-roll로 분류 확인 + 커밋**

Commit: `feat: classify b-roll with the local vision model`

### Task 20: 의미 검색 실제 동작 확인 (A-1)

`A-1`은 근거 등급이 `코드`다. 설계는 확인했으나 **동작하는 것을 본 적이 없다.**
Task 19로 재료가 생긴 뒤 실제로 검색이 되는지 확인한다.

- [ ] **Step 1: 실패 테스트** — 대본 문장으로 검색했을 때 정확히 같은 단어가 없어도
      의미가 가까운 B-roll이 상위에 오는지. 같은 영상에서 한 클립이 반복되면 감점되는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 필요한 만큼만 보완한다. 랭킹 구조는 이미 있으므로
      대부분 연결과 가중치 조정이다
- [ ] **Step 4: GREEN + owner의 실제 B-roll 라이브러리로 확인 + 커밋**

Commit: `feat: find b-roll by meaning`

**이 Task는 owner 판단이 최종 기준이다.** 추천이 실제로 쓸 만한지는 사람이 봐야 안다.

### Task 21: 자동 배치 정책 확정 (S-2) — **완료 (2026-08-05)**

owner 결정: **완전 자동 배치 후 검토.**

`architecture-plan.ko.md` §6.5의 Recommendation 모델에 `auto_apply_allowed` 필드가 이미 있다.
구조 변경은 불필요하고 **정책만 정하면 된다.** 그러나 현재 이 정책을 설정하는 코드가 없다.

`product-plan.ko.md` §6.4는 "초기에는 무조건 자동 적용하지 않는다"고 규정하지만,
OSS 채택 계획이 이미 "`초안 만들기` 1회 승인 뒤 ranked placement bundle을 atomic하게 apply"로
옮겨갔으므로 owner 결정과 충돌하지 않는다. 승인은 초안 생성 시점 1회로 유지한다.

**실측 (2026-08-05, `verify_owner_path.py`, `S-4`):** owner 실제 나레이션 60초로
end-to-end 실행 시 **세그먼트 14개 전부가 `segment_review_required`로 자동 차단**되어
`approve_timeline_review`가 거부되고 preview/자막/렌더/CapCut까지 전부 도달 불가능했다.
점수 임계값 문제가 아니라 review 요구 자체가 항상 켜져 있는 것으로 보인다.
따라서 이 Task는 `auto_apply_allowed` 설정 이전에 **왜 review가 무조건 걸리는지 원인 규명**이
선행되어야 한다.

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/director_proposal_service.py`
- Create: `tests/test_auto_apply_policy.py`

- [x] **Step 0: 원인 규명 (선행) — 완료 (2026-08-05)** — 원인은 정책이 아니라 버그였다.
      `FasterWhisperSTTProvider`가 `confidence = 1 - no_speech_prob`(음성 존재 여부)를
      전사 품질처럼 썼다. `avg_logprob`(실제 디코드 신뢰도) 기반 `exp(avg_logprob)`로 교체했고,
      owner 실제 영상 재검증에서 14개 중 3개가 review 대상에서 빠졌다(0.19→0.873).
      남은 11개는 0.816~0.821로 근소 미달 — 여기부터가 진짜 정책 질문이다.
      커밋: `fix: score STT confidence from decode quality, not speech presence`
- [x] **Step 1: 실패 테스트** — `tests/test_auto_apply_policy.py`. 기본값(false)은 기존처럼
      막고, `auto_approve_segment_review=true`면 review가 있어도 승인되며 플래그 자체는
      timeline에 그대로 남아 나중에 볼 수 있는지
- [x] **Step 2: RED 확인** — `resolve_auto_approve_segment_review` 없어 import 실패
- [x] **Step 3: 구현** — owner가 Option A를 선택했다. 자산 종류별 임계값이 아니라
      **세그먼트 review 자체를 승인 차단에서 제외**하는 정책 스위치로 구현했다.
      `resolve_auto_approve_segment_review()`(환경변수 `VIDEOBOX_AUTO_APPROVE_SEGMENT_REVIEW`,
      컨테이너 기본값 `1`) → `LocalPipelineRunner(auto_approve_segment_review=...)` →
      `_normalized_timeline_blockers`에서 `segment_review_required`만 차단 목록에서 제외.
      플래그 데이터 자체는 지우지 않는다 — owner가 나중에 결과를 보고 판단한다
- [x] **Step 4: GREEN(3/3) + `verify_owner_path.py --auto-approve-segment-review`로
      owner 실제 영상 최종 확인 — **9단계 전부 통과**(ingest→...→capcut_draft_export
      실제 draft 폴더 생성까지). 커밋 3건**

과정에서 발견·수정한 파생 버그 2건은 `S-4`(findings backlog)에 기록했다:
CapCut 임시 폴더 정리 시 Windows 파일 잠금으로 성공한 job이 실패로 찍히던 문제
(`ignore_cleanup_errors=True`), 그리고 `verify_owner_path.py` 자체가
draft export 결과를 잘못된 API로 읽던 버그.

Commit: `feat: place confident recommendations automatically`,
`fix: let capcut draft export survive an unremovable temp directory`,
`fix: read capcut draft export results with the right getter`

---

## 계획서 완성도

Task 14개 중 상세 Step까지 완성된 것과 개요만 있는 것을 구분한다.
"계획서 완성"이라고 뭉뚱그리지 않기 위해 명시한다.

| Task | 상태 |
|---|---|
| 1–4, 6–11, 13–17, 19–21 | 상세 Step·Files·재사용 게이트 완성 |
| 5 | 간략하지만 실행 가능 |
| 12 | **완료** (2026-08-05, 커밋 `d503ce2`) |
| 11A | 상세 Step 완성. 승인된 **값**만 Task 10에서 들어온다 |
| 18 | 상세 Step 완성. Drive 동작 실측 완료 (2026-08-05) |

**모든 Task의 Step이 채워졌다.** Task 10과 12는 완료 상태다.

Task 11A는 처음에 "승인 전이라 못 쓴다"고 비워뒀으나 그 판단이 틀렸다.
승인된 값은 이 Task의 **입력**이지 Step 구조를 바꾸지 않는다. owner 지적으로 바로잡았다.

## 검증 이력

### 2026-08-05 리뷰·갭 검증·역방향 검증

**역방향 검증** — 계획서가 참조하는 파일 경로를 전수 대조했다. 오류 2건을 수정했다.

| 오류 | 수정 |
|---|---|
| `TimelineDock.test.tsx` | 실제 파일명은 `timeline-dock.test.tsx` |
| `packages/provider-interfaces/.../lm_studio.py` | 생략 경로를 정확한 경로로 교체 |

이전 역방향 검증에서 `EditorAssets.tsx` → `EditorAssetBrowser.tsx` 오류도 잡았다.
**세 번의 역방향 검증에서 매번 경로 오류가 나왔다.** 계획서 작성 시 파일명을 기억으로 쓰지 않는다.

**갭 검증** — backlog 항목이 Task로 이어지는지 대조했다. **중대한 누락 2건을 찾았다.**

| 누락 | 조치 |
|---|---|
| `D-2` 미디어 분석 worker가 "계획에 넣지 않은 것"에 있었다. **owner가 가장 강조한 요구**인데 빠졌다 | Slice 7 Task 19로 편입 |
| `A-1` 의미 검색이 어느 Task에도 없었다. 근거 등급이 `코드`라 동작 확인이 필요한데 확인 계획이 없었다 | Task 20 신설 |
| `S-2` 자동 배치 정책에 Task가 없었다. owner가 "완전 자동 배치"를 결정했는데 설정하는 작업이 없었다 | Task 21 신설 |

`D-2` 누락이 가장 심각했다. owner의 핵심 가치("B-roll을 녹화해 두면 자동 분류되고
의미로 검색된다")가 계획서에서 제외 항목으로 밀려 있었다.
Task 13이 여는 컨테이너→호스트 경로를 재사용하면 되는데도 "함께 해결될 수 있다"는
모호한 문장으로만 남겨뒀다.

**리뷰** — 순서와 의존성을 점검했다.

- Task 15(자산 정보 저장)가 Task 3(썸네일), Task 17(세로), Task 19(분석)의 선행이다
- Task 13(호스트 LM Studio 경로)이 Task 19(vision 분석)의 선행이다
- Task 11(색상 토큰)이 Task 11A(디자인 반영)의 선행이며 Task 10 승인과 무관하게 착수 가능하다
- Task 1(provider 활성화)이 Task 2(기준선)의 선행이다. 꺼진 채로 기준선을 잡으면 의미가 없다

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
| ~~`D-2` 미디어 분석 worker~~ | **Slice 7 Task 19로 편입 (2026-08-05 갭 검증).** owner 핵심 요구이므로 제외 대상이 아니다 |
| `S-3` 대본 생성 | `implementation-plan` §23.3이 제품 범위 밖으로 차단 중. 조항 개정이 선행 |
| TTS 활성화 | owner가 2026-08-05에 보류 결정. 음성 인식 확인 후 재논의 |

`D-1` 팔레트와 `F-6` 하드코딩은 Slice 4로, `D-4` Hermes는 Slice 5로 각각 편입했다.
둘 다 owner 요구가 명확해졌으므로 "넣지 않은 것"에서 계획 본문으로 옮겼다.

## 실행 순서

Slice 번호가 아니라 **의존성과 가치 순서**로 진행한다.

| 순서 | Task | 이유 |
|---|---|---|
| 1 | **Task 1** provider 활성화 | 이게 꺼져 있으면 이후 모든 작업이 가짜 데이터 위에 선다 |
| 2 | **Task 15** 반입 metadata 저장 | Task 3·17·19의 공통 선행. 길이·크기·방향을 여기서 확보 |
| 3 | **Task 3** 썸네일 연결 | 체감 개선 최대. Task 15가 선행 |
| 4 | **Task 4** 편집 데드엔드 | 독립적이고 짧다. 사용 흐름을 막는 결함 |
| 5 | **Task 2** 런타임 기준선 | Task 1 이후에 해야 의미가 있다. backlog 등급을 실측으로 갱신 |
| 6 | **Task 11** 색상 토큰 일원화 | 독립적. 이게 돼야 승인된 디자인이 화면에 반영된다 |
| 7 | **Task 11A** 승인 디자인 적용 | Task 11 선행 |
| 8 | **Task 13** 로컬 LLM 유진 | 호스트 LM Studio 경로를 연다. Task 19의 선행 |
| 9 | **Task 19** 미디어 분석 worker | owner 핵심 가치. Task 13이 연 경로를 재사용 |
| 10 | **Task 20** 의미 검색 확인 | Task 19가 재료를 만든 뒤 |
| 11 | **Task 16, 18** 업로드·Drive 반입 | Task 15 선행. 평소 자산 축적 경로 |
| 12 | **Task 17** 숏폼 세로 편집 | Task 15의 `orientation` 선행 |
| 13 | **Task 21** 자동 배치 정책 | Task 19·20의 추천 품질이 확인된 뒤 |
| 14 | **Task 6–9** 잔여 결함 | 독립적. 사이사이 처리 가능 |
| 15 | **Task 14** provider 어댑터 | 로컬이 안정된 뒤 |
| 16 | **Task 5** 문서 정합 | 마지막. 실측 결과를 문서에 반영 |

Task 6–9는 서로 독립적이라 위 순서 사이 어디에나 끼울 수 있다.
Task 10과 12는 이미 완료다.

## 완료 기준

이 계획은 아래가 모두 성립할 때 닫는다.

1. owner의 실제 나레이션에서 실제 전사가 나온다
2. `verify_owner_path.py`가 각 단계의 실제 동작을 기록하고 backlog 등급이 갱신됐다
3. 편집기에서 영상을 썸네일로 보고 고를 수 있다
4. 초안 없는 프로젝트에서도 편집 진입이 막히지 않는다
5. `implementation-plan` §23이 실측 상태와 일치한다
6. 승인된 화이트·오렌지 방향이 화면에 반영되고 하드코딩 색상이 변수로 일원화됐다
7. 유진이 로컬 LLM으로 실제 대화하고, provider 어댑터로 전환이 가능하다
8. 촬영한 B-roll이 자동 분류되고, 대본 문장으로 의미 검색이 된다
9. Drive 폴더에 올린 영상이 자동 반입되고, 세로 영상으로 숏폼을 만들 수 있다
10. 전체 Python·frontend 회귀와 production build가 통과한다

**최종 인수 기준:** owner가 설명 없이 대시보드를 열어 대본을 넣고,
자동 초안을 받고, 썸네일로 자산을 고르고, 유진과 대화하며 고친 뒤 내보낼 수 있다.
이 흐름 중 어디서도 막히지 않아야 한다.

사람의 시각·청취·취향 판정, 저작권·게시 승인, CapCut Desktop 실제 편집·export는
이 계획의 완료 기준에 포함하지 않는다. 계속 별도 human gate다.
