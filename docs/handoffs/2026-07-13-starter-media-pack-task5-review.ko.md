# Starter media pack Task 5 — release-gate remediation handoff (2026-07-14)

## 현재 위치

- branch: `codex/production-readiness-blocker-slice-1`
- base HEAD: `53553f1`; 이 handoff와 release-gate 수정은 아직 이번 closeout commit 전이다.
- 공식 계획: `docs/superpowers/plans/2026-07-12-starter-media-pack-implementation.md` Task 5
- Task 1–4는 완료다. Task 5는 실제 무료 asset research·팩 생성·release smoke 전이며 완료가 아니다. 이번 slice는 Task 5 Step 2 verifier 계약과 이전 review blocker만 닫는다.

## 해결한 review blocker

- **Critical (direct install 우회):** reusable `videobox_core_engine.media_pack_release`가 service source에 대해 staging copy 전 release contract를 검사한다. missing/tampered evidence, wrong codec, fake average-320kbps VBR은 `release_contract`를 반환하며 destination/index/activation/search 결과를 만들지 않는다.
- **Important (VBR average bitrate):** `ffprobe_media()`는 format average bitrate 외에 MPEG-1 Layer III frame 전체를 검사하는 `is_cbr_320_mp3()`를 제공한다. ID3v2.4 footer와 ID3v2.3 experimental flag를 구분한다.
- **정리 안전성:** failed validation은 기존 inactive pack index를 지우지 않는다. `indexed_by_attempt`가 true인 경우에만 cleanup한다.
- **정책 단일화:** `scripts/verify-starter-media-pack.py`는 service에 core `ffprobe_media`를 주입한다. `scripts/starter_media_pack.py`는 core validator를 호출하는 compatibility/integrity wrapper라 codec/evidence 정책을 중복하지 않는다.

## TDD와 검증 증거

- RED: stale inactive index가 release failure cleanup으로 삭제됨; GREEN: index 보존.
- RED: release probe가 staging file을 사용함; GREEN: source asset을 probing한 뒤 invalid pack은 staging을 만들지 않음.
- RED: ID3v2.4 footer valid CBR, ID3v2.3 experimental-flag valid CBR; GREEN: 둘 다 CBR로 통과.
- RED: real MPEG frame VBR (mixed bitrate index); GREEN: CBR parser가 거부.
- focused final: `tests/test_media_pack_service.py tests/test_starter_media_pack_release.py tests/test_api_media_library.py tests/test_media_controls.py` → `47 passed, 1 warning in 21.18s`.
- final full Python 3.12 backend: `.venv\\Scripts\\python.exe -m pytest -q` → `793 passed, 1 warning in 186.66s`; prior `test_manual_music_asset_uses_resolvable_asset_uri_in_the_render_timeline`도 이 전체 run에서 통과했다.
- final frontend: `npm --prefix apps/web test` → `105 passed`; `npm --prefix apps/web run build` → success. Error-boundary intentional error와 일부 React `act(...)` test-hygiene stderr는 exit 0의 known output이다.
- independent review/reverse validation: direct service gate, CLI core path, install→materialize→timeline project-local URI→renderer resolve를 확인했다. 재리뷰에서 발견한 ID3v2.3 issue도 위 TDD cycle로 처리했다.

## 아직 하지 않은 것 / 다음 세션 첫 작업

1. remediation slice commit/push 뒤 Task 5 Step 1의 official license research를 시작한다.
2. evidence가 완결된 asset만 ignored `dist/starter-media-pack`에 300–500 MiB real pack으로 build하고 CLI/service verifier를 통과시킨다.
3. install → preview/favorite → materialize → 600-second Korean ingest/SRT/MP4/real CapCut draft smoke를 수행한다. 실제 pack 없이 Task 5 release 완료로 표시하지 않는다.

## 사람 인수 항목

실제 사용자 음성 TTS listening approval 및 다른 Windows PC CapCut handoff는 외부 입력 대기로 유지한다. runbook: `docs/handoffs/2026-07-13-human-acceptance-runbook.ko.md`. 합성 smoke 또는 개발 PC 성공을 사람 승인으로 대체하지 않는다.
