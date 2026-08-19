import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  getYujinStarters,
  readYujinStarterUsage,
  recordYujinStarterUse,
  type YujinStarterContext,
} from "./starterRegistry";
import { YujinStarters } from "./YujinStarters";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe("Yujin starter registry", () => {
  it("selects edit starters from the current segment context", () => {
    const starters = getYujinStarters({ surface: "edit", selection: "segment" });

    expect(starters.map((starter) => starter.id)).toEqual([
      "broll-recommendation",
      "edit-flow-review",
      "caption-tighten",
      "vertical-cut",
    ]);
  });

  it("keeps the baseline edit starters available before a segment is selected", () => {
    const starters = getYujinStarters({ surface: "edit", selection: "none" });

    expect(starters.map((starter) => starter.id)).toEqual(expect.arrayContaining([
      "broll-recommendation",
      "edit-flow-review",
      "caption-tighten",
      "vertical-cut",
    ]));
  });

  it("selects footage starters without mixing in editor-only prompts", () => {
    const starters = getYujinStarters({ surface: "footage", selection: "none" });

    expect(starters.map((starter) => starter.label)).toEqual([
      "장면 변화로 나누기",
      "출근 과정만 고르기",
      "흔들린 구간 찾기",
      "짧은 영상 묶기",
      "세로 장면 고르기",
      "30초 묶음 만들기",
    ]);
    expect(starters.some((starter) => starter.id === "caption-tighten")).toBe(false);
  });

  it("offers the thumbnail prompt starter where thumbnails are decided", () => {
    // owner 승인(2026-08-19): 유진이 썸네일 이미지 생성 도구에 붙여 넣을
    // 프롬프트를 추천한다. 이미지 생성 자체는 하지 않는다.
    const label = "썸네일 만들 프롬프트 추천해 줘";
    expect(getYujinStarters({ surface: "plan", selection: "none" })
      .some((starter) => starter.label === label)).toBe(true);
    expect(getYujinStarters({ surface: "output", selection: "proposal" })
      .some((starter) => starter.label === label)).toBe(true);
    // 편집 화면의 유진 패널은 includeRelated로 관련 스타터까지 보여 준다.
    expect(getYujinStarters({ surface: "edit", selection: "segment", includeRelated: true })
      .some((starter) => starter.label === label)).toBe(true);
  });

  it("keeps plan, asset, review, and output contexts separate", () => {
    expect(getYujinStarters({ surface: "plan", selection: "none" })).toHaveLength(5);
    expect(getYujinStarters({ surface: "assets", selection: "asset" })[0]?.id)
      .toBe("assets-organize-sources");
    expect(getYujinStarters({
      surface: "assets",
      selection: "asset",
      blockers: ["needs_assets"],
    })[0]?.id).toBe("assets-missing-broll");
    expect(getYujinStarters({ surface: "review", selection: "proposal" }).map((starter) => starter.id))
      .toEqual(["review-risk-segments", "review-approval-check"]);
    expect(getYujinStarters({ surface: "output", selection: "variant" })
      .some((starter) => starter.id === "output-vertical-check")).toBe(true);
  });

  it("promotes frequently used starters without changing project context", () => {
    const starters = getYujinStarters({
      surface: "edit",
      selection: "segment",
      recentUsage: { "caption-tighten": 4, "broll-recommendation": 1 },
    });

    expect(starters[0]?.id).toBe("caption-tighten");
  });

  it("persists only local starter usage counts", () => {
    const storage = new MemoryStorage();

    recordYujinStarterUse("caption-tighten", storage);
    recordYujinStarterUse("caption-tighten", storage);

    expect(readYujinStarterUsage(storage)).toEqual({ "caption-tighten": 2 });
  });
});

describe("YujinStarters", () => {
  const context: YujinStarterContext = { surface: "edit", selection: "segment" };

  it("fills the composer and exposes more examples without sending", () => {
    const onSelect = vi.fn();
    render(<YujinStarters context={context} onSelect={onSelect} />);

    const group = screen.getByRole("group", { name: "대화 스타터" });
    expect(within(group).getByRole("button", { name: "다른 예시" })).toBeVisible();
    expect(within(group).getByRole("button", { name: "전체 보기" })).toBeVisible();

    fireEvent.click(within(group).getByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "broll-recommendation" }));

    fireEvent.click(within(group).getByRole("button", { name: "전체 보기" }));
    expect(within(group).getByRole("button", { name: "검토할 위험 구간 알려 줘" })).toBeVisible();
  });

  it("rotates the visible examples without invoking a mutation callback", () => {
    const onSelect = vi.fn();
    render(<YujinStarters context={context} onSelect={onSelect} />);
    const group = screen.getByRole("group", { name: "대화 스타터" });

    fireEvent.click(within(group).getByRole("button", { name: "다른 예시" }));

    expect(within(group).getByRole("button", { name: "검토할 위험 구간 알려 줘" })).toBeVisible();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("disables navigation controls with the composer", () => {
    render(<YujinStarters context={context} onSelect={vi.fn()} disabled />);
    const group = screen.getByRole("group", { name: "대화 스타터" });

    expect(within(group).getByRole("button", { name: "다른 예시" })).toBeDisabled();
    expect(within(group).getByRole("button", { name: "전체 보기" })).toBeDisabled();
  });
});
