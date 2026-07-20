import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { api } from "../../../api";
import { EditorWorkbenchRoute } from "./EditorWorkbenchRoute";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const manifest = (projectId: string, sessionId: string) => ({ project_id: projectId, session_id: sessionId, timeline_id: `timeline-${sessionId}`, session_revision: 1, timeline_version: "v1", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 }, tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: sessionId, source_session_revision: 1 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 1 } });

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
});
