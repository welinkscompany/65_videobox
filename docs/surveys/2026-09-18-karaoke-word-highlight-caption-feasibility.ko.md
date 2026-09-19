# 가라오케(단어별 강조) 자막 — 전제조건 조사 (2026-09-18)

**대체됨:** 없음 (신규 문서)
**상태: 조사만 완료, 구현 안 함.** owner 승인("1,2번 진행하자")에 따라 전제조건부터
확인했고, 결과가 "쉽게 얻을 수 있다"와 "훨씬 큰 작업"의 경계에 걸쳐 있어 무리해서
구현까지 밀어붙이지 않았다(`CLAUDE.md` §1.6·§1.11에 따른 판단). 아래에 근거와 필요한
작업 규모를 정리한다.

## 결론 요약

1. **단어 단위 타이밍은 "없는" 게 아니라 "두 군데에서 이미 버려지고 있다."**
   STT 엔진(faster-whisper)은 이미 `word_timestamps=True`로 단어별 타임스탬프를
   요청해서 받고 있다. 하지만 그 값(`segment.words`)을 우리 코드가 한 번도 저장하지
   않고 그 자리에서 버린다.
2. 이 저장소의 자막 굽기는 **ASS(libass) 한 경로**로 통일돼 있어(`render_editing_session_ass`),
   ASS가 표준으로 지원하는 `\k` 가라오케 태그를 쓸 수 있다는 점은 유리하다.
3. 그러나 이 값이 **화면(웹 미리보기)에 닿기까지, 그리고 완성본 MP4까지 닿기까지**
   거쳐야 하는 층이 예상보다 많다 — 최소 8곳. 특히 "미리보기"가 DOM 오버레이가
   아니라 **실제 ffmpeg로 구운 영상**이라는 점, 그리고 자막 텍스트를 owner가 손으로
   고치면 단어 타이밍과 어긋난다는 정합성 문제가 새로 생긴다는 점이 이번에 새로
   확인된 리스크다.

## 확인된 사실 (코드로 직접 읽음)

### 1) STT 엔진은 단어 타임스탬프를 이미 받지만 버린다

`packages/provider-interfaces/src/videobox_provider_interfaces/faster_whisper_stt.py:74-96`

```python
segment_iter, _info = model.transcribe(
    str(wav_path), language=language, word_timestamps=True, vad_filter=True,
)
segments = [
    STTSegment(start_sec=..., end_sec=..., text=segment.text.strip(), confidence=...)
    for segment in segment_iter
]
```

`word_timestamps=True`를 주면 faster-whisper의 각 `segment`에 `segment.words`
(단어별 `word`, `start`, `end`, `probability`)가 실제로 채워진다. 그런데 위 리스트
컴프리헨션이 `segment.words`를 아예 읽지 않는다 — **라이브러리는 이미 계산해서
주는데, 우리 도메인 모델(`STTSegment`, `packages/provider-interfaces/.../stt.py:14-19`)에는
애초에 그 필드가 없다.**

### 2) 두 번째로 버려지는 자리

`packages/core-engine/src/videobox_core_engine/local_pipeline.py:1118-1138`
(`run_transcription_job`)이 `stt_result.segments`를 순회하며 `start_sec/end_sec/text/
confidence`만 뽑아 `store.save_transcript(...)`에 넘긴다. 설령 1)을 고쳐서
`STTSegment`가 단어를 들고 있어도, 여기서 두 번째로 버려진다.

### 3) 자막 텍스트가 "segments" JSON 딕셔너리로 흐른다 (스키마 자체는 유연함)

`editing_session.py`의 `caption_text`/`caption_style`는 고정 컬럼이 아니라 세션
JSON 안의 자유 딕셔너리 키다(`postgres_schema.py`의 ID 접두사 표에 `"segments":
"segment_id"`만 있고 별도 컬럼 목록은 없음 — JSONB로 저장되는 구조). 이 자체는
긍정적이다: `words` 같은 새 키를 추가해도 **SQL 스키마 마이그레이션이 필수는
아닐 가능성이 높다**(정확한 컬럼 확인은 `local_project_store.py`/
`postgres_project_store.py`의 실제 write 경로를 더 봐야 하며, 이번 조사에서는
`editing_session.py`가 세션 전체를 하나의 JSON으로 다루는 패턴만 확인했다).

### 4) 자막 굽기는 **한 함수**로 통일 — 그러나 그걸 부르는 자리가 셋

`packages/core-engine/src/videobox_core_engine/ass_subtitles.py:316`의
`render_editing_session_ass()`가 세그먼트 딕셔너리 리스트를 ASS 텍스트로 굽는
유일한 함수다. 이걸 부르는 자리가 `local_pipeline.py`에 **셋**:

- L556 — 숏폼/세로 변형 렌더
- L669 — **"정확 미리보기"(exact preview)** — 뒤에서 설명하지만 이게 owner가
  화면에서 보는 미리보기의 실체다.
- L2453 — 완성본(master) 렌더

셋 다 `segments`(딕셔너리) 또는 `plan.captions`(`CaptionCue` dataclass,
`composition_plan.py:927-932`, 필드는 `start_sec/end_sec/text/style/segment_id`뿐)를
조립해서 같은 함수에 넘긴다. **단어 타이밍을 추가하려면 이 세 조립 지점 모두에
`words`를 같이 실어 날라야 한다** — 하나만 고치면 memory
`videobox-two-render-paths-fix-both.md`가 경고한 바로 그 함정("같은 필터를 한
곳만 고쳐서 두 번째 경로가 계속 틀리게 나온" 전례)이 그대로 재현된다. 여기선
경로가 둘이 아니라 **셋**이다.

### 5) "미리보기"는 DOM 오버레이가 아니라 실제 ffmpeg 렌더

`apps/web/src/features/editor/preview/preview-stage.tsx:9,18,130,277`를 보면
`captions` prop(`{text, startSec, endSec}`)은 **화면에 글자로 그리지 않는다.**
`aria-live` 스크린리더 전용 문구(`vb-preview-stage__visually-hidden`)로만 쓰인다.
실제로 보이는 자막은 `exact.url`이 가리키는, 서버가 `run_exact_preview()`
(`local_pipeline.py:648-679`)에서 **위 4)의 `render_editing_session_ass`로 구운
진짜 mp4**다.

**이건 이번 작업 지시서의 전제와 다르다.** 지시서는 "기존 캡션 렌더링
컴포넌트를 찾아 확장하라"고 했는데, DOM 기반 캡션 렌더링 컴포넌트 자체가 없다
— 웹 미리보기와 완성본 MP4가 **같은 ASS 굽기 경로를 공유**한다. 이건 한편으론
유리하다(구현 지점이 하나로 줄어든다 — ASS에 `\k`를 넣으면 미리보기·완성본이
동시에 해결된다는 뜻). 하지만 동시에, "미리보기에서만 가볍게 먼저 확인" 같은
저위험 중간 단계가 없다는 뜻이기도 하다 — **첫 구현부터 완성본과 같은
렌더 경로를 직접 건드리게 된다.**

### 6) ASS 스타일 정의가 현재 karaoke 색칠에 필요한 조건을 안 갖추고 있다

`ass_subtitles.py:344-347`의 `style_line()`이 `Style:` 줄을 지을 때
`PrimaryColour`와 `SecondaryColour`를 **같은 값**으로 채운다:

```python
f"Style: {name},{value.font_family},{size},{primary},{primary},..."
```

ASS의 네이티브 `\k` 렌더링은 "아직 안 부른 구간 = SecondaryColour, 이미 부른
구간 = PrimaryColour"로 색을 바꾼다. 지금처럼 둘이 같은 값이면 `\k` 태그를
그냥 추가해도 **눈에 보이는 변화가 없다.** 강조색을 실제로 보이게 하려면
- (a) `SecondaryColour`를 강조색으로 분리하고 libass 네이티브 `\k`에 맡기거나,
- (b) 단어마다 `{\k<centi>}{\c&H강조색&}...{\c&H기본색&}` 식으로 색 전환 태그를
  직접 끼워 넣는 수동 방식(플레이어별 `\k` 렌더 편차를 피하려는 목적)
둘 중 하나를 골라야 한다 — "태그만 추가하면 된다"가 아니라 **스타일 설계
결정**이 하나 더 필요하다.

### 7) 자막 텍스트를 손으로 고치면 단어 타이밍과 어긋난다 (새로 확인한 리스크)

이 저장소는 owner가 자막 텍스트를 화면에서 직접 고치는 것과(`update_caption`,
`editing_session.py:1549` 근처), 유진이 채팅으로 바로 편집을 적용하는 것을
정식 기능으로 갖고 있다(`2026-09-01-yujin-chat-applies-edits-directly` 결정).
STT가 준 단어 타이밍은 **STT가 뽑은 원문 글자열**에 묶여 있다. owner가 자막을
고치면(오탈자 수정, 문장 합치기/쪼개기, 번역 등) 단어 개수·순서가 달라져 저장된
타이밍과 더 이상 맞지 않는다. "고친 자막에도 단어 강조를 켤 것인가, 아니면 STT
원문에서 벗어난 세그먼트는 조용히 단어 강조를 끄고 기존처럼 통짜 자막으로
보여줄 것인가"를 owner가 정해야 한다 — 지금 지시서에는 이 결정이 없다.

## 크기 추정 — 왜 "배선만 하면 되는 작업"이 아닌가

지시서의 전제("저장은 되는데 화면에 안 쓰이면 배선만 하면 되는 작은 작업")는
**저장 단계까지는 이미 끝나 있는 경우**를 가정한 것이다. 실측 결과는 그게 아니라
**저장 전 단계(STT 응답을 우리 모델에 담는 첫 줄)에서부터 버려지고 있다.** 그래서
touch해야 하는 지점이 최소 아래 8곳이다.

| # | 위치 | 필요한 변경 |
|---|---|---|
| 1 | `provider-interfaces/stt.py` | `STTSegment`에 단어별 `(text, start_sec, end_sec)` 목록 필드 추가 |
| 2 | `faster_whisper_stt.py` | `segment.words`를 실제로 읽어서 채움 |
| 3 | `local_pipeline.py:run_transcription_job` | `save_transcript`에 단어 목록도 같이 저장 |
| 4 | `editing_session.py` | STT 결과 → 세그먼트 `caption_text` 반영 지점에서 단어 목록도 세그먼트 JSON에 실음. **자막을 손으로 고치면 무효화하는 규칙**(§7) 설계·구현 |
| 5 | `composition_plan.py`의 `CaptionCue` | `words` 필드 추가, 세 조립 지점(`local_pipeline.py` L556/669/2453 인근)에서 채워 넘김 |
| 6 | `ass_subtitles.py` `render_editing_session_ass` | 단어 강조 켜졌을 때 세그먼트 하나를 여러 `\k` 조각으로 굽는 로직 추가. §6의 스타일 설계 결정 필요 |
| 7 | `caption_style.py`의 `CaptionStyle` | 새 불리언 필드(기본값 꺼짐) + 강조색 필드, `from_dict`/`to_dict`/검증 갱신 |
| 8 | 프론트 자막 스타일 설정 (`CaptionPresetPicker.tsx`/`InspectorControls.tsx`) | 새 토글 UI, 기존 캡컷 벤치마킹 패턴(드롭다운·토글)을 그대로 따름 |

여기에 **회귀 테스트**가 걸린 기존 파일이 `tests/test_ass_subtitles.py`(자막 ASS
굽기, 12개 호출부), `tests/test_caption_style.py`, `tests/test_caption_style_fields_reach_the_render.py`,
`tests/test_ffmpeg_final_renderer.py`, `tests/test_vertical_composition.py`,
`tests/test_overlay_text_avoids_the_caption_band.py`(자막이 차지하는 세로 띠
계산도 단어별로 쪼개진 줄바꿈에 영향을 받을 수 있음), `tests/test_local_pipeline_final_render.py` 등
**최소 7개 기존 테스트 파일**이며, 전부 지금 통짜 자막을 전제로 값을 검증하고
있다. 새 토글이 꺼졌을 때 기존 동작이 바이트 단위로 그대로인지까지 확인해야
한다(memory `videobox-one-successful-render-is-not-proof-of-a-fix` — 렌더 한 번
성공은 증거가 아니다, 반복 검증 필요).

## 권고

1. 이 작업은 **공식 Task/계획서 항목으로 먼저 쪼개서** 진행하는 게 맞다고
   본다 — 지금은 `implementation-plan.ko.md`에 이 기능의 자리가 없다(확인:
   grep으로 `karaoke`/단어 강조 관련 Task 0건). owner가 "1,2번 진행하자"고
   승인한 것은 기능 방향이지, 위 8개 지점을 한 세션에 다 처리하라는 뜻은 아니라고
   판단했다.
2. 가장 안전하게 시작할 수 있는 조각은 **1~3번(STT 캡처)**이다 — 렌더 경로를
   전혀 안 건드리고, 단위 테스트로만 검증 가능하다(`tests/test_faster_whisper_stt.py`).
   다만 이것만 하면 아무도 안 읽는 값이 되므로(memory
   `videobox-unwired-api-methods-are-not-automatically-dead`류 함정), 이번 턴에
   단독으로 끝내지 않았다 — 다음 세션이 4~8번과 묶어서 한 Task로 가져가는 걸
   권한다.
3. §6(스타일 설계)과 §7(수동 편집 정합성)은 코드보다 **owner 결정**이 먼저
   필요한 지점이다. 특히 §7은 "자막을 고치면 강조가 조용히 사라진다"를 owner가
   받아들일 수 있는지부터 확인해야, 그 위에 무엇을 지을지 정해진다.

## 이번 턴에 한 일 / 안 한 일

- 한 일: 코드 근거로 위 사실 1~7 확인, touch 지점 8곳과 관련 테스트 파일 목록
  정리, 이 문서 작성.
- 안 한 일: 코드 변경 전혀 없음(RED/GREEN 없음). 컨테이너 재빌드·브라우저
  확인·렌더 픽셀 확인도 안 함 — 구현이 없으므로 검증 대상이 없다.
- 커밋: 이 문서 하나만 커밋한다. `CLAUDE.md` §2 표는 갱신하지 않는다(그 줄은
  "최신 세션 인계" 전용이고 이번 건 구현 인계가 아니라 조사 기록이라
  `docs/surveys/`에 남긴다 — 지시서의 "조사만 했다면 surveys" 지침을 따름).
