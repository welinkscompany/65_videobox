# 찍어 둔 영상으로 시작하는 문이 화면까지 닿았다

- 작성: 2026-08-21
- 앞 문서: `2026-08-21-videobox-scene-images-and-the-donkey.ko.md`
- 개발선: `codex/videobox-container-compatibility`
- 이 턴의 커밋: `1dda575cc`

## 한 줄

하루 전에 놓인 백엔드 문(`7ed84d040`)에 **부르는 화면을 붙였다.** 이제 owner가
첫 화면에서 "찍어 둔 영상이 있어요"를 눌러 영상을 올리면, 받아쓴 대본이 고칠 수
있는 칸에 나오고, 확인하면 기존 기획 흐름으로 넘어간다.

## 무엇을 했나

- 첫 화면 선택창(`StartChooser.tsx`)에 세 번째 길을 넣었다.
- 이야기 화면에 올리는 자리를 만들었다(`features/creation/SourceVideoStart.tsx`, 새 파일).
  올림 → 받아쓰는 동안 상태 표시 → **고칠 수 있는 칸** → 확인 → `createCreationBrief`.
- 대본을 만들어 준 그 영상을 **내레이션 후보(`raw_video`)로도 이어 붙였다.**
- `api.ts`에 `uploadSourceVideo`(FormData)를 더했다.
- `ProductShell.tsx`를 건드렸으므로 `docs/oss/editor-ui-source-map.json`의
  `normalized_sha256` 두 줄도 함께 옮겼다.

## 실제로 재서 알게 된 것

**받아쓰기는 생각보다 훨씬 빠르다.** 3분 20초짜리 영상이 **24초**에 끝났다
(대략 8배속, 잡음 없는 한 사람 목소리 기준). 처음에 화면 안내를 "5분 안쪽"이라고
**짐작으로** 적었는데, 재 보니 근거가 없어 "128MB보다 작고 20분 안쪽"으로 고쳤다.
중간에서 끊는 벽은 330초다(`docker/workspace-nginx.conf`).

**받아쓰기는 실제로 틀린다.** 검증 중에 "받아써서"가 `받았어서`로 나왔다.
고칠 칸을 두는 설계가 장식이 아니라는 증거다. 그대로 확정했으면 그 오타가
자막까지 그대로 갔다.

**`raw_video` 내레이션 단추는 이번에 처음으로 그려졌다.** 그리는 코드
(`CreationInterview.tsx:520`)와 후보를 읽는 API(`listDraftNarrationOptions`)는
전부터 있었지만, `raw_video` 후보를 **만들 방법이 아예 없어서** 한 번도 화면에
나온 적이 없었다. 이 저장소가 반복해 온 "부품은 있는데 부르는 자리가 없다"의
또 한 번이고, 이번에 닫혔다.

## 검증한 것

컨테이너를 다시 띄우고(`scripts/owner-ready.ps1 -Mode Start -Rebuild
-WithYujinMemory`, 전 항목 PASS) **브라우저에서 owner 경로를 그대로 밟았다.**
말소리가 든 영상을 직접 만들어 올렸다(Windows SAPI 한국어 음성 + ffmpeg).

- 첫 화면에 세 번째 길이 보이고, 누르면 이야기 화면으로 간다
- 17초 영상 → 받아쓴 한국어 대본이 textarea에 나옴 (정확)
- 그 글을 **고친 뒤** 확인 → 고친 글로 기획이 열림 (받아쓴 원문이 아니라)
- 승인 뒤 "영상 소리로 초안 준비"가 뜨고, 누르면 실제 요청이
  `narration_choice: {kind: "source_video", asset_id: "asset_ecd15ac2ad55"}`
- 무음 영상 → "이 영상에는 말소리가 없어요…"
- `.txt` 파일 → "열 수 없는 형식이에요…" (서로 다른 말)
- 3분 20초 영상 → 기다리는 동안 "영상에서 말을 받아쓰고 있어요" + 대기 안내가
  뜨고 단추가 잠긴다. **그 상태에서 다시 눌러도 요청이 두 번 가지 않았다**(1건)
- `npm --prefix apps/web test -- --run` 1207개 전부 통과, `npx tsc --noEmit` 깨끗
- `test_editor_ui_source_provenance.py` + `test_api_source_video_start.py` 26개 통과

## 검증하지 못한 것

- **330초 벽을 실제로 넘겨 보지 못했다.** 8배속이면 45분짜리 영상이 있어야 하는데
  만들지 못했다. 504를 받았을 때 나올 문구는 **되짚기에서만** 확인했고 실물
  프록시로는 확인하지 못했다. 긴 영상이 실제로 504로 오는지, 아니면 다른 방식으로
  끊기는지는 미확인이다.
- **128MB 상한을 실제로 넘겨 보지 못했다.** 413/400 문구도 되짚기까지만이다.
- **화면 스크린샷을 찍지 못했다.** Browser pane이 화면에 떠 있지 않아 접근성
  트리도 비어 있었다. 대신 `document.body.innerText`와 DOM 조회로 확인했으므로
  **문구와 동작은 실제로 확인했지만, 생김새·배치·간격은 확인하지 못했다.**
  세 번째 단추가 선택창 안에서 어떻게 보이는지는 사람이 한 번 봐야 한다.
- **긴 영상의 업로드 시간**은 재지 않았다. 받아쓰기 시간만 쟀다. 330초 예산은
  올리는 시간과 받아쓰는 시간을 **함께** 쓴다.

## 다음 사람이 알아야 할 것

- **지금 도는 컨테이너는 이 에이전트 worktree에서 빌드된 것이다.** 개발선 branch
  (`codex/videobox-container-compatibility`)에는 아직 이 커밋이 없다. 합친 뒤
  개발선 worktree에서 다시 `owner-ready.ps1 -Mode Start -Rebuild`를 돌려야
  컨테이너와 개발선이 일치한다.
- 검증용 프로젝트 두 개를 만들어 두었다: `project-15ed00b1`(찍어둔 영상 시작 확인),
  `project-04180302`(실패 문구 확인). 지우지 않았다 — 지우기는 owner 몫이다.
- 남은 길은 하나다: **유진이 처음부터 대본을 써 주는 길.** 선택창에서 일부러
  빼 두었고, 그 이유는 `StartChooser.tsx` 주석과 되짚기에 적혀 있다.
