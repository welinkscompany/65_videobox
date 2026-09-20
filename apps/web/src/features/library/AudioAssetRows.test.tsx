import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
