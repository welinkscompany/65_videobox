# 얼굴 학습은 설정이 아니라 카드 한계에 막혔다

- 작성: 2026-08-22
- 앞 문서: `2026-08-22-videobox-scene-transitions-and-the-frame-rate-trap.ko.md`
- 개발선: `codex/videobox-container-compatibility`

## 한 줄

**ComfyUI 내장 학습 노드로는 32GB 카드에서 FLUX LoRA 학습이 안 된다.** 설정 문제가
아니다. 손잡이를 더 돌리지 마라 — 나는 일곱 번 돌렸고 전부 헛수고였다.

## 왜 안 되는지 (숫자로 확정했다)

요구 메모리를 손잡이마다 쟀다. 한계는 31.84GB다.

| 설정 | 요구 | 결과 |
|---|---|---|
| `training_dtype: bf16`, `checkpoint_depth: 1` | 59.08GB | 터짐 |
| `training_dtype: none` | 54.73GB | 터짐 (dtype이 4.35GB 아꼈다) |
| `checkpoint_depth: 5` | 57.99GB | 터짐 — **깊게 하면 오히려 나쁘다** |
| `offloading: True` | 55.79GB | 터짐 |
| 사진을 512x512로 | 55.16GB | 터짐 |

**사진을 72장→18장으로, 크기도 4분의 1로 줄였는데 숫자가 안 움직인다.** 계산이
맞아떨어진다:

    FLUX.1-dev 12B x 4바이트(fp32) = 48GB + 활성값 ~7GB = 55GB

이 노드는 12B 모델을 fp32로 통째로 올린다. 사진과 무관하다.

## 되는 길 — ai-toolkit (owner 승인 2026-08-22)

`C:\Users\atgro\Documents\ai-toolkit`에 **코드는 받아 뒀다.** 설치가 남았다.

`config/examples/train_lora_flux_24gb.yaml`이 예제로 들어 있다 — **24GB 카드용이라
32GB인 우리 것에서는 확실히 돈다.**

**막힌 자리:** `python -m venv`가 `Python was not found`로 죽는다(Windows 스토어
별칭이 가린다). 전체 경로를 쓰면 된다:

```
C:\Users\atgro\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
```

그다음 torch(cu126) → `requirements.txt`. 끝나면 학습, 그리고
`scripts/owner-path/measure_face_likeness.py`로 시간·닮은 정도 표를 찍는다.
**이 표가 2026-08-21부터 계속 밀린 원래 요청이다.**

## 이 산책에서 나온 것 — 앞으로도 걸릴 자리들

**1. 사진이 지워지지 않고 쌓이고 있었다.** `upload()`가 이름에 무작위 꼬리를 붙여서
돌릴 때마다 18장이 새로 들어갔다. 폴더를 열어 보니 **72장**이었고
`LoadImageDataSetFromFolder`는 폴더를 통째로 읽는다. 학습은 매번 앞선 실패의 사진까지
물고 있었다. 고쳤다(같은 이름 + `overwrite=true`).

**폴더를 한 번 열어 보는 데 3초 걸렸다.** 나는 그 3초를 안 쓰고 설정을 네 번 바꿨다.

**2. `lms unload`만으로는 모델이 안 내려간다.** 몇 초 만에 저절로 다시 올라온다 —
VideoBox 컨테이너의 분석 루프가 1분마다 부르고 LM Studio가 알아서 다시 올린다.
**부르는 쪽을 먼저 멈춰야 한다.** 순서는 `train_face_lora.py` 머리말에 적었다.

**3. 죽은 학습 작업이 큐를 막고 있었다.** 2차 학습(4시간 초과로 포기한 것)이 **아직도
"실행 중"이었다.** 스크립트가 지켜보기를 그만뒀을 뿐 ComfyUI는 안 멈춘다. CPU를 20초에
1초도 안 쓰면서 큐만 잡고 있었다. `/interrupt`가 안 먹어서 ComfyUI를 다시 띄워 풀었다.

**4. ComfyUI 설치본이 둘이다.** 진짜는 `C:\Users\atgro\Documents\comfy\ComfyUI`(42GB,
`flux1-dev.safetensors`가 여기 있다). `C:\Users\atgro\ComfyUI-Installs`는 모델이
비어 있어 중복처럼 보이지만 **owner가 다른 프로젝트에서 쓴다고 명시했다. 지우지 마라.**
나는 이걸 진짜인 줄 알고 띄웠다가 모델 목록이 비어서 알아챘다.

**5. 커밋을 끝을 안 보고 적었다.** `offloading` 실행에서 GPU 100%를 보고 "돈다"고
커밋했는데 그건 터지기 전 몇 분이었다. 다음 커밋에서 정정했다(`2e58ffa5d`).
**돌고 있는 것과 끝난 것은 다르다.**

## 캡컷 벤치마킹 — 대부분 됐는데 아무도 못 봤다

| 항목 | 상태 |
|---|---|
| 위 띠(왼쪽 기둥 제거), 시작 선택창, 흰 톤, 툴바, 스크롤, 프로젝트 화면, 전환 탭 | **됨** |
| 효과 · 필터 · 스티커 탭 | 비어 있음 |
| 문구를 키워드 중심으로 | **안 함** (owner가 시켰는데 못 했다) |

**이번 세션에서 화면을 한 픽셀도 못 봤다.** 브라우저 창이 `5173` 접근을 거부하고
Playwright도 `apps/web`에 모듈이 없어 실패했다. `cd apps/web && npm i` 후 다시 시도하라.

**owner가 막힌 문제가 "어떤 버튼을 눌러야 할지 모르겠다"이다.** 나아졌는지는
**owner가 보셔야만** 알 수 있다. 내가 "됐다"고 적은 것은 그 판단을 대신하지 못한다.
`§4 완료의 정의`가 말하는 그 자리다.

## 디스크 (owner 질문, 2026-08-22)

972GB 사용 / 1,862GB (890GB 남음). **아직 1TB 아래고 여유는 넉넉하다.**
OneDrive가 380.7GB로 압도적 1등이다(클라우드 동기화라 지우면 다른 기기에서도 사라진다 —
손대지 않았다). **사용자 폴더 합 450GB와 실제 972GB 사이의 520GB는 아직 못 셌다** —
숨김 폴더를 안 셌다. 정리 판단은 그것부터 재고 하라.

## 다음 세션이 바로 이어서 할 일

```
CLAUDE.md와 이 인계를 읽어라. ai-toolkit 설치를 마치고 얼굴 학습을 끝낸 뒤,
시간·닮은 정도 표를 만들어라. 그다음 캡컷 화면을 실제로 캡처해서 owner에게 보여라.
```
