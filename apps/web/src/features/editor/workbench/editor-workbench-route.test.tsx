import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { startTransition, Suspense, useState } from "react";

import { ApiConflictError, api } from "../../../api";
import { EditorWorkbenchRoute } from "./EditorWorkbenchRoute";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const manifest = (projectId: string, sessionId: string) => ({ project_id: projectId, session_id: sessionId, timeline_id: `timeline-${sessionId}`, session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: sessionId, source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 1 } });

const narrationManifest = (revision: number, startSec = 0) => ({
  ...manifest("project-a", "session-a"),
  session_revision: revision,
  output: { ...manifest("project-a", "session-a").output, duration_sec: 5 },
  source_status: { status: "current" as const, source_session_id: "session-a", source_session_revision: revision },
  tracks: [{
    track_id: "narration",
    track_type: "narration" as const,
    clips: [{
      clip_id: "n-1", segment_id: "segment-1", clip_type: "narration" as const,
      asset_id: null, asset_uri: null, start_sec: startSec, end_sec: 5,
      media_controls: {},
    }],
  }],
});

const twoNarrationManifest = (revision: number) => ({
  ...narrationManifest(revision),
  output: { ...narrationManifest(revision).output, duration_sec: 2 },
  tracks: [{
    track_id: "narration",
    track_type: "narration" as const,
    clips: [
      { clip_id: "n-1", segment_id: "segment-1", clip_type: "narration" as const, asset_id: null, asset_uri: null, start_sec: 0, end_sec: 1, media_controls: {} },
      { clip_id: "n-2", segment_id: "segment-2", clip_type: "narration" as const, asset_id: null, asset_uri: null, start_sec: 1, end_sec: 2, media_controls: {} },
    ],
  }],
});

const captionManifest = (revision: number, text = "원래 자막") => ({
  ...narrationManifest(revision),
  captions: [{
    segment_id: "segment-1", caption_id: "caption-1", placement_id: "caption:segment-1", text, start_sec: 0, end_sec: 5,
    style: { font_family: "Pretendard", font_size_px: 42, text_color: "#ffffff", outline_color: "#000000", outline_width_px: 2, background_color: "#00000000", position_x_percent: 50, position_y_percent: 85, horizontal_align: "center" as const, safe_area_enabled: true, shadow_blur_px: 0 },
  }],
});

function pointer(target: Element, type: string, clientX: number) {
  fireEvent(target, new MouseEvent(type, { bubbles: true, cancelable: true, clientX }));
}

describe("EditorWorkbenchRoute", () => {
  it("never displays the old A session while B is loading", async () => {
    let resolveB!: (value: ReturnType<typeof manifest>) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId, sessionId) => sessionId === "session-a" ? Promise.resolve(manifest(projectId, sessionId)) : new Promise((resolve) => { resolveB = resolve; }));
    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(screen.queryByText("timeline-session-a · revision 1")).toBeNull();
    expect(screen.getByText("편집 내용을 불러오는 중이에요.")).toBeVisible();
    resolveB(manifest("project-b", "session-b"));
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("fails closed for missing or mismatched session identity", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(manifest("wrong-project", "session-a") as never);
    const { rerender } = render(<EditorWorkbenchRoute projectId="project-a" sessionId={null} />);
    expect(screen.getByText("편집 세션을 찾을 수 없어요. 다시 열어 주세요.")).toBeVisible();
    rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("편집 세션 정보가 일치하지 않아요. 다시 열어 주세요.")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("commits one current-revision narration trim on release and refreshes the manifest", async () => {
    let resolveUpdate!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(narrationManifest(2, 1) as never);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });

    pointer(trim, "pointerdown", 100);
    expect(update).not.toHaveBeenCalled();
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update).toHaveBeenCalledWith("project-a", "session-a", "segment-1", {
      end_sec: 5,
      expected_revision: 1,
      start_sec: 1,
    });
    expect(await screen.findByText("변경 내용을 저장하고 있어요.")).toBeVisible();
    expect(trim).toBeDisabled();
    resolveUpdate({});
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("timeline-session-a · revision 2")).toBeVisible();
  });

  it("saves linked caption text through the same revision fence and refreshes the manifest", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "새 자막") as never);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 4")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    expect(await screen.findByRole("dialog", { name: "자산과 대본" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "원래 자막 대본 선택" }));
    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "새 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith("project-a", "session-a", "segment-1", { caption_text: "새 자막", expected_revision: 4 }));
    expect(await screen.findByText("timeline-session-a · revision 5")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("refreshes after a linked-caption revision conflict without retrying the caption command", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(captionManifest(4) as never)
      .mockResolvedValueOnce(captionManifest(5, "다른 변경 자막") as never);
    const update = vi.spyOn(api, "updateEditingSessionCaption").mockRejectedValue(
      new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/segments/segment-1/caption"),
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 4")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
    expect(await screen.findByRole("dialog", { name: "자산과 대본" })).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "segment-1 자막 텍스트" }), { target: { value: "새 자막" } });
    fireEvent.click(screen.getByRole("button", { name: "자막 저장" }));

    expect(await screen.findByText("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("timeline-session-a · revision 5")).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps the current view, refreshes after a revision conflict, and does not retry the command", async () => {
    let resolveRefresh!: (value: ReturnType<typeof narrationManifest>) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve as typeof resolveRefresh; }));
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(
      new ApiConflictError({}, "/api/projects/project-a/editing-sessions/session-a/segments/segment-1/bounds"),
    );

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("다른 변경이 먼저 저장됐어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.getByText("timeline-session-a · revision 1")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(update).toHaveBeenCalledTimes(1);

    resolveRefresh(narrationManifest(2, 0));
    expect(await screen.findByText("timeline-session-a · revision 2")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("commits one complete narration reorder layout on pointer release", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(twoNarrationManifest(3) as never)
      .mockResolvedValueOnce(twoNarrationManifest(4) as never);
    const reorder = vi.spyOn(api, "reorderEditingSessionSegments").mockResolvedValue({} as never);

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 3")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const control = screen.getByRole("button", { name: "n-1 순서 바꾸기" });

    pointer(control, "pointerdown", 0);
    expect(reorder).not.toHaveBeenCalled();
    pointer(control, "pointermove", 200);
    pointer(control, "pointerup", 200);

    await waitFor(() => expect(reorder).toHaveBeenCalledTimes(1));
    expect(reorder).toHaveBeenCalledWith("project-a", "session-a", {
      bounds_by_id: {
        "segment-1": { start_sec: 1, end_sec: 2 },
        "segment-2": { start_sec: 0, end_sec: 1 },
      },
      expected_revision: 3,
      segment_ids: ["segment-2", "segment-1"],
    });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("refreshes after an ordinary save failure and gives safe retry guidance", async () => {
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(5) as never)
      .mockResolvedValueOnce(narrationManifest(5) as never);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds").mockRejectedValue(new Error("offline"));

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 5")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    const trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);

    expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(update).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("ignores an old A mutation after navigating A to B to A while a new A mutation is saving", async () => {
    let resolveOldUpdate!: (value: unknown) => void;
    let resolveNewUpdate!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(manifest("project-b", "session-b") as never)
      .mockResolvedValueOnce(narrationManifest(10) as never)
      .mockResolvedValueOnce(narrationManifest(11, 1) as never);
    const update = vi.spyOn(api, "updateEditingSessionSegmentBounds")
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldUpdate = resolve; }) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewUpdate = resolve; }) as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    let track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    let trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 10")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    track = screen.getByTestId("timeline-track");
    vi.spyOn(track, "getBoundingClientRect").mockReturnValue({ left: 0 } as DOMRect);
    trim = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(trim, "pointerdown", 100);
    pointer(trim, "pointermove", 200);
    pointer(trim, "pointerup", 200);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible();

    await act(async () => { resolveOldUpdate({}); });
    expect(load).toHaveBeenCalledTimes(3);
    expect(screen.getByText("timeline-session-a · revision 10")).toBeVisible();
    expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible();
    expect(trim).toBeDisabled();

    resolveNewUpdate({});
    await waitFor(() => expect(load).toHaveBeenCalledTimes(4));
    expect(await screen.findByText("timeline-session-a · revision 11")).toBeVisible();
    expect(screen.getByText("변경 내용을 저장했어요.")).toBeVisible();
  });

  it("keeps the committed A mutation current when an uncommitted B render is abandoned", async () => {
    let navigate!: (route: "a" | "b") => void;
    let resolveUpdate!: (value: unknown) => void;
    const never = new Promise<never>(() => undefined);
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(twoNarrationManifest(1) as never)
      .mockResolvedValueOnce(twoNarrationManifest(2) as never);
    vi.spyOn(api, "reorderEditingSessionSegments")
      .mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }) as never);

    function SuspendAbandonedRoute({ route }: { route: "a" | "b" }) {
      if (route === "b") throw never;
      return null;
    }

    function Harness() {
      const [route, setRoute] = useState<"a" | "b">("a");
      navigate = setRoute;
      return <Suspense fallback={<p>전환 중</p>}>
        <EditorWorkbenchRoute
          projectId={route === "a" ? "project-a" : "project-b"}
          sessionId={route === "a" ? "session-a" : "session-b"}
        />
        <SuspendAbandonedRoute route={route} />
      </Suspense>;
    }

    render(<Harness />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
    const reorder = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    fireEvent.keyDown(reorder, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByText("변경 내용을 저장하고 있어요.")).toBeVisible());

    act(() => {
      startTransition(() => navigate("b"));
    });
    expect(screen.getByText("timeline-session-a · revision 1")).toBeVisible();

    await act(async () => { resolveUpdate({}); });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("timeline-session-a · revision 2")).toBeVisible();
    expect(screen.getByText("변경 내용을 저장했어요.")).toBeVisible();
    expect(reorder).not.toBeDisabled();
  });

  it("ignores an old exact-preview completion after navigating A to B to A", async () => {
    let resolveOldPreview!: (value: unknown) => void;
    const load = vi.spyOn(api, "getEditorPlaybackManifest")
      .mockResolvedValueOnce(narrationManifest(1) as never)
      .mockResolvedValueOnce(manifest("project-b", "session-b") as never)
      .mockResolvedValueOnce(narrationManifest(10) as never)
      .mockResolvedValueOnce(narrationManifest(2) as never);
    const startPreview = vi.spyOn(api, "startExactPreview")
      .mockImplementation(() => new Promise((resolve) => { resolveOldPreview = resolve; }) as never);

    const rendered = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "미리보기 새로 만들기" }));
    await waitFor(() => expect(startPreview).toHaveBeenCalledTimes(1));

    rendered.rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
    expect(await screen.findByText("timeline-session-b · revision 1")).toBeVisible();
    rendered.rerender(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    expect(await screen.findByText("timeline-session-a · revision 10")).toBeVisible();

    await act(async () => { resolveOldPreview({}); });
    expect(load).toHaveBeenCalledTimes(3);
    expect(screen.getByText("timeline-session-a · revision 10")).toBeVisible();
  });
});
