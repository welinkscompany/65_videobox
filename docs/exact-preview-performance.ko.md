# Exact preview 로컬 성능 측정

이 측정은 현재 editing-session의 exact preview cold render와 완료된 generation의 warm cache lookup만 확인한다. provider/Hermes, output approval, CapCut, editing mutation은 호출하지 않는다. 머신 성능과 FFmpeg 상태에 의존하므로 CI 테스트에 넣지 않는다.

## 재현 명령

PowerShell에서 저장소 루트 기준으로 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts\measure_exact_preview_performance.py --enforce
```

스크립트는 임시 local store와 10초·1280×720 local B-roll fixture를 만들고 제거한다. JSON에 `cold_seconds`, `warm_seconds`, 각 기준과 pass 여부를 기록한다. `--enforce`는 cold가 20초를 넘거나 warm cache lookup이 500ms를 넘으면 종료 코드 1을 반환한다. 인자 없이 실행하면 측정값은 출력하되 종료 코드를 성능 결과로 실패시키지 않는다.

2026-07-21 bounded publish-fence 후 최신 재측정 결과는 cold `0.3875s`(기준 ≤`20.0s`), warm `0.0832s`(기준 ≤`0.5s`)였다. 이 값은 10초·1280×720 local B-roll fixture에서 full SHA 재검증과 completed MP4 staging을 SQLite writer lock 밖으로 이동한 현재 구현의 측정값이다.

## 재생 E2E 경계

`apps/web/e2e/exact-preview.spec.mjs`는 tracked local 2초 H.264 MP4와 byte-Range intercept로 metadata load와 native seek을 검증한다. 따라서 browser player와 Range 전달 경계의 회귀는 잡지만, FFmpeg final/proxy composition parity 자체의 증명은 아니다. 그 parity는 backend의 real FFmpeg/ffprobe fixture 검증이 담당한다.
