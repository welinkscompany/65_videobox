# 남아 있던 2·3·4를 닫고, 리뷰가 찾은 결함까지 정리했다

- 작성: 2026-08-19 (밤)
- **읽는 순서:** 이 문서 → `docs/handoffs/2026-08-19-videobox-verification-guards-and-the-open-four.ko.md`
- 커밋: `9707ae3b`(2번) → `b81ced3f`(3번) → `652a94f7`(4번) → `758e9f85`(리뷰 수정) → `051f6843`(provenance 해시)
- 컨테이너: `758e9f85` 기준으로 재빌드·기동·실화면 검증 완료 (`owner-ready -Mode Start -Rebuild` pass, health 200)

## 2번 — 내레이션 음량 + 무음 B-roll (닫음)

- `amix`에 `normalize=0`이 빠진 자리가 인계에 적힌 353행 말고 **세 곳 더 있었다**
  (음악 믹스 두 갈래·효과음 믹스, 옛 1125·1127·1167행). 무음 음악을 깔아도
  내레이션이 6dB 내려가는 것을 **실제 mp4의 peak dBFS로 재서** 확인하고 고쳤다.
- 무음 B-roll(오디오 스트림 없는 원본) + `원본 소리 살리기` 가드를 **두 렌더 경로
  모두**에 넣었다. 계획 경로는 없는 `[N:a]`를 그래프에서 건너뛰고, 조각 경로는
  무음을 실어 조각들의 스트림 모양을 맞춘다(concat은 첫 조각을 기준 삼는다 —
  무음이 앞에 오면 막히거나 뒤 소리가 사라졌다).
- 리뷰에서 하나 더 나왔다: **설명 카드(오버레이) 재인코딩이 `-an`이라, 오버레이가
  하나라도 있으면 소리 살리기 믹스가 통째로 막혔다.** 믹스가 오버레이 얹기 **전**
  파일에서 소리를 가져오게 고쳤다.
- 재발 방지: `tests/test_ffmpeg_final_renderer.py`의
  `test_every_amix_line_in_the_renderer_keeps_normalize_off`가 소스를 직접 훑는다.
  ffmpeg 없는 기계에서도 돈다.

## 3번 — 자막 프리셋 왕복 + 포맷 템플릿 (닫음)

- **프리셋 왕복 단절의 원인:** 저장할 때 `fromSnapshot`(화면 이름으로 변환)을 거친
  값을 저장하고, 적용할 때 또 `fromSnapshot`이 스냅샷 이름을 기대했다. 저장한
  프리셋을 적용하면 **아무 일도 일어나지 않았다.** 지금은 스냅샷(정본 이름)을
  그대로 저장하고 변환은 적용 때 한 번만 한다. 실화면에서 글자 크기 30→적용→54
  복원까지 확인.
- **포맷 적용이 항상 500이던 원인:** 라우터가 자막 스타일 경로에 없는
  scope(`all`)와 `segment_ids=None`을 넘겼다. `whole_project`(장면 없으면
  `project_default`)로 고치고, 실제 컨테이너에서 저장→적용 200→undo 복원까지
  확인했다. 404·422만 확인하던 테스트에 **성공 경로 왕복 테스트**를 추가했다.
- 빈 포맷(자막 모양 없는 편집본에서 뜬 것)을 적용하면 기본값이 손본 장면 모양을
  전부 덮어쓰던 결함도 리뷰에서 나와 400 + 쉬운 말 안내로 막았다.

## 4번 — 화면이 거짓말하는 것들 (6건 전부 닫음)

1. 의미검색 0건/불일치인데 `SEMANTIC_MATCH` → 실제로 점수가 붙은 자산이 있을
   때만 `뜻으로 찾음`.
2. `hsl(var(--token))` 무효 선언 **17곳(선언 13줄)** → `var()`로. 가드 테스트가
   이제 `src` 아래 **모든 css**를 훑는다(`theme-tokens.test.ts`).
3. 설정 저장 실패가 조용함 → 이번 세션에는 적용하되 "저장하지 못했어요 + 다음
   행동"을 말한다. updater 안 부수효과·closure 읽기(같은 batch 두 토글 중 하나
   유실)도 리뷰에서 나와 effect로 옮겼다.
4. `vb-preview-stage__elsewhere` CSS 부재 → status 줄과 같은 규칙 + 전체화면 밝은
   글자.
5. `searchLibraryAssets` 호출부 없음 → 라이브러리 화면의 종류 탭+검색어에 연결.
   **연결하고 보니 응답 행에 화면이 필터하는 필드(media_type·lifecycle·id)가
   없어서 전부 걸러지는 2차 거짓말이 있었다** — 서버가 그 필드를 채우고
   (`semantic_match` 표시 포함), 화면은 다룰 수 있는 행만 남기고 남은 행 기준으로
   배지를 말한다. 촬영본 색인 조각(`source_segment_id` 행)은 촬영본 정리 화면
   계약이라 dedup에서 제외 — 여기 손대면 `test_api_footage_organizer.py`가 깨진다.
6. `verify_container_stack.ps1`이 합쳐져 사라진 `videobox-api`·`videobox-web`을
   요구 → `videobox-postgres`+`videobox-workspace`로 갱신, 루프백 검사 포함.
   compose와 스크립트의 서비스 이름 대조 테스트를 `test_compose_contract.py`에
   추가했다.

## 코드리뷰 (8각도) — 10건 보고, 9건 수정, 1건 이관

위에 녹인 것 외: ffprobe 헬퍼 4벌 중복 → 캐시 달린 `_has_stream` 하나로 통합
(클립 30개가 같은 원본을 30번 재던 것), 죽은 `audio_items` 제거, 검색 배지를
label 밖으로(검색칸 accessible name 오염), 프리셋 스냅샷 어휘 통일 +
`safe_area_enabled` 동승 + `horizontal_align` 허용목록.

**이관 1건:** 포맷 적용이 화면 크기(width/height)를 버려 `keep_output_size`가
no-op이고 `applyFormatTemplate`을 부르는 화면이 없다 — **원래부터 있던 설계
격차**라 이번 범위에서 빼고 병렬 작업으로 넘겼다(아래).

## 전체 pytest — 단독 실행 결과

**3,664 통과 / 6 실패 / 53 skip (31분 35초).** 도중에 아무것도 커밋하지 않았다.

- 5건: `test_editor_ui_source_provenance.py` — ProductShell.tsx를 고쳤는데
  `docs/oss/editor-ui-source-map.json`의 해시 핀 갱신을 잊은 것(기억에 있는
  함정 그대로). `051f6843`으로 갱신, 21개 전부 통과.
- 1건: `test_api_footage_organizer.py::test_yujin_footage_interpretation_is_bound_to_current_proposal_and_does_not_mutate`
  — **단독 재실행은 통과.** 이번엔 실행 중 커밋도 없었으므로 순수한 테스트 격리
  문제로 보인다. `-q | tail`로 돌려 **트레이스백이 안 남았다** — 다음에 전체를
  돌릴 때는 `--tb=short`를 남겨라. 다음 사람 확인 목록에 넣는다.

웹은 영향 스위트 통과(라이브러리·인스펙터·프리뷰·앱·스타일 280+, 에디터 588),
`tsc --noEmit` 깨끗. e2e는 이번에 돌리지 않았다.

## 병렬 작업 4건 — 진행 중 (owner 승인, 2026-08-19 밤)

격리 worktree에서 topic 브랜치로 작업 중. **끝나면 개발선에 병합하고 focused
테스트 재실행 후 푸시·재빌드해야 한다.** 각 브랜치는 `codex/videobox-container-compatibility`
(051f6843)에서 분기.

1. `feat/audio-gain-slider` — 음악·효과음 클립 "소리 크기" 슬라이더(내부 gain_db,
   화면엔 쉬운 말만). 백엔드 반영 경로는 이미 있음.
2. `fix/workbench-test-rejections` — 워크벤치 vitest의 unhandled rejection 24건.
3. `fix/format-output-size` — 위 이관 건. 반영하거나, 화면 약속을 동작에 맞추거나.
4. `feat/yujin-thumbnail-prompts` — 유진이 썸네일 **이미지 생성 프롬프트 5개**를
   추천(생성은 owner가 GPT·Flux/ComfyUI에서). owner 컴퓨터에 Flux·ComfyUI 있음,
   RAM 128GB 교체 예정. 로컬 이미지 생성은 **하지 않기로 함** — 프롬프트 추천까지만.

## owner와 나눈 방향 논의 (2026-08-19 밤, 결정 대기 아님·기록용)

owner가 도형·표·이미지 추가와 로컬 이미지 생성을 물었다. 정리한 답:
표·이미지·설명카드·훅타이틀 오버레이는 **부품이 이미 있고 화면 연결만 없다**
(1순위 후보). 도형은 신규(정지 도형까지만 권장 — 모션그래픽은 계획서 명시 제외).
로컬 이미지 생성은 별도 인프라 결정이라 측정 후. 썸네일은 위 4번 병렬 작업으로
프롬프트 추천 방식 확정.

## 다음 사람 확인

- 병렬 4건 병합·검증·푸시·재빌드 (위)
- footage interpretation 테스트 격리 문제 (위, 트레이스백부터)
- 이전 인계의 owner 확인 3건 그대로: 미리보기 전체화면 실제 진입, 소리 살린
  B-roll 실제 청취, 임시 프로젝트 `project-92f12825`·`project-8536fd6d` 삭제 여부
  (92f12825는 이번 유진 대화 테스트로 대화 기록 2건이 생겼다)
- `my-project`의 포맷 적용 실험은 undo로 복원했고 검증용 템플릿은 지웠다.
  `project-92f12825`에 검증용 프리셋 `내 모양 1`이 하나 남아 있다(무해, 실사용 가능)
