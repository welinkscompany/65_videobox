# VideoBox loopback E2E harness lock

> **2026-09-07 전체 점검 정정.** "fake provider endpoint는 deterministic empty key list만 반환한다"는 낡았다 —
> provider/key 경로 자체가 퇴역해 `apps/web/e2e/support/fake-api-server.mjs`에 없다. "외부 호출 0"은 여전히 참
> (`release-gates.mjs:34,41`이 non-loopback 요청을 abort). 나머지(Playwright 1.61.1, Chromium 1228, `127.0.0.1` 바인딩)는 일치.


- `@playwright/test`는 `1.61.1` exact version으로 `apps/web/package-lock.json`에 잠근다.
- lockfile integrity: `sha512-8nKv6+0RJSL9FE4jYOEGXnPeM/Hg12qZpmqzZjRh3qM0Y7c3z1mrOTfFLids72RDQYVh9WpLEfR5WdpNX4fkig==`.
- `playwright` resolved version: `1.61.1`.
- Browser download contract: Chromium revision `1228`, Chrome for Testing `149.0.7827.55`.
- 브라우저 바이너리는 로컬 cache artifact이며 저장소에 커밋하지 않는다. `playwright.config.mjs`는 fake API와 Vite를 `127.0.0.1`에만 열고, E2E는 모든 non-loopback browser request를 abort한다.
- fake provider endpoint는 deterministic empty key list만 반환한다. external/Gemini provider call은 0이다.
