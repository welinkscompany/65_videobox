import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import { longWaitNotice, useWaitElapsedSeconds, waitElapsedLabel } from "./waitingNotice";

afterEach(cleanup);

describe("기다림 문구", () => {
  it("흘러간 시간을 사람이 읽는 말로 적는다", () => {
    expect(waitElapsedLabel(0)).toBe("0초");
    expect(waitElapsedLabel(45)).toBe("45초");
    expect(waitElapsedLabel(60)).toBe("1분");
    expect(waitElapsedLabel(65)).toBe("1분 5초");
    // 장면 나누기 93번째 실측값(298초).
    expect(waitElapsedLabel(298)).toBe("4분 58초");
  });

  it("짧은 기다림에는 아무 말도 덧붙이지 않는다", () => {
    expect(longWaitNotice(0)).toBeNull();
    expect(longWaitNotice(9)).toBeNull();
  });

  it("길어지면 오래 걸릴 수 있다고 정직하게 말한다 -- 백분율은 만들지 않는다", () => {
    const notice = longWaitNotice(605);
    expect(notice).toBe("10분 5초 지났어요. 오래 걸릴 수 있어요. 이 화면을 열어 둔 채 기다려 주세요.");
    expect(notice).not.toMatch(/%/);
  });
});

function Clock({ active }: { active: boolean }) {
  const elapsed = useWaitElapsedSeconds(active);
  return <p aria-label="지난 시간">{String(elapsed)}</p>;
}

describe("기다림 시계", () => {
  it("기다리는 동안 계속 세고, 기다릴 것이 없어지면 타이머까지 거둔다", () => {
    vi.useFakeTimers();
    try {
      const view = render(<Clock active />);
      expect(screen.getByLabelText("지난 시간")).toHaveTextContent("0");

      act(() => { vi.advanceTimersByTime(65_000); });
      expect(Number(screen.getByLabelText("지난 시간").textContent)).toBeGreaterThanOrEqual(60);

      // **멈추는 조건**: 기다릴 것이 없어지면 다음 한 번을 걸지 않는다.
      view.rerender(<Clock active={false} />);
      act(() => { vi.advanceTimersByTime(600_000); });
      expect(screen.getByLabelText("지난 시간")).toHaveTextContent("0");
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("화면을 떠나면 타이머가 남지 않는다", () => {
    vi.useFakeTimers();
    try {
      const view = render(<Clock active />);
      act(() => { vi.advanceTimersByTime(10_000); });
      expect(vi.getTimerCount()).toBeGreaterThan(0);

      view.unmount();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });
});
