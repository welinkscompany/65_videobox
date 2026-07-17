# SFX real-asset acceptance handoff

## 완료

- 실제 SFX asset 없는 추천은 timeline clip으로 materialize되지 않는다.
- 편집 세션의 SFX asset 선택은 `sfx_refresh`로 pending operator review를 만들며, 승인 뒤 partial regeneration의 candidate timeline과 timeline 저장본에 SFX track을 함께 반영한다.
- FFmpeg final MP4와 real CapCut draft에 승인된 SFX가 유지되는 600초 Korean smoke를 추가했다.
- 웹 편집 화면은 효과음 asset ID 저장·해제와 재생성 범위 반영을 지원한다.

## 검증

- frontend: `npm test -- --run` 83 passed, `npm run build` success.
- backend Python 3.12: 632 passed (API 388, non-API 244; 실행 채널 120초 제한 때문에 동일 옵션으로 분할).
- smoke: `scripts/verify-production-readiness-smoke.py` with the real 600-second Korean narration, all 12 checks true; final MP4 SHA-256 `036bc6ccfbcd5aba814e44aceb9b654f41ead6c9613d9ebfd4eb2dc8f672a93e`.

## 다음 goal

실제 사용자 음성 녹음에 대한 human listening approval 또는 서로 다른 실제 10분 프로젝트 3건의 CapCut open/edit/export UX QA 중 하나를 독립 acceptance slice로 진행한다.
