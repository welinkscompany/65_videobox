# 세로 배경 채우기(blur/검정) 판단을 여백 크기 기준값으로 일반화

**이 문서가 2026-09-17 세션 전체의 마지막 인계다.** 이 세션은 세 가지를
순서대로 했다:

1. LM Studio 재부팅 뒤 `<think>` 누출로 실제 채팅이 전부 죽어 있던 것을
   찾아 고침(`2026-09-17-think-block-outage-and-ambiguous-confirmation-
   fixed.ko.md`에 상세).
2. 애매한 확인 문장("그걸로 적용해줘") 거짓 긍정 고침 — 같은 문서.
3. **세로 배경 채우기 일반화(이 문서의 본론, 아래).**

세 가지 다 실물로 확인했고, 전체 backend pytest는 두 단계 모두 단독
실행했다(마지막 결과는 아래 §검증). 커밋 6개(문서 포함), `§10.21` 규정대로
"논리 단위 닫힘 + 전체 시험 초록" 시점에 `origin/main`이 이 브랜치의
조상임을 확인(`git merge-base --is-ancestor origin/main HEAD`)한 뒤
순수 fast-forward로 `origin/codex/videobox-container-compatibility`와
`origin/main` 둘 다 push 완료.

앞 인계(`2026-09-17-think-block-outage-and-ambiguous-confirmation-fixed.
ko.md`)에 이어, 대표님이 세로 배경 채우기를 장면마다 LLM이 판단하게
하면 어떠냐고 물었다. 코드를 확인해 보니 이미 "제목 띠 유무"로 갈리는
결정론적 로직이 있었고, 그 판단을 낳은 진짜 잣대(여백 크기)로
일반화하자고 제안드렸다 — 승인받아 진행했다.

## 무엇을 바꿨나

`packages/core-engine/src/videobox_core_engine/output_variants.py`의
`_vertical_fill_fit`이 `has_title_band: bool` 대신 `box_aspect: float`을
받는다. 원본(가정 16:9)을 그 화면비 상자에 잘리지 않게 담을 때 남는
여백 비율(`_padding_fraction`)을 계산해서, 50%(`_BLUR_PADDING_THRESHOLD`)를
넘으면 `blur`, 아니면 `fit`(검정)을 고른다.

- 숏폼 영상 띠(1.3:1): 여백 26.9% → `fit`(검정) — 기존과 동일.
- 일반 세로(9:16): 여백 68.3% → `blur` — 기존과 동일.
- 제목 띠가 있을 때는 캔버스 전체가 아니라 `shorts_layout.shorts_geometry`가
  계산하는 **영상 띠 안쪽**의 화면비를 재사용해서 넣는다(새 계산을 만들지
  않고 이미 검증된 함수를 재사용 — 같은 로직 두 자리 함정을 피함).

`_filled_broll_controls`, `_fill_frame_for_vertical_session`,
`_fill_frame_for_vertical_variant`도 같은 파라미터로 바꿨고,
`build_variant_timeline_payload`/`variant_render_session`(실제 캔버스
크기·제목 유무를 아는 두 호출자)이 `_video_box_aspect`로 실제 화면비를
계산해서 넘긴다.

## 왜 장면별 LLM 판단이 아니라 이 방향인가

갈리는 기준이 "가독성"이 아니라 "여백이 얼마나 큰가"였다 — 여백이 크면
검정이 화면 절반 넘게 시커멓게 보여서 블러를 쓰고, 작으면 검정이
자연스럽다(참고 숏폼 4개 전부 검정). 이 크기는 이미 코드가 아는 값(캔버스
크기, 제목 띠 유무)에서 결정론적으로 계산되므로, 장면마다 LLM을 불러
판단할 필요가 없었다.

## 검증

**RED→GREEN(TDD)**: 새 함수 이름(`_padding_fraction`, `_video_box_aspect`)을
먼저 테스트에 적고 ImportError로 실패하는 것을 확인한 뒤 구현했다.

**단위·통합 시험**: `tests/test_vertical_short_keeps_the_sides.py`에 4건
추가(계산식이 두 실측값 26.9%/68.3%를 정확히 재현하는지, 경계값 근처
동작, `_video_box_aspect`가 제목 있음/없음 각각 맞는지). 기존 시험은
**하나도 안 고쳤다** — `tests/test_shorts_layout.py`의 실측 케이스
(`test_the_title_band_turns_the_blurred_backdrop_back_off` 등)를 포함해
관련 파일 5개, 138건 전부 그대로 통과했다 — 이름 붙은 특례를 없앤 것뿐,
결과값은 안 바뀌었다는 뜻이다.

**코드리뷰(medium)**: 이번엔 결함 없음(빈 배열로 보고).

**전체 backend pytest(단독 실행)**: **5132 passed, 56 skipped, 1 xfailed,
실패 0건**(38분 36초). 이번 세션이 추가한 시험 5건(local_qwen 앵커링 1건 +
여백 기준값 4건)만큼 정확히 늘었다 — 회귀 없음.

**실제 렌더로 눈으로 보는 확인은 못 했다.** `/output-variants/{id}/
materialize` API로 확인하려 했으나, 그 엔드포인트는 `materialize_variant`
(장면만 투영)를 부르고 이번에 고친 로직(`build_variant_timeline_payload`/
`variant_render_session`)은 실제 렌더 타임라인을 짤 때만 지난다 — API
응답으로는 안 보인다. 시도했던 프로젝트(0907-b26195af)도 낡은
`unresolved_variant_conflicts`로 막혀 있었다. `task_acfd8147`로 다음
세션 확인 항목으로 큐에 올렸다.

## 다음 세션이 먼저 할 일

1. `task_acfd8147`: 실제 숏폼/일반 세로 렌더를 한 번씩 돌려 배경이 여전히
   의도대로(검정/블러) 보이는지 눈으로 확인 — 이번 세션이 못 한 것.
2. `task_77685434`는 이미 닫혔다(이 세션에서 고치고 실물 확인 완료) — 큐에서
   빠졌는지 확인만 하면 됨.
3. `task_006f1523`(R1 경계 나누기), CapCut R2(세로 블러 육안 확인)는 여전히
   대기 — 전자는 급하지 않음 확인됨, 후자는 대표님이 사무실 데스크톱에서
   직접 캡컷을 열어야 하는 항목.
4. 서버가 꺼져 있으면(재부팅 등) `scripts/owner-ready.ps1 -Mode Start
   -WithYujinMemory`로 켠다. LM Studio 모델이 이상하게 느리면(150초+)
   `lms ps`로 CONTEXT/PARALLEL이 평소(32768/1)와 다른지 먼저 본다
   ([[videobox-lm-studio-think-leak-broke-all-chat]] 메모 참고, 코드
   방어는 이미 되어 있지만 확인 습관은 남겨 둔다).

## 이번 세션 전체 커밋 (2026-09-13 세션 이후, main에 push 완료)

- `427ff5a7d`, `61dccd37`: 프롬프트 스윕·오류 문구 실물 확인 인계 문서
  (2026-09-13 세션 마무리분, 이번 세션 시작 시점에 이미 있었음).
- `2546808b`: LM Studio `<think>` 블록 방어적 제거, 애매한 확인 문장
  되묻기 지침 추가, 신규 단위 시험 4건.
- `b79b5c09`: 코드리뷰에서 잡은 결함(정규식 앵커링) 수정 + 회귀 시험 1건 +
  `short_form_scene_pick.py` 낡은 주석 정정.
- `61dccd37`: 전체 pytest 결과(5127 passed) + 코드리뷰 결과 인계 반영.
- `4bf61c03`: `_vertical_fill_fit`을 `box_aspect` 기반 여백 비율 계산으로
  일반화, `_video_box_aspect` 추가(제목 띠 영상 띠 재사용), 시험 4건.
- `1108b64d`: 세로 배경 채우기 일반화 인계 + `task_acfd8147` 큐에 올림.

## 서버·환경 상태 (세션 종료 시점)

- 컨테이너: 이번 세션이 재빌드한 최신 코드로 켜져 있음(`videobox-workspace`
  등 healthy).
- LM Studio: `qwen/qwen3.8-27b`, `CONTEXT 32768 / PARALLEL 1`(정상 설정으로
  되돌려 둠). 여전히 `<think>` 블록을 흘리지만(원인 미상, GUI 프리셋
  추정) 코드가 방어하므로 제품 동작에는 영향 없음.
- worktree: `.worktrees/videobox-container-compatibility`, 브랜치
  `codex/videobox-container-compatibility`. `origin/codex/videobox-
  container-compatibility`와 `origin/main` 둘 다 fast-forward로 push
  완료(충돌 없음, 26커밋).
- 저장소 루트(`D:\...\65_videobox`, 이 worktree 아님)의 로컬 `main` 체크아웃은
  이번 push 전에는 `origin/main`보다도 뒤처져 있었다(다른 세션들이 각자
  worktree에서 작업 중이라 루트를 오래 안 갱신한 것으로 보임) — 다음에 그
  경로에서 작업하면 먼저 `git pull`부터 할 것.
