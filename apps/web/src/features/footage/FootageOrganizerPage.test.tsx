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
  vi.spyOn(api, "previewFootageSequence").mockResolvedValue({ status: "ready", sequence_id: "sequence-1", revision: 1, preview_url: "/api/footage/sources/source-1/preview?ranges=0.000-8.000%2C8.000-20.000", preview_items: [], items: [] });
  vi.spyOn(api, "cancelFootageSequence").mockResolvedValue({ status: "cancelled", sequence_id: "sequence-1", revision: 1 });
  vi.spyOn(api, "approveFootageSequence").mockResolvedValue({ sequence_id: "sequence-1", source_id: "source-1", source_sha256: "a".repeat(64), name: "새 가상 묶음", revision: 1, items: [{ item_id: "item-1", source_segment_id: "source-seg-1", item_order: 1, start_sec: 0, end_sec: 8 }, { item_id: "item-2", source_segment_id: "source-seg-2", item_order: 2, start_sec: 8, end_sec: 20 }] });
  vi.spyOn(api, "getFootageSequence").mockResolvedValue({ sequence_id: "sequence-1", source_id: "source-1", source_sha256: "a".repeat(64), name: "새 가상 묶음", revision: 2, items: [{ item_id: "item-2", source_segment_id: "source-seg-2", item_order: 1, start_sec: 8, end_sec: 20 }, { item_id: "item-1", source_segment_id: "source-seg-1", item_order: 2, start_sec: 0, end_sec: 8 }] });
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

  it("preselects the source a library entry named in the URL", async () => {
    window.history.replaceState({}, "", "/footage?library_asset_id=asset-1");
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: [{ ...asset, library_asset_id: "asset-0", user_metadata: { filename: "other.mp4" } }, asset], total: 2 });

    render(<FootageOrganizerPage />);

    expect(await screen.findByRole("heading", { name: "clip.mp4" })).toBeInTheDocument();
    window.history.replaceState({}, "", "/footage");
  });

  it("links the selected source back to its library preview", async () => {
    render(<FootageOrganizerPage />);
    await screen.findByTestId("footage-workspace");
    fireEvent.click(screen.getByRole("button", { name: /clip\.mp4/ }));

    const entry = await screen.findByRole("link", { name: "라이브러리에서 보기" });
    expect(entry).toHaveAttribute("href", "/library?library_asset_id=asset-1");
  });

  it("keeps proposal changes local until explicit preview/apply and exposes frame steps", async () => {
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.change(screen.getByLabelText("정리 요청"), { target: { value: "장면 변화로 나누기" } });
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await waitFor(() => expect(api.proposeFootage).toHaveBeenCalledWith(expect.objectContaining({ library_asset_id: "asset-1" })));
    expect(api.proposeFootage).toHaveBeenCalledWith(expect.not.objectContaining({ analysis: expect.anything() }));
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

  it("combines shift-selected sources while preserving each source identity", async () => {
    const assets = [
      asset,
      { ...asset, library_asset_id: "asset-2", content_sha256: "b".repeat(64), user_metadata: { filename: "short-b.mp4" } },
      { ...asset, library_asset_id: "asset-3", content_sha256: "c".repeat(64), user_metadata: { filename: "short-c.mp4" } },
    ];
    const proposals = new Map([
      ["asset-1", proposal],
      ["asset-2", { ...proposal, proposal_id: "proposal-2", source_id: "source-2", source_sha256: "b".repeat(64), segments: [{ ...proposal.segments[0], source_segment_id: "source-seg-2", source_sha256: "b".repeat(64) }] }],
      ["asset-3", { ...proposal, proposal_id: "proposal-3", source_id: "source-3", source_sha256: "c".repeat(64), segments: [{ ...proposal.segments[0], source_segment_id: "source-seg-3", source_sha256: "c".repeat(64) }] }],
    ]);
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets, total: assets.length });
    vi.mocked(api.proposeFootage).mockImplementation(async ({ library_asset_id }) => proposals.get(library_asset_id)!);
    vi.mocked(api.createFootageSequence).mockResolvedValue({ sequence_id: "multi-sequence", source_id: "source-1", source_sha256: "a".repeat(64), sources: [{ source_id: "source-1", source_sha256: "a".repeat(64) }, { source_id: "source-2", source_sha256: "b".repeat(64) }, { source_id: "source-3", source_sha256: "c".repeat(64) }], name: "선택한 촬영본 가상 묶음", revision: 1, items: [] });
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await screen.findByTestId("scene-timeline");
    fireEvent.click(screen.getByRole("button", { name: /short-b\.mp4/ }), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: /short-c\.mp4/ }), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: "선택한 촬영본으로 가상 묶음 만들기" }));
    await waitFor(() => expect(api.createFootageSequence).toHaveBeenCalledWith(expect.objectContaining({
      items: expect.arrayContaining([
        expect.objectContaining({ source_id: "source-1" }),
        expect.objectContaining({ source_id: "source-2" }),
        expect.objectContaining({ source_id: "source-3" }),
      ]),
    })));
  });

  it("keeps sequence preview, cancel, reload, and approval explicit", async () => {
    render(<FootageOrganizerPage />);
    fireEvent.click(await screen.findByRole("button", { name: /clip\.mp4/ }));
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    await screen.findByTestId("scene-timeline");
    fireEvent.click(screen.getByRole("button", { name: /거리/ }), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: "선택 장면으로 가상 묶음 만들기" }));
    await screen.findByText("새 가상 묶음");
    fireEvent.click(screen.getByRole("button", { name: "가상 묶음 미리보기" }));
    await waitFor(() => expect(api.previewFootageSequence).toHaveBeenCalledWith("sequence-1"));
    expect(api.approveFootageSequence).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "가상 묶음 취소" }));
    await waitFor(() => expect(api.cancelFootageSequence).toHaveBeenCalledWith("sequence-1"));
    fireEvent.click(screen.getByRole("button", { name: "가상 묶음 새로고침" }));
    await waitFor(() => expect(api.getFootageSequence).toHaveBeenCalledWith("sequence-1"));
    fireEvent.click(screen.getByRole("button", { name: "가상 묶음 승인" }));
    await waitFor(() => expect(api.approveFootageSequence).toHaveBeenCalledWith("sequence-1", { idempotency_key: expect.any(String) }));
  });
});
