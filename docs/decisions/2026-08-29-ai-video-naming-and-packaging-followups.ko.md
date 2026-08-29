# AI 영상 생성 방향 · 설치형 재확인 · "미디어" 이름 충돌 — 후속 결정

- 결정 상태: **approved**
- 결정 시각: 2026-08-29
- 승인자: owner (루이스 대표님)
- 배경: 같은 날 앞서 나온 `2026-08-29-capcut-full-structure-and-dark-theme.ko.md`가
  남긴 "다음 세션에서 결정" 항목들 중 방향성 결정 세 건을 여기서 마무리한다.

## owner가 답한 것 (AskUserQuestion 구조화 질문에 대한 답)

> 진행 순서 — "둘다 하는데 너가 최적화방안으로 자율모드로 개발하자"
> (다크 테마 구현과 첫 화면 재구성 순서를 스스로 판단해 자율로 진행하라는 뜻)
>
> AI 영상 생성 방향 — "로컬 비디오 모델 (ComfyUI 확장)"
>
> 설치형 패키징 — "보류 유지 (권장)"
>
> "미디어" 이름 충돌 — "전체 메뉴만 새 이름"

## 1. AI 영상 생성(진짜 동영상) 방향 — 로컬 비디오 모델

**클라우드 API(힉스필드·클링 등)가 아니라 로컬 비디오 모델(ComfyUI 확장)로 간다.**
비용·외부 전송 승인이 필요 없고, owner의 RTX 5090에서 계속 무료로 돈다.

**이 결정은 방향 승인이지 구현 완료가 아니다.** 2026-08-29 세션에서 실제로 검증한
"AI 영상 생성"은 정지 이미지 확대/축소(zoompan)였고, 진짜 동영상 생성(예:
AnimateDiff·Stable Video Diffusion류 ComfyUI 노드)은 아직 조사도 시작 전이다.
`implementation-plan.ko.md` §4의 제외 목록(전문 색보정·고급 마스크 등)과는 별개로,
이 기능 자체가 이번 결정으로 **범위 안에 들어왔다** — 이전에는 "범위 밖"이었다
(2026-08-28 결정 참고).

구현 시작 전에 필요한 것 (다음 세션 몫):

**재사용 게이트 조사 결과(2026-08-29, 이어진 세션, 읽기 전용 확인만 함 —
파일 다운로드·설치는 owner 자신의 몫이라 손대지 않았다):**

**정정(같은 세션, 몇 시간 뒤): 아래 "받을 것 없다"는 처음에 성급하게 적은
것이고 틀렸다.** 체크포인트만 보고 판단했지 텍스트 인코더·VAE까지는 안
살폈다 — 다시 살펴보니 실제로 부족한 것이 있다.

- **영상 모델 체크포인트는 있다.** `models/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors`
  (Wan 2.1 텍스트→영상, 1.3B, fp16).
- **ComfyUI 코어 노드도 있다.** `custom_nodes/`에 별도 확장 없이 코어 자체가
  Wan을 지원한다 — `comfy/ldm/wan/model.py`, `comfy_extras/nodes_wan.py`
  (`WanImageToVideo`는 `start_image`가 optional이라 이미 만들어 둔 장면
  그림을 그대로 넣어 이미지→영상으로 쓸 수 있다). 영상 저장 노드도 코어에
  있다(`comfy_extras/nodes_video.py`의 `SaveWEBM` — `SaveImage`와 같은 방식으로
  `/history`·`/view`에서 꺼낼 수 있어 기존 `ComfyUIHTTPTransport` 재사용 가능).
- **텍스트 인코더가 미완성이다.** `models/text_encoders/umt5_xxl_fp16.safetensors.2nb_9owj.part`
  — `.part` 확장자가 그대로 남은 **중단된 다운로드**다(2026-08-06 날짜, 1.74GB
  중 어디까지 받혔는지 불명).
- **Wan 전용 VAE가 아예 없다.** Wan은 FLUX가 쓰는 `AutoencoderKL`(`ae.safetensors`)이
  아니라 별도 `WanVAE` 클래스가 필요하다(`comfy/ldm/wan/vae.py`). `models/vae/`에는
  `ae.safetensors`뿐이고 Wan용 파일(`wan_2.1_vae.safetensors`류)은 없다.
- 다운로드·설치는 owner의 로컬 ComfyUI 설정이라 **owner 승인 없이 손대지
  않았다**(파일 다운로드는 명시 승인 필요 항목). 다음 세션이 이 작업을
  시작하려면 먼저 owner에게 두 파일(완결된 UMT5 텍스트 인코더, Wan VAE)이
  필요하다고 알리고 받아도 되는지 물어야 한다.
- VideoBox 쪽 워크플로 JSON·서비스 코드는 모델 준비와 별개로 **아직 하나도
  없다** — `scene_image_service.py`의 `_generate`(정지 이미지 생성)와
  `_still_to_clip`(zoompan 가짜 영상)이 지금 실제로 도는 전부다. 그래프
  설계(`ComfyUIImageGenerationProvider._graph`와 같은 자리)는 모델 파일이
  갖춰지지 않아도 미리 짤 수 있다.

## 후속 — owner 승인으로 파일 받고 실제로 검증함 (같은 날, 2026-08-29 세 번째 이어진 세션)

owner가 "comfyui 추가 파일받고, 원래 만든거외에 별도로 만들자. 그리고 gif
이미지 만드는 기능도 해야되"라고 명시적으로 지시. 파일 둘을 huggingface에서
받고(UMT5 텍스트 인코더 11.37GB, Wan VAE 253.8MB, 둘 다 정확한 크기로 완결),
`ComfyUIVideoGenerationProvider`의 그래프를 owner의 실제 ComfyUI에 직접 걸어
**진짜로 검증했다** — 추정이 아니라 실측이다.

**실측 결과:**
- 작은 설정(512x288·17프레임·8스텝): 약 12초. 실제 webm(vp9, 512x288, 1.42초) 생성 확인.
- **실제 제품 기본값(1920x1080·81프레임·20스텝): 약 18분(1067초).** 실제
  webm(vp9, 1920x1080, 3.375초 분량, 1.38MB) 생성 확인 — 진짜 GPU 추론이지
  가짜가 아니다.
- mp4 변환(h264)·GIF 변환(팔레트 2단계) 둘 다 이 실제 출력 파일로 검증
  완료 — 각각 1초 미만.

**제품적 함의: 18분은 매우 느리다.** "빈 장면 모두 AI로 채우기"(자동채우기,
`CreationInterview.tsx`의 `autoFillRemainingGapsWithAi`) 흐름에 이대로 넣으면
장면 하나당 18분씩 걸려 여러 장면을 자동으로 채우는 용도에는 안 맞는다.
그래서 **별도 기능**(owner 지시)으로 짰다 — `SceneVideoService`는
`scene_image_service.py`·자동채우기 흐름을 전혀 건드리지 않고, 장면 하나를
owner가 명시적으로 골라 만드는 별개 문(`POST /api/projects/{id}/scene-videos`)이다.

**만든 것 (커밋 예정):**
- 백엔드: `packages/core-engine/.../scene_video_service.py`(새 서비스, mp4·GIF
  둘 다 만듦), `services/api/.../routers/scene_videos.py`(비동기 202+`job_id`
  폴링, 유튜브 학습과 같은 패턴), `provider_factories.py`·`main.py`·`models.py`
  연결.
- **GIF는 새 자산 종류를 안 만든다** — `AssetType.IMAGE`로 등록하면
  `LibraryPreviewPane.tsx`가 이미 그림 자산을 `<img src=...>`로 그리고 있어서
  애니메이션 GIF도 브라우저가 그냥 재생한다. 화면 코드 한 줄도 안 고쳤다.
- 테스트: `test_scene_video_service.py`(8건, 진짜 ffmpeg로 mp4·GIF 확인) +
  `test_api_scene_videos.py`(6건) + `test_video_generation_config.py`(4건) +
  `test_comfyui_video_generation_provider.py`(5건) = 백엔드 전체 pytest에 23건 추가.

**아직 안 한 것 (다음 세션 몫):**
- 프론트엔드 진입점(버튼)이 없다 — 지금은 API만 있고 화면에서 부르는 곳이
  없다. `CLAUDE.md` §4의 "부품과 제품은 다르다"가 정확히 이 상태를 가리킨다.
- `VideoGenerationConfig.enabled` 기본값은 여전히 `False`다 — 이제 실제로
  도는 것을 확인했으니 owner가 켜기로 결정하면
  `VIDEOBOX_VIDEO_GENERATION_ENABLED=true` 환경변수 한 줄이면 된다
  ([[videobox-local-model-swap-is-config-not-code]]와 같은 패턴).
- 18분이라는 실측 시간을 owner에게 보여주고, 이 정도 대기 시간이 제품에
  맞는지 다시 판단받아야 한다(품질을 낮춰 더 빠르게 할지, 이대로 둘지).
- 컨테이너 CPU 제약(2코어)이 정지화면 확대에서도 문제였다(`-threads 2` 수정,
  2026-08-29 커밋 `6ce7b51db`) — 실제 동영상 생성은 훨씬 무거우므로 리소스 요구량을
  먼저 실측한다.
- 생성 시간이 길어지면 nginx 프록시 330초 타임아웃과 부딪힐 수 있다 — 유튜브
  학습 기능을 비동기로 바꾼 패턴(`BackgroundTasks` + `job_id` 폴링, 2026-08-29
  이어진 세션 커밋 `4029f9baf`)을 그대로 재사용할 수 있는지 먼저 검토한다.

## 2. 설치형(Electron/Tauri) 패키징 — 보류 유지

owner가 "보류 유지(권장)"를 선택했다. `2026-08-29-capcut-full-structure-and-dark-theme.ko.md`의
"확인된 것 — '웹이라 안 된다'는 전제는 틀렸다" 절이 여전히 유효하다 — VideoBox 편집
작업판은 이미 `react-resizable-panels`로 마우스 드래그 크기조절을 갖고 있다.
**이 문서로도 설치형은 승인되지 않는다.** 구조·다크 테마 작업이 끝난 뒤 owner가
직접 화면을 보고 다시 논의하기로 한 것은 그대로다.

## 3. "미디어" 이름 충돌 — 전체 메뉴만 새 이름("자료실")

세 자리 중 **전체 메뉴의 공용 라이브러리(구 `/library`, 프로젝트를 넘나드는 자산
보관소)만** 이름을 바꾼다. 프로젝트 단계 탭의 "미디어"(그 프로젝트의 자산)와
편집기 도크 탭의 "미디어"(편집 중 자산 브라우저)는 **그대로 "미디어"로 남는다** —
owner는 그 둘을 문제로 보지 않았다.

새 이름: **"자료실"**. "보관함"은 이미 프로젝트 보관·복원 기능이 쓰고 있어(첫
화면의 "보관함 보기" 단추) 겹치는 이름으로 새로 쓰지 않았다.

바뀐 자리 (전체 메뉴·전역 화면 껍데기 문구만, 화면 내부 콘텐츠는 그대로):
- `apps/web/src/features/shell/TopBar.tsx` — `globalMenuItems`의 `library` 항목
- `apps/web/src/app/routeManifest.ts` — `/library`의 `screenName`·breadcrumb,
  `/footage`의 상위 breadcrumb
- `apps/web/src/app/ProductShell.tsx` — `section === "library"`일 때의 화면 이름
- `apps/web/src/features/library/LibraryPage.tsx` — 스크린리더 전용 페이지 이름표

관련 테스트(`AppRouter.test.tsx`·`ProductShell.test.tsx`·`top-bar.test.tsx`·
`routeManifest.test.ts`)도 같은 범위로만 갱신했다 — 프로젝트 단계·편집기 도크의
"미디어" 검증은 손대지 않았다.
