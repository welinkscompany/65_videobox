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
    expect(screen.getByRole("status")).toHaveTextContent("유진의 추천을 사용할 수 없어도 직접 미디어를 골라 계속 편집할 수 있어요.");
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

    fireEvent.focus(screen.getByLabelText("B롤 영상 1"));
    fireEvent.keyDown(screen.getByLabelText("선택 구간 배치 대상"), { key: "Enter" });

    expect(applyBroll).toHaveBeenCalledWith(broll);
  });

  it("filters B-roll by usable metadata and keeps excluded assets unplaceable", async () => {
    const approved = { ...broll, metadata: { ...broll.metadata, title: "회의 시작 장면" } };
    const excluded = { ...broll, asset_id: "broll-excluded", metadata: { ...broll.metadata, title: "제외한 장면", aspect_ratio: "9:16", duration_seconds: 12, analysis_status: "pending", review_required: true } };
    vi.spyOn(api, "getDirectorPreferences").mockResolvedValue({ pin_asset: ["broll-1"], exclude_asset: ["broll-excluded"] });
    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[approved, excluded]} favoriteIds={[]} localFavoriteIds={["broll-1"]} recentIds={["broll-1"]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "B롤 필터: 즐겨찾기" }));
    expect(screen.getByText("회의 시작 장면")).toBeInTheDocument();
    expect(screen.queryByText("제외한 장면")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "B롤 필터: 전체" }));
    fireEvent.click(screen.getByRole("button", { name: "B롤 검토 필요" }));
    await waitFor(() => expect(screen.getByText("제외한 장면")).toBeInTheDocument());
    expect(screen.getByText("제외한 장면").closest("article")?.querySelector("button:last-of-type")).toBeDisabled();
  });

  it("keeps realistic internal media IDs out of rendered copy and accessible names", async () => {
    const internalMusic = { ...music, asset_id: "asset_internal_music_772", library_asset_id: "pack:internal:music:772" };
    const internalBroll = { ...broll, asset_id: "asset_internal_broll_881", metadata: { ...broll.metadata, title: "회의 시작 장면" } };
    vi.spyOn(api, "getDirectorPreferences").mockResolvedValue({ pin_asset: [], exclude_asset: [] });

    render(<ManualMediaLibrary projectId="p" assets={[internalMusic]} brollAssets={[internalBroll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);

    const copy = document.body.textContent ?? "";
    expect(copy).not.toContain("asset_internal_music_772");
    expect(copy).not.toContain("asset_internal_broll_881");
    expect(screen.getByRole("button", { name: "선택 구간 배치 대상" })).not.toHaveAccessibleName(/asset_internal/i);
    expect(screen.getByRole("article", { name: "B롤 영상 1" })).toBeVisible();
  });

  it("keeps selected-range IDs and media processing enums out of the creator-facing library", () => {
    const processingBroll = {
      ...broll,
      asset_id: "asset_internal_broll_992",
      asset_type: "broll_video",
      metadata: { ...broll.metadata, analysis_status: "succeeded", title: "작업 공간 장면" },
    };

    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[processingBroll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "segment_internal_441", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);

    const copy = document.body.textContent ?? "";
    expect(copy).not.toContain("segment_internal_441");
    expect(copy).not.toContain("broll_video");
    expect(copy).not.toContain("succeeded");
    expect(screen.getByRole("combobox", { name: "B롤 종류" })).toHaveTextContent("영상");
    expect(screen.getByRole("combobox", { name: "B롤 준비 상태" })).toHaveTextContent("준비됨");
    expect(screen.getByText(/대상 구간 · 1\.00–2\.00초/)).toBeVisible();
  });

  it("uses creator-safe labels when B-roll metadata is absent or contains an unknown sentinel", () => {
    const missingMetadata = { ...broll, asset_id: "broll-missing-metadata", metadata: { title: "정보가 비어 있는 장면" } };
    const unknownMetadata = { ...broll, asset_id: "broll-unknown-metadata", metadata: { title: "확인 중인 장면", aspect_ratio: "unknown", duration_seconds: "unknown" } };
    vi.spyOn(api, "getDirectorPreferences").mockRejectedValue(new Error("preferences are not needed for metadata display"));

    render(<ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[missingMetadata, unknownMetadata]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={vi.fn()} onApplyBroll={vi.fn()} />);

    const copy = document.body.textContent ?? "";
    expect(copy).not.toMatch(/unknown/i);
    expect(screen.getAllByText(/정보 없음/)).not.toHaveLength(0);
    expect(screen.getByRole("combobox", { name: "B롤 화면비" })).toHaveTextContent("정보 없음");
    expect(screen.getByText("확인 중인 장면").closest("article")).toHaveTextContent("화면비: 정보 없음 · 길이: 정보 없음");
  });
});
