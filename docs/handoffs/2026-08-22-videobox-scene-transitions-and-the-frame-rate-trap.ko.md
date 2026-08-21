# 장면 전환이 생겼다 — 그리고 로컬만 초록이던 함정

- 작성: 2026-08-22
- 앞 문서: `2026-08-21-videobox-top-bar-says-the-shape.ko.md`
- 개발선: `codex/videobox-container-compatibility`

## 한 줄

캡컷 왼쪽 패널의 없는 넷 중 **전환**을 만들었다. `xfade` 여섯 개를 골라
편집기에서 고르고 실제 mp4에 그려지는 데까지 닫았다. **길이는 1초도 안 움직인다.**

## 무엇을 만들었나

| 층 | 어디 |
|---|---|
| 목록·검증 | `packages/core-engine/src/videobox_core_engine/transitions.py` (새 파일) |
| 클립에 싣기 | `timeline-schema/models.py`의 `TimelineClip.transition` |
| 계획 | `composition_plan.py`의 `CompositionItem.transition` |
| 세션 | `editing_session.py`의 `update_segment_transition` (`segment["transition_in"]`) |
| API | `PATCH .../segments/{id}/transition` |
| 화면 | 편집 항목의 `앞 장면에서 넘어오기` |
| 렌더 | `ffmpeg_final_renderer.py`의 `build_plan_filter_graph` |

고른 여섯: `fade`(서서히 겹치기) · `fadeblack`(검게 저물기) · `dissolve`(흩어지며
넘기기) · `wipeleft`(왼쪽으로 쓸어내기) · `slideup`(위로 밀어올리기) ·
`circleopen`(원으로 열기).

**1,137개를 만들지 않은 이유는 §4.1.1이 이미 적어 두었다** — 그건 효과가 아니라
캡컷 서버 자원의 이름표다. 여섯은 *생김새 갈래*가 겹치지 않게 골랐다(겹침/쓸기/
밀기/모양). 방향 변종(`wiperight` 등)은 뺐다 — `TRANSITION_CATALOG`에 한 줄
더하면 렌더러는 손댈 것이 없다.

## 렌더 경로 둘 — 어느 쪽을 고쳤나

**지시받은 대로 먼저 둘을 찾았고, 결론은 지금 하나로 합쳐져 있다는 것이다.**

- **합성 계획 그래프** — `_render_composition_plan_to_mp4` → `build_plan_filter_graph`.
  **완성본과 정확 미리보기가 둘 다 이쪽이다.** 둘 다 `composition_plan`을 넘기므로
  같은 함수로 들어온다(`local_pipeline.py:556`, `:2177`). **여기를 고쳤다.**
- **조각 추출 + concat** — `render_timeline_to_mp4`를 `composition_plan` **없이**
  부를 때만 탄다. 지금 제품 경로에는 그런 호출이 없고 테스트만 쓴다.
  **여기는 안 고쳤다.** 대신 전환이 실린 타임라인이 들어오면 **거절한다** —
  전환 없는 mp4를 성공이라고 돌려주는 것이 이 저장소가 두 번 데인 자리다.

## 길이를 어떻게 맞췄나 (지시가 반드시 적으라고 한 것)

**아무것도 안 움직인다. 전체 길이·클립 시각·자막 위치 전부 그대로다.**

지시는 "`xfade`는 클립을 겹치므로 전체 길이가 줄어든다"고 경고했다. **이 저장소에서는
그렇지 않다** — 여기는 concat 모델이 아니라 **검은 캔버스 위에 각 클립을 자기
타임라인 시각(PTS)에 얹는** 오버레이 모델이고, 겹침을 이미 지원한다
(`test_broll_dissolve.py`가 같은 사실 위에 서 있다).

그래서 이렇게 넣었다.

- 전환은 들어오는 클립 B의 **첫 `d`초 안에서만** 일어난다. 구간은 `[T, T+d]`.
- 그 구간에 `xfade(앞 장면의 남은 원본, B의 앞부분)`을 얹는다.
- **A쪽 재료는 타임라인이 아니라 원본 뒷부분**(`source_out_sec` 이후)에서 빌린다.
  타임라인에서 빌리면 A의 마지막 구간이 두 번 보인다.

치르는 값은 하나다: **앞 장면 원본이 모자라면 마지막 프레임이 `d`초 동안 멎는다.**
`tpad=stop_mode=clone`이 맡는다.

## 가장 비싸게 배운 것 — 로컬은 전부 초록인데 실물만 터졌다

전환을 켠 미리보기가 컨테이너에서 **실패**했다. 단위 테스트 19개는 전부 초록이었고
개발 기기에서 실제 mp4까지 나왔다. 원인:

```
The inputs needs to be a constant frame rate; current rate of 1/0 is invalid
```

`xfade`는 **고정 프레임률**이 아니면 거부한다. 내가 넣은 `settb=AVTB`가 프레임률을
`1/0`(모름)으로 지웠다. **개발 기기의 ffmpeg 8.1은 통과시키고 컨테이너의 7.1은
거부한다.**

고침: `settb`를 빼고 **`fps`를 사슬 맨 끝**에 둔다(`trim`·`setpts`가 프레임률
정보를 지우므로). `test_scene_transitions.py`가 문자열로 못박는다.

**교훈 두 개.**

1. **ffmpeg 판이 다르면 같은 그래프가 다르게 거절된다.** 개발 기기 8.1, 컨테이너 7.1.
   필터를 새로 쓰면 **컨테이너에서 한 번은 돌려 봐야 한다.**
2. **오류 문구가 잘려서 원인이 안 보인다.** `FinalRenderError`가 `stderr[-800:]`만
   싣는데 진짜 이유는 **맨 앞줄**에 있었다. 꼬리만 보면
   `Could not open encoder before EOF` / `-22`만 보이고, 그건 예전의 스레드 고갈과
   똑같이 생겼다 — 실제로 그쪽으로 한참 헛짚었다.
   **막히면 컨테이너에서 ffmpeg를 직접 돌려 전체 stderr를 봐라.**

곁다리: 수동으로 ffmpeg를 돌릴 때 `-filter_complex_threads`/`-filter_threads`를
빼면 같은 그래프가 `-11 (Resource temporarily unavailable)`로 죽는다. 렌더러는
이미 붙이고 있다. **수동 재현할 때 이 두 개를 빼먹으면 없는 병을 쫓게 된다.**

## 또 하나 — 원본을 다 쓴 앞 장면

앞 장면이 원본을 **끝까지 다 썼으면** 빌릴 프레임이 한 장도 없다. 이때 ffmpeg는
**실패하지 않는다** — 성공(0)으로 끝나고 길이도 맞는데 **전환만 조용히 사라진다.**
실측으로 확인했다(`tpad`가 붙들 프레임이 없어서다).

그래서 렌더러가 원본 길이를 **재서** 마지막 프레임 자리를 넘긴다
(`TransitionSources.outgoing_start_sec`). 회귀 시험이 있다.

## 검증한 것

- `scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory` 전 항목 PASS
- **실제 프로젝트(`project-318cc020`)에서 브라우저로 밟았다.** 편집기 →
  2번째 장면 선택 → `왼쪽으로 쓸어내기` → `넘기기 저장` → 서버에
  `transition_in`이 남고 `session_revision`이 올라감(화면이 아니라 **서버에서** 확인)
- **첫 장면에는 넘기기 칸이 아예 안 뜬다**(앞 장면이 없으므로). 실물로 확인
- **완성본 mp4를 만들어 프레임을 뽑았다** — 4.60초 파랑(1장면) → 5.20/5.50/5.80
  오른쪽에서 왼쪽으로 쓸려 오는 경계 → 주황(2장면). **눈으로 확인**
- **길이 25.000초로 그대로**(전환 없을 때와 동일). 자막 위치도 안 밀림
- `npm --prefix apps/web test -- --run` 1226개 전부 통과, `npx tsc --noEmit` 깨끗
- 전환 관련 pytest 19 + 7 + 2개 통과

## 검증하지 못한 것 — 나눠서 적는다

- **완성본(final render)은 실물로 못 만들었다.** `확인과 내보내기`가 **검토 승인
  게이트**에 막혀 있고(설계대로다), owner의 실제 프로젝트에서 그 승인을 대신
  누르지 않았다. 대신 **정확 미리보기**로 확인했다 — `_render_composition_plan_to_mp4`
  로 들어가는 **같은 함수**이고 같은 `build_plan_filter_graph`를 쓴다.
  완성본 경로만의 차이(자막 굽기, 최종 인코딩 설정)는 **실물로 안 밟혔다.**
- **여섯 중 `wipeleft` 하나만 실물로 봤다.** 나머지 다섯은 이름만 바뀌는
  같은 자리라 단위 시험으로만 확인했다.
- **생김새 판단은 owner 몫이다.** 프레임은 뽑아서 봤지만 "이 여섯이 쓸 만한가",
  "0.5초가 적당한가"는 실제로 영상을 만들어 봐야 안다.
- **전환 길이를 화면에서 못 고친다.** 지금은 0.5초 고정이고, 이미 값이 있으면
  그 값을 지킨다. 칸을 하나 더 놓을지는 owner 판단.
- **CapCut 내보내기에는 안 붙였다.** `pycapcut_adapter.py`는 여전히 전환을 하나도
  얹지 않는다(§4.1.1 그대로). 이번 범위 밖.

## 다음 사람이 알아야 할 것

- **유진 추천은 아직이다.** 이번 범위가 "실제로 렌더되는 것까지"였다.
  데이터는 준비돼 있다 — `transition.chosen_by`가 `owner`/`yujin`을 구분하고
  세션·타임라인·계획·화면까지 그 값이 살아서 간다.
- **화면 목록과 렌더러 목록이 두 벌이다.** `sceneTransitions.ts`와 `transitions.py`.
  `tests/test_scene_transition_catalog_matches_the_screen.py`가 둘을 맞대어 본다.
  한쪽만 고치면 거기서 걸린다.
- **에이전트 worktree는 낡은 `main`에서 시작한다** — 이번엔 463 커밋 뒤였다.
- **compose 프로젝트 이름이 worktree마다 같다(`65_videobox`).** 다른 에이전트
  worktree가 `owner-ready.ps1 -Rebuild`를 돌리면 **내 컨테이너를 덮어쓴다.**
  이번에 실제로 겪었다 — `owner-ready`는 PASS인데 컨테이너 안 코드는 남의
  worktree 것이었다. 확인 방법:

  ```
  docker inspect 65_videobox-videobox-workspace-1 --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
  ```

  **띄운 뒤 이 한 줄로 기반을 확인하고 시작하라.** 안 하면 남의 코드를 내 코드로
  믿고 검증한다.
- 이 worktree에도 `.venv`·`node_modules`·`.env.container`가 없어서 직접 만들었다
  (앞 인계와 같음).
