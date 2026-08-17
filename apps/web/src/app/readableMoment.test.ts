import { describe, expect, it } from "vitest";

import { readableMoment } from "./readableMoment";

const now = new Date("2026-08-17T12:00:00Z");

describe("readableMoment", () => {
  it("says how long ago it was, the way a person would", () => {
    // owner가 본 것: `2026-08-17T06:13:40.438824+00:00`. 카드 폭에서 줄바꿈돼
    // `+00:0 0`으로 잘리기까지 했다.
    expect(readableMoment("2026-08-17T11:59:30Z", now)).toBe("방금");
    expect(readableMoment("2026-08-17T11:20:00Z", now)).toBe("40분 전");
    expect(readableMoment("2026-08-17T06:13:40.438824+00:00", now)).toBe("5시간 전");
    expect(readableMoment("2026-08-16T12:00:00Z", now)).toBe("어제");
    expect(readableMoment("2026-08-14T12:00:00Z", now)).toBe("3일 전");
  });

  it("falls back to a plain date once it is no longer recent", () => {
    expect(readableMoment("2026-07-02T12:00:00Z", now)).toBe("7월 2일");
    // 해가 넘어가면 연도까지 붙는다 -- 없으면 언제인지 알 수 없다.
    expect(readableMoment("2025-12-30T12:00:00Z", now)).toBe("2025년 12월 30일");
  });

  it("says nothing rather than something wrong when the moment is unreadable", () => {
    expect(readableMoment("", now)).toBe(null);
    expect(readableMoment("어제쯤", now)).toBe(null);
    // 시계가 어긋나 미래로 보이는 것을 "-3분 전"이라고 하지 않는다.
    expect(readableMoment("2026-08-17T12:05:00Z", now)).toBe("방금");
  });
});
