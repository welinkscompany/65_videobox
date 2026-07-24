# VideoBox Task 22C2 voice/TTS closeout

## 닫은 범위

- `/settings/voice`가 내 목소리 샘플의 로컬 경로 등록, 파일 업로드, 목록/새로고침을 소유한다.
- active editing segment를 사용자가 직접 고른 뒤 TTS 후보를 만들고, 로컬 오디오를 들어 본 후 승인 또는 거부한다.
- removed segment, 내부 asset/candidate/segment ID, 자동 적용 control은 사용자 화면에 노출하지 않는다.
- project key/epoch, newest-request token, single-flight로 A→B/A→B→A와 중복 요청을 막는다.
- 저장 POST 성공과 후속 목록 refresh 실패를 구분해 같은 음성을 중복 등록하지 않는다.
- 청취 결정은 candidate 상태만 저장한다. editing session TTS replacement는 별도 explicit revisioned editor action이며 이번 settings 흐름에서는 0회다.

## 실제 dogfood 연결

- 실제 사용자 영상 샘플 4개로 B-roll 적용과 20초 exact preview 재생을 확인했다.
- 로컬 합성 BGM 220 Hz와 SFX 880 Hz를 서로 다른 구간에 적용하고, 렌더된 AAC에서 구간별 주파수를 역방향 확인했다.
- one-narration/multi-caption의 20초 음성 보존, remove/reorder source slice, exact/final/PyCapCut source range parity도 회귀와 실제 draft JSON으로 확인했다.
- 이 증거는 실제 CapCut Desktop 사람 실증이나 Task 9 사람 acceptance를 대체하지 않는다.

## 검증

- Task 22C2 focused frontend: `3 files / 43 tests passed`.
- full frontend: `60 files / 618 tests passed`.
- canonical voice/TTS E2E: `1 passed`, snapshot manifest verifier 통과.
- production build, Editor UI OSS provenance verifier, UI-system verifier, external-runtime/network guard, `git diff --check` 통과.
- independent spec/quality/gap/reverse review: Critical/Important/Minor 0.
- 전체 Python regression은 실행하지 않았다.
- 브라우저 직접 external/provider/Hermes/Mem0 요청은 0이었다. 명시적 candidate generation backend는 구성된 TTS provider를 호출할 수 있으므로 서버 provider 실행 전체가 0이라고 주장하지 않는다.

## 보존 범위

- `?? .tmp-final-fence-debug/`는 기존 범위 밖 잔재이므로 stage/remove/delete하지 않는다.
- `?? .tmp-real-video-dogfood/`, `?? apps/web/.tmp-real-video-dogfood/`는 이번 실제 로컬 검증 증거이며 stage/remove/delete하지 않는다.
- 사용자 원본 `C:\Users\atgro\OneDrive\바탕 화면\영상샘플`은 read-only로 유지한다.
- 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.

## 다음 goal prompt

`VideoBox만 작업해. D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility와 codex/videobox-container-compatibility만 사용해. 먼저 AGENTS.md, docs/development-fast-path.ko.md §10, docs/development-status-2026-06-29.ko.md §296, docs/superpowers/plans/2026-07-23-videobox-task22-release-parity.md, 이 handoff를 읽고 branch/HEAD/upstream/status/worktree/diff-check를 확인해. 보호된 임시 폴더 3개는 절대 stage/remove/delete하지 마. 다음은 Task 22C1 supported editor commands와 partial regeneration을 RED-first로 구현해. current revision, route epoch, one-player ownership, refresh-after-conflict, manual fallback을 유지하고 unsupported effect/automatic apply/provider/API expansion은 추가하지 마. 독립 spec/quality/gap/reverse review 뒤 focused/full frontend, build, provenance/network/E2E를 통과시키고, 이어서 Task 22C3 output reachability와 22D legacy owner removal을 진행해. 전체 Python regression은 실행하지 않았으면 통과라고 주장하지 마. Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도이며 공식 누적 9/22 (40.9%), 잔여 59.1%를 유지해.`
