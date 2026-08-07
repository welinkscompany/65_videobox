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

**owner 결정 (2026-08-07): Voicebox(`github.com/jamiepine/voicebox`)로 간다.**
보류를 풀었다. 상세 조사와 반입 단위는 **Task 25**에 적었다. 요약하면, Voicebox는
엔진 7개를 감싼 로컬 데스크톱 스튜디오이고 **한국어는 그중 Chatterbox Multilingual이
담당**한다. VideoBox는 파이프라인에서 프로그램으로 호출해야 하므로 GUI 앱을 상시
띄우는 대신 **엔진(`chatterbox-tts`, MIT, pip)을 직접 반입**한다. 위 표의 `local_xtts`
자리를 이것이 대체한다.

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

### Task 5: 계획서를 실측 상태에 맞추기 — **완료 (2026-08-06)**

Task 1·2의 실측 결과로 어긋난 문서를 갱신한다. 최소 대상은 아래다.

- `implementation-plan.ko.md` §23: gateway·signer·OAuth·편집 mutation의 실제 상태
- `development-status`: 새 authoritative 항목 추가
- backlog 문서: 근거 등급 최종 갱신

코드 동작을 바꾸지 않으므로 §10.2.1에 따라 TDD를 강제하지 않는다.

- [x] **Step 1: Task 1·2·13·14 결과와 §23 각 항목 대조** — §23.3B가 Task 13·14 완료 이후에도
      `[ ] 미완료`로 멈춰 있는 것과, `CLAUDE.md`가 이미 삭제된 `AGENTS.md`를 "하위 호환
      포인터로 남아있다"고 잘못 설명하는 것을 찾았다
- [x] **Step 2: 갱신 및 커밋** — §23.3B를 `[~] 진행 중`으로 바꾸고 실제로 된 것/안 된 것을
      기록했다. `CLAUDE.md`의 stale 문구를 고쳤다. `development-status-2026-06-29.ko.md`에는
      322번째 turn별 closeout을 새로 추가하는 대신(그 관례는 이미 `§10.8`/`§10.9`에서
      퇴역시켰다) authoritative 기록이 이제 이 계획서와 backlog 문서에 있다는 안내를
      상단에 남겼다

Commit: `docs: reconcile the plan with measured runtime state`

---

## Slice 3 — 잔여 결함

Task 2 실측이 세부를 조정할 수 있으나, 각 항목의 결함 자체는 이미 화면에서 직접 관측했으므로
Step을 지금 확정한다. 실측으로 전제가 바뀌면 갱신 규칙에 따라 해당 Task를 수정한다.

### Task 6: 미리보기 자동 갱신 (F-4) — **완료 (2026-08-06)**

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

- [x] **Step 1: 실패 테스트** — 편집 mutation 성공 뒤 새 revision으로 미리보기 생성이
      자동 호출되는지, 자동 갱신이 실패해도 수동 버튼이 계속 활성 상태인지 (2개 신설).
      `stale` 내부 용어 노출은 실측해보니 **이미 해소돼 있었다** —
      `exact-preview-state.ts`의 `kind: "stale"`는 이미 창작자 언어 문구
      ("이전 편집본 미리보기는 재생하지 않아요")로만 표시되고 있었다
- [x] **Step 2: RED 확인** — `git stash`로 구현을 잠시 되돌려 새 테스트 2개가
      실제로 실패하는 것을 확인한 뒤 복원했다
- [x] **Step 3: 구현** — 모든 편집(trim/reorder/자막/B-roll·BGM·SFX 적용/오버레이 등)이
      이미 거쳐가는 단일 통로 `commitTimelineMutation`에 한 단계만 추가했다:
      mutation 성공 후 방금 받아온 revision으로 `api.startExactPreview`를 호출하고
      `refreshToken`을 올려, 기존 manifest 재조회 effect와 기존 pending/running
      폴링 루프(둘 다 이미 있던 코드)가 자동으로 이어받게 했다. 새 상태 머신은
      만들지 않았다 — 재사용 게이트 그대로. 자동 갱신 실패는 조용히 무시하고
      기존 수동 버튼(`미리보기 새로 만들기`)이 폴백으로 계속 활성 상태로 남는다
- [x] **Step 4: GREEN(121/121, 프론트 전체 764/764, tsc clean) + 커밋** —
      브라우저 실측은 못 했다. 지금 실행 중인 앱에 실제 세그먼트가 있는 편집
      세션을 가진 프로젝트가 없어서(둘 다 초안 없음) 실제 mutation을 걸어볼 수
      없었다 — 대신 실제(mock 아닌) `EditorWorkbenchRoute` 컴포넌트를 그대로
      렌더하는 유닛 테스트로 대체했다

Commit: `feat: refresh the preview after an edit`

### Task 7: 타임라인 클립 이름을 사람이 읽는 말로 (F-3) — **완료 (2026-08-06)**

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

- [x] **Step 1: 실패 테스트** — 클립 접근성 이름에 내부 ID가 없고
      트랙 이름과 (트랙 내) 순번·시작 시각으로 사람이 읽을 수 있는지 (3개 신설)
- [x] **Step 2: RED 확인**

Run: `npm --prefix apps/web test -- src/features/editor/timeline`

- [x] **Step 3: 구현** — `formatClipDisplayName(lane, ordinalInLane, startSec)` 포맷터를
      추가했다(`B-roll 2번째 장면, 3초부터`). 선택·조작 로직(`data-clip-id`, `onClick`,
      trim/reorder/placement 버튼 라벨)은 전부 `rect.clipId`를 그대로 쓴다 — 컨테이너
      aria-label, 선택 버튼 aria-label, 버튼 표시 텍스트 **셋만** 바꿨다.
      **파급 범위가 예상보다 컸다** — `AppRouter.test.tsx`, `editor-workbench.test.tsx`,
      `editor-workbench-route.test.tsx` 3개 파일, 55곳 이상이 `"${clipId} 클립 선택"`을
      accessible name으로 직접 하드코딩하고 있었다. 각 fixture의 lane·순번·startSec을
      일일이 계산해 문자열을 갱신하는 대신, 각 파일에 `clipSelectionButton(clipId)`/
      `findClipSelectionButton(clipId)` 로컬 헬퍼를 추가해 `data-clip-id`/
      `data-native-control` 속성으로 버튼을 찾게 바꿨다 — 표시 문구가 나중에 또
      바뀌어도 이 테스트들이 다시 깨지지 않는다
- [x] **Step 4: GREEN(761/761, tsc clean) + 커밋** — 실제 프로젝트로 브라우저 확인은
      실패했다: `b-roll-smoke-test` 등 지금 접근 가능한 프로젝트 중 실제 편집 세션
      (timeline)이 있는 게 없어서 채워진 타임라인을 렌더해볼 수 없었다. 대신 유닛
      테스트가 실제(mock 아닌) `TimelineDock` 컴포넌트를 그대로 렌더해 DOM의
      aria-label·텍스트를 직접 검증하는 것으로 대체했다

Commit: `feat: name timeline clips in plain language`

### Task 8: 프로젝트 삭제 경로 (F-5) — **완료 (2026-08-06). 보관 + 완전 삭제(이중 확인) 모두 구현·검증됨**

owner 결정(2026-08-06): "정말 지울지 알림은 있어야되. 이중알림으로 해줘" — 완전 삭제를
이중 확인(3단계: 완전 삭제 → 1차 확인 → 영구 삭제) UI로 구현. 서버도 `?confirm=true`를
항상 요구해 UI 우회 시도를 한 번 더 막는다.

- `LocalProjectStore`/`PostgresProjectStore.delete_project_permanently`: 프로젝트 디렉터리
  (Postgres는 공유 `projects` 행도 함께) 제거. 실제 Postgres 16 컨테이너로 라이브 검증함.
- `DELETE /api/projects/{id}?confirm=true` — `confirm` 없으면 400.
- `ProductShell.tsx`의 3단계 확인 UI, `AppRouter.tsx`의 모든 진입점에 핸들러 연결.
- 브라우저 실런타임으로 실제 프로젝트 생성 → 3단계 클릭 → API 목록에서 실제 사라짐까지 확인함
  (테스트 통과만이 아니라 살아있는 API·UI로 재검증).
- 이 검증 과정에서 발견한 별개 이슈: 세션 중 떠 있던 API 서버 프로세스가 시스템 python으로
  기동돼 있어 새 DELETE 라우트가 없는 옛 코드를 서빙 중이었다(405). `.venv` 프로세스로
  교체 재기동 후 정상 동작 확인 — 저장소 코드 결함이 아니라 뜬 프로세스 문제였다.

Commit: `fix: default unspecified render orientation to landscape (F-9)`,
`feat: add permanent project deletion with double confirmation (Task 8)`

<details><summary>이전 경과 기록 (2026-08-06 이전, 보관 API만 있던 시점)</summary>

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

**실측으로 알게 된 사실:** `ProjectStatus.ARCHIVED`는 `domain-models/projects.py`에 이미
있었고 `projects` 테이블의 `status` 컬럼도 이미 그 값을 저장할 수 있었다. 다만 그 상태로
바꾸는 코드도, 목록에서 걸러내는 코드도 어디에도 없었다 — 이번 세션에서 반복해서 나온
"설계는 있는데 연결이 안 됨" 패턴과 똑같다.

- [x] **Step 1: 실패 테스트** — `tests/test_project_archive.py`: 보관 처리 후 목록에서
      빠지는지, `include_archived`로 보면 다시 보이는지, 데이터(DB 파일)가 그대로 남는지,
      되돌리기가 되는지, 존재하지 않는 프로젝트 요청이 안전하게 실패하는지, 이미 보관된
      프로젝트를 다시 보관해도 안전한지 — store 레벨 6개 + 실제 `create_app()` TestClient로
      API 왕복 2개 (8개)
- [x] **Step 2: RED 확인** — `AttributeError: 'LocalProjectStore' object has no attribute
      'archive_project'`
- [x] **Step 3: 구현** — `archive_project`/`restore_project`(상태 컬럼만 바꾼다.
      프로젝트 폴더·DB는 절대 건드리지 않는다), `list_projects(include_archived=False)`.
      `POST /api/projects/{id}/archive`·`.../restore`, `GET /api/projects?include_archived=`.
      존재하지 않는 프로젝트는 `get_project`를 거치지 않고 DB 파일 존재 여부를 직접 확인해
      `KeyError`(→404)로 안전하게 실패한다 — `get_project`로 확인하면 진짜 없는 프로젝트일 때
      `sqlite3.OperationalError`가 그대로 새 나가는 것을 발견해 이 두 메서드에서만 고쳤다
- [x] **Step 4: GREEN(8/8, 전체 회귀 3043 passed·0 failed) + 커밋** — **완전 삭제는
      이번 범위에 넣지 않았다.** 계획서 권장(`§10.12.3` preserve-evidence 취지)대로
      보관만 구현했다 — 되돌릴 수 있고 무인 세션에서도 안전한 기본값이다.
      `api.ts`에 `archiveProject`/`restoreProject`를 추가했지만 **UI에는 아직 연결하지
      않았다** — `ProductShell`(프로젝트 전환 UI)이 `AppRouter.tsx`의 10곳 이상에서
      생성되는데, 여기에 새 콜백을 다 연결하고 카탈로그 새로고침까지 잇는 건 이 Task와
      분리해서 별도로 할 만큼 크고 기계적인 작업이라 판단해 미뤘다

Commit: `feat: let the owner put a project away`

**후속 (2026-08-06): 화면 진입점 연결 완료.** `ProductShell`에 `onArchiveProject` prop과
"보관"/"보관 확인" 2단계 인라인 컨트롤을 추가했다(native `confirm()` 없이 두 번째 클릭으로
확인). `AppRouter.tsx`에 `archiveProjectAndRefresh(router, projectId)` 헬퍼 하나를 두고
`WorkspacePage`의 9곳, `SettingsRoutePage`의 1곳 — 총 10개 `ProductShell` 호출부 전부에
기계적으로 연결했다. 실제 `AppRouter`를 렌더하는 통합 테스트로 확인 절차·API 호출·목록에서
사라짐을 검증했다(프론트 전체 765/765, tsc clean). **아직 없는 것:** 복원 화면(보관된
프로젝트가 어디에도 나열되지 않아 되돌릴 곳이 없다), 완전 삭제(범위 밖 유지).

Commit: `feat: wire project archiving into the project switcher`

**완전 삭제(2026-08-06 최종): 위 상단 요약 참고.** 복원 화면은 여전히 없음(보관된
프로젝트를 되돌릴 UI 진입점 부재) — owner가 별도로 요청하면 후속 Task로 다룬다.

</details>

### Task 9: 중복 진입점 정리 (F-7) — **완료 (2026-08-06)**

`새 영상 만들기`가 사이드바(`ProductShell.tsx:41`), 헤더 버튼(`ProductShell.tsx:56`),
그리고 홈 화면 카드에 동시에 있다. 같은 동작이 세 번 보인다.

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx`
- Modify: `apps/web/src/app/ProductShell.test.tsx`

- [x] **Step 1: 실패 테스트** — 홈이 아닌 화면(`/media`)에서 `새 영상 만들기` 버튼이
      정확히 1개만 있는지
- [x] **Step 2: RED 확인** — 2개 발견(사이드바 + 헤더)
- [x] **Step 3: 구현** — 헤더의 `새 영상 만들기` 버튼을 제거했다. 사이드바 항목이
      어느 화면에서나 보이는 유일한 주 진입점으로 남는다. 홈 화면 자체의
      맥락 문구 + 버튼("다음 장면을 이어서 만들어 볼까요?")은 계획서가 명시한
      예외라 그대로 유지했다
- [x] **Step 4: GREEN(8/8, 프론트 전체 762/762, tsc clean) + 브라우저 실측 + 커밋** —
      실제 실행 중인 앱에서 `document.querySelectorAll('button')`으로 직접 확인:
      `/media` 화면에 `새 영상 만들기` 버튼이 정확히 1개(사이드바)만 남았다

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

### Task 13: 로컬 LLM으로 유진 대화 실제 동작 — **완료 (화면 연결까지, 2026-08-06)**

**실측으로 계획서 재사용 게이트를 두 군데 정정했다.**

| 후보 | 원래 분류 | 정정 | 근거 |
|---|---|---|---|
| `lm_studio.py`가 대화 클라이언트 | `adopt as-is` | **오류.** `lm_studio.py`엔 vision·embedding provider만 있고 chat 클라이언트가 없다 | 실제 채택 대상은 `provider-interfaces/local_qwen.py`의 `LocalQwenHTTPTransport`/`LocalQwenStructuredProvider` — 이미 `services/api/orchestration.py`를 통해 `create_app`에 production 연결돼 있었다 |
| `HermesRunService`/`AgentGatewayClient`가 대화 경로 | (암묵) | **실제 대화 UI는 이 경로에 물려 있지만, `videobox-agent-gateway` 서비스 자체가 배포돼 있지 않아 항상 "유진의 답을 받지 못했어요"로 종료된다** | `agent_gateway_client.py`가 `base_url`을 `http://videobox-agent-gateway:8081`로 엄격 고정하고, capability token·reservation·ledger 계약 전체가 실제 원격 게이트웨이를 전제로 설계돼 있다 |

**이번에 한 일 — 로컬 대화 능력 자체 (검증 완료):**

- [x] **Step 1: 실패 테스트** — `tests/test_yujin_local_conversation.py`: 정책 위반 요청 10종이
      모델을 부르지 않고 `blocked`로 끝나는지, 일반 대화는 로컬 runtime을 통해
      실제 응답을 받는지, 빈 입력·빈 모델 응답을 거부하는지 (14개 테스트)
- [x] **Step 2: RED 확인** — `ModuleNotFoundError`
- [x] **Step 3: 구현** — `packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py`
      신설. `LLMTaskType.YUJIN_CONVERSATION` 추가. 정책 위반 의도는 모델 호출 전
      결정적 패턴 매칭으로 차단한다 — 이 경계가 모델의 순응 여부에 의존하면 안 되기 때문이다.
      일반 대화는 기존에 이미 프로덕션에 연결돼 있던 `LocalOnlyStructuredRuntime`/
      `LocalQwenStructuredProvider`를 그대로 재사용한다(JSON Schema 응답 `{"reply": "..."}`).
      capability token·publish 권한을 전혀 발급하지 않으므로 모델 출력은 순수 untrusted
      텍스트다 — 편집 mutation 경로에 어떤 식으로도 닿지 않는다
- [x] **Step 4: GREEN(14/14) + 실제 대화 확인** —
      `tests/test_yujin_local_conversation_live_smoke.py`(`@pytest.mark.live_lmstudio`,
      `VIDEOBOX_RUN_YUJIN_LOCAL_CONVERSATION_SMOKE=1`로만 실행)가 실제 실행 중인
      LM Studio(`qwen/qwen3.6-35b-a3b`)에 실제로 요청해 실 응답을 받는 것과,
      정책 위반 요청이 모델에 닿지 않고 차단되는 것을 둘 다 확인했다. 2/2 통과

**아직 안 한 일 — 명시적으로 범위 밖으로 남긴다:**

1. **UI 배선.** 편집기의 유진 채팅 UI(`EditorWorkbenchRoute.tsx`)는 이미 완성돼 있지만
   `HermesRunService`→`AgentGatewayClient`→(배포 안 된) `videobox-agent-gateway` 경로에만
   물려 있다. 이 서비스를 로컬 응답으로 실제로 채우려면 `HermesRunService`가 기대하는
   capability token·reservation 계약(서명된 토큰 형식, 만료 검증, ledger)까지 로컬 경로가
   흉내 내야 한다. 이건 §23.2.6이 아직 배포하지 않은 **capability signer의 보안 경계와
   직접 맞닿는 부분**이라, 무인 세션 도중 서둘러 만들면 안전 경계를 잘못 재구현할 위험이
   실제 이득보다 크다고 판단해 유보했다. 다음 세션에서 owner와 함께 다음 중 하나를 정해야 한다.
   - (a) `HermesRunService`가 gateway 없을 때 이 로컬 서비스로 폴백하도록 확장
   - (b) 로컬 전용 새 엔드포인트를 만들고 프론트를 그쪽으로 돌림
2. **컨테이너→호스트 네트워크 경로.** `compose.yaml`에 `extra_hosts`/`host.docker.internal`
   매핑이 없다. 다만 owner의 실제 검증 환경(`scripts/run_api.py` 호스트 네이티브 dev 서버)은
   컨테이너를 거치지 않으므로 `127.0.0.1:1234`가 이미 바로 LM Studio에 닿는다 — 이번 실측도
   그 경로로 했다. 컨테이너 스택 지원은 별도 §10.14 기록과 함께 후속 작업으로 남긴다.
3. `LocalOpenAICompatibleRuntimeConfig.model_name` 기본값이 `qwen3-35b`인데 실제 로드된
   모델 id는 `qwen/qwen3.6-35b-a3b`다. live smoke 테스트는 `LMStudioHTTPTransport.
   capability_profile()`로 로드된 모델을 실측해 우회했지만, production 기본값은
   여전히 불일치한다. 환경변수로 덮어쓰거나 기본값을 갱신해야 한다.

Commit: `feat: answer Yujin's conversation with the local model`

### Task 14: provider 어댑터와 전환 — **완료 (2026-08-06)**

- [x] **Step 1: 실패 테스트** — `tests/test_yujin_provider_adapter.py`: provider를 바꾸면
      다음 응답이 실제로 그 provider로 가는지, 전환 이력이 매번 기록되는지, 미설정
      provider(`gpt-5.4`/`gpt-5.4-mini`) 선택은 로컬로 조용히 안 넘어가고 `blocked`로
      끝나는지, 알 수 없는 provider 이름은 거부되는지 (9개)
- [x] **Step 2: RED 확인** — 모듈을 임시로 옮겨 `ModuleNotFoundError`를 확인한 뒤 복원했다
- [x] **Step 3: 구현** — `YujinProviderAdapter`가 `local`/`gpt-5.4`/`gpt-5.4-mini`를
      같은 인터페이스(`reply()`) 뒤에 둔다. `local`은 Task 13의
      `YujinLocalConversationService`를 그대로 채택한다. GPT 두 provider는
      **의도적으로 항상 `blocked`다** — §23.1 egress allowlist gate와 Hermes OAuth가
      아직 없어서 실제로 나갈 수 있는 외부 HTTP 클라이언트 자체가 없다. "나중에 채울
      플레이스홀더"가 아니라, 그 전제조건이 열리기 전에는 구조적으로 호출할 수 없게
      만든 것이다. 전환(`switch_provider`)은 항상 명시적 호출로만 일어나고 매번
      `switch_history`에 남는다 — §23.3A.3 "조용히 대체하지 않는다"
- [x] **Step 4: GREEN(9/9, 전체 회귀 통과) + 실제 확인 + 커밋** — 실제 LM Studio로
      구성한 `YujinLocalConversationService`를 어댑터에 연결해 확인했다: `local`에서
      실제 응답을 받고, `gpt-5.4`로 전환하면 로컬 모델은 호출조차 되지 않고
      `blocked`(`external_provider_egress_not_configured`)로 끝나며, 다시 `local`로
      전환하면 실제 응답이 재개된다. 전환 이력도 정확히 기록됐다

**화면 연결 완료 (2026-08-06, 커밋 `f26d88bf5`).** owner가 방식 B(새 로컬 전용
엔드포인트 재사용)를 선택해, 기존에 만들어져 있었으나 프론트에 연결되지 않았던 동기
`POST .../director/conversations/{id}/messages`의 자유 대화 생성 로직을
`YujinLocalConversationService`로 교체하고 `EditorWorkbenchRoute.tsx`를 그 경로로
재배선했다. `HermesRunService`/`AgentGatewayClient`/capability-token 코드는 건드리지 않았다.

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

### Task 16: 자산 업로드 영역 — **완료 (2026-08-06)**

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

- [x] **Step 1: 실패 테스트** — `MediaWorkspacePage.test.tsx`에 3개 추가: 파일 여러 개를
      순차 업로드하고 목록이 새로고침되는지, 일부 실패를 원본 에러 노출 없이 창작자
      언어로 보여주는지, 업로드 중 다른 작업(input 포함)이 막히는지
- [x] **Step 2: RED 확인** — 라벨 `장면 영상 파일 추가`를 찾지 못해 3개 실패
- [x] **Step 3: 구현** — `api.uploadDraftBroll`를 그대로 재사용해 파일마다 순차 업로드하고,
      기존 `busyKey` 단일 in-flight 패턴에 편승시켰다. 성공/실패 개수를 창작자 언어로
      요약한다. 헤딩 문구는 `DraftGapMedia`의 `장면 영상 추가`와 **의도적으로 다르게**
      (`영상 올리기`) 지었다 — `AppRouter.test.tsx`가 그 정확한 문자열로 두 화면이
      다른 진입점임을 검증하고 있어서, 같은 문구를 쓰면 그 계약을 깨게 된다
- [x] **Step 4: GREEN(9/9) + 프론트 전체 회귀(758/758) + 브라우저 실측 + 커밋** —
      실제 실행 중인 앱의 `b-roll-smoke-test` 프로젝트 자산 화면에서
      `장면 영상 파일 추가` 파일 입력과 `영상 올리기` 섹션이 실제 렌더되는 것을 확인했다

Commit: `feat: add media from the asset screen`

### Task 17: 숏폼 편집 — 세로 캔버스로 기존 편집기 재사용 — **완료, F-9 owner 결정까지 반영 (2026-08-06)**

**실측으로 계획서 전제 자체가 틀렸다는 걸 알았다.** 이 Task는 "지금은 가로만 되니
세로를 추가해야 한다"는 전제였는데, 실제로 확인해보니 **정반대였다.**

`composition_plan.py:18-19`의 `DEFAULT_OUTPUT_WIDTH = 1080`, `DEFAULT_OUTPUT_HEIGHT = 1920`—
**기본값이 이미 세로다.** `build_timeline()`이 지금까지 `timeline["output"]`이나
`timeline["video_width"]`를 설정하는 코드가 **어디에도 없어서**, 모든 프로젝트가
암묵적으로 이 기본값(세로 1080×1920)으로 렌더돼 왔다. 실제로 확인했다 —
`artifacts/owner-sample-edit-20260803-r4/.../output.mp4`를 `ffprobe`로 열어보니
**진짜로 1080×1920이었다.** 롱폼 설명형 영상(가로가 정상이어야 할)도 지금까지
전부 세로로 렌더되고 있었다는 뜻이다.

이건 이번 세션이 만든 문제가 아니다 — `DEFAULT_OUTPUT_WIDTH/HEIGHT`는 내가 손대기 전부터
이 값이었다. 다만 지금까지 아무도 실측하지 않아 발견되지 않았을 뿐이다.
**owner 확인이 필요한 사항으로 별도 기록한다** (아래 "발견한 별도 사안" 참고).

**재사용 게이트 (§8.1) — 실측으로 재확인:**

| 후보 | 분류 | 실측 결과 |
|---|---|---|
| 기존 편집 작업판과 14개 조작 | `adopt as-is` | 변경 없음 |
| `composition_plan`의 canvas width/height | `partial port` | 이미 `output`/`video_width`/`video_height`를 읽는 코드가 있었다. **호출부가 값을 채워 넣기만 하면 됐다** |
| `ffmpeg_final_renderer`의 `force_original_aspect_ratio=increase,crop` | `adopt as-is` (확인) | 코드를 읽어 확인: `render_timeline_to_mp4`가 `composition_plan.width/height`로 렌더러의 `video_width/height`를 교체하고(737-744행), 그 값을 그대로 scale/crop 필터에 쓴다. **손대지 않아도 이미 세로 캔버스에 가로 소재를 crop으로 채운다** |
| `ass_subtitles.render_editing_session_ass` | `adopt as-is` (확인) | `video_width`/`video_height`를 그대로 받아 `PlayResX`/`PlayResY`와 퍼센트 기반 margin을 계산한다. **자막은 이미 세로 화면에 맞게 스케일된다** — 새로 만들 게 없었다 |
| 숏폼 전용 새 편집기 | `exclude` | owner 결정으로 범위 밖 (변경 없음) |

**Files (실제):**
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py` (`build_timeline`에 `orientation` 파라미터)
- Modify: `services/api/src/videobox_api/orchestration.py`, `routers/timeline.py`, `models.py` (API로 노출)
- Modify: `apps/web/src/api.ts` (타입만 — 아직 호출부 없음, 아래 참고)
- Create: `tests/test_vertical_composition.py`
- (계획에 있던 `preview-stage.tsx` 수정은 **불필요했다** — 아래 참고)

- [x] **Step 1: 실패 테스트** — 세로 출력 규격을 고르면 canvas가 세로가 되는지,
      가로 출력을 고르면 16:9가 되는지, 선택하지 않으면(기존 호출부와 동일) `output`
      키 자체가 안 생기는지(현재 상태를 고정하는 회귀 테스트), 잘못된 값은 거부되는지,
      가로 소재가 세로 캔버스에서 crop 분기를 타는지, 자막이 세로 PlayRes로 스케일되는지
      (6개 테스트)
- [x] **Step 2: RED 확인** — `build_timeline() got an unexpected keyword argument 'orientation'`
- [x] **Step 3: 구현** — `LocalPipelineRunner.build_timeline(orientation: str | None = None)` —
      `"landscape"` → `{width:1920,height:1080}`, `"vertical"` → `{width:1080,height:1920}`를
      `timeline_payload["output"]`에 채운다. `None`(기본값)이면 아무것도 안 채워서
      **기존 동작(암묵적 세로 기본값)을 그대로 유지한다** — 이 Task에서 그 기본값
      자체를 바꾸는 건 별도 owner 결정 사항이라고 판단했다. `ApiOrchestrator`/
      `BuildTimelineRequest`/`timeline.py` 라우터로 그대로 흘려보냈다
- [x] **Step 4: GREEN(6/6, `test_api.py`의 timeline 관련 52개 포함) + 코드 읽기로
      역방향 검증 + 커밋** — 실제 ffmpeg 렌더 재실행은 하지 않았다. 대신 (1) 내 유닛
      테스트가 진짜 `CompositionPlan.from_timeline`(mock 아님)을 직접 통과시켜
      치수가 맞는지 확인했고, (2) `ffmpeg_final_renderer.py`/`ass_subtitles.py`의
      다운스트림 코드를 직접 읽어 이미 `composition_plan.width/height`를 그대로
      쓰고 있음을 확인했다 — 이 두 파일은 이번에 전혀 수정하지 않았다.
      Task 21에서 이미 이 렌더 경로 전체가 실제 footage로 한 번 검증됐으므로,
      같은 코드 경로에 다른 치수를 흘려보내는 것 이상의 새로운 위험은 없다고 판단했다

**계획에 있던 프론트 변경이 필요 없었던 이유:** `preview-stage.tsx`는 `<video>` 엘리먼트를
고정 종횡비 없이 `width: min(100%, 35rem); max-height: 28rem`로만 감싼다
(`editor-workbench.css:22`). 브라우저가 영상 파일 자체의 실제 종횡비를 그대로 쓰므로
세로 영상도 이미 올바르게 표시된다 — 수정할 게 없었다.

**아직 없는 것:**

- 프론트엔드에 `buildTimeline`을 호출하는 곳 자체가 없다(서버가 초안 생성 흐름을
  자동으로 오케스트레이션하는 것으로 보인다). `orientation` 선택 UI를 실제로
  노출하려면 그 자동화 흐름을 먼저 파악해야 한다 — API 타입은 준비해 뒀지만
  사용자가 실제로 고를 수 있는 화면은 아직 없다
- `orientation="vertical"`로 실제 렌더를 한 번도 안 돌려봤다(코드 경로 재사용
  확인으로 대체했다는 판단을 위에 남겼다)

**발견한 별도 사안 — owner 확인 필요 (S-5로 백로그에 기록):**

지금까지 `orientation`을 명시하지 않은 모든 프로젝트(사실상 전부)가 세로 1080×1920으로
렌더돼 왔다. 롱폼 설명형 영상이 주 제품이라면 이건 아마 의도가 아닐 것이다.
이 Task는 "세로를 고를 수 있게" 만드는 것이 목적이라 이 기본값 자체를 바꾸지 않았다 —
바꾸려면 "명시 안 하면 무엇이 기본인가"라는 별도 결정이 필요하고, 과거 실제 렌더 결과물이
전부 세로였다는 사실 자체가 owner에게 먼저 확인받아야 할 사안이라고 판단했다.

Commit: `feat: let projects choose a vertical or landscape canvas`

**F-9 owner 결정 및 반영 (2026-08-06):** "가로로 기본값으로 해야지. 다른 일반 캡컷이나
프리미어 프로도 모두 기본이 가로야" — 명시 안 하면 **가로(1920×1080)**를 기본값으로
확정. `build_timeline`의 `resolved_orientation = orientation or "landscape"`로
`timeline["output"]`을 항상 명시적으로 채우도록 고쳐, `CompositionPlan`의 세로 기본
상수(`DEFAULT_OUTPUT_WIDTH/HEIGHT`)에 암묵적으로 기대는 경로 자체를 없앴다.
`test_vertical_composition.py`의 미지정-오리엔테이션 테스트를 GREEN으로 재작성해 확인.
`docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`의 S-5/F-9
항목도 이 결정으로 종결 처리했다.

Commit: `fix: default unspecified render orientation to landscape (F-9)`

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

### Task 18: 촬영본 반입 경로 — Drive 폴더 감시 — **핵심 로직 완료, 실제 이동은 보류 (2026-08-06)**

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

- [x] **Step 1: 실패 테스트** — `tests/test_media_inbox.py`: 감시 폴더의 동영상만 반입
      대상으로 잡는지, `desktop.ini`·숨김 파일/폴더·비동영상을 건너뛰는지,
      해시가 일치할 때만 원본을 옮기는지, 불일치·이동 실패 시 원본을 건드리지 않고
      실패로 남기는지, 아직 크기가 변하는 중인 파일(다운로드 중)을 건너뛰고 다음
      주기에 다시 보는지, 라이브러리에 같은 내용 파일이 이미 있으면 중복으로 처리하는지,
      한 파일이 실패해도 나머지를 계속 처리하는지 (9개 테스트)
- [x] **Step 2: RED 확인** — `ModuleNotFoundError: No module named 'videobox_core_engine.media_inbox'`

Run: `.venv\Scripts\python.exe -m pytest tests/test_media_inbox.py -q`

- [x] **Step 3: 구현** — `media_inbox.py` 신설: `scan_inbox_candidates`(재귀 스캔,
      `desktop.ini`·숨김 항목·비동영상 제외) → `is_file_settled`(두 번의 stat 크기
      비교로 다운로드 중 여부 판정 — Drive의 내부 placeholder 메커니즘에 의존하지
      않는 OS-이식적인 방법) → `run_inbox_cycle`(해시 검증 후 `shutil.move`,
      실패·해시불일치 시 원본 보존, 라이브러리 내 동일 해시는 중복 처리).
      **감시 경로는 Task 15의 프로젝트별 `register_broll_asset`이 아니라 별도의
      project-독립적 로컬 폴더(`resolve_media_inbox_library_root()`)로 옮긴다** —
      A-1이 이미 짚었듯 `MediaLibraryStore`/`ProjectAssetMaterializer`가
      "여러 프로젝트가 같은 B-roll을 공유"하는 구조이므로, 반입 시점에 특정
      project로 확정하지 않는 것이 그 구조와 맞다. `settings.py`에
      `resolve_media_inbox_watch_path()`(`VIDEOBOX_MEDIA_INBOX_WATCH_PATH`,
      기본값 실측된 실제 경로 `G:\내 드라이브\100_videobox`)와
      `resolve_media_inbox_library_root()` 추가
- [x] **Step 4: GREEN(9/9) + 실제 Drive 폴더로 확인** — `scan_inbox_candidates`를
      owner의 실제 `G:\내 드라이브\100_videobox`에 대해 읽기 전용으로 실행해
      정확히 9개 파일(최상위 8개 + `가로/FHD/` 1개)을 찾는 것을 확인했다 —
      이전 실측 인벤토리와 정확히 일치. **실제 이동은 이번 무인 세션에서
      실행하지 않았다** — owner의 실제 촬영 원본을 사람 확인 없이 옮기는 것은
      Drive 휴지통이라는 안전장치가 있어도 무인 상태에서 할 일이 아니라고 판단했다.
      owner가 있을 때 `run_inbox_cycle()`을 한 번 실제로 돌려 결과를 직접 확인하는
      절차가 남아 있다

**아직 없는 것 — 후속 결정 필요:**

- 주기적으로 도는 백그라운드 감시 루프(스케줄러/워커) 자체는 만들지 않았다.
  `run_inbox_cycle()`은 한 번 호출하면 한 번 훑는 함수이고, 반복 실행은
  API 라우터나 스크립트에서 아직 걸지 않았다
- 반입된 파일이 라이브러리 폴더에만 있고 어느 project의 자산 목록에도 아직
  나타나지 않는다 — Task 19/20이 여러 project가 공유하는 B-roll 구조를
  전제하므로, 라이브러리 → project 복사(materialize) 경로는 별도로 설계해야 한다

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

### Task 19: 미디어 분석 worker 연결 (D-2, A-1) — **활성화 완료 (2026-08-05)**

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

**실측으로 계획서 전제를 정정했다.** `packages/core-engine/src/videobox_core_engine/media_analysis.py`의
`MediaAnalysisService`는 이미 vision 분석 결과 저장·태그 4축·임베딩·재시작 후 영속까지
**전부 완성돼 있었고 이미 테스트도 있었다**(`tests/test_api_media_analysis.py`의
`test_explicit_local_profile_preflights_exact_loopback_and_wires_real_provider`,
`test_analysis_persists_selected_profile_scene_windows_and_embeddings_across_restart` 등).
`services/api/src/videobox_api/main.py:create_app`도 `enable_local_media_analysis=True`를
받으면 실제 LM Studio provider를 완전히 연결하는 코드까지 이미 있었다.
**막혀 있던 건 설계가 아니라 Task 1과 같은 종류의 활성화 누락이었다** —
`scripts/run_api.py`와 컨테이너 factory 어느 경로도 이 플래그를 켜지 않아
`_UnavailableMediaAnalysisService`가 항상 쓰였다.

- [x] **Step 1: 실패 테스트** — `tests/test_media_analysis_worker.py`: 환경변수 해석 함수 기본값·on 값,
      그리고 인자 없이 호출되는 factory 경로(컨테이너 패턴)가 플래그 on일 때 실제 worker를,
      off일 때 여전히 `_UnavailableMediaAnalysisService`를 쓰는지 (4개 테스트)
- [x] **Step 2: RED 확인** — `resolve_enable_local_media_analysis` 없어 import 실패,
      factory 경로 테스트는 `media_analysis_vision_provider`가 여전히 `None`이라 실패
- [x] **Step 3: 구현** — `settings.py`에 `resolve_enable_local_media_analysis()`
      (`VIDEOBOX_MEDIA_ANALYSIS_ENABLED`, Task 1과 같은 패턴) 추가.
      `create_app`의 `enable_local_media_analysis` 파라미터를 `bool | None = None`으로 바꿔
      명시적으로 안 넘기면 이 환경변수로 해석하게 했다 — `scripts/run_api.py`는 코드 변경 없이
      환경변수만 켜면 실제 worker를 쓴다. 태그·임베딩 저장 로직은 이미 있어 손대지 않았다
- [x] **Step 4: GREEN(16/16, 기존 `test_api_media_analysis.py` 포함) + 실제 LM Studio로 확인** —
      `create_app(enable_local_media_analysis=True)`를 실제 실행 중인 LM Studio에 대고 직접
      호출해 `media_analysis_vision_provider`가 진짜 `LMStudioVisionProvider`로 채워지는 것을
      확인했다(mock 아님, 실제 preflight 요청 3회 왕복)

**컨테이너 스택엔 아직 안 켰다.** `compose.yaml`에 이 플래그를 켜면 컨테이너가 시작 시점에
`127.0.0.1:1234`로 동기 preflight를 시도하는데, Task 13에서 이미 확인했듯 컨테이너→호스트
네트워크 경로가 아직 없어 **컨테이너 자체가 기동 실패한다.** 호스트 네이티브 dev 서버
(`scripts/run_api.py`, 이번 실측 경로)는 환경변수만 켜면 바로 동작한다.
컨테이너 지원은 Task 13의 네트워크 경로 후속 작업과 함께 처리한다.

Commit: `feat: turn on the local media analysis worker`

### Task 20: 의미 검색 실제 동작 확인 (A-1) — **완료 (2026-08-05)**

`A-1`은 근거 등급이 `코드`였다. 설계는 확인했으나 **동작하는 것을 본 적이 없었다.**

**실측 결과 — 진짜 빠진 연결 지점을 찾았다.** `media_ranking.rank_candidates`는
`asset["semantic_score"]`가 이미 채워져 있다고 가정하지만, 실제로 그 값을 채우는
코드가 **어디에도 없었다.** `store.find_local_media_embedding_matches`(코사인 유사도 랭킹)는
이미 구현·테스트까지 돼 있었는데(`tests/test_media_analysis_store.py`) `director_proposal_service.py`
어디서도 호출되지 않아, 지금까지 모든 B-roll 추천은 `semantic_similarity=0.0`으로 고정된 채
태그 일치(lexical fallback)로만 동작하고 있었다. `A-1`이 지적한 "설계는 있는데 본 적이 없다"가
정확히 이거였다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `media_ranking.rank_candidates` | `adopt as-is` | 점수 체계·가중치를 바꾸지 않는다 |
| `store.find_local_media_embedding_matches` | `adopt as-is` | 코사인 랭킹이 이미 있고 이미 테스트됐다. 새로 안 만든다 |
| `LMStudioEmbeddingProvider` | `adopt as-is` | Task 19가 이미 연결한 provider를 그대로 쓴다 |
| 새 검색 인덱스/랭킹 알고리즘 | `exclude` | 있는 조각을 잇기만 하면 된다 |

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/director_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `services/api/src/videobox_api/main.py`
- Create: `tests/test_media_semantic_search.py`

- [x] **Step 1: 실패 테스트** — `tests/test_media_semantic_search.py`: 대본 문장이 두 자산의
      태그와 전혀 겹치지 않아도, 저장된 임베딩이 더 가까운 자산이 상위에 오고
      `semantic_provenance`가 `asset_semantic_score`로 찍히는지. embedding provider가 없거나
      예외를 던지면 기존 lexical fallback으로 안전하게 내려가는지 (3개 테스트)
- [x] **Step 2: RED 확인** — `DirectorProposalService.__init__()`가 `embedding_provider`를
      모른다는 `TypeError`
- [x] **Step 3: 구현** — `DirectorProposalService`에 `embedding_provider`/`embedding_model_name`을
      주입받게 하고, 세그먼트마다 `_apply_semantic_scores()`로 대본 문장을 임베딩한 뒤
      `store.find_local_media_embedding_matches()`로 자산별 코사인 점수를 받아
      `semantic_score`로 주입한다. 임베딩·조회 어느 단계든 예외가 나면 기존 lexical
      fallback으로 조용히 내려간다 — 로컬 모델이 느리거나 꺼져 있다고 추천 생성 자체가
      막히면 안 되기 때문이다. `main.py`가 Task 19에서 만든
      `app.state.media_analysis_embedding_provider`/`media_analysis_profile`을
      그대로 라우터에 흘려보낸다
- [x] **Step 4: GREEN(3/3, 기존 director proposal 테스트 78/78 포함) + 실제 확인** —
      실제 LM Studio 임베딩 모델(`text-embedding-bge-m3`)로 두 개의 가짜 B-roll을 등록하고
      "스타벅스에서 아메리카노" 대본 문장으로 검색했다. 태그가 전혀 겹치지 않는데도
      카페 클립이 `semantic_similarity=0.666`, 바다/서핑 클립이 `0.365`로 정확히
      의미가 가까운 쪽이 이겼다 — 실제 모델로 처음 증명된 결과다

**"반복 감점" 항목은 이미 있다.** `_SCORE_NAMES`의 `repetition`은
`-float(asset.get("repetition_count") or 0)`으로 이미 감점 로직이 있으나, 호출부가
`repetition_count`를 채우는지는 이번 범위에서 확인하지 않았다 — 별도 확인이 필요하면
후속 Task로 남긴다.

Commit: `feat: find b-roll by meaning`

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

### 진행 상태 (2026-08-06 기준 — 계획서 Task 1~21 전부 완료)

**완료:** Task 1~21 전부.
Task 8(프로젝트 완전 삭제, 이중 확인)과 F-9(렌더 기본 방향 가로)는 같은 세션에서 owner 결정을
받아 닫았다. Task 13(로컬 LLM 유진 대화)·Task 14(provider 어댑터)의 화면 연결은 owner가
방식 B(새 로컬 전용 엔드포인트 재사용 — 실제로는 이미 만들어져 있었으나 프론트에 연결되지
않았던 동기 `POST .../director/conversations/{id}/messages`를 재사용)를 선택해 커밋
`f26d88bf5`로 닫았다. `HermesRunService`/`AgentGatewayClient`/capability-token 코드는
건드리지 않았다.

Task 18(구글 드라이브 반입)도 완료했다. 감시·해시검증·이동 로직은 이미 있었고,
2026-08-06에 owner가 지켜보는 중에 실제 Drive 폴더(`G:\내 드라이브\100_videobox`)에서
첫 실제 이동을 실행했다(커밋 `295ebe721`, `scripts/run_media_inbox_cycle.py` 신설,
영상 9개 전부 해시 검증까지 통과해 이동, 중복·스킵·실패 0건). 이어서 반복 워처 루프와
라이브러리→project 복사 경로도 마저 구현했다: `run_inbox_watcher_loop()`가
`VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED=1`일 때 앱 시작 시 백그라운드 스레드로 돈다(기본은
꺼짐 — 감시 경로가 실제 owner Drive 폴더라 opt-in 없이 테스트가 건드리면 안 된다).
`import_media_inbox_asset_to_project()` + `POST /api/projects/{id}/media-inbox/import`,
`GET /api/media-inbox/assets`로 라이브러리 파일을 프로젝트 자산(raw_video)으로 복사할 수
있다. 프론트 UI(라이브러리 파일을 고르는 화면)는 아직 없다 — 백엔드 API까지만 이번
범위다.

**검증.** 코드리뷰에서 실제 결함 1건을 잡았다 — `filename`에 경로 탐색(`../`) 방어가
없어 library_root 밖 임의 파일을 프로젝트로 복사할 수 있었다. 파일명에 구분자가 오면
거부하도록 고치고 회귀 테스트를 추가했다(라이브러리는 항상 flat이라 정당한 파일명에
구분자가 올 일이 없다). 실제 dev 서버로 역방향 검증도 했다 — 미리보기 도구가 worktree가
아니라 main 브랜치 경로에서 서버를 띄우는 걸 발견해(구버전 코드가 서빙되고 있었다)
`scripts/run_api.py`를 worktree에서 직접 띄워 재확인: `GET /api/media-inbox/assets`가
이전에 이동시킨 실제 파일 9개를 정확히 나열했고, 실제 프로젝트를 만들어
`POST .../media-inbox/import`로 실제 파일을 복사한 뒤 디스크에서 확인, traversal 거부까지
전부 실제 서버로 확인했다. 백엔드 전체 회귀 3076 passed, 52 skipped, 0 failed(수정 전
1차 실행에서 lifespan 테스트 3건이 `app.state`를 SimpleNamespace로 모킹하는 곳에서
`AttributeError`로 깨진 걸 잡아 `getattr` 기본값 패턴으로 고쳤다).

**owner 결정으로 닫은 것 (2026-08-06):**

- 컨테이너→호스트 LM Studio 네트워크 경로 — owner가 옵션 2(분석 worker는 계속
  호스트 네이티브로만 실행, 컨테이너→호스트 경계는 열지 않음)를 선택해 코드 변경 없이
  닫았다. `architecture-plan.ko.md` §11의 "GPU 의존 로컬 모델은 컨테이너화하지 말라"
  권고와 일치한다. 컨테이너 배포/패키징이 실제로 필요해지면 그때 재논의한다
- F-7(중복 액션 노출) — 재확인해보니 이전 세션에서 이미 해결·테스트로 고정돼 있었다.
  홈 화면 밖은 진입점 1개, 홈 화면은 의도적 "action-only" 설계. 추가 변경 없음
- `LocalOpenAICompatibleRuntimeConfig.model_name` 기본값 불일치는 커밋 `a3a4c201f`로
  해결했다 — `resolve_local_runtime_config()`를 추가해 `VIDEOBOX_LOCAL_MODEL_NAME`
  환경변수로 오버라이드 가능하게 하고 `compose.yaml`에도 통과시켰다

**남은 것:** 계획서(Task 1~21) 자체에는 더 없다. 라이브러리 파일을 프로젝트에
가져오는 프론트 UI(지금은 API만 있다)가 자연스러운 다음 후보다. 그 외 근거는 이 문서와
`docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`에 근거와 함께
기록돼 있다. 계획서 자체의 실행 순서(Task 1~21)는 전부 완료했다.

**2026-08-06 코드리뷰로 고치고 넘어간 것 (Task 13/20 관련):**

- `yujin_local_conversation.py`의 정책 차단 정규식이 한국어 표현에만 대응했다.
  영어로 같은 요청("delete the database", "write me a script")을 하면 차단 없이
  모델까지 그대로 갔다 — 실제 시스템 접근 권한은 애초에 이 경로에 전혀 없어서
  데이터가 위험했던 건 아니지만, 의도한 차단 동작 자체가 뚫려 있었다.
  영어 패턴을 추가하고 회귀 테스트 9건을 더했다(24/24 통과)
- `director_proposal_service.py`의 semantic scoring fail-open 경로가 예외를
  완전히 삼켜 로그가 전혀 안 남았다 — 임베딩 provider가 계속 죽어 있어도
  운영자가 알 방법이 없었다. `logging.warning(exc_info=True)`를 추가했다
- `contrast.test.ts`가 `borderStrong`/`accentBg`/`accentBorder`/`success`/
  `successBg` 값을 선언만 하고 실제 CSS 파일과 대조하지 않아, 이 다섯 토큰의
  드리프트를 못 잡는 상태였다 — 대조 assertion을 추가했다(이미 값은 정확했다)

Task 10과 12도 이미 완료다(위 목록에 포함).

### 진행 상태 (2026-08-07 갱신 — 코드 실측으로 재확인)

2026-08-07 세션에서 "계획서가 정말 다 구현됐는가"를 문서 표기가 아니라 **코드로 직접
대조**했다. 체크박스가 비어 있는 Task 4개(1·3·4·15)를 하나씩 확인한 결과, **체크만
누락됐을 뿐 구현은 되어 있었다.** 근거를 남긴다. 이 표가 완료 표기의 SSOT다.

| Task | 표기 상태 | 코드 실측 결과 | 근거 |
|---|---|---|---|
| 1 | 체크 없음 | **STT·CapCut 완료 / TTS만 열림** | `compose.yaml:57,74` 기본값 `1` |
| 3 | 체크 없음 | **완료** | `editorAssetProjection.ts:140`이 `api.assetThumbnailUrl` 호출 |
| 4 | 체크 없음 | **완료** | `AppRouter.tsx`가 `ProductShell`로 감쌈 |
| 15 | 체크 없음 | **완료** | `local_pipeline.py:515~535`가 길이·해상도·방향·오디오 저장 |
| 2·5~14·16~21 | 완료 표기 | **완료** | 각 Task 본문의 closeout 기록 |

**따라서 계획서 Task 1~21 중 미완은 정확히 하나다 — Task 1 Step 7 (TTS 엔진).**
이것도 누락이 아니라 owner가 2026-08-05에 "보류"로 직접 결정한 항목이다(엔진 선택과
그에 따른 다운로드·외부 전송이 owner 승인 사항이라서다). **owner 결정 전에는 착수하지
않는다.**

**2026-08-07에 한 일:** 라이브러리→project 가져오기 **프론트 UI를 만들었다**(커밋
`9c8c203c2`). 위 "남은 것"에서 다음 후보로 지목했던 화면이다. 실제 API 서버를 worktree에서
직접 띄워 브라우저로 역방향 검증까지 마쳤다(가져오기 클릭 → 201 → 목록 갱신 → 디스크 확인).

**다만 이 UI는 Task 22에서 정정이 필요하다.** 아래 참조.

---

## 2026-08-07 추가 계획 — 긴 촬영본을 B-roll로 쓰기 (Task 22~24)

**추가 이유.** owner의 실제 작업 방식이 2026-08-07에 처음 명확해졌다.

> 폰으로 찍어 Google Drive에 올리는 영상은 **그 자체가 B-roll**이다. 여러 채널의
> 유튜브 영상을 만들 때 가져다 쓴다. B-roll이니 **무음이 맞다**. 다만 10분짜리 산책
> 영상을 올리면 **10분을 다 쓰지 않으므로, 쓸 구간을 잘라내는 편집이 필요하다.**

계획서 Task 1~21은 이 작업 방식을 전제하지 않았다. Task 21은 "추천을 자동 적용할지"를
정한 것이지 "긴 영상 중 **어디를** 쓸지"는 다룬 적이 없다. 따라서 아래는 기존 Task의
미완이 아니라 **새로 추가되는 범위**다. 계획서 밖 작업을 계획서 없이 시작하지 않기 위해
정식 Task로 등록한다.

**owner 결정 (2026-08-07):** 구간은 **에이전트가 먼저 추천**한다. 사람이 손댈 때는
**편집 화면에서** 조절한다. 따라서 Task 23(추천)이 Task 24(수동 조절)보다 앞선다.

### Task 22: 라이브러리 가져오기를 B-roll로 정정 — **완료 (2026-08-07, 커밋 `82355e743`)**

`import_media_inbox_asset_to_project()`가 `AssetType.RAW_VIDEO`로 등록한다. owner
요구에 따르면 **B-roll이어야 한다.** 단순 분류 문제가 아니다 — B-roll로 등록돼야
분석이 걸려 태그와 장면 구간이 생기고, 그래야 Task 23의 재료가 만들어진다. 지금
경로로는 그 흐름을 아예 타지 못한다. 2026-08-07 프론트 UI도 이 위에 서 있다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `pipeline.register_broll_asset` | `adopt as-is` | 업로드 경로가 이미 쓰는 canonical 등록 경로. 분석 큐잉과 probe 메타데이터 저장이 딸려 온다 |
| 파일명 전용 API + traversal 방어 | `adopt as-is` | 절대경로를 브라우저에 노출하지 않는 기존 경계를 유지한다 |
| `broll-video/batch` 엔드포인트로 대체 | `exclude` | 클라이언트가 절대경로를 알아야 해서 위 경계가 깨진다 |
| 새 등록 경로 신설 | `exclude` | 기존 경로로 충분하다 |

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/media_inbox.py`
- Modify: `apps/web/src/features/media/MediaWorkspacePage.tsx`
- Modify: 해당 테스트

- [x] **Step 1: 실패 테스트** — 가져온 자산이 `broll_video`이고 분석이 큐잉되는지
- [x] **Step 2: RED 확인** — `'LocalPipelineRunner' object has no attribute 'register_asset'`
- [x] **Step 3: 구현** — `register_broll_asset` 경로로 교체. traversal 방어 유지.
      분석 큐잉은 b-roll batch 엔드포인트와 동일한 패턴으로 라우터에 붙였고,
      분석이 실패해도 가져오기 자체는 남는다
- [x] **Step 4: 프론트 정정** — 가져온 영상이 "준비한 자산"과 "분석 상태"에 실제로
      나타나므로, 임시로 넣었던 "원본 영상 N개" 카운터는 제거했다
- [x] **Step 5: GREEN + 실제 서버 역방향 검증 + 커밋** — worktree에서 직접 띄운 실제
      API로 확인(201 + `broll_video` + 분석 큐잉 + b-roll 목록에 등장), 이어서
      브라우저에서 실제 클릭 시 두 목록에 즉시 표시되는 것까지 확인.
      백엔드 회귀 **3081 passed / 52 skipped / 0 failed**, 프론트 764 passed, tsc 통과.
      커밋 `82355e743`

**갭 검증으로 잡은 내 결함 2건.** 반환 어노테이션에 `Any`를 쓰면서 import를 하지 않았고
(`from __future__ import annotations` 때문에 런타임에는 안 터지지만 타입 해석에서 깨진다),
교체 후 쓰이지 않게 된 `AssetRecord`·`AssetType` import가 남아 있었다. 같은 커밋에서 고쳤다.

### Task 23: 긴 촬영본에서 쓸 구간 추천 — **완료 (2026-08-07, Task 27로 막힘 해소)**

한 번 중단됐다가 같은 날 Task 27이 상류를 채우면서 풀렸다. 경과를 남긴다 —
"읽는 쪽만 맞게 만들어도 데이터가 없으면 효과가 0"이라는 사례다.

1. 읽는 쪽(구간 선택 + 배선)을 먼저 구현·검증했다 (커밋 `acc816e48`)
2. **실측에서 막혔다** — 읽을 데이터가 placeholder였다. 아래 "실측" 항목
3. Task 27이 실제 장면 감지를 채워 넣자 **추가 변경 없이 동작**했다.
   최종 실측은 Task 27 Step 5 표에 있다 (owner 실제 영상 9개 전부 개선)

**현재 결함.** B-roll 후보의 기본 구간이 하드코딩돼 있다.

`local_project_store.py:2278` — `"target_range": {"start_sec": 0, "end_sec": min(5.0, duration_sec)}`

10분 영상이든 10초 영상이든 **무조건 맨 앞 5초**다. 산책 영상의 앞 5초는 보통 카메라를
켜고 자세를 잡는 구간이라 가장 쓸 수 없는 부분이다. 추천이 없는 게 아니라 **추천인 척하는
고정값**이 들어가 있다.

**이미 있는 재료 (중요).** 분석이 이미 장면 구간을 계산해 저장하고 있다.

- `media_analysis.py:102` — `probe.scene_boundaries`로 장면 구간 계산
- `media_analysis.py:103` — `media_scene_windows` 테이블에 저장
- `local_project_store.py:8285` — `list_media_scene_windows()`로 읽기 가능
- `routers/media_analysis.py:45` — provenance API로 노출

**그런데 이 값을 읽어서 배치에 쓰는 코드가 없다.** 저장까지 해놓고 안 쓰는,
이 프로젝트가 고치려는 "만들어놓고 연결 안 함" 패턴이다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `media_scene_windows` + `list_media_scene_windows()` | `adopt as-is` | 이미 계산·저장되고 있다. 읽기만 하면 된다 |
| `media_controls`의 `in_sec`/`out_sec` | `adopt as-is` | 원본 구간 지정이 이미 정규화·검증된다 |
| 새 장면 감지 구현 | `exclude` | 기존 ffprobe 경로로 충분하다 |
| 외부 하이라이트 검출 모델 | `exclude` | 로컬 우선 경계를 넘고, 실측 전에는 필요 근거가 없다 |

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Create: `tests/test_broll_range_recommendation.py`

- [x] **Step 1: 실패 테스트** — `videobox_storage.broll_source_window` 없어 collection 실패
- [x] **Step 2: RED 확인**
- [x] **Step 3: 구현** — `choose_broll_source_window()` 순수 함수로 분리했다.
      원래 자리(`_draft_readiness_plan`)가 실제 ffprobe와 진짜 영상 파일을 요구해
      그대로는 결정적으로 테스트할 수 없기 때문이다. 필요 길이를 담을 수 있는 구간 중
      **맨 앞이 아닌 가장 긴 구간**을 고르고, 없으면 기존 동작(앞에서 자르기)으로
      안전하게 되돌아간다. `local_project_store.py`의 하드코딩을 이 함수 호출로 교체하고
      `_scene_windows_for_asset()`로 자산의 최신 분석 구간을 읽게 배선했다
- [x] **Step 4: owner 실제 영상으로 실측 — 여기서 막혔다.** 아래 참조
- [x] **Step 5: 전체 회귀 + 커밋** — 1차로 읽는 쪽만 커밋(`acc816e48`)한 뒤,
      Task 27이 장면 감지를 채우면서 목표를 달성했다. 최종 실측은 Task 27 Step 5 참조

**실측 (2026-08-07, owner 실제 촬영본 `videobox-user-library/media-inbox`).**

| 파일 | 길이 | 감지된 경계 | 구간 수 |
|---|---|---|---|
| 20250827_유튜브영상.mp4 | 494.8s | `(0.0, 494.837)` | **1** |
| 20260323_152848.mp4 | 18.4s | `(0.0, 18.401)` | **1** |
| 20260323_152916.mp4 | 11.7s | `(0.0, 11.700)` | **1** |
| 20260323_153258.mp4 | 10.6s | `(0.0, 10.645)` | **1** |

**원인 — 장면 감지가 애초에 구현돼 있지 않다.** `media_probe.py:_probe()`가
`boundaries = (0.0, duration) if duration > 0 else (0.0,)`로 **길이 전체를 구간 하나로
고정**한다. 같은 파일 주석도 "Scene-aware providers can later refine
`scene_boundaries`"라고 적어, 처음부터 자리만 잡아둔 placeholder였음을 밝히고 있다.

즉 `media_scene_windows` 테이블에는 **항상 `[0, 전체길이]` 한 개만** 들어간다.
8분짜리 영상도 구간 1개다.

**그래서 이 Task의 개선 효과는 현재 0이다.** 구간이 `[0, 전체길이]` 하나뿐이면
`choose_broll_source_window()`는 그것을 유일한 후보로 받아 `start_sec=0`을 돌려주고,
결과는 **기존 "앞에서 5초"와 완전히 동일**하다. 코드는 맞게 동작하지만 먹일 데이터가 없다.

**이전 기록 정정.** 이 계획서의 Task 23 최초 작성분과 2026-08-07 세션 초반 보고에서
"장면 구간이 이미 계산·저장되고 있는데 아무도 안 읽는다"고 적었다. **틀렸다.**
저장되는 것은 계산된 장면 구간이 아니라 **길이 전체를 감싼 placeholder 한 개**다.
`record_media_scene_windows` 호출부만 보고 `media_probe`의 `scene_boundaries` 생성부를
확인하지 않은 채 단정했다.

**남긴 것.** 읽는 쪽(순수 함수 + 배선 + 테스트 12개)은 정확하고 회귀도 없으므로 커밋해
남긴다. Task 27이 진짜 경계를 채워 넣는 순간 **추가 변경 없이 바로 동작한다.**
기존 동작으로 안전하게 되돌아가므로 지금 켜져 있어도 해롭지 않다.

### Task 27: 실제 장면 경계 감지 — **미착수 · Task 23의 선행 조건**

`media_probe._probe()`의 placeholder를 실제 감지로 교체해야 Task 23이 값을 갖는다.

**유력한 방법.** ffmpeg의 scene 필터는 이미 있는 의존성으로 해결된다.

```
ffmpeg -i <input> -filter:v "select='gt(scene,0.3)',showinfo" -f null -
```

`showinfo`의 `pts_time`이 장면 전환 지점이다. 새 모델이나 외부 의존성이 필요 없다.

**미리 밝히는 비용 문제 (owner 판단이 필요할 수 있다).** 이 방식은 **영상 전체를
디코딩**한다. 지금 분석은 대표 프레임 6장만 뽑아 싸게 끝내는데, 그것과 비용 차원이
다르다. owner의 520MB·8분짜리 파일에서 실제로 몇 초 걸리는지 **먼저 재고** 나서
결정해야 한다. 느리면 대안이 있다:

1. 샘플링 간격을 낮춰(예: 초당 1프레임) 정밀도를 희생하고 속도를 얻는다
2. 긴 영상에만 적용하고 짧은 영상은 지금처럼 통째로 둔다
3. 분석 단계가 아니라 "구간 고르기"를 실제로 할 때 lazy하게 돌린다

- [x] **Step 0: 실제 영상으로 소요 시간 실측 (선행) — 완료 (2026-08-07)**

**실측 결과 (owner 실제 촬영본 9개 전부).**

| 파일 | 길이 | 소요 | 전환 @0.3 | 전환 @0.15 |
|---|---|---|---|---|
| 20250827_유튜브영상 | 494s | **7초** | **11** | **43** |
| 20260323_152848 | 18s | 1초 | 0 | 0 |
| 20260323_152916 | 11s | 1초 | 0 | 1 |
| 20260323_153258 | 10s | 1초 | 0 | 1 |
| 20260612_091959 | 10s | 0초 | 0 | 0 |
| 20260612_092018 | 17s | 2초 | 0 | 0 |
| 20260626_163224 | 29s | 2초 | 0 | 0 |
| 20260628_165922 | 14s | 1초 | 0 | 0 |
| 가로_FHD_20260319 | 11s | 1초 | 0 | 1 |

**비용은 문제가 아니다.** 521MB·8분 파일이 **7초**다. 위에 적어둔 "느리면 이렇게 하자"
대안 3가지는 **필요 없다.** 전체 디코딩을 걱정했지만 실측이 그 걱정을 지웠다.

**대신 다른 것이 드러났다 — 자료가 두 종류다.**

1. **긴 편집본(494s)**: 전환 11개가 정확히 잡힌다. Task 23이 바로 값을 갖는 경우다.
   owner가 말한 "10분짜리 산책 영상"이 여기 해당한다
2. **짧은 폰 클립(10~29초, 현재 라이브러리의 8/9개)**: 전환이 **0개**다. 임계값을
   0.15로 낮춰도 0~1개다

**2번은 결함이 아니라 당연한 결과다.** 폰으로 찍은 원본 클립은 컷 없이 **한 번에 쭉 찍은
단일 테이크**라서 "장면 전환"이라는 것이 물리적으로 존재하지 않는다. 감지기가 못 찾는 게
아니라 찾을 게 없다.

**따라서 장면 전환 감지만으로는 절반만 해결된다.** 짧은 단일 테이크에는 다른 기준이
필요하다. 후보:

- 앞부분 N초를 카메라 세팅으로 보고 건너뛴다 (가장 단순, 데이터 불필요)
- 흔들림·밝기 변화가 적은 안정 구간을 고른다 (추가 측정 필요)
- 10~30초짜리는 애초에 고를 여지가 적으니 그대로 둔다 (아무것도 안 함)

**owner 결정 (2026-08-07): 롱폼·숏폼 둘 다 만든다. 따라서 두 경우를 모두 처리한다.**

질문은 "올리는 원본 영상의 종류"였고 답변은 "만드는 결과물의 종류"라 층위가 다르지만,
어느 쪽으로 읽어도 **긴 촬영본과 짧은 단일 테이크가 모두 들어온다**는 결론은 같다.
따라서 범위는 둘 다이며, 위 후보 중 **1번(앞부분 건너뛰기)**을 단일 테이크 규칙으로
채택한다. 추가 측정이 필요 없고 데이터 없이도 성립하는 유일한 후보다.

- [x] **Step 1: owner 확인 후 범위 확정 — 완료 (2026-08-07)**
- [x] **Step 2: 실패 테스트** — `tests/test_scene_boundary_detection.py`(컷 감지,
      단일 테이크 오검출 방지, 정렬·중복, `probe_metadata`는 싼 경로 유지) +
      `test_broll_range_recommendation.py`에 단일 테이크 앞부분 건너뛰기 4건
- [x] **Step 3: RED 확인** — 컷 있는 영상에서 감지된 전환 `[]`(0개), 단일 테이크
      `start_sec == 0.0`
- [x] **Step 4: 구현**
      - `media_probe._detect_scene_boundaries()`: ffmpeg scene 필터(`gt(scene,0.3)`)의
        `showinfo` `pts_time`을 파싱해 `(0.0, ...컷..., duration)`을 만든다.
        디코딩 실패·타임아웃이면 예전처럼 통짜 구간 1개로 돌아간다(best-effort)
      - **비싼 경로에만 넣었다**: 분석이 쓰는 `probe()`에만 적용하고, 자산 등록이 매번
        쓰는 `probe_metadata()`는 ffprobe 한 번으로 그대로 뒀다
      - `choose_broll_source_window()`에 `SETTLE_HEAD_SEC = 2.0` 추가. **컷이 하나도
        없는 단일 테이크에만** 적용한다 — 실제로 감지된 장면 구간은 그 경계가 이미
        올바른 시작점이라 건드리지 않는다. 여유가 없는 짧은 클립은 건너뛰지 않는다
- [x] **Step 5: owner 실제 영상 9개로 실측 — 완료 (2026-08-07)**

**최종 실측 (owner 실제 촬영본 9개 전부, `probe()` 실행).**

| 파일 | 길이 | 소요 | 감지 구간 | 추천 구간(5초) | 개선 |
|---|---|---|---|---|---|
| 20250827_유튜브영상 | 495s | 6s | **12** | **346.6~351.6s** | O |
| 20260323_152848 | 18s | 2s | 1 | 2.0~7.0s | O |
| 20260323_152916 | 12s | 2s | 1 | 2.0~7.0s | O |
| 20260323_153258 | 11s | 2s | 1 | 2.0~7.0s | O |
| 20260612_091959 | 10s | 2s | 1 | 2.0~7.0s | O |
| 20260612_092018 | 17s | 2s | 1 | 2.0~7.0s | O |
| 20260626_163224 | 29s | 3s | 1 | 2.0~7.0s | O |
| 20260628_165922 | 15s | 2s | 1 | 2.0~7.0s | O |
| 가로_FHD_20260319 | 11s | 2s | 1 | 2.0~7.0s | O |

**9개 전부 개선됐다.** 이전에는 예외 없이 `0.0~5.0s`였다.

- 긴 편집본은 컷 12개를 잡아 **6분 지점의 안정된 장면**(346.6s)을 고른다. 맨 앞 5초와
  비교할 여지가 없는 차이다
- 짧은 단일 테이크 8개는 컷이 없으므로 **앞 2초(카메라 세팅)를 건너뛴** 2.0~7.0s를 고른다
- 비용은 파일당 2~6초. 분석은 이미 비동기 큐라서 문제되지 않는다

**남은 한계 (정직하게 남긴다).** 장면 전환은 "화면이 바뀌는 지점"이지 "볼 만한 장면"이
아니다. 12개 구간 중 가장 긴 것을 골랐을 뿐, 그 6분 지점이 실제로 좋은 그림인지는
**사람이 봐야 안다.** Task 24(편집 화면에서 구간 손보기)가 그 손잡이다.

**영향 범위 확인 (갭 검증).** 느려진 `probe()`의 호출처는 `media_analysis.py:91`
**하나뿐**이다. 브라우저 미리보기는 별개 클래스(`FFprobeBrowserPreviewProbe`)를 쓰므로
사용자가 기다리는 대화형 경로는 느려지지 않는다.

### Task 28: 장면 구간을 비전 모델과 분리해 저장 — **미착수 · Task 23/27이 실제로 동작하려면 필요**

**2026-08-07 실사용 실증 — 가설이 아니라 실제로 재현했다.**

owner가 LM Studio를 켜둔 상태에서 실제 촬영본(`20260626_163224.mp4`, 29초)을 가져와
진짜 분석을 돌렸다. 결과:

| 항목 | 결과 |
|---|---|
| 분석 상태 | `blocked` / `LM_STUDIO_BLOCKED` |
| 실패 원인 | **미확정** (Task 29 참조 — 최초 진단은 틀렸고 철회했다) |
| **저장된 장면 구간** | **`[]` — 하나도 없음** |

**이 Task의 근거는 실패 원인이 무엇이냐와 무관하게 성립한다.** ffmpeg이 장면 구간을
이미 다 계산해 둔 상태였는데, 그 뒤의 비전 호출이 실패하자 **계산 결과가 통째로
버려졌다.** 원인이 부하든 타임아웃이든 LM Studio가 꺼져 있어서든, **비전 호출이 실패하는
모든 경우에 같은 일이 벌어진다.** 실제로 같은 분석을 재시도하니 성공했고 그때는 구간이
정상 저장됐다 — 즉 **구간 저장이 비전 성공 여부에 매달려 있다는 사실 자체**가 문제다.

owner가 LM Studio를 항상 켜두지는 않으므로 실사용에서 흔히 걸린다.

**갭 검증으로 찾은 제약.** `media_analysis.py`의 저장 순서가 이렇다.

```
probe()                      # 장면 구간 계산 (ffmpeg만 필요)
vision_provider.analyze_images(...)   # ← LM Studio 필요. 여기서 실패하면
record_media_scene_windows(...)       # ← 여기에 도달하지 못한다
```

장면 구간은 **ffmpeg만으로 이미 계산이 끝나 있는데**, 비전 모델 호출 뒤에 저장한다.
따라서 **LM Studio가 꺼져 있으면 장면 구간이 한 번도 저장되지 않는다.** 2026-08-07
실측에서 개발 서버가 `MEDIA_ANALYSIS_WORKER_UNAVAILABLE`로 분석을 막는 것을 확인했고,
그 상태에서는 Task 23/27이 애써 만든 추천이 **전혀 동작하지 않는다.**

owner가 LM Studio를 항상 켜두지는 않으므로 실사용에서 자주 걸릴 조건이다.

**고칠 방향.** `record_media_scene_windows` 호출을 `probe()` 직후, 비전 호출 **앞으로**
옮긴다. 장면 구간은 비전 모델과 무관하게 유도되는 값이므로 그 의존을 가질 이유가 없다.

**주의할 점.** 이 변경은 이전 세션에서 검증된 분석 흐름의 순서를 바꾼다. 실패·취소된
분석에도 장면 구간이 남게 되므로, 기존 정리 경로(`local_project_store.py:8433, 8510,
8648`의 `DELETE FROM media_scene_windows`)가 그 경우를 제대로 덮는지 먼저 확인해야 한다.

- [ ] **Step 1: 실패 테스트** — 비전 provider가 죽어도 장면 구간은 저장되는지,
      취소·실패 시 정리가 여전히 도는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — 저장 위치를 비전 호출 앞으로 옮긴다
- [ ] **Step 4: LM Studio를 끈 채 실제 서버로 역방향 검증 + 회귀 + 커밋**

### Task 29: 분석이 `LM_STUDIO_BLOCKED`로 실패하는 조건 규명 — **미착수 · 원인 미확정**

**주의 — 이 항목의 최초 진단(비전 타임아웃 120초 부족)은 틀렸다. 철회한다.**

처음에 owner의 실제 촬영본(29초)이 약 2분간 `running`이다가 `LM_STUDIO_BLOCKED`로
떨어지는 것을 보고 "120초 타임아웃이 짧아서"라고 적었다. **실측이 이를 뒤집었다.**

| 측정 | 소요 |
|---|---|
| 단순 스키마 + 이미지 6장 (reasoning on) | 2.0초 |
| 단순 스키마 + 이미지 6장 (reasoning off) | 0.9초 |
| **실제 `FIXED_VISION_RESPONSE_SCHEMA` + 이미지 6장** | **4.6초** |
| **앱 코드 경로 그대로**(`probe`→`capability_profile`→`preflight`→`analyze_images`) | **총 약 9초** |

120초 근처도 가지 않는다. 그리고 같은 분석을 **재시도하니 즉시 `succeeded`** 했고
장면 구간도 정상 저장됐다(`[{0.0, 29.12}]`).

**틀린 이유.** 최초 측정 때 **내가 동시에 전체 백엔드 회귀(3,100여 건)를 돌리고 있었다.**
CPU가 포화된 상태에서 잰 수치를 제품 결함으로 단정했다. `CLAUDE.md` §1.13이 금지하는
"자기 작업을 결함으로 오진"에 해당한다. `Task 19`를 사각지대라고 쓴 것도 근거가 없으므로
함께 철회한다.

**부하 없는 상태 재측정 (2026-08-07) — 원인이 확정됐다. 모델 속도가 아니라 대기열이다.**

| 측정 | 결과 |
|---|---|
| 8분 편집본, 부하 없음, timeout=120s (기본값) | **120.1초에 실패** |
| **같은 호출, 직후 재실행, timeout=600s** | **4.0초에 성공** |

같은 파일·같은 프레임(6장, 7~115KB)·같은 스키마인데 한 번은 120초를 넘기고 한 번은
4초에 끝난다. **추론 자체는 4~6초다.** 차이는 그 시점에 LM Studio가 다른 요청을
처리 중이었는지 여부다.

**확정된 원인 — 중단된 요청이 LM Studio를 계속 점유한다.**

1. 어떤 이유로든(CPU 포화 등) 비전 요청이 120초 클라이언트 타임아웃에 걸린다
2. **클라이언트는 포기했지만 LM Studio는 그 생성을 계속한다**
3. 다음 요청은 그 뒤에 줄을 서고, 역시 120초를 넘겨 실패한다
4. 한 번 밀리면 연쇄적으로 계속 실패한다

실제로 이 세션에서 실패 3건이 전부 이 연쇄였고, LM Studio가 한가해진 뒤의 호출은
예외 없이 4~6초에 성공했다.

**실사용 영향.** owner가 B-roll을 여러 개 한꺼번에 가져오면 분석이 줄줄이 들어간다.
프로세스 안에서는 `MediaAnalysisService._dispatch_lock`이 한 번에 하나만 보내지만,
**타임아웃으로 버려진 요청이 LM Studio 쪽에 남아 있으면 그 보호가 소용없다.**

**고칠 방향 (택일이 아니라 조합일 수 있다).**

1. `VIDEOBOX_LOCAL_VISION_TIMEOUT_SECONDS` 환경변수 추가 — 4~6초 걸리는 작업에 120초는
   이미 넉넉하므로 **단순히 늘리는 것은 근본 해결이 아니다.** 다만 대기 여유는 준다
2. 타임아웃으로 실패했을 때 **바로 재시도하지 않고 LM Studio가 한가해질 때까지 기다린다**
   — 연쇄를 끊는 가장 직접적인 방법
3. 요청 전에 LM Studio가 처리 중인지 확인해 대기 — 네이티브 API가 그 상태를 주는지
   먼저 확인해야 한다

- [x] **Step 0: 부하 없는 상태에서 재측정 — 완료 (2026-08-07)**
- [ ] **Step 1: 실패 테스트** — 타임아웃 뒤 곧바로 재시도하면 연쇄 실패가 나는 것을 고정
- [ ] **Step 2~: 구현 · 실측 · 커밋**

**교훈으로 남긴다.** 이 항목은 한 세션 안에서 진단이 **세 번** 바뀌었다
(타임아웃 부족 → 내 부하 탓 → 대기열 점유). 처음 두 번 모두 **한 번의 측정으로 단정**한
것이 원인이다. 부하 조건과 반복 측정을 갖추기 전에는 원인을 적지 않는다.

**경계 주의(유지).** 장면 전환 감지는 "화면이 바뀌는 지점"이지 "좋은 장면"이 아니다.
전환이 잡혀도 그 구간이 볼 만한지는 별개이고, 그 판정은 사람 몫으로 남는다.

### Task 24: 편집 화면에서 B-roll 구간 손보기

Task 23의 추천을 받은 뒤, 마음에 들지 않을 때 사람이 조절하는 경로다.

**현재 상태.** 엔진은 지원하는데 화면이 없다.

- `media_controls.py:55~64` — `in_sec`/`out_sec` 정규화·검증 있음
- `editorViewModel.ts:50~51` — 프론트까지 값이 흘러옴
- `inspectorRegistry.ts:52,55` — **B-roll은 `fields: []`, `clearOnly: true`.
  즉 편집 화면에서 B-roll은 "빼기"만 되고 구간 조절 칸이 없다**

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `inspectorRegistry` 필드 정의 | `partial port` | B-roll에만 구간 필드를 추가한다 |
| `applyMedia(controls)` 명령 경로 | `adopt as-is` | 이미 controls를 전달할 수 있다 |
| `AssetPreviewPlayer` | `adopt as-is` | 이미 in/out 구간만 재생한다 |
| 새 타임라인 트리밍 UI | `exclude` | §2.1 MVP 제외(자유 키프레임·풀 NLE) 경계를 넘는다 |

**Files:**
- Modify: `apps/web/src/features/editor/inspector/inspectorRegistry.ts`
- Modify: `apps/web/src/features/editor/inspector/InspectorControls.tsx`
- Modify: 해당 테스트

- [ ] **Step 1: 실패 테스트** — B-roll 선택 시 시작/끝 조절이 보이고 저장되는지
- [ ] **Step 2: RED 확인**
- [ ] **Step 3: 구현** — §10.13 creator 어휘를 따른다(`in_sec` 같은 내부 용어 금지)
- [ ] **Step 4: GREEN + 브라우저 실측 + 커밋**

**범위 경계 확인.** 이 Task는 `implementation-plan.ko.md` §8.4가 고정한 편집기 14개
조작 중 "컷 경계 조정"과 "B-roll 교체"에 해당한다. 풀 NLE 타임라인 편집으로 확장하지
않는다.

### Task 25: 내 목소리 TTS — Voicebox 계열 엔진 반입 — **미착수 · 후순위**

Task 1 Step 7이 열어둔 TTS 엔진 선택을 owner가 2026-08-07에 결정했다.

**우선순위 (owner, 2026-08-07 추가 결정): 후순위다.** owner는 초반에 **직접 녹음을
주로 쓴다.** 목소리 복제는 "나중을 위해" 넣어두는 기능이지 지금 막고 있는 것이 아니다.
따라서 실행 순서에서 Task 22·23·24 뒤에 둔다. **이 Task가 늦어져도 owner의 실제 작업은
막히지 않는다** — 그 판단의 근거가 아래 Task 26이다.

### Task 26: 직접 녹음 경로 실제 마이크 실측 — **미착수 · owner 참관 필요**

직접 녹음이 owner의 **1순위 경로**가 됐으므로, 이 경로가 실제로 도는지 실측이 필요하다.

**구현은 이미 되어 있다 (2026-08-07 코드 확인).** `CreationInterview.tsx:360~372`,
`398`에 마이크 녹음 시작·마치기·다시 올리기가 있고, 화면 이탈 시 스트림 정리까지
테스트로 고정돼 있다(`CreationInterview.test.tsx:369~396`). **새로 만들 것은 없다.**

**그런데 그 테스트는 jsdom 목이다.** 실제 마이크로 소리를 넣어 전사까지 나오는 것을
확인한 기록이 없다. 이 저장소는 **테스트 2,960개가 통과하는 동안 실제 음성 인식이 한 번도
실행되지 않은** 전례가 있고(`CLAUDE.md` §검증), 지금 이 경로가 owner의 주 경로가 됐다.

- [ ] **Step 1: owner 참관 실측** — 실제 마이크로 한 문장 녹음 → 업로드 → 전사 →
      초안까지 실제로 도달하는지 확인한다. 마이크 권한과 실제 발화가 필요하므로
      **무인 실행 불가.** owner와 함께 진행한다
- [ ] **Step 2: 실패 지점이 나오면 그때 Task로 등록** — 지금은 결함이 있다고 단정하지
      않는다. 구현은 있고, 실측만 없다

**이 Task를 Task 25보다 먼저 닫는 것이 맞다.** 주 경로가 실제로 도는지 모르는 채
보조 경로(목소리 복제)를 만드는 것은 순서가 뒤바뀐 것이다.

**조사 결과 (2026-08-07, 실제 저장소·모델 카드 확인).**

| 항목 | 확인 내용 |
|---|---|
| Voicebox 라이선스 | MIT |
| Voicebox 형태 | 엔진 7개를 감싼 로컬 데스크톱 스튜디오. REST(`POST /speak`)와 MCP 서버도 제공 |
| 한국어 담당 엔진 | **Chatterbox Multilingual** (Voicebox의 7개 엔진 중 하나). `ko` 공식 지원 |
| 엔진 라이선스 | MIT (`resemble-ai/chatterbox`) |
| 반입 방식 | `pip install chatterbox-tts` — 파이썬 라이브러리로 직접 사용 가능 |
| 모델 크기 | Multilingual V3 500M / Turbo 350M / Nano 110M 파라미터 |
| 가중치 출처 | Hugging Face Hub (`ResembleAI`) — 최초 1회 다운로드 |
| 외부 전송 | **없음.** 전부 로컬 추론 |
| GPU | CUDA 지원. CPU도 가능(Nano는 8코어에서 실시간의 3배) |
| 음성 복제 | 참조 음성 약 10초로 클로닝 |
| **워터마크** | **생성 음성 전부에 Resemble Perth 신경 워터마크가 박힌다** |

**반입 결정 — GUI 앱이 아니라 엔진을 반입한다.** Voicebox 자체는 데스크톱 앱이라,
VideoBox가 쓰려면 그 앱이 항상 떠 있어야 하고 로컬 서비스가 하나 더 늘어난다
(LM Studio에 이어 두 번째). VideoBox에 필요한 건 스튜디오가 아니라 **엔진**이고,
한국어를 실제로 만드는 것은 Chatterbox이므로 파이썬 라이브러리로 직접 붙인다.
owner가 목소리를 들어보고 고르는 GUI가 필요하면 Voicebox 앱은 **VideoBox와 무관하게
따로 설치해 쓰면 된다.** 둘은 같은 엔진을 쓴다.

**재사용 게이트 (§8.1):**

| 후보 | 분류 | 이유 |
|---|---|---|
| `chatterbox-tts` (MIT, pip) | `adopt as-is` | 한국어·클로닝·로컬을 모두 만족하는 엔진 본체 |
| 기존 `TTSEngineConfig` / `_build_tts_provider` | `adopt as-is` | provider 어댑터 자리가 이미 있다. 하드코딩 직접 호출은 §8.1 반입 금지 |
| 기존 `voice-sample` 자산 경로 | `adopt as-is` | 참조 음성 업로드가 이미 구현돼 있다 |
| Voicebox 데스크톱 앱을 런타임 의존으로 | `exclude` | GUI 앱 상시 실행을 제품 의존성으로 만들지 않는다 |
| Voicebox의 UI 구조 | `exclude` | §8.1 `UI 구조` 반입 금지 |

**Files:**
- Modify: `requirements-runtime.txt` (또는 별도 extra)
- Create: Chatterbox provider 어댑터 + 테스트

- [ ] **Step 1: 격리 환경에서 한국어 품질 실측 (선행)** — 기존 venv를 건드리지 않는다.
      `chatterbox-tts`가 torch 계열을 끌어와 `faster-whisper`가 쓰는 기존 환경을 깨뜨릴
      수 있으므로 **별도 환경에서 먼저 확인**한다. 한국어 문장 + owner 참조 음성으로
      샘플을 만들어 파일로 남긴다
- [ ] **Step 2: owner 청취 판정** — 목소리 품질은 사람이 듣고 정한다. 이 계획의
      "완료 기준"도 청취·취향 판정을 human gate로 남겨두고 있다. **owner가 듣기 전에는
      파이프라인에 연결하지 않는다**
- [ ] **Step 3: 실패 테스트** — provider 어댑터가 참조 음성으로 한국어 음성을 만드는지
- [ ] **Step 4: RED 확인**
- [ ] **Step 5: 구현** — `TTSEngineConfig`에 엔진 추가. 기존 provider 인터페이스를 지킨다
- [ ] **Step 6: GREEN + 실제 파이프라인 검증 + 커밋**

**owner에게 미리 알릴 것 (§Task 1의 승인 요건).**

1. **워터마크.** 만들어지는 음성마다 Resemble의 신경 워터마크가 들어간다. 사람 귀에는
   안 들리고 편집을 거쳐도 남는다. 유튜브 업로드 자체에 문제되는 건 아니지만,
   "AI 생성 음성"임이 기술적으로 식별 가능하다는 뜻이다. **알고 쓰는 것과 모르고 쓰는
   것은 다르므로 명시한다**
2. **다운로드.** 최초 1회 Hugging Face에서 모델 가중치를 받는다(500M 파라미터급).
   저장 위치와 실제 용량은 Step 1에서 실측해 보고한다
3. **외부 전송 없음.** 추론은 전부 로컬이다

**경계 유지.** `product-plan.ko.md` §6.4와 `architecture-plan.ko.md` §13.7의
"TTS는 자동 전면 대체가 아니라 review 기반으로만 적용"은 그대로 지킨다. 엔진이
바뀌어도 이 경계는 바뀌지 않는다.

---

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
