import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { DirectorProposal } from "../../api";
import { ManualMediaLibrary } from "../media/ManualMediaLibrary";
import { DirectorWorkspace } from "./DirectorWorkspace";

const proposal: DirectorProposal = {
  proposal_id: "proposal-responsive", revision_code: "PR-1", revision: 1, base_session_revision: 1,
  asset_index_revision: 1, source_session_id: "session-1", target_segment_ids: ["segment-1"], source_script_segment_ids: ["segment-1"], status: "ready", diff: {}, expires_at: null,
  candidates: [{ candidate_id: "candidate-1", visible_reference_code: "PR-1-B-01", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: ["전환"], scores: {}, availability: "available", review_status: "verified", preview_uri: null, controls: {}, expected_content_sha256: null, media_revision: "1", canonical_metadata: {}, license_policy: "ok", warning_provenance: [] }],
};

let viewportWidth = 1000;
let viewportReducedMotion = false;
const mediaListeners = new Map<string, Set<(event: MediaQueryListEvent) => void>>();
function mediaMatches(query: string) { return query === "(max-width: 760px)" ? viewportWidth <= 760 : query === "(prefers-reduced-motion: reduce)" && viewportReducedMotion; }
function setViewport(width: number, reducedMotion = false) {
  viewportWidth = width; viewportReducedMotion = reducedMotion;
  if (!window.matchMedia) Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn((query: string) => ({ get matches() { return mediaMatches(query); }, media: query, onchange: null, addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => { const listeners = mediaListeners.get(query) ?? new Set(); listeners.add(listener); mediaListeners.set(query, listeners); }, removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => mediaListeners.get(query)?.delete(listener), addListener: (listener: (event: MediaQueryListEvent) => void) => { const listeners = mediaListeners.get(query) ?? new Set(); listeners.add(listener); mediaListeners.set(query, listeners); }, removeListener: (listener: (event: MediaQueryListEvent) => void) => mediaListeners.get(query)?.delete(listener), dispatchEvent: vi.fn() })) });
  mediaListeners.forEach((listeners, query) => listeners.forEach((listener) => listener({ matches: mediaMatches(query), media: query } as MediaQueryListEvent)));
}

function renderResponsiveDirector(width: number, reducedMotion = false, background?: ReactNode) {
  setViewport(width, reducedMotion);
  render(<><DirectorWorkspace state="proposal_ready" projectId="project-1" sessionId="session-1" sessionRevision={1} proposal={proposal} sendMessage={vi.fn()} preflightProposal={vi.fn().mockResolvedValue({ status: "ready", diff: {} })} materializeCandidate={vi.fn()} applyProposal={vi.fn()} onManualMode={vi.fn()} />{background}</>);
}

const music = { library_asset_id: "pack:music", asset_id: "music-1", media_type: "music" as const, duration_seconds: 12, version: "1", verified: true, available: true, tags: ["calm"], source: "starter", creator: "VideoBox", official_license_url: "https://license", attribution_required: false, attribution_text: "" };
const broll = { asset_id: "broll-1", asset_type: "broll_video", storage_uri: "local://projects/p/assets/broll-1", created_at: "r-1", metadata: { aspect_ratio: "16:9", duration_seconds: 3, analysis_status: "succeeded", content_sha256: "sha" } };

describe("responsive Director workspace", () => {
  it("640px sheet preserves the draft and returns focus after Escape", async () => {
    renderResponsiveDirector(640);
    const openButton = screen.getByRole("button", { name: "루미 열기" });
    fireEvent.click(openButton);
    const textbox = screen.getByRole("textbox", { name: "루미에게 요청하기" });
    fireEvent.change(textbox, { target: { value: "사람 없는 영상" } });
    fireEvent.keyDown(textbox, { key: "Escape" });
    await waitFor(() => expect(openButton).toHaveFocus());
    fireEvent.click(openButton);
    expect(screen.getByRole("textbox", { name: "루미에게 요청하기" })).toHaveValue("사람 없는 영상");
  });

  it("640px sheet is an aria-modal dialog and traps keyboard focus", async () => {
    renderResponsiveDirector(640);
    fireEvent.click(screen.getByRole("button", { name: "루미 열기" }));
    const dialog = screen.getByRole("dialog", { name: "루미 영상 도우미" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const closeButton = screen.getByRole("button", { name: "닫기" });
    closeButton.focus();
    fireEvent.keyDown(closeButton, { key: "Tab" });
    await waitFor(() => expect(screen.getByRole("button", { name: "뒤로" })).toHaveFocus());
  });

  it("moves initial focus into the dialog and wraps both Tab directions", async () => {
    renderResponsiveDirector(640);
    fireEvent.click(screen.getByRole("button", { name: "루미 열기" }));
    const backButton = screen.getByRole("button", { name: "뒤로" });
    const closeButton = screen.getByRole("button", { name: "닫기" });
    await waitFor(() => expect(backButton).toHaveFocus());
    fireEvent.keyDown(backButton, { key: "Tab", shiftKey: true });
    expect(closeButton).toHaveFocus();
    fireEvent.keyDown(closeButton, { key: "Tab" });
    expect(backButton).toHaveFocus();
  });

  it("back and close both return to the trigger while preserving the draft", async () => {
    renderResponsiveDirector(640);
    const openButton = screen.getByRole("button", { name: "루미 열기" });
    fireEvent.click(openButton);
    fireEvent.change(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { target: { value: "유지할 초안" } });
    fireEvent.click(screen.getByRole("button", { name: "뒤로" }));
    await waitFor(() => expect(openButton).toHaveFocus());
    fireEvent.click(openButton);
    expect(screen.getByRole("textbox", { name: "루미에게 요청하기" })).toHaveValue("유지할 초안");
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(openButton).toHaveFocus());
    fireEvent.click(openButton);
    expect(screen.getByRole("textbox", { name: "루미에게 요청하기" })).toHaveValue("유지할 초안");
  });

  it("uses a bounded desktop aside and an accessible collapse control", async () => {
    renderResponsiveDirector(1000);
    await screen.findByText("추천을 적용하기 전에 변경된 내용이 있는지 확인하고 있어요.");
    const aside = screen.getByRole("complementary", { name: "루미 영상 도우미" });
    expect(aside).toHaveClass("director-aside");
    fireEvent.click(screen.getByRole("button", { name: "루미 접기" }));
    expect(screen.getByRole("button", { name: "루미 펼치기" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("textbox", { name: "루미에게 요청하기" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "루미 펼치기" }));
    expect(screen.getByRole("textbox", { name: "루미에게 요청하기" })).toBeVisible();
  });

  it("marks the narrow candidate tray as a carousel and exposes reduced-motion preference", async () => {
    renderResponsiveDirector(640, true);
    fireEvent.click(screen.getByRole("button", { name: "루미 열기" }));
    await screen.findByText("추천을 적용하기 전에 변경된 내용이 있는지 확인하고 있어요.");
    expect(screen.getByLabelText("추천 항목")).toHaveAttribute("data-responsive-candidate-tray", "carousel");
    expect(screen.getByRole("dialog", { name: "루미 영상 도우미" })).toHaveAttribute("data-reduced-motion", "true");
  });

  it("blocks Task16 manual library background focus and apply while the sheet is open", async () => {
    const applyGlobal = vi.fn(); const applyBroll = vi.fn();
    renderResponsiveDirector(640, false, <ManualMediaLibrary projectId="p" assets={[music]} brollAssets={[broll]} favoriteIds={[]} localFavoriteIds={[]} recentIds={[]} selectedSegment={{ segmentId: "seg-1", startSec: 1, endSec: 2 }} busy={false} onToggleFavorite={vi.fn()} onToggleLocalFavorite={vi.fn()} onApplyGlobal={applyGlobal} onApplyBroll={applyBroll} />);
    fireEvent.click(screen.getByRole("button", { name: "루미 열기" }));
    await screen.findByRole("dialog", { name: "루미 영상 도우미" });
    const backgroundApply = screen.getByRole("button", { name: "BGM 적용", hidden: true });
    const backgroundBrollApply = screen.getByRole("button", { name: "선택 구간에 B롤 적용", hidden: true });
    fireEvent.focus(backgroundApply);
    fireEvent.click(backgroundApply);
    fireEvent.click(backgroundBrollApply);
    expect(backgroundApply).not.toHaveFocus();
    expect(applyGlobal).not.toHaveBeenCalled();
    expect(applyBroll).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "뒤로" })).toHaveFocus();
  });

  it("returns focus to the mounted desktop control when the narrow sheet exits at the breakpoint", async () => {
    renderResponsiveDirector(640);
    fireEvent.click(screen.getByRole("button", { name: "루미 열기" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "뒤로" })).toHaveFocus());
    act(() => setViewport(1000));
    await waitFor(() => expect(screen.getByRole("button", { name: "루미 접기" })).toHaveFocus());
  });

  it("does not close the sheet while an IME composition handles Escape", async () => {
    renderResponsiveDirector(640);
    fireEvent.click(screen.getByRole("button", { name: "루미 열기" }));
    await screen.findByText("추천을 적용하기 전에 변경된 내용이 있는지 확인하고 있어요.");
    fireEvent.keyDown(screen.getByRole("textbox", { name: "루미에게 요청하기" }), { key: "Escape", isComposing: true });
    expect(screen.getByRole("dialog", { name: "루미 영상 도우미" })).toBeVisible();
  });
});
