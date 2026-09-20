import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LibraryAsset } from "../../api";
import { VideoAssetGrid } from "./VideoAssetGrid";

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  return {
    library_asset_id: "asset_1",
    media_type: "broll",
    origin: "user",
    lifecycle: "ready",
    user_metadata: { filename: "walk.mp4" },
    ...overrides,
  };
}

describe("VideoAssetGrid", () => {
  it("의미검색으로 찾은 카드에는 관련도를 보여준다", () => {
    render(<VideoAssetGrid assets={[asset({ semantic_match: true, relevance_percent: 92 })]} onSelect={() => {}} />);
    expect(screen.getByText("관련도 92%")).toBeInTheDocument();
  });

  it("단어로 찾았거나 관련도가 없는 카드에는 아무것도 안 붙인다", () => {
    render(<VideoAssetGrid assets={[asset()]} onSelect={() => {}} />);
    expect(screen.queryByText(/관련도/)).toBeNull();
  });
});
