import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { MediaLibraryBrowser } from "./MediaLibraryBrowser";

function asset(overrides: Partial<api.MediaLibraryAsset> = {}): api.MediaLibraryAsset {
  return {
    library_asset_id: "pack:starter-v1:music-intro",
    asset_id: "music-intro",
    media_type: "music",
    duration_seconds: 82,
    version: "1.0.0",
    verified: true,
    available: true,
    tags: ["밝은"],
    source: "https://example.test",
    creator: "Tozan",
    official_license_url: "https://example.test/license",
    attribution_required: false,
    attribution_text: "",
    ...overrides,
  } as api.MediaLibraryAsset;
}

describe("MediaLibraryBrowser", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api.api, "listRecentMediaLibraryAssetIds").mockResolvedValue({ asset_ids: [] } as never);
  });

  it("lets the owner listen to a track before choosing it", async () => {
    // 130 assets arrived with no way to hear one, so picking meant reading
    // filenames and guessing.
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    const player = await screen.findByLabelText("music-intro 미리 듣기");
    expect(player).toHaveAttribute(
      "src",
      "/api/media-library/assets/pack%3Astarter-v1%3Amusic-intro/preview",
    );
  });

  it("remembers a favourite and shows it first", async () => {
    const plain = asset({ library_asset_id: "pack:starter-v1:music-plain", asset_id: "music-plain" });
    const loved = asset({ library_asset_id: "pack:starter-v1:music-loved", asset_id: "music-loved" });
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [plain, loved] } as never);
    vi.spyOn(api.api, "listMediaLibraryFavorites").mockResolvedValue({
      asset_ids: ["pack:starter-v1:music-loved"],
    } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    const items = await screen.findAllByRole("article");
    expect(within(items[0]).getByText("music-loved")).toBeVisible();
  });

  it("saves a new favourite the owner marks", async () => {
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [asset()] } as never);
    vi.spyOn(api.api, "listMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);
    const save = vi.spyOn(api.api, "setMediaLibraryFavorite").mockResolvedValue({
      asset_ids: ["pack:starter-v1:music-intro"],
    } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "music-intro 즐겨찾기" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith("pack:starter-v1:music-intro", true));
    expect(await screen.findByRole("button", { name: "music-intro 즐겨찾기 해제" })).toBeVisible();
  });

  it("separates music from effects so a search is not one long list", async () => {
    const music = asset();
    const effect = asset({
      library_asset_id: "pack:starter-v1:sfx-pop", asset_id: "sfx-pop", media_type: "sfx", duration_seconds: 1,
    });
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music, effect] } as never);
    vi.spyOn(api.api, "listMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);
    await screen.findByText("music-intro");

    fireEvent.click(screen.getByRole("button", { name: "효과음만 보기" }));

    expect(screen.getByText("sfx-pop")).toBeVisible();
    expect(screen.queryByText("music-intro")).toBeNull();
  });

  it("says so plainly when the library has not been installed", async () => {
    vi.spyOn(api.api, "listMediaLibraryAssets").mockResolvedValue({ assets: [] } as never);
    vi.spyOn(api.api, "listMediaLibraryFavorites").mockResolvedValue({ asset_ids: [] } as never);

    render(<MediaLibraryBrowser projectId="project-a" />);

    expect(await screen.findByText("아직 준비된 음악과 효과음이 없어요.")).toBeVisible();
  });
});
