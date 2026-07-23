# Playwright 스냅샷 무결성

이 폴더의 PNG는 Playwright E2E가 만든 검토 산출물이다. `playwright-snapshot-manifest.json`은 정확한 PNG 파일 집합, viewport 크기, bytes와 SHA-256을 고정한다. 검증은 PNG를 만들거나 바꾸지 않는다.

생성 계약은 Chromium, loopback-only fake API fixture, epoch `0`의 고정 시간 계약, `animations: "disabled"`, `caret: "hide"`다. 화면에 시간을 새로 표시하는 E2E를 추가하면 캡처 전에 이 epoch를 적용해야 한다.

검증:

`node e2e/verify-snapshot-manifest.mjs`

PNG를 의도적으로 다시 만든 경우에만 사람이 차이를 검토한 뒤 manifest의 bytes·SHA-256·viewport를 함께 갱신한다. manifest만 갱신해 검토를 우회하면 안 된다.
