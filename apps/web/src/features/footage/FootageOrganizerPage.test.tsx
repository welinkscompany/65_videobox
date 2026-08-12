import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, type LibraryAsset } from "../../api";
import { FootageOrganizerPage } from "./FootageOrganizerPage";

const asset: LibraryAsset = {
  library_asset_id: "asset-1",
  media_type: "broll",
  origin: "user",
  lifecycle: "ready",
  content_sha256: "a".repeat(64),
  byte_count: 100,
  mime_type: "video/mp4",
  managed_relative_path: "assets/clip.mp4",
  technical_metadata: { duration_seconds: 20, width: 1920, height: 1080 },
  machine_metadata: {},
  user_metadata: { filename: "clip.mp4" },
  duration_seconds: 20,
  preview_url: "/api/library/assets/asset-1/preview",
  thumbnail_url: null,
  waveform_url: null,
};

const proposal = {
  proposal_id: "proposal-1",
  source_id: "source-1",
  source_sha256: "a".repeat(64),
  status: "draft" as const,
  revision: 1,
  confirmed_fields: {},
  machine_fields: { total_duration: 20 },
  segments: [
    { segment_id: "seg-1", source_segment_id: "source-seg-1", source_sha256: "a".repeat(64), start_sec: 0, end_sec: 8, machine_fields: { label: "출근" }, confirmed_fields: {} },
    { segment_id: "seg-2", source_segment_id: "source-seg-2", source_sha256: "a".repeat(64), start_sec: 8, end_sec: 20, machine_fields: { label: "거리" }, confirmed_fields: {} },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listLibraryAssets").mockResolvedValue({ assets: [asset], total: 1 });
  vi.spyOn(api, "proposeFootage").mockResolvedValue(proposal);
  vi.spyOn(api, "previewFootageProposal").mockResolvedValue({ status: "ready", proposal_id: "proposal-1", revision: 1, source_id: "source-1", preview_url: "/api/footage/sources/source-1/preview?ranges=0.000-8.000%2C8.000-20.000", segments: proposal.segments });
  vi.spyOn(api, "cancelFootageProposal").mockResolvedValue({ status: "cancelled", proposal_id: "proposal-1", revision: 1 });
  vi.spyOn(api, "approveFootageProposal").mockResolvedValue({ ...proposal, status: "approved", revision: 2 });
  vi.spyOn(api, "interpretYujinFootageProposal").mockResolvedValue({
    status: "candidate_only",
    reply_text: "출근 장면 후보를 준비했어요.",
    candidate: {
      source_id: "source-1",
      source_sha256: "a".repeat(64),
      proposal_id: "proposal-1",
      base_revision: 1,
      requires_approval: true,
      operations: [{ intent: "select_process", segment_ids: ["seg-1"], process_label: "출근", ranges: [] }],
    },
    preview: { status: "ready", preview_url: "/api/footage/sources/source-1/preview?ranges=0.000-8.000", ranges: [[0, 8]] },
  });
  vi.spyOn(api, "createFootageSequence").mockResolvedValue({ sequence_id: "sequence-1", source_id: "source-1", source_sha256: "a".repeat(64), name: "새 가상 묶음", revision: 1, items: [{ item_id: "item-1", source_segment_id: "source-seg-1", item_order: 1, start_sec: 0, end_sec: 8 }, { item_id: "item-2", source_segment_id: "source-seg-2", item_order: 2, start_sec: 8, end_sec: 20 }] });
  vi.spyOn(api, "reorderFootageSequence").mockResolvedValue({ sequence_id: "sequence-1", source_id: "source-1", source_sha256: "a".repeat(64), name: "새 가상 묶음", revision: 2, items: [{ item_id: "item-2", source_segment_id: "source-seg-2", item_order: 1, start_sec: 8, end_sec: 20 }, { item_id: "item-1", source_segment_id: "source-seg-1", item_order: 2, start_sec: 0, end_sec: 8 }] });
});

describe("FootageOrganizerPage", () => {
  it("renders four bounded panes and starter chips only fill the input", async () => {
    render(<FootageOrganizerPage />);
    expect(await screen.findByTestId("footage-workspace")).toHaveAttribute("data-layout", "four-pane");
    expect(screen.getByTestId("footage-source-list")).toBeInTheDocument();
    expect(screen.getByTestId("footage-preview")).toBeInTheDocument();
    expect(screen.getByTestId("footage-suggestions")).toBeInTheDocument();
    expect(screen.getByTestId("footage-actions")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "출근 과정만 고르기" }));
    expect(screen.getByLabelText("정리 요청")).toHaveValue("출근 과정만 고르기");
    expect(api.proposeFootage).not.toHaveBeenCalled();
  });

  it("keeps proposal changes local until explicit preview/apply and exposes frame steps", async () => {
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await waitFor(() => expect(api.proposeFootage).toHaveBeenCalledWith(expect.objectContaining({ library_asset_id: "asset-1" })));
    expect(screen.getByTestId("scene-timeline")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "1프레임 앞으로" }));
    expect(screen.getByText(/0\.03초/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "제안 미리보기" }));
    await waitFor(() => expect(api.previewFootageProposal).toHaveBeenCalledWith("proposal-1", { expected_revision: 1 }));
    expect(screen.getByTestId("footage-video")).toHaveAttribute("src", "/api/footage/sources/source-1/preview?ranges=0.000-8.000%2C8.000-20.000");
    expect(api.approveFootageProposal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "제안 적용" }));
    await waitFor(() => expect(api.approveFootageProposal).toHaveBeenCalledWith("proposal-1", expect.objectContaining({ expected_revision: 1, idempotency_key: expect.any(String) })));
  });

  it("sends a non-mutating Yujin request and shows the candidate preview separately from approval", async () => {
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await screen.findByTestId("scene-timeline");
    fireEvent.change(screen.getByLabelText("정리 요청"), { target: { value: "출근 장면만 골라줘" } });
    fireEvent.click(screen.getByRole("button", { name: "유진에게 제안 요청" }));

    await waitFor(() => expect(api.interpretYujinFootageProposal).toHaveBeenCalledWith("proposal-1", { instruction: "출근 장면만 골라줘" }));
    expect(await screen.findByText("출근 장면 후보를 준비했어요.")).toBeVisible();
    expect(screen.getByTestId("yujin-candidate")).toHaveTextContent("select_process");
    expect(screen.getByTestId("footage-video")).toHaveAttribute("src", "/api/footage/sources/source-1/preview?ranges=0.000-8.000");
    expect(api.approveFootageProposal).not.toHaveBeenCalled();
  });

  it("shows retry state when the source list fails", async () => {
    vi.mocked(api.listLibraryAssets).mockRejectedValueOnce(new Error("offline"));
    render(<FootageOrganizerPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("촬영본을 불러오지 못했습니다");
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeVisible();
  });

  it("keeps video timeupdate, playhead, and accessible announcement synchronized", async () => {
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await screen.findByRole("button", { name: /출근/ });
    const video = screen.getByTestId("footage-video");
    Object.defineProperty(video, "currentTime", { configurable: true, value: 4 });
    fireEvent.timeUpdate(video);
    expect(screen.getByText("0:04.0 / 0:20.0")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "재생 위치" })).toHaveTextContent("0:04.0");
    expect(screen.getByTestId("scene-timeline").querySelector(".vb-footage-track")).toHaveAttribute("style", expect.stringContaining("--playhead: 20%"));
  });

  it("creates a sequence from the selected scene and reorders the selected sequence item", async () => {
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await screen.findByTestId("scene-timeline");
    fireEvent.click(screen.getByRole("button", { name: /거리/ }), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: "선택 장면으로 가상 묶음 만들기" }));
    await waitFor(() => expect(api.createFootageSequence).toHaveBeenCalledWith(expect.objectContaining({ items: [{ source_segment_id: "source-seg-1", item_order: 1, start_sec: 0, end_sec: 8 }, { source_segment_id: "source-seg-2", item_order: 2, start_sec: 8, end_sec: 20 }] })));
    fireEvent.click(screen.getByRole("button", { name: "묶음 항목 2" }));
    fireEvent.click(screen.getByRole("button", { name: "위로" }));
    await waitFor(() => expect(api.reorderFootageSequence).toHaveBeenCalledWith("sequence-1", { expected_revision: 1, item_ids: ["item-2", "item-1"] }));
  });
});
