// 재생 빠르기 (2026-10-09 계획 P Task 4). 보는 속도만 바꾼다 -- 완성 영상과 장면 `속도`는 그대로다.
export const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8] as const;
export type PlaybackRate = (typeof PLAYBACK_RATES)[number];
export const PLAYBACK_RATE_STORAGE_KEY = "videobox.editor.playback-rate";
/** "L 키로 빠르게" 첫 사용 안내를 이미 봤는지 -- 한 번 보면 다시 안 띄운다. */
export const PLAYBACK_RATE_HINT_STORAGE_KEY = "videobox.editor.playback-rate-hint-seen";

/** 사생활 창에서는 `localStorage` 접근 자체가 던진다 -- 항상 try 안에서 읽는다. */
function defaultStorage(): Storage | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }
}

export function readPlaybackRate(storage?: Pick<Storage, "getItem"> | null): PlaybackRate {
  try {
    const source = storage === undefined ? defaultStorage() : storage;
    const raw = source?.getItem(PLAYBACK_RATE_STORAGE_KEY);
    if (raw === null || raw === undefined || raw.trim() === "") return 1;
    const value = Number(raw);
    return PLAYBACK_RATES.find((rate) => rate === value) ?? 1;
  } catch { return 1; }
}

export function writePlaybackRate(rate: PlaybackRate, storage?: Pick<Storage, "setItem"> | null): void {
  try {
    const target = storage === undefined ? defaultStorage() : storage;
    target?.setItem(PLAYBACK_RATE_STORAGE_KEY, String(rate));
  } catch { /* 저장하지 못해도 이번 보기는 그대로 간다 */ }
}

/** 한 단계. 끝에서는 멈춘다. */
export function stepPlaybackRate(rate: PlaybackRate, direction: 1 | -1): PlaybackRate {
  const index = PLAYBACK_RATES.indexOf(rate);
  const next = Math.min(PLAYBACK_RATES.length - 1, Math.max(0, (index < 0 ? PLAYBACK_RATES.indexOf(1) : index) + direction));
  return PLAYBACK_RATES[next];
}

/** 소스가 바뀌면 `playbackRate`가 `defaultPlaybackRate`로 돌아간다 -- 둘 다 건다. */
export function applyPlaybackRate(media: HTMLMediaElement, rate: PlaybackRate): void {
  try {
    // 순서가 중요하다: 기본값을 먼저 바꾸면 `ratechange`가 옛 빠르기를 들고 먼저 온다.
    media.playbackRate = rate;
    media.defaultPlaybackRate = rate;
  } catch { /* 해제된 재생기일 수 있다 */ }
}

export function formatPlaybackRate(rate: PlaybackRate): string {
  return `${rate}배`;
}

export function maxPlaybackRate(): PlaybackRate {
  return PLAYBACK_RATES[PLAYBACK_RATES.length - 1];
}

/** 저장소를 못 읽으면 "봤다"로 친다 -- 안내를 지울 수 없는 창에서 계속 뜨지 않게. */
export function readRateHintSeen(storage?: Pick<Storage, "getItem"> | null): boolean {
  try {
    const source = storage === undefined ? defaultStorage() : storage;
    if (!source) return true;
    return source.getItem(PLAYBACK_RATE_HINT_STORAGE_KEY) === "1";
  } catch { return true; }
}

export function markRateHintSeen(storage?: Pick<Storage, "setItem"> | null): void {
  try {
    const target = storage === undefined ? defaultStorage() : storage;
    target?.setItem(PLAYBACK_RATE_HINT_STORAGE_KEY, "1");
  } catch { /* 저장하지 못해도 이번 화면에서는 이미 지웠다 */ }
}
