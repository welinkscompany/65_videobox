# VideoBox Desktop

**owner 결정 2026-08-30** — `docs/decisions/2026-08-30-installed-desktop-shell-tauri.ko.md`.

Tauri로 만든 얇은 데스크톱 창 셸이다. VideoBox의 실제 편집·렌더·AI 생성 로직은
전부 그대로 `services/api`(FastAPI)와 owner 로컬 ComfyUI가 돌린다 — 이 셸은
브라우저 탭 대신 native 창으로 같은 화면(`http://127.0.0.1:5173`)을 보여줄
뿐이다. 새 UI나 새 백엔드가 아니다.

## 전제 조건

이 창은 `scripts/owner-ready.ps1 -Mode Start`로 이미 떠 있는 컨테이너 스택을
가리킨다 — 이 셸을 여는 것과 스택을 띄우는 것은 별개다. 스택이 안 떠 있으면
창은 빈 페이지나 연결 오류를 보여준다(아직 자동 기동 로직 없음, 아래
"다음에 할 일" 참고).

## 빌드 전 필요한 것

- Rust 툴체인(`rustup`) — 이 저장소 개발 머신엔 아직 없다. 설치는
  owner 확인 후 진행(시스템 전역 도구 설치이므로).
- `@tauri-apps/cli` (Node, `apps/web`이 이미 Node 24를 쓰므로 별도 설치 불필요)

## 빌드·실행

```bash
cd apps/desktop
npm install
npm run tauri dev    # 개발 중 실행 (owner-ready 스택이 먼저 떠 있어야 함)
npm run tauri build  # 배포용 실행 파일
```

## 실제 빌드·설치·실행 검증 완료 (2026-08-30)

**`npm run tauri build`가 실제로 끝까지 성공했고, 나온 설치 파일로 실제 설치·
실행까지 확인했다.** 그전 세션에 겪은 Windows 11 Smart App Control 차단
(`os error 4551`, 새로 컴파일된 서명 안 된 `build-script-build.exe`를
차단)은 owner가 "항목별 예외로 처리"하기로 정한 뒤 재시도에서 **재현되지
않았다** — 다만 이번엔 이전 빌드 캐시가 남아 있는 상태에서 재시도한
것이라, **캐시를 지우고 처음부터(clean) 다시 빌드하면 다시 막힐 가능성이
남아 있다.** "이번엔 안 막혔다"를 "이 결함이 근본적으로 해결됐다"로
읽지 않는다.

막힌 진짜 원인은 따로 있었다 — `src-tauri/icons/`가 비어 있는데
`tauri.conf.json`의 `bundle.icon`이 그 안의 파일 4개를 가리키고 있어서,
"Tauri 기본 아이콘으로 조용히 대체"가 아니라 **Windows 리소스 생성
단계에서 빌드 자체가 실패**했다(`icon.ico not found`). `npm run tauri icon
<소스 이미지>`로 임시 아이콘 세트를 만들어 넣어 해결했다 — `icon-source.png`가
그 소스이고, VideoBox 실제 로고가 아니라 자리표시용(주황 배경에 흰 "V")이다.
**진짜 로고로 바꿀 때는 owner 확인 후 같은 명령으로 다시 만들면 된다.**

검증한 것:
- `npm run tauri build` → `videobox-desktop.exe` 빌드 성공, NSIS 설치
  파일(`VideoBox_0.1.0_x64-setup.exe`) 생성 확인.
- 그 설치 파일로 실제 설치(`/S` 조용히 설치, 관리자 권한 요구 없음 —
  `%LOCALAPPDATA%\VideoBox`에 사용자 단위로 설치됨) 확인.
- 설치된 `videobox-desktop.exe` 실제 실행 → owner-ready 스택이 띄운
  실제 화면(프로젝트 목록, 실제 프로젝트 데이터, 이번 세션에 고친
  CTA 버튼·아이콘 단추 스타일까지)이 native 창 안에 그대로 뜨는 것을
  스크린샷으로 확인.

## 남은 것

- **clean 빌드에서 Smart App Control 재현 여부는 아직 확인 안 됨.** 지금
  검증은 캐시가 남아 있는 상태의 재시도였다 — `target/` 전체를 지우고
  처음부터 다시 빌드했을 때도 안 막히는지가 이 결함이 실제로 해결됐다고
  말할 수 있는 다음 확인 지점이다.
- **아이콘은 임시다.** `icon-source.png`는 자리표시용 — 실제 VideoBox
  로고가 정해지면 owner 확인 후 교체한다(팔레트·비주얼 방향 변경에
  준하는 승인 절차, `CLAUDE.md` §6).
- 컨테이너 스택이 안 떠 있을 때 창이 자동으로 `owner-ready.ps1 -Mode Start`를
  불러 주는 부트스트랩은 아직 없다(지금은 스택이 이미 떠 있다고 가정).
- macOS/Linux 타깃 — owner 개발 머신이 Windows라 Windows만 먼저 본다.
  `src-tauri/icons/android`·`ios`는 `tauri icon`이 기본으로 만들지만
  범위 밖이라 지웠다.
