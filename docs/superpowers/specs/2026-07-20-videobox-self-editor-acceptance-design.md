# VideoBox 자체 편집기 수용과 선택적 CapCut 호환 설계

**Date:** 2026-07-20
**Status:** 사용자 방향 승인 완료, 서면 명세 검토 대기
**Amends:** `docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md`, `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`

## 1. 결정

VideoBox의 주 편집 경로는 자체 경량 편집기다. 사용자는 VideoBox 안에서 자산·대본·자막·타임라인을 검수하고 수정하며, 현재 revision의 합성 편집본을 VideoBox에서 재생해 수용한다.

CapCut은 기존 export/handoff adapter를 보존하는 **선택적 상호운용 경로**다. CapCut Desktop 등록·열기·import는 해당 adapter의 별도 호환성 증거일 수 있지만, VideoBox 자체 편집기 기능의 완료나 Task 9 진행률의 필수 조건이 아니다.

이 결정은 풀 NLE를 새로 구현한다는 뜻이 아니다. 기존 계획의 설명형 영상용 경량 후편집 범위(컷/경계, B-roll·BGM·SFX·overlay 선택, 자막 text/style, 검수·undo/redo, 정확한 미리보기)를 유지하고 고급 색보정·모션그래픽·자유 keyframe·멀티트랙 NLE는 계속 제외한다.

## 2. 고려한 대안

1. **권장: 자체 편집기 수용 + 선택적 CapCut 호환.** 제품의 기본 경험과 완료 기준을 VideoBox에 두고, CapCut은 필요할 때만 내보내기/인계한다.
2. CapCut Desktop import를 Task 9의 필수 gate로 유지. 이미 존재하는 adapter는 검증되지만, 자체 편집기의 가치 검증을 외부 앱에 종속시키므로 거부한다.
3. CapCut 기능을 즉시 삭제. 제품 범위를 단순화하지만 기존 export 사용자를 깨고 이번 방향 전환에 필요 없는 호환성 회귀를 만든다. 보존하되 기본 경로에서 분리한다.

## 3. Task 9의 수정된 사람 수용 기준

Task 9은 다음 네 조건이 모두 실제로 증빙될 때만 완료 후보가 된다.

1. `B-roll Smoke Test` 또는 동등한 실제 프로젝트에서 각 장면에 재생 가능한 실제 자산이 있고 unresolved visual gap이 없다. 현재 `script-2`의 실제 MP4 부재는 계속 blocker다.
2. 한 번의 `초안 만들기` 승인으로 editing session과 실제 asset placement가 원자적으로 생성되고, current revision의 composited MP4가 VideoBox 내부에서 재생된다.
3. 사용자가 VideoBox에서 그 MP4를 확인한 뒤 **영상·자막·소리·장면 전환** 각각을 명시적으로 승인 또는 거부한다. 이 확인은 CapCut 화면이나 source audition으로 대체하지 않는다.
4. 수용 결과는 Task 9 closeout의 status/handoff에 사실 그대로 남긴다. 이번 방향 전환을 위해 새 DB, API route, 자동 승인, provider 호출을 만들지 않는다.

거부, 미승인, 자산 부재, stale artifact, 재생 실패는 모두 Task 9을 열어 둔다. CapCut Desktop import의 성공·실패·미실행은 Task 9 상태를 바꾸지 않으며, 필요하면 별도 호환성 handoff에 기록한다.

## 4. 편집기와 출력의 경계

`EditorViewModel`과 typed `EditorCommandPort`, revision/source-SHA binding, FFmpeg current-revision composition은 계속 authoritative하다. 브라우저 source audition은 선택한 클립 보기일 뿐 편집본 수용 증거가 아니다. Task 12의 exact proxy와 Task 13의 PreviewStage는 이 구분을 강화한다.

CapCut adapter는 current output의 선택적 consumer다. adapter가 실패하거나 대상 PC에 CapCut이 없더라도 VideoBox 편집 세션, preview, final MP4, 사용자 수용 기록을 변경하거나 무효화하지 않는다. 반대로 stale·gap·승인되지 않은 output은 기존 안전 규칙에 따라 CapCut export도 계속 차단할 수 있다.

## 5. 실행 순서와 진행률

- Task 9은 core 사람 수용이 남아 있어 현재 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.
- 실제 scene 2 MP4와 사용자 수용은 별도 사람/자산 gate로 추적한다. 임시 빈 장면, fake handoff, 과거 CapCut project는 증거가 아니다.
- 그 gate가 열려 있다고 이후 편집기 구현 전체를 멈추지 않는다. 다음 production increment는 기존 22-Task 계획의 **Task 11: source-derived responsive editor workbench**다.
- Task 11은 기존 `EditorViewModel` adapter를 read-only로 소비하고, 자체 편집기 layout·focus·panel persistence·responsive density를 만든다. Task 14 전의 두 번째 visual approval은 기존 계획대로 유지한다. 이 프로젝트 대화에서 visualization은 비활성화돼 있으므로 그 승인은 committed deterministic artifact를 사용자가 직접 검토하는 방식으로만 받는다.
- Task 12–20은 자체 편집기의 정확한 preview, navigation, mutation, waveform, captions, assets, 유진/Inspector를 순서대로 보강한다. CapCut의 새로운 자동 실행, host bridge, provider/OAuth, Hermes network는 이 전환 범위 밖이다.

## 6. 검증과 비목표

- 계획 수정은 문서 검토, `git diff --check`, scoped diff/status로 검증한다. production Task 11부터는 기존 22-Task RED/GREEN matrix, independent review, source→runtime 검증, focused/full attempt, production build, SSOT, commit/push 순서를 따른다.
- external Gemini/provider call은 0을 유지한다.
- 이번 변경은 CapCut adapter 코드, 기존 export artifact, DB/API route, provider, Hermes, OAuth, MCP transport, mem0, render/mutation 기능을 수정하거나 활성화하지 않는다.
- 사용자 수용은 이 명세의 승인과 다르다. 이 문서는 제품 경계를 승인하는 것이며, 실제 Task 9의 영상 품질 승인을 대체하지 않는다.
