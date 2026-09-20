import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type LibraryAsset } from "../../../api";
import { LibraryPickerDialog } from "./LibraryPickerDialog";

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

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listLibraryAssets").mockResolvedValue({ assets: [asset()], total: 1 });
});
afterEach(() => cleanup());

/**
 * 2026-09-20 코드리뷰 실측: 이 팝업은 `/library` 화면의 옛 검색 로직을 그대로
 * 베껴 왔는데, "전체" 탭 fan-out(같은 owner 결정)은 안 따라왔었다 -- 같은
 * 검색어로 두 진입점이 다른 결과·다른 배지를 보여 주는 불일치였다. 여기서
 * 잠근다.
 */
describe("LibraryPickerDialog", () => {
  it("`전체` 탭에서도 네 종류에 함께 물어 뜻으로 찾는다", async () => {
    const search = vi.spyOn(api, "searchLibraryAssets").mockImplementation(async (_query, mediaType) => ({
      matches: [{ ...asset({ library_asset_id: `${mediaType}_1`, media_type: mediaType, user_metadata: { filename: `${mediaType}.dat` } }), score: 0.9, semantic_match: true }],
      semantic: true,
    }));
    render(<LibraryPickerDialog open projectId="project-a" onOpenChange={() => {}} />);
    fireEvent.change(await screen.findByLabelText("검색"), { target: { value: "공원" } });

    await waitFor(() => expect(search).toHaveBeenCalledWith("공원", "broll", undefined));
    expect(search).toHaveBeenCalledWith("공원", "music", undefined);
    expect(search).toHaveBeenCalledWith("공원", "sfx", undefined);
    expect(search).toHaveBeenCalledWith("공원", "image", undefined);
    expect(await screen.findByRole("status", { name: "찾은 방식" })).toHaveTextContent("뜻으로 찾음");
  });

  it("의미검색 결과 카드에도 관련도 배지를 붙인다", async () => {
    vi.spyOn(api, "searchLibraryAssets").mockImplementation(async (_query, mediaType) => ({
      matches: mediaType === "broll"
        ? [{ ...asset({ library_asset_id: "hit", user_metadata: { filename: "hit.mp4" } }), score: 0.9, semantic_match: true }]
        : [],
      semantic: mediaType === "broll",
    }));
    render(<LibraryPickerDialog open projectId="project-a" onOpenChange={() => {}} />);
    fireEvent.change(await screen.findByLabelText("검색"), { target: { value: "공원" } });

    await screen.findAllByText("hit.mp4");
    expect(within(screen.getByTestId("library-video-grid")).getByText("관련도 100%")).toBeInTheDocument();
  });
});
