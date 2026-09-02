# 인계 — 자막 번역기 1단계 · 속성 탭 · 유진 의도 넷 (2026-09-02)

앞 인계: `2026-09-01-yujin-speaks-and-edits-capcut-clip-controls.ko.md`

## 이번에 한 것

### 1. 동영상 번역기 1단계 — 자막 번역 (새로 만듦)

`docs/decisions/2026-09-02-video-translator-step-one-captions.ko.md`가 결정 기록.

편집기 속성 패널 `자막 스타일` 바로 아래에 **`자막 언어`** 절이 생겼다.
`원본 · 영어 · 일본어 · 중국어` 네 칸이고, 아직 안 옮긴 언어는 `영어로 번역`으로,
이미 옮긴 언어는 `영어`로 뜬다. 누르면 로컬 모델이 옮기고 바로 그 언어가
완성본에 실린다.

**원본은 지우지 않는다.** `segment["caption_translations"]`에 언어별로 쌓이고,
`session["caption_language"]`가 어느 쪽을 낼지 고른다. `원본`으로 되돌려도 번역은
남아 있다.

닿는 자리(새 필드를 더할 때 여기를 다 지나야 한다):

| 층 | 파일 |
|---|---|
| 읽는 곳(하나) | `composition_plan.py` `materialize_editing_session_timeline` |
| 저장·읽기 | `caption_translation.py` |
| 모델 호출 | `caption_translation_service.py` |
| 저장 화이트리스트 | `local_project_store.py` `_write_editing_session` |
| API | `routers/editing_session.py` (POST `caption-translations`, PATCH `caption-language`) |
| 화면 | `InspectorControls.tsx` → `RightDock` → `editorWorkbenchReadOnlyAdapters` |
| 상태 | `editorSnapshot.ts` (`captionLanguage`, `translatedLanguages`) |

### 2. 속성 패널 탭 (앞 세션에서 이어짐)

B-roll 칸이 `화면 · 소리 · 속도 · 보정` 네 탭으로 나뉘었다.

### 3. 유진이 할 수 있는 것 넷 추가

손떨림 보정·화면 노이즈·확대/위치/기울이기·소리 정리를 말로 시킬 수 있다.

## 실제로 재 본 것

- 로컬 모델이 5개 장면을 **자막 길이의 영어**로 옮겼다(실제 문장 확인)
- 화면 버튼이 `영어로 번역` → `영어`(눌림)로 바뀌고 **새로고침 뒤에도 유지**
- SRT 내려받기 전부 영어
- **완성본 mp4에 영어 자막이 구워졌다** — 2초·22초 프레임을 실제로 봤다
- `원본`으로 되돌리니 SRT가 다시 한국어, 영어 번역은 안 지워짐

## 만들면서 걸린 함정 셋 (다음 사람이 또 밟는다)

1. **장면 식별자에 콜론이 있다**(`timeline_001:001`). `식별자: 자막` 꼴로
   모델에 보내면 되받은 줄을 가를 수 없다. 번호만 보내고 되돌리는 일은 우리가 한다.
2. **저장 화이트리스트가 두 겹**이다. 세션에 새 칸을 더하면
   `_write_editing_session`의 목록에도 넣어야 한다. 안 넣으면 조용히 사라진다.
3. **`except Exception`이 내 실수를 삼켰다.** 프롬프트 만들다 난 NameError가
   "모델이 바빴다"로 둔갑해 번역이 빈 채 200이 나갔다. 좁혀 두었다.
4. **빈 칸이라도 늘 실으면 응답 모양이 바뀐다.** `caption_translations`를 모든
   장면에 `{}`로 실었더니 번역을 한 번도 안 쓴 프로젝트의 응답까지 달라졌고,
   저장 파일과 응답을 그대로 맞대는 창작 흐름 점검이 그걸 잡았다
   (`session_file_api_mismatch`). `exclude_if`로 안 쓰면 빼도록 맞췄다 --
   **이 넷은 전부 전체 pytest가 잡았다. 부분 실행으로는 안 나왔다.**

## 남은 것

### 이 기능에서 미룬 것 (결정 기록에 이유 있음)

- **목소리 더빙(2단계)** — 다음 큰 것
- **자막 타이밍 재조정** — 언어마다 길이가 달라 원문 구간에 안 맞을 수 있다.
  "짧게 옮기라"는 지시로 완화했을 뿐 없앤 것이 아니다. 넘치는 사례가 나오면 연다.
- **번역문 직접 고치기** — 지금은 다시 번역하거나 원본으로 되돌리는 두 길뿐

### 앞 인계에서 넘어온 것

- 캡컷 대조가 안 끝난 화면 넷(자료실·촬영본 정리·검토·출력) — owner 캡처 필요
- Tauri clean 빌드를 Smart App Control이 막는다 — OS 정책, owner 판단

## 청소하면 좋을 것

`기능 섞어 쓰기 시험`(`project-318cc020`)에 이번 검증 흔적이 남아 있다 —
영어 번역 5개, 출력 `export_012`, 자막 `subtitle_render_job_016/018`.
지금은 `원본`으로 되돌려 둔 상태다. 지워도 되고 그대로 둬도 된다.
