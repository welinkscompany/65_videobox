import { afterEach, describe, expect, it, vi } from "vitest";
import { readCssPixels } from "./timelineCssMetrics";

describe("readCssPixels", () => {
  afterEach(() => vi.restoreAllMocks());

  it("요소가 없으면 fallback을 돌려준다", () => {
    expect(readCssPixels(null, "--x", 32)).toBe(32);
  });

  it("계산값이 NNpx면 그 수를 돌려준다", () => {
    const el = document.createElement("div");
    vi.spyOn(window, "getComputedStyle").mockReturnValue({ getPropertyValue: () => " 44px" } as never);
    expect(readCssPixels(el, "--x", 32)).toBe(44);
  });

  it("숫자가 아니거나 비었거나 0 이하면 fallback이다", () => {
    const el = document.createElement("div");
    const spy = vi.spyOn(window, "getComputedStyle");
    for (const raw of ["abc", "", "0px", "-4px", "2rem", "calc(1px + 2px)", "50%"]) {
      spy.mockReturnValue({ getPropertyValue: () => raw } as never);
      expect(readCssPixels(el, "--x", 32)).toBe(32);
    }
  });

  it("jsdom은 사용자 변수를 못 읽어 fallback으로 간다", () => {
    const el = document.createElement("div");
    expect(readCssPixels(el, "--not-set", 32)).toBe(32);
  });
});
