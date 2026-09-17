# LM Studio 재부팅 뒤 실제 채팅이 전부 죽어 있던 것 + 애매한 확인 거짓 긍정, 둘 다 고침 (2026-09-17)

**대체됨:** 같은 날 이어진 세션 `2026-09-17-vertical-fill-fit-generalized-
to-padding-threshold.ko.md`가 세로 배경 채우기 일반화를 다뤘다. 최신
인계는 그쪽을 읽을 것.

앞 인계(`2026-09-13-conversation-prompt-sweep-and-error-leak-confirmed.ko.md`)가
`task_77685434`로 큐에 올린 "애매한 확인 문장이 거짓 긍정한다"를 마무리하러
들어왔다가, 그보다 훨씬 급한 **실제 서비스 전체 장애**를 발견해서 먼저 고쳤다.

## 1. 서버가 꺼져 있었다 (컴퓨터 재부팅)

세션 시작 시점에 VideoBox 컨테이너가 전부 내려가 있었다 — 다른 프로젝트
컨테이너까지 전부 18시간 전에 종료된 것으로 보아 컴퓨터 자체가 재부팅된
것으로 보인다. `scripts/owner-ready.ps1 -Mode Start -WithYujinMemory`로
정상 기동했다.

## 2. 재부팅 뒤 LM Studio가 기본값으로 다시 떠서 실제 채팅이 전부 죽어 있었다

`lms ps`로 확인하니 `qwen/qwen3.8-27b`가 `CONTEXT 131072 / PARALLEL 4`로
떠 있었다(평소는 `32768`/`1`). 이 상태에서 `task_77685434` 재현 시험을
돌렸더니 **6번 전부 타임아웃 또는 잘못된 JSON**으로 실패했다 — 대표님께
여쭤서 평소 설정(`32768`/`1`)으로 되돌렸다(`lms unload` → `lms load -c
32768 --parallel 1`).

되돌린 뒤에도 여전히 실패했다. curl로 LM Studio API를 직접 두드려 원인을
확인했다: 응답 `content`가 순수 JSON이 아니라 **`<think>...(추론
과정)...</think>{"reply": "..."}` 형태**로 왔다 — Qwen3 계열의 "생각" 모드가
켜진 채로 오는데, 평소엔 LM Studio가 이 블록을 걸러내 주는 것 같은데
재부팅 뒤 CLI로 다시 올리니 그 걸러내기가 사라졌다. 우리 쪽 파서
(`local_qwen.py`의 `complete_structured`)는 `content`가 순수 JSON이라고만
가정하고 있어서 `json.loads`가 그대로 실패했다.

**이게 실제로 화면 채팅을 전부 막고 있는지 curl로 직접 확인했다** —
실제 프로젝트(`0907-b26195af`)에 "안녕 유진"을 보내보니 화면에 실제로
`"local_only_blocked: local_qwen: Local Qwen returned invalid JSON
content."`가 응답으로 왔다. **완료의 정의 기준으로 이건 이번 세션 시작
시점에 실제 서비스가 완전히 멈춰 있었다는 뜻이다.**

**고쳤다(커밋 예정).** `local_qwen.py`에 `<think>...</think>` 블록을
`json.loads` 전에 정규식으로 걷어내는 `_strip_reasoning_block()`을
추가했다. LM Studio의 걸러내기 설정에 기대지 않고 우리 쪽에서 항상
방어하게 했다 — 그 설정이 로드 방식(GUI vs CLI)에 따라 달라진다는 게
이번에 실측으로 확인됐기 때문이다.

**검증**: 신규 단위 시험 4건(`tests/test_local_qwen_structured_provider.py`)
— 평소처럼 순수 JSON(회귀 없음), `<think>` 블록이 앞에 붙은 경우(이번
버그의 정확한 재현, 실제 LM Studio 원문을 그대로 fixture로 옮김), 걷어내도
못 쓰는 경우, 잘린 `<think>`(닫는 태그 없음)는 각각 정확히 실패하는 것까지
확인했다. 관련 스위트(`test_yujin_local_conversation.py`,
`test_director_conversation.py`, `test_yujin_editing_short_form.py`,
`test_yujin_editing_proposal_adapter.py`) 80건 통과. 컨테이너를
`-Rebuild`로 다시 만들고, **LM Studio를 원인이 된 그 상태 그대로 둔 채로**
실제 화면 채팅에 "안녕 유진, 짧게 인사해줘"를 curl로 보내 정상 답변이
오는 것을 직접 확인했다("안녕하세요, 창작자님! 오늘도 함께 영상
만들어볼까요?").

## 3. `task_77685434` — 애매한 확인 문장 거짓 긍정, 실제로 고침

`yujin_local_conversation.py`의 `_YUJIN_SYSTEM_PROMPT`에 "장면 번호나
구체적인 편집 내용 없이 '그걸로'/'응'/'네'처럼 순수 확인·동의뿐이면
이미 적용됐다고 단정하지 말고 정확히 무엇을 적용할지 되물어라"를
추가했다.

**실물(실제 화면 채팅 경로)로 확인.** 같은 프로젝트에서:
- "응 그걸로 적용해줘" → "네, '그걸'이 정확히 무엇을 가리키는지
  알려줘요... 만약 화면에 뜨는 영상·음악·효과음 추천 카드의 후보라면,
  대화에서 '응'이라고 하는 대신 해당 카드의 '적용' 버튼을 눌러야
  반영돼요." — 더 이상 거짓 긍정하지 않는다.
- "그 후보 적용해줘" → "어떤 후보를 말씀하시는 거예요? ... 이름이나
  순서를 알려주세요." — 카드 구분 유지, 회귀 없음.
- "1번 장면 속도를 두 배로 빠르게 해줘" → 이 프로젝트엔 낡은 후보가
  많이 쌓여 있어 결정론적 리졸버(`resolve_director_command`)가
  `needs_disambiguation`으로 먼저 가로챘다 — 이건 이 프로젝트의 상태
  때문이지 이번 수정과 무관하다(블라인드 LLM까지 가지도 않았다).

## 4. 코드리뷰(medium)에서 잡은 결함 하나, 바로 고침

`_REASONING_BLOCK_PATTERN`이 문자열 아무 데나 있는 `<think>...</think>`를
다 지웠다 — 창작자가 그 태그 이름을 물어봐서 유진의 답변 텍스트가 정당하게
그 낱말을 담고 있으면, JSON 값 안쪽이 잘려 나갈 수 있는 결함이었다(실제
관찰된 누출은 항상 문자열 맨 앞이었다). `^`로 문자열 맨 앞만 지우도록
좁히고 회귀 시험을 추가했다. 같이 손본 `short_form_scene_pick.py`의 낡은
주석("스키마를 주면 `<think>`를 낼 수 없다")도 이번 실측으로 깨졌다는 것을
밝혀 정정했다 — 그 모듈도 같은 `local_qwen.py` 경로를 타므로 이번 방어로
같이 보호된다.

## 5. 전체 backend pytest(단독 실행) 결과

**5127 passed, 56 skipped, 1 xfailed, 0 failed** (37분 53초). xfailed 1건은
`test_short_form_split_does_not_change_master_bytes.py`로, 앞 세션이
`task_006f1523`을 위해 `xfail(strict=True)`로 고정해 둔 기존 것이다 —
이번 변경과 무관.

## 6. 남은 것

- `task_006f1523`(R1 경계 나누기), CapCut R2(세로 블러 육안 확인)는
  이번 세션에서 안 건드림 — 전자는 급하지 않다고 이미 확인됐고, 후자는
  대표님이 사무실 데스크톱에서 직접 캡컷을 열어야 하는 항목이라 여전히
  대신할 수 없다.
- LM Studio가 왜 CLI 재로드 때 `<think>` 걸러내기를 잃는지(GUI 프리셋
  차이로 추정)는 근본 원인까지는 못 밝혔다 — 코드 쪽에서 항상 방어하게
  고쳤으므로 제품 동작에는 더 이상 영향 없지만, GUI에서 그 모델의
  "reasoning parsing" 설정이 어디 있는지는 확인 안 함.
- 대표님이 세로 배경 채우기(blur/검정)를 장면마다 LLM이 판단하게 하면
  어떠냐고 물었다. 코드를 확인해 보니 숏폼(제목 띠 있는 레이아웃)은 이미
  2026-09-12부터 검정(`fit`)이 기본값이고(`output_variants.py:399`), 참고
  숏폼 4개 실측도 전부 검정이었다는 것이 주석에 남아 있다. `blur`는 제목
  띠 없는 일반 세로 변환에서만 쓴다 — 그쪽은 여백이 68.3%로 커서 검정이면
  화면 절반이 시커멓게 보이기 때문이다. 갈리는 기준이 "가독성"이 아니라
  "여백 크기"이므로 장면별 LLM 판단은 과하다고 답해 드렸고, 대표님 결정
  대기 중.

## 7. 커밋

- `2546808b`: `local_qwen.py` `<think>` 블록 방어적 제거,
  `yujin_local_conversation.py` 애매한 확인 문장 되묻기 지침 추가, 신규
  단위 시험 4건.
- `b79b5c09`: 코드리뷰에서 잡은 결함(정규식 앵커링) 수정 + 회귀 시험 1건 +
  `short_form_scene_pick.py` 낡은 주석 정정.
