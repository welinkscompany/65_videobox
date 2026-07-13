# Starter media pack Task 5 — review handoff (2026-07-13)

## 현재 위치

- branch: `codex/production-readiness-blocker-slice-1`
- pushed HEAD: `2c5f903 test: align manual music timeline with asset validation`
- 공식 계획: `docs/superpowers/plans/2026-07-12-starter-media-pack-implementation.md` Task 5
- Task 1–4는 완료다. Task 5는 실제 무료 자산 선별·팩 생성·release smoke 전이며 완료가 아니다.

## 이번에 한 일

`scripts/starter_media_pack.py`와 `scripts/verify-starter-media-pack.py`에 release 전용 검증을 추가했다.

- 음악: MP3 / 320 kbps를 확인한다.
- SFX: PCM WAV / 48 kHz / mono를 확인한다.
- `evidence/<asset_id>.txt`의 SHA-256이 manifest license evidence와 일치하는지 확인한다.
- 실제 pack bytes/digest가 manifest 및 300–500 MiB 경계와 일치하는지 확인한다.
- CLI는 release-contract failure를 설치 전에 `FAILED [release_contract]`로 표시한다.

TDD 증거:

- RED 1: `starter_media_pack` module 부재로 `tests/test_starter_media_pack_release.py` collection import failure.
- GREEN 1: release validator tests `4 passed`.
- RED 2: CLI가 `pack_integrity_mismatch`를 먼저 표시해 release contract failure를 식별하지 못함.
- GREEN 2: `tests/test_starter_media_pack_release.py tests/test_media_pack_service.py` -> `21 passed`.

## 독립 코드리뷰 — 반드시 먼저 해결

리뷰 범위 `89bf98d..633fd9d`에서 다음 두 문제를 확인했다.

1. **Critical — API install 우회 가능**: `MediaPackService.install()`은 manifest/integrity/duration만 검증한다. 새 release validator는 CLI만 호출한다. 따라서 API/direct caller는 codec, immutable evidence snapshot을 거치지 않고 install할 수 있다. 다음 RED test는 service/API direct install이 bad codec/evidence에 `release_contract`를 반환하고 index/activation하지 않음을 보여야 한다. 검증을 core-engine의 importable gate로 옮기거나 service에 mandatory injected media probe/validator를 연결한다.
2. **Important — VBR 우회 가능**: 현재 MP3의 `bit_rate == 320000`만 확인한다. 평균 bitrate가 320kbps인 VBR은 통과할 수 있다. ffprobe packet/frame bitrate consistency(또는 동등하게 신뢰 가능한 CBR 판정)를 추가하고 VBR RED fixture/fake probe를 고정한다.

## 최신 검증

- focused backend: `tests/test_starter_media_pack_release.py tests/test_media_pack_service.py tests/test_api_media_library.py` -> `34 passed` (reviewer run).
- full backend (review 시점): `.venv\\Scripts\\python.exe -m pytest -q` -> `783 passed, 1 failed`, `175.73s`.
  - failing test: `tests/test_media_controls.py::test_manual_music_asset_uses_resolvable_asset_uri_in_the_render_timeline`
  - symptom: `TimelineBuilder().build(...)` result에 `bgm` clip이 없어 `StopIteration`.
  - 원인: Task 3의 fail-closed BGM/SFX asset URI validator 계약과 오래된 test fixture가 어긋났다. `2c5f903`에서 test에 valid project-local URI와 validator를 명시했고 focused `tests/test_media_controls.py`는 `4 passed`다. 전체 backend 재실행은 아직 필요하다.
- frontend: `npm --prefix apps/web test` -> `105 passed`.
- frontend build: `npm --prefix apps/web run build` -> success.
- `git diff 89bf98d..633fd9d --check` -> clean.

## 사람 인수 항목

실제 사용자 음성 TTS listening approval 및 다른 Windows PC CapCut handoff는 외부 입력 대기로 남는다. runbook: `docs/handoffs/2026-07-13-human-acceptance-runbook.ko.md`. 합성 smoke 또는 개발 PC 성공을 사람 승인으로 대체하지 않는다.

## 다음 세션 첫 작업 순서

1. `MediaPackService.install()` direct gate Critical RED test와 VBR RED test를 먼저 추가한다.
2. release contract를 core service/API install gate로 이동하고, CBR 판정을 강화한다.
3. focused tests → independent review → full backend failure (`test_media_controls`)의 root-cause trace/fix or documented baseline classification을 수행한다.
4. full backend green 뒤 official source evidence를 파일별로 저장하고, 실제 300–500 MiB BGM/SFX pack을 ignored `dist/starter-media-pack`에 build한다.
5. install → preview → favorite → materialize → 600-second Korean ingest/SRT/MP4/real CapCut draft smoke → final review/gap/reverse validation → SSOT closeout 순서로 끝낸다.
