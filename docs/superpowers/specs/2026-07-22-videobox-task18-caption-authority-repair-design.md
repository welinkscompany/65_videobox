# VideoBox Task 18 Caption Time Authority Repair Design

## Goal

Task 18의 연결 자막은 내레이션 구간 하나의 시간을 항상 따른다. 과거 Task 17에서 저장된 caption placement override가 있어도 editor manifest, exact preview/final composition, CapCut materialization, 대본은 같은 내레이션 bounds를 사용한다.

## Decision

- caption은 generic timeline placement의 대상이 아니다. 새 `caption:*` placement change는 fail-closed로 거부한다.
- 기존 session에 남은 `caption:*` override는 삭제하거나 revision을 올리지 않는다. materialization에서만 무시해 기존 session을 열 수 있고, 다음 output부터 narration-derived caption bounds를 사용하게 한다.
- caption의 stable ID는 manifest에 유지한다. 이는 선택·표시 identity이며 시간 변경 권한이 아니다.
- 저장 요청이 진행 중이면 대본 textarea와 대본 행 선택을 함께 비활성화한다. 완료/실패 refresh가 draft를 교체하기 전에 새 입력을 받지 않는다.
- caption text의 durable source는 materializer가 읽는 `content_windows`의 matching `source_segment_id`다. caption command는 상위 segment text와 일치하는 window text를 같은 revisioned mutation으로 갱신한다. merge 뒤 child source caption을 수정할 때는 해당 child window만 바꾸며, 다른 window의 text는 유지한다.

## Boundaries

- 포함: core placement contract/materialization, content-window caption text synchronization, existing manifest consumer regression, TranscriptPanel saving lock, focused Python/frontend tests.
- 제외: stored-data migration write, caption text/style API 변경, caption drag/trim 재도입, asset/UI navigation, provider/Hermes/Mem0, OpenCut source/runtime, full Python regression.

## Verification

RED→GREEN으로 (1) legacy caption override가 materialized caption bounds를 바꾸지 않음, (2) 새 caption placement patch가 revision 없이 거부됨, (3) caption PATCH 뒤 manifest와 composition이 새 text를 읽음, (4) manifest/TimelineDock/PreviewStage가 narration timing을 보임, (5) pending caption save 동안 textarea와 행 선택이 잠김을 검증한다. 이후 affected Python/frontend, full frontend attempt, production build, provenance verifier, diff check를 실행한다.

## Self-review

한 시간 권한을 backend materialization에 두므로 UI만 보정하는 경우의 output 불일치를 남기지 않는다. legacy override를 즉시 삭제하지 않아 session history와 revision CAS를 우회하지 않는다.
