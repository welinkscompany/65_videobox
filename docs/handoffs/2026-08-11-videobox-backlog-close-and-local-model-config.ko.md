# VideoBox 인계 — 백로그 마감과 로컬 모델 config화 (2026-08-11)

계획서: `docs/superpowers/plans/2026-08-10-videobox-consolidated-priorities.md` (SSOT)
앞 인계: `docs/handoffs/2026-08-10-videobox-session-close-owner-walk-and-media-split.ko.md`
(그 인계가 "완성본 mp4가 처음 나왔다"까지 다룬다. 이 문서는 그 뒤부터다.)

**백엔드 3,316 통과 / 53 건너뜀(Postgres 주소 없을 때 기준) / 실패 0.**
`-Full`(Postgres 실제로 띄운 채 전체)로도 **3,363 통과 / 6 건너뜀 / 실패 0** 확인.
프런트 850 통과 / 빌드 통과. `main`·`codex/videobox-container-compatibility` 모두 푸시 완료,
worktree는 깨끗하다.

## 이 세션에서 한 일 (커밋 순)

1. **저장소 분할 3단계 — 유진 기억 갈래.** `local_project_store.py` 10,321 → **9,106줄**
   (원래 11,512였으니 절반 아래로 내려왔다). 세 갈래(hermes/촬영본분석/유진기억) 전부
   믹스인으로 나갔다. AST 확인이 눈으로 못 본 이름(`_director_exchange_was_blocked`)을
   또 잡았다.
2. **회귀가 두 번 중 한 번 깨지던 CapCut 리스 테스트 고침.** 하트비트 주기가 리스의 1/3이라
   여유가 세 틱뿐이었다(0.12초→0.04초). 0.6초로 올렸다. 부하 중 7/8 → 12/12.
3. **`-Full` 스위치를 만들자 구멍 셋이 드러났다** — 자격증명 가드가 스칼라를 한 번도
   못 막던 것(`[pscustomobject]`가 사실상 `[psobject]`로 풀림), 그 테스트가 실행 실패를
   성공으로 세던 것(`-ExecutionPolicy Bypass` 누락), 스타터 팩 테스트가 콘솔 코드페이지를
   타던 것. 셋 다 고쳤다.
4. **P0-1·P4-1 계획서 절 닫음.**
5. **의미검색 임베딩 실패에 이유를 남김.** `library_audio_indexer.py`/
   `library_footage_indexer.py` 둘 다 로거조차 없었다. 실패해도 측정은 지키되(동작 동일)
   이유를 남긴다 — "음악 추천이 늘 분위기만 모드"의 유력한 원인이었다.
6. **에이전트 worktree 6개, 브랜치 6개 정리.** 병합 안 된 커밋 0개 확인 후 삭제.
   **319MB 회수.**
7. **owner 지시로 데이터 정리 (a) 진행.**
   - `smoke_sources/` 110MB — 완전 중복 재확인 후 삭제 완료
   - `projects/`(`b-roll-smoke-test` 포함) 95.3MB — **아직 안 지워졌다.** 아래 "owner가
     할 일" 참고
8. **owner 지시로 `api.ts` 정리 (b) 진행.** 21개 중 안전하게 지울 수 있는 3개만 제거
   (`buildTimeline`, `createEditingSession`, `assetBrowserPreviewContentUrl`) + 같이 쓰던
   요청 타입 2개. 나머지 18개는 그대로 뒀다 — 그중 2개는 부를 화면을 아직 안 만든 것이라
   지우면 문제를 가린다. 백엔드 라우터는 손대지 않았다(테스트 6개 파일이 직접 씀).
9. **로컬 모델 교체를 config 한 줄로 확실히 만듦.**
   - 모델 이름 교체는 원래도 `VIDEOBOX_LOCAL_MODEL_NAME` env var로 이미 됐다(정정: 지난
     턴에 "코드를 고쳐야 한다"고 말한 건 확인 없이 준 틀린 답이었다).
   - 진짜 빠진 건 문서화와 어긋남 감지였다. **실측으로 지금 이 저장소가 바로 그 어긋남
     상태였다** — `.env.container`에 값이 없어 기본값 `qwen3-35b`를 쓰는데 LM Studio엔
     `qwen/qwen3.6-35b-a3b`가 로드돼 있었다. LM Studio가 불일치를 조용히 무시하고 지금
     켜진 모델로 답해서 겉으로는 문제가 없었을 뿐이다.
   - `.env.container.example`에 문서화. `owner-ready.ps1 -Mode Check`에 `local_model`
     확인 추가(운영 코드 경로가 아니라 기동 전 진단 자리 — LocalFirst 계열의 "꺼져 있으면
     휴리스틱으로 물러난다" 설계를 하드 실패로 깨뜨리지 않으려고 여기 넣었다).
   - **실제 켜져 있는 `.env.container`도 맞는 값으로 고치고 컨테이너를 재기동해 확인했다.**
     (이 파일은 gitignore 대상이라 git에는 안 남는다.)

## owner가 끝낸 것

**`projects/` 폴더(95.3MB) 삭제 — owner가 직접 실행, 완료 확인함(2026-08-11).**
자동 모드 안전 장치가 repo 밖 데이터 폴더 삭제를 막아서 손으로 실행해야 했다.

**`main` 병합·배포도 owner 지시로 완료.** `codex/videobox-container-compatibility`를
`main`으로 fast-forward, 양쪽 다 푸시했다(`a1394ad60`). 실행 중이던 컨테이너는 이번
세션에서 이미 만든 이미지 그대로라 재기동 없이 healthy 상태를 유지했다.

## 다음 세션이 이어서 할 것

0. **`projects/` 삭제와 `main` 배포는 이미 끝났다.** 아래 목록에서 지웠다.
1. **owner가 자기 촬영본으로 직접 한 편 만들어 볼 것.** 막힌 곳은 다 뚫렸고 mp4도
   나온다. 이제부터는 실제로 쓰면서 남은 불편을 찾는 단계다. **여는 순서: LM Studio에
   모델을 올린 뒤 컨테이너를 띄운다.** `owner-ready.ps1 -Mode Check`로 먼저 확인하면
   모델 이름이 어긋나 있어도 미리 안다.
2. P2-1 나머지 — 삼키고 조용한 곳 64곳 중 아직 안 건드린 63곳. 기계적으로 훑지 말고
   owner 증상과 이어지는 자리부터.
3. `api.ts` 남은 18개 — 이번에 3개만 지웠다. 나머지는 계획서 P3-1 표 참고.

## 검증 방법

- 백엔드 전체: `.venv/Scripts/python.exe -m pytest -q` (약 24분)
- **Postgres까지 포함한 전체**: `.\scripts\run-postgres-store-tests.ps1 -Full` (약 23분,
  건너뜀 6개만 남는다 — 이번 세션에 추가한 옵션)
- Postgres 저장소만: `.\scripts\run-postgres-store-tests.ps1` (약 30초)
- 프런트: `apps/web`에서 `npx vitest run`
- 컨테이너: `docker compose --env-file .env.container build videobox-workspace` 후 `up -d`
- **로컬 모델이 맞게 켜져 있나**: `.\scripts\owner-ready.ps1 -Mode Check` (이번에 추가된
  `local_model` 항목이 알려 준다)

## 함정 (이번에 실제로 걸린 것)

- **초록불이 "지킨다"는 뜻이 아니었다.** `-Full` 스위치를 만들자마자 평소 안 보이던
  구멍 셋이 나왔다. 회귀를 근거로 쓰기 전에 그 코드가 실제로 도는지 의심할 것.
- **의존성을 정규식으로 세지 말 것.** 세 번의 분할 중 두 번, AST가 눈으로 못 본 이름을
  잡았다.
- **repo 밖 데이터 폴더 삭제는 자동 모드 안전 장치가 막는다.** 조사까지는 자동으로 하되
  삭제 자체는 owner가 실행해야 한다.
- **PowerShell `-is [pscustomobject]`는 `[psobject]`로 풀린다.** 실제 타입 이름
  (`[System.Management.Automation.PSCustomObject]`)으로 판정해야 스칼라를 걸러낸다.
- **LM Studio는 `model` 필드 불일치를 조용히 무시한다.** 설정과 로드된 모델이 달라도
  지금 켜진 모델로 답해 준다 — 여러 모델을 동시에 켜기 전까지는 안 드러난다.
