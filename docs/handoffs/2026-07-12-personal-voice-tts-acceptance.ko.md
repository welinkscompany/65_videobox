# VideoBox handoff — 2026-07-12 personal voice TTS acceptance

## 완료

- branch `codex/production-readiness-blocker-slice-1`에서 개인 음성 TTS 후보의 technical acceptance와 pending listening-review 상태를 구현했다.
- 실제 사람의 음성 샘플이 없는 자동 검증은 결정론적 한국어 WAV fixture를 사용한다. 실제 speaker-similarity 합격은 사람이 청취해 승인해야 한다.
- provider failure는 generic 음성 fallback이 아니라 original narration 유지로 처리한다.

## 검증

- frontend: 83 passed, production build success.
- backend: `.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider` → 628 passed.
- 600초 Korean smoke: TTS candidate pending review, approved timeline, SRT, MP4, real CapCut draft 통과; MP4 SHA-256 `6e257a604e05a15963a69554b1541107d999cb74a769b8d073747b81d1b46ba5`.

## 다음 목표

실제 동의된 사용자 음성 샘플을 등록한 뒤 청취 승인 UX와 human acceptance 기록을 수행하거나, 별도 SFX recommendation/materialization slice를 TDD로 진행한다.
