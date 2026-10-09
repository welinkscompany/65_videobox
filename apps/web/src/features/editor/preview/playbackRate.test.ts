import { describe, expect, it } from "vitest";
import { applyPlaybackRate, formatPlaybackRate, PLAYBACK_RATES, PLAYBACK_RATE_STORAGE_KEY, readPlaybackRate, stepPlaybackRate, writePlaybackRate } from "./playbackRate";

const store = (value: string | null) => ({ getItem: (key: string) => (key === PLAYBACK_RATE_STORAGE_KEY ? value : null) });

describe("playbackRate", () => {
  it("허용 빠르기와 저장 키", () => {
    expect([...PLAYBACK_RATES]).toEqual([0.25, 0.5, 0.75, 1, 1.5, 2]);
    expect(PLAYBACK_RATE_STORAGE_KEY).toBe("videobox.editor.playback-rate");
  });
  it("한 단계씩 오르내리고 끝에서 멈춘다", () => {
    expect(stepPlaybackRate(1, 1)).toBe(1.5);
    expect(stepPlaybackRate(1.5, 1)).toBe(2);
    expect(stepPlaybackRate(2, 1)).toBe(2);
    expect(stepPlaybackRate(1, -1)).toBe(0.75);
    expect(stepPlaybackRate(0.75, -1)).toBe(0.5);
    expect(stepPlaybackRate(0.5, -1)).toBe(0.25);
    expect(stepPlaybackRate(0.25, -1)).toBe(0.25);
  });
  it.each([["0.5", 0.5], ["2", 2], ["0.25", 0.25], ["3", 1], ["abc", 1], ["NaN", 1], ["", 1], ["0.6", 1], [null, 1]])("읽기 %s -> %s", (raw, expected) => {
    expect(readPlaybackRate(store(raw as string | null))).toBe(expected);
  });
  it("저장소가 없거나 던지면 1배", () => {
    expect(readPlaybackRate(null)).toBe(1);
    expect(readPlaybackRate({ getItem: () => { throw new Error("blocked"); } })).toBe(1);
  });
  it("쓰기는 던지는 저장소에서도 안 던진다", () => {
    expect(() => writePlaybackRate(0.5, { setItem: () => { throw new Error("full"); } })).not.toThrow();
    expect(() => writePlaybackRate(0.5, null)).not.toThrow();
    const calls: string[][] = [];
    writePlaybackRate(0.75, { setItem: (k, v) => { calls.push([k, v]); } });
    expect(calls).toEqual([[PLAYBACK_RATE_STORAGE_KEY, "0.75"]]);
  });
  it("재생기의 defaultPlaybackRate와 playbackRate를 둘 다 바꾼다", () => {
    const media = document.createElement("video");
    applyPlaybackRate(media, 0.5);
    expect(media.playbackRate).toBe(0.5);
    expect(media.defaultPlaybackRate).toBe(0.5);
  });
  it("글자", () => {
    expect(formatPlaybackRate(0.25)).toBe("0.25배");
    expect(formatPlaybackRate(1)).toBe("1배");
    expect(formatPlaybackRate(2)).toBe("2배");
  });
});
