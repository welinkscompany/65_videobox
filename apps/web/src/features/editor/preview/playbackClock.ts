// 재생 시계 (2026-10-09 계획 P Task 2).
// 미리보기가 재생기 시각을 화면 프레임마다 읽어 여기에 알리면, 타임라인 재생 머리와 시간 글자가
// React를 다시 그리지 않고 DOM만 직접 고친다. React 상태(`playbackSec`)는 예전처럼 `timeupdate` 빈도(≈4Hz)로만 바뀐다.

export type PlaybackClockReading = Readonly<{ seconds: number; playing: boolean }>;
export type PlaybackClock = Readonly<{
  /** 같은 값이면 알리지 않는다. */
  publish(seconds: number, playing: boolean): void;
  read(): PlaybackClockReading;
  subscribe(listener: (reading: PlaybackClockReading) => void): () => void;
}>;

export function createPlaybackClock(initialSeconds = 0): PlaybackClock {
  let reading: PlaybackClockReading = Object.freeze({ seconds: Number.isFinite(initialSeconds) ? initialSeconds : 0, playing: false });
  const listeners = new Set<(reading: PlaybackClockReading) => void>();
  return {
    publish(seconds, playing) {
      if (!Number.isFinite(seconds)) return;
      if (reading.seconds === seconds && reading.playing === playing) return;
      reading = Object.freeze({ seconds, playing });
      // 복사본을 돈다 -- 알리는 도중 구독이 풀려도 안전하고, 하나가 던져도 나머지는 받는다.
      for (const listener of [...listeners]) {
        try { listener(reading); } catch { /* 한 구독자의 오류가 다른 구독자를 막지 않는다 */ }
      }
    },
    read: () => reading,
    subscribe(listener) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  };
}
