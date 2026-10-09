import { describe, expect, it, vi } from "vitest";

import { createPlaybackClock } from "./playbackClock";

describe("재생 시계", () => {
  it("값을 알리면 구독자가 한 번 받고 read가 같은 값을 돌려준다", () => {
    const clock = createPlaybackClock();
    const listener = vi.fn();
    clock.subscribe(listener);
    clock.publish(1, true);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith({ seconds: 1, playing: true });
    expect(clock.read()).toEqual({ seconds: 1, playing: true });
  });

  it("처음 값은 만들 때 준 시각이고 멈춘 상태다", () => {
    expect(createPlaybackClock(4).read()).toEqual({ seconds: 4, playing: false });
    expect(createPlaybackClock().read()).toEqual({ seconds: 0, playing: false });
  });

  it("같은 값을 다시 알리면 알리지 않는다", () => {
    const clock = createPlaybackClock();
    const listener = vi.fn();
    clock.subscribe(listener);
    clock.publish(1, true);
    clock.publish(1, true);
    expect(listener).toHaveBeenCalledTimes(1);
    clock.publish(1, false);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("구독을 풀면 더는 알리지 않는다", () => {
    const clock = createPlaybackClock();
    const listener = vi.fn();
    const unsubscribe = clock.subscribe(listener);
    unsubscribe();
    clock.publish(2, true);
    expect(listener).not.toHaveBeenCalled();
  });

  it("구독자 하나가 던져도 다른 구독자는 받는다", () => {
    const clock = createPlaybackClock();
    const second = vi.fn();
    clock.subscribe(() => { throw new Error("깨진 구독자"); });
    clock.subscribe(second);
    expect(() => clock.publish(3, true)).not.toThrow();
    expect(second).toHaveBeenCalledWith({ seconds: 3, playing: true });
  });

  it("숫자가 아닌 값은 받지 않는다", () => {
    const clock = createPlaybackClock(1);
    const listener = vi.fn();
    clock.subscribe(listener);
    clock.publish(Number.NaN, true);
    expect(listener).not.toHaveBeenCalled();
    expect(clock.read().seconds).toBe(1);
  });
});
