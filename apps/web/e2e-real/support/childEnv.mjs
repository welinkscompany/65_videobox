// 자식 프로세스(API·vite)에 넘길 환경을 허용 목록으로 만든다 (2026-10-08 계획 H Task 1 보정).
// 소유자 셸의 VIDEOBOX_* 와 토큰류가 진짜 게이트웨이·받은편지함에 닿지 않게 한다.
export const SAFE_ENV_NAMES = new Set([
  "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "USERPROFILE",
  "LOCALAPPDATA", "APPDATA", "HOME", "HOMEDRIVE", "HOMEPATH", "PROGRAMDATA", "PROGRAMFILES",
  "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
  "OS", "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUTF8", "NODE", "FFMPEG_PATH",
  "PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_WEB_PORT", "PLAYWRIGHT_FAKE_API_PORT",
  "VIDEOBOX_E2E_FIXTURE_FILE", "VIDEOBOX_E2E_PROTECT_ROOT", "VIDEOBOX_LOG_LEVEL",
]);
const SECRET_MARKERS = ["TOKEN", "SECRET", "PASSWORD", "KEY"];

export function buildChildEnv(parentEnv, extra = {}) {
  const child = {};
  for (const [name, value] of Object.entries(parentEnv)) {
    const upper = name.toUpperCase();
    if (!SAFE_ENV_NAMES.has(upper) || SECRET_MARKERS.some((marker) => upper.includes(marker))) continue;
    child[name] = value;
  }
  // 소유자가 설정해 둔 데이터 폴더는 시드 보호 대상으로만 넘긴다(자식이 데이터 폴더로 쓰지 못하게 이름을 바꾼다).
  if (parentEnv.VIDEOBOX_DATA_ROOT) child.VIDEOBOX_E2E_PROTECT_ROOT = parentEnv.VIDEOBOX_DATA_ROOT;
  return { ...child, ...extra };
}
