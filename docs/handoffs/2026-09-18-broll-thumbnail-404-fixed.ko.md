# INVEST-04 -- broll 영상 썸네일 404, 재현하고 고쳤다

`docs/system-audit-2026-09-10-claude-remediation.ko.md`의 INVEST-04(목록 썸네일
404) 코드 추적 조사를 이어받아, 합성 프로젝트로 실제 재현까지 확인한 뒤 고쳤다.

## 원인

- `services/api/src/videobox_api/routers/assets.py`의 `get_asset_thumbnail`은
  2026-09-17에 IMAGE 자산에 한해 썸네일 파일이 없으면 원본에서 즉석으로 다시
  그려 캐시하는 fallback이 생겼다. **BROLL_VIDEO(영상) 자산에는 이 fallback이
  없었다.**
- 영상 자산의 썸네일은 `packages/core-engine/.../local_pipeline.py`의
  `_try_generate_broll_thumbnail`이 **자산 등록 시점에 딱 한 번** best-effort로
  만든다. 캐시 파일(`derived/thumbnails/{asset_id}.jpg`)은 §10.16 정리 규칙상
  "다시 만들 수 있는 파생물"이라 지우는 대상이다.
- 결과: 등록 시점엔 성공해서 metadata에 `thumbnail_uri`가 남는데, 나중에 캐시
  파일만 정리로 지워지면(원본 영상은 안 지워짐) 실제 파일이 없어져 그냥
  404였다. `browser-readonly-B.json`이 실측한 홈·프로젝트 화면 404가 이
  메커니즘으로 보인다는 게 코드 추적 결론이었다.
- 프론트 쪽도 반쪽이었다: `AppRouter.tsx`의 프로젝트 카드 `<img>`에
  `onError` 핸들러가 없어서, 404가 나면 깨진 이미지 아이콘이 그대로 보였다.

## 재현 (추측을 코드로 옮기기 전에 먼저 확인)

`tests/test_broll_thumbnail_generation.py`에
`test_thumbnail_survives_derived_cache_cleanup_for_broll_video` 추가:
ffmpeg로 진짜 영상 만들기 → broll 자산 등록 → 첫 GET 200 확인 → **캐시
파일만** `unlink()` → 재요청. **RED로 먼저 404를 실물로 봤다**(추측이
아니라 확인):

```
assert second_response.status_code == 200
E   assert 404 == 200
```

## 고친 것

1. `services/api/src/videobox_api/routers/assets.py:614-627` -- 즉석
   재생성 분기 조건을 `AssetType.IMAGE`에서 `(IMAGE, BROLL_VIDEO)`로
   넓혔다. `render_thumbnail_bytes`를 `media_type="broll"`로 재사용
   (이미 있는 함수, 새 렌더 경로를 만들지 않았다).
2. `apps/web/src/app/AppRouter.tsx` -- 프로젝트 카드 `<img>`에
   `onError`로 `thumbnailFailed` state를 세워 이미지를 빼는 fallback을
   추가했다. 404면 깨진 아이콘 대신 그림 없는 카드로 조용히 넘어간다
   (기존 "thumbnail_url 없으면 안 그린다" 분기와 합류).
3. `tests/test_broll_thumbnail_generation.py` -- 위 재현 테스트를 GREEN
   회귀 시험으로 남겼다.
4. `apps/web/src/app/AppRouter.test.tsx` -- `fireEvent.error`로 실제
   onError 경로를 태우는 회귀 테스트
   (`drops a broken project thumbnail instead of showing a broken-image icon`)
   추가.

## 검증

- RED → GREEN: 위 재현 테스트, 최소 수정 후 통과 확인.
- 프론트 GREEN: `AppRouter.test.tsx` 58/58 통과(신규 1건 포함),
  `fireEvent.error`가 실제 React state를 태우므로 시뮬레이션 신뢰도는
  높지만 실제 브라우저 DOM `<img>` 로드 실패 이벤트는 아니다.
- 넓은 검증: 전체 backend pytest(`.venv/Scripts/python.exe -m pytest`,
  독립 실행, `--ignore=tests/test_mcp_server.py`만 제외 -- `mcp` 모듈이
  이 venv에 아예 없는 기존 환경 문제라 내 변경과 무관) --
  **5070 passed, 67 failed, 56 skipped, 1 xfailed, 2 errors**(44분 12초).
  실패 67건을 전부 확인: `test_set_local_model_script.py`(LM Studio 필요),
  `test_smoke_hermes_yujin_creator_flow_script.py`·
  `test_start_hermes_yujin_script.py`(Hermes 컨테이너 필요),
  `test_youtube_import.py`·`test_api_reference_style_import.py`(yt-dlp
  모듈 미설치) -- 전부 이 worktree에 없는 외부 의존성 문제였고, 썸네일·
  assets 관련 실패는 0건. 표본으로 세 파일을 단독 재실행해 같은 실패가
  이 세션의 변경과 무관하게 재현됨을 확인했다.
- **못한 것**: 실제 브라우저 + API 서버 + Postgres 컨테이너 스택으로
  화면에서 밟아 보는 검증은 못 했다 -- API가 컨테이너 스택(postgres 등)을
  요구하고, 이번 세션은 백엔드 단위 재현(ffmpeg 실제 호출) + 프론트
  단위 시험까지만 했다. 다음에 화면으로 직접 확인하려면 `scripts/
  owner-ready.ps1`로 격리 스택을 띄우고 프로젝트 카드에서 실제로
  캐시를 지운 뒤 새로고침해 보면 된다.

## 재사용 원칙

- 재사용 후보: `render_thumbnail_bytes`(이미 `media_type="broll"` 분기를
  갖고 있었다, `library_assets.py`가 먼저 쓰던 함수) -- **adopt as-is**로
  그대로 재사용, 새 렌더 함수를 만들지 않았다.
- 제외: `generate_video_thumbnail`(파일에 직접 써서 반환값이 없는 버전,
  등록 시점 전용) -- 이 자리는 바이트를 반환받아 확장자 판별까지 직접
  하는 기존 이미지 분기 패턴과 맞추려고 `render_thumbnail_bytes` 쪽을
  택했다.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.

## 커밋·푸시

커밋 `504cc72b0`, origin/main과 뒤처짐 없이 fast-forward 병합 후 push
완료(`d2f648032..504cc72b0`).

## 다음 세션 백로그

1. 위 "못한 것" -- 화면(브라우저)에서 실제로 캐시 삭제→404 사라짐을
   확인하는 역방향 검증이 남았다. 급하진 않다(백엔드 재현 + 프론트
   회귀 시험으로 메커니즘과 수정 모두 확인됨).
2. `tests/test_mcp_server.py`가 이 venv에서 `mcp` 모듈 부재로 collection
   자체가 실패한다 -- 이번 세션과 무관한 기존 환경 문제, 별도로
   `.venv`에 `mcp` 패키지가 빠진 것인지 확인이 필요하다.
