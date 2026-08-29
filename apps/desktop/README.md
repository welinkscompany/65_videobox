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

## 아직 안 한 것 (다음 세션 몫)

- **실제 빌드가 막혀 있다.** Rust(rustup)와 Visual Studio Build Tools(C++
  워크로드)는 2026-08-30에 winget으로 설치했고 MSVC 링커까지는 통과했지만,
  **Windows 11 Smart App Control**(`Get-CimInstance ... SmartAppControlState`
  → `On`)이 새로 컴파일된 서명 안 된 `build-script-build.exe`(cargo가 빌드
  스크립트를 실행하려고 만드는 임시 실행 파일)를 차단한다(`os error 4551`,
  "애플리케이션 제어 정책에서 이 파일을 차단했습니다"). **owner 확인 없이
  Smart App Control을 끄지 않았다** — 이 기능은 한 번 끄면 OS 재설치 없이는
  되돌리기 어려운 시스템 보안 설정이라 임의로 손대지 않는다.
  - owner가 고를 수 있는 길: (1) Windows 보안 → 앱 및 브라우저 제어에서 이번에
    막힌 항목을 개별적으로 허용(전체를 끄는 것보다 가볍다), (2) Smart App
    Control 자체를 끄기(되돌리기 어려움, 신중히), (3) 서명된 빌드 파이프라인을
    별도로 구성(더 큰 작업).
  - 이 문제를 owner가 해결한 뒤에야 `npm run tauri dev`/`build` 실제 검증이
    가능하다(`CLAUDE.md` §4, "완료 = owner가 화면에서 실제로 쓸 수 있는가").
- 컨테이너 스택이 안 떠 있을 때 창이 자동으로 `owner-ready.ps1 -Mode Start`를
  불러 주는 부트스트랩(지금은 스택이 이미 떠 있다고 가정).
- 앱 아이콘 — `src-tauri/icons/`가 비어 있어 Tauri 기본 아이콘으로 빌드된다.
- macOS/Linux 타깃 — owner 개발 머신이 Windows라 Windows만 먼저 본다.
