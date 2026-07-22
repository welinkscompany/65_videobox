# VideoBox Task 17 closeout — 2026-07-22

- 범위: B-roll/BGM/SFX/overlay/caption의 독립 배치 이동·자르기를 revision-bound batch mutation으로 구현했다. 저장된 override는 editor manifest와 local FFmpeg composition, CapCut이 읽는 동일 materialized timeline에 적용된다.
- 안전: 저장소는 `timeline_placement_overrides`를 보존한다. 서버는 범위 밖/중복/unknown/kind 불일치/비유한 값과 한 프레임 미만을 거부한다. UI 포인터 draft는 local이며 release에서만 한 요청을 보낸다.
- 검증: targeted Python `38 passed`, frontend full `45 files / 447 passed`, production build, UI provenance verifier, `git diff --check` 성공. 전체 Python regression은 실행하지 않았다.
- 경계: provider/Hermes/Mem0, OpenCut runtime/source copy, preview-job 생성, asset/control/text/style/z-order 변경은 추가하지 않았다. `?? .tmp-final-fence-debug/`는 기존 범위 밖 잔재라 stage/remove하지 않는다.
- 진행률: Task 9 사람/환경 acceptance와 별개로 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.

## 다음 goal prompt

```text
VideoBox만 작업해. canonical worktree와 branch/upstream을 먼저 확인하고 `.tmp-final-fence-debug/`는 건드리지 마.

AGENTS.md, development-fast-path §10, development-status의 §288, implementation-plan의 current next goal을 읽어.
Task 18 written spec부터 만들고 사용자 승인을 받은 뒤 TDD로 진행해. 전체 Python regression은 별도 지시 없이는 실행하거나 통과로 주장하지 마. Task 9 공식 누적은 9/22 (40.9%)로 유지해.
```
