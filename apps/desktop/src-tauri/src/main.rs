// VideoBox 데스크톱 셸 — owner 결정 2026-08-30.
//
// 이 파일은 새 애플리케이션 로직을 담지 않는다. 창을 하나 열어 이미
// `scripts/owner-ready.ps1`로 떠 있는 컨테이너 스택(http://127.0.0.1:5173)을
// 보여줄 뿐이다 — 창 내용은 tauri.conf.json의 `app.windows[0].url`이 정한다.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running the VideoBox desktop shell");
}
