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

- **모델은 이미 있다.** `C:\Users\atgro\Documents\comfy\ComfyUI\models\diffusion_models\wan2.1_t2v_1.3B_fp16.safetensors`
  (Wan 2.1 텍스트→영상, 1.3B, fp16) — 새로 받을 것 없다.
- **노드도 이미 있다.** `custom_nodes/`에 별도 확장이 없는데도 ComfyUI 코어
  자체가 Wan을 지원한다 — `comfy/ldm/wan/model.py`, `comfy_extras/nodes_wan.py`.
  **커스텀 노드 설치가 필요 없다.**
- 다만 이 발견은 "모델·노드가 있다"까지다. **VideoBox 쪽 워크플로 JSON·서비스
  코드는 아직 하나도 없다** — `scene_image_service.py`의 `_generate`(정지
  이미지 생성)와 `_still_to_clip`(zoompan 가짜 영상)이 지금 실제로 도는
  전부다. 다음 세션은 여기서부터 시작: Wan t2v/i2v용 워크플로 그래프를
  짜고, `_still_to_clip`을 대체하거나 나란히 두는 새 서비스 메서드를 만드는
  일이 실제 구현 범위다.
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
