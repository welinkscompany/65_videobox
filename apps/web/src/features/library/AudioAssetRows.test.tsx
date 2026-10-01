import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { LibraryAsset } from "../../api";
import { AudioAssetRows } from "./AudioAssetRows";

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  return {
    library_asset_id: "asset_1",
    media_type: "music",
    origin: "user",
    lifecycle: "ready",
    user_metadata: { filename: "calm.mp3" },
    ...overrides,
  };
}

describe("AudioAssetRows", () => {
  it("의미검색으로 찾은 행에는 관련도를 보여준다", () => {
    render(<AudioAssetRows assets={[asset({ semantic_match: true, relevance_percent: 70 })]} onSelect={() => {}} />);
    expect(screen.getByText("관련도 70%")).toBeInTheDocument();
  });

  it("단어로 찾았거나 관련도가 없는 행에는 아무것도 안 붙인다", () => {
    render(<AudioAssetRows assets={[asset()]} onSelect={() => {}} />);
    expect(screen.queryByText(/관련도/)).toBeNull();
  });

  // 2026-10-01 점검: ☆ 단추는 클릭 전파만 막고 아무 일도 하지 않았다.
  it("☆ 단추가 즐겨찾기를 바꾸고, 켜져 있으면 ★로 보인다", () => {
    const onToggleFavorite = vi.fn();
    const onSelect = vi.fn();
    render(<AudioAssetRows assets={[asset({ user_metadata: { filename: "calm.mp3", favorite: true } })]} onSelect={onSelect} onToggleFavorite={onToggleFavorite} />);
    const star = screen.getByRole("button", { name: "calm.mp3 즐겨찾기" });
    expect(star).toHaveTextContent("★");
    expect(star).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(star);
    expect(onToggleFavorite).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("기본 소재팩에는 ☆를 내지 않는다 (바꿀 수 없다)", () => {
    render(<AudioAssetRows assets={[asset({ origin: "builtin" })]} onSelect={() => {}} onToggleFavorite={() => {}} />);
    expect(screen.queryByRole("button", { name: /즐겨찾기/ })).toBeNull();
  });
});
