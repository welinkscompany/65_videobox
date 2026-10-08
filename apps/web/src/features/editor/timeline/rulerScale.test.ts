import { describe, expect, it } from "vitest";
import { formatRulerLabel, rulerIntervals, rulerLabelAlignsEnd, rulerMarks } from "./rulerScale";
const fps30 = { num: 30, den: 1 };
describe("눈금 간격 (2026-10-08 점검 그림 10, 스파이크 §3(라))", () => {
  it("742e1924 전체 보기 11.2px/초는 15초마다(168px), 잔눈금 3초", () => {
    expect(rulerIntervals(11.2, fps30, 120)).toEqual({ majorSec: 15, minorSec: 3 });
    expect(rulerMarks({ startSec: 0, endSec: 120, majorSec: 15 })).toHaveLength(9);
  });
  it("50px/초는 3초마다", () => expect(rulerIntervals(50, fps30, 120).majorSec).toBe(3));
  it("0907 전체 보기 173px/초는 1초마다(그대로 8개)", () => {
    expect(rulerIntervals(173, fps30, 120).majorSec).toBe(1);
    expect(rulerMarks({ startSec: 0, endSec: 7.75, majorSec: 1 })).toHaveLength(8);
  });
  it("아주 크게 늘리면 프레임 단위로 내려간다(2프레임 = 133px)", () => expect(rulerIntervals(2000, fps30, 120).majorSec).toBeCloseTo(2 / 30, 9));
  it("글자는 간격에 맞춰 읽기 좋게", () => {
    expect(formatRulerLabel(15, 15)).toBe("15s");
    expect(formatRulerLabel(90, 30)).toBe("1:30");
    expect(formatRulerLabel(0.1, 0.1)).toBe("0.1s");
  });
});

describe("눈금 간격 경계", () => {
  const gap = 120;
  it("고른 간격은 글자 사이가 최소 간격 이상이고, 한 단계 작은 후보는 모자란다", () => {
    for (const pps of [0.2, 0.37, 1, 4.5, 11.2, 33.3, 50, 99.9, 120, 173, 450, 2000]) {
      const { majorSec } = rulerIntervals(pps, fps30, gap);
      expect(majorSec * pps).toBeGreaterThanOrEqual(gap - 1e-9);
    }
  });
  it("1시간 영상 전체 보기(1343px에 3600초 = 0.373px/초)는 10분마다 7개", () => {
    const { majorSec } = rulerIntervals(1343 / 3600, fps30, gap);
    expect(majorSec).toBe(600);
    expect(rulerMarks({ startSec: 0, endSec: 3600, majorSec })).toHaveLength(7);
    expect(formatRulerLabel(3000, majorSec)).toBe("50:00");
  });
  it("후보 끝을 넘는 극단 축소는 가장 큰 간격에 머문다", () => {
    expect(rulerIntervals(0.001, fps30, gap).majorSec).toBe(3600);
  });
  it("정수가 아닌 배율(383.877159px/초, 7.31px/초)도 같은 규칙이다", () => {
    expect(rulerIntervals(383.877159, fps30, gap).majorSec).toBeCloseTo(10 / 30, 9); // 10프레임=127.9px
    expect(rulerIntervals(7.31, fps30, gap).majorSec).toBe(30); // 15초=109.7px < 120, 30초=219px
  });
  it("잔눈금은 큰 눈금의 약수이고 최소 간격/5 이상이다", () => {
    for (const pps of [11.2, 50, 173, 7.31]) {
      const { majorSec, minorSec } = rulerIntervals(pps, fps30, gap);
      expect(minorSec * pps).toBeGreaterThanOrEqual(gap / 5 - 1e-9);
      expect(Math.abs(majorSec / minorSec - Math.round(majorSec / minorSec))).toBeLessThan(1e-9);
    }
  });
  it("25fps에서도 프레임 간격은 그 fps의 프레임 길이를 따른다", () => {
    expect(rulerIntervals(2000, { num: 25, den: 1 }, gap).majorSec).toBeCloseTo(0.08, 9);
  });
  it("보이는 구간이 0이 아닌 데서 시작해도 간격의 배수 위에 찍힌다", () => {
    expect(rulerMarks({ startSec: 20, endSec: 70, majorSec: 15 })).toEqual([30, 45, 60]);
    expect(rulerMarks({ startSec: 0.2, endSec: 1, majorSec: 0.1 })).toEqual([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]);
  });
  it("잘못된 입력은 안전하게 비운다", () => {
    expect(rulerMarks({ startSec: 5, endSec: 1, majorSec: 1 })).toEqual([]);
    expect(rulerMarks({ startSec: 0, endSec: 10, majorSec: 0 })).toEqual([]);
  });
  it("글자: 60초 이상은 분:초, 1초 미만 간격은 소수", () => {
    expect(formatRulerLabel(60, 60)).toBe("1:00");
    expect(formatRulerLabel(0, 15)).toBe("0s");
    expect(formatRulerLabel(1.5, 0.5)).toBe("1.5s");
    expect(formatRulerLabel(2 / 30, 2 / 30)).toBe("0.067s");
  });
});

describe("칸 끝 눈금은 글자를 선 왼쪽에 얹는다", () => {
  const base = { viewportEndSec: 120, pixelsPerSecond: 11.2, labelRoomPx: 40 };
  it("영상 끝(120초)과 3초 안쪽(33.6px)은 얹고, 15초(168px) 안쪽은 그대로", () => {
    expect(rulerLabelAlignsEnd({ ...base, seconds: 120 })).toBe(true);
    expect(rulerLabelAlignsEnd({ ...base, seconds: 117 })).toBe(true);
    expect(rulerLabelAlignsEnd({ ...base, seconds: 105 })).toBe(false);
  });
  it("0초는 왼쪽 끝이라 얹지 않고, 보이는 구간이 1초밖에 안 되어도 마찬가지다", () => {
    expect(rulerLabelAlignsEnd({ ...base, seconds: 0 })).toBe(false);
    expect(rulerLabelAlignsEnd({ viewportEndSec: 1, pixelsPerSecond: 20, labelRoomPx: 40, seconds: 0 })).toBe(false);
  });
  it("전체 보기 120초의 큰 눈금 9개 중 마지막 하나만 얹는다", () => {
    const marks = rulerMarks({ startSec: 0, endSec: 120, majorSec: 15 });
    expect(marks.filter((seconds) => rulerLabelAlignsEnd({ ...base, seconds }))).toEqual([120]);
  });
});
