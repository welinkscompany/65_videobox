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

- Rust 설치 뒤 실제 빌드·실행 검증 — 지금은 설정 파일만 있고 owner 화면에서
  실제로 눌러 본 적이 없다(`CLAUDE.md` §4, 완료 아님).
- 컨테이너 스택이 안 떠 있을 때 창이 자동으로 `owner-ready.ps1 -Mode Start`를
  불러 주는 부트스트랩(지금은 스택이 이미 떠 있다고 가정).
- 앱 아이콘 — `src-tauri/icons/`가 비어 있어 Tauri 기본 아이콘으로 빌드된다.
- macOS/Linux 타깃 — owner 개발 머신이 Windows라 Windows만 먼저 본다.
