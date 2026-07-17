import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ManualMediaLibrary } from "./ManualMediaLibrary";
import { api } from "../../api";

const music = { library_asset_id: "pack:music", asset_id: "music-1", media_type: "music" as const, duration_seconds: 12, version: "1", verified: true, available: true, tags: ["calm"], source: "starter", creator: "VideoBox", official_license_url: "https://license", attribution_required: false, attribution_text: "" };
const broll = { asset_id: "broll-1", asset_type: "broll_video", storage_uri: "local://projects/p/assets/broll-1", created_at: "r-1", metadata: { aspect_ratio: "16:9", duration_seconds: 3, analysis_status: "succeeded", content_sha256: "sha" } };

describe("ManualMediaLibrary", () => {
  it("keeps preview mutation-free and permits explicit placement while Director is unavailable", () => {
    const applyGlobal = vi.fn(); const applyBroll = vi.fn();
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={applyGlobal} onApplyBroll={applyBroll} />);
    fireEvent.click(screen.getByRole("button", { name: "BGM 미리보기" }));
    expect(screen.getByTestId("media-library-preview")).not.toHaveAttribute("autoplay");
    expect(applyGlobal).not.toHaveBeenCalled(); expect(applyBroll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "BGM 적용" }));
    expect(applyGlobal).toHaveBeenCalledWith(music);
    fireEvent.click(screen.getByRole("button", { name: "선택 구간에 B롤 적용" }));
    expect(applyBroll).toHaveBeenCalledWith(broll);
  });

  it("requires a selected segment before explicit placement but never disables preview", () => {
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={null} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);
    expect(screen.getByRole("button", { name: "BGM 적용" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "BGM 미리보기" })).toBeEnabled();
  });

  it("does not let a blocked Director disable manual placement", () => {
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} directorState="blocked" selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("루미의 추천을 사용할 수 없어도 직접 미디어를 골라 계속 편집할 수 있어요.");
    expect(screen.getByText("미리보기는 현재 편집본을 바꾸지 않아요. 마음에 들면 프로젝트에 추가해 주세요.")).toBeInTheDocument();
    expect(screen.queryByText(/Director blocked|세션|파이프라인|job/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "BGM 적용" })).toBeEnabled();
  });

  it("drops a draggable B-roll onto the explicit selected-range target only", () => {
    const applyBroll = vi.fn();
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={applyBroll} />);
    fireEvent.drop(screen.getByLabelText("선택 구간 배치 대상"), { dataTransfer: { getData: (type: string) => type === "application/x-videobox-local-broll" ? "broll-1" : "" } });
    expect(applyBroll).toHaveBeenCalledWith(broll);
  });

  it("lets keyboard users apply the focused B-roll to the explicit selected-range target", () => {
    const applyBroll = vi.fn();
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={applyBroll} />);

    fireEvent.focus(screen.getByLabelText("B롤 자산 broll-1"));
    fireEvent.keyDown(screen.getByLabelText("선택 구간 배치 대상"), { key: "Enter" });

    expect(applyBroll).toHaveBeenCalledWith(broll);
  });

  it("filters B-roll by usable metadata and keeps excluded assets unplaceable", async () => {
    const excluded = { ...broll, asset_id: "broll-excluded", metadata: { ...broll.metadata, aspect_ratio: "9:16", duration_seconds: 12, analysis_status: "pending", review_required: true } };
    vi.spyOn(api, "getDirectorPreferences").mockResolvedValue({ pin_asset: ["broll-1"], exclude_asset: ["broll-excluded"] });
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll, excluded]} favoriteIds={[]} localFavoriteIds={["broll-1"]} recentIds={["broll-1"]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "B롤 필터: 즐겨찾기" }));
    expect(screen.getAllByText("broll-1").length).toBeGreaterThan(0);
    expect(screen.queryByText("broll-excluded")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "B롤 필터: 전체" }));
    fireEvent.click(screen.getByRole("button", { name: "B롤 검토 필요" }));
    await waitFor(() => expect(screen.getAllByText("broll-excluded").length).toBeGreaterThan(0));
    expect(screen.getAllByText("broll-excluded")[0].closest("article")?.querySelector("button:last-of-type")).toBeDisabled();
  });
});
