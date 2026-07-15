import { describe, expect, it, vi } from "vitest";
import { ApiConflictError, api } from "./api";

describe("caption style API conflicts", () => {
  it("uses the exact immutable Director proposal routes and request bodies", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ proposal_id: "proposal_1" }), { status: 201 })));
    vi.stubGlobal("fetch", fetchMock);
    await api.createDirectorProposal("project_001", { session_id: "session_001" });
    await api.getDirectorProposal("project_001", "proposal_1");
    await api.preflightDirectorProposal("project_001", "proposal_1");
    await api.refreshDirectorProposal("project_001", "proposal_1");
    await api.updateDirectorPreferences("project_001", { pin_asset: ["asset_1"] });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/project_001/director/proposals", expect.objectContaining({ method: "POST", body: JSON.stringify({ session_id: "session_001" }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project_001/director/proposals/proposal_1", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/projects/project_001/director/proposals/proposal_1/preflight", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(4, "/api/projects/project_001/director/proposals/proposal_1/refresh", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(5, "/api/projects/project_001/director/preferences", expect.objectContaining({ method: "PUT", body: JSON.stringify({ pin_asset: ["asset_1"] }) }));
    vi.unstubAllGlobals();
  });
  it("preserves batch analysis jobs and per-file failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      assets: [{ asset_id: "asset_1" }], analysis_jobs: [{ analysis_id: "analysis_1" }], failures: [{ source_path: "bad.mp4", reason: "missing" }],
    }), { status: 201 })));
    const batch = await api.importBrollBatch("project_001", { source_paths: ["good.mp4"], tags: [] });
    expect(batch.analysis_jobs).toEqual([{ analysis_id: "analysis_1" }]);
    expect(batch.failures).toEqual([{ source_path: "bad.mp4", reason: "missing" }]);
    vi.unstubAllGlobals();
  });

  it("preserves latest_session from a 409 response for recovery", async () => {
    const latestSession = { session_id: "session_001", session_revision: 4 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ latest_session: latestSession }), { status: 409 })));
    await expect(api.updateEditingSessionCaptionStyle("project_001", "session_001", {
      expected_revision: 3, scope: "whole_project", segment_ids: [], style: {},
    })).rejects.toMatchObject({ name: "ApiConflictError", latestSession });
    vi.unstubAllGlobals();
  });

  it("sends the loaded revision in patch, delete, and partial-regeneration mutations", async () => {
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(JSON.stringify({}), { status: 200 })),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.updateEditingSessionCaption("project_001", "session_001", "segment_001", {
      expected_revision: 7,
      caption_text: "Updated caption",
    });
    await api.clearEditingSessionBrollOverride(
      "project_001",
      "session_001",
      "segment_001",
      7,
    );
    await api.runPartialRegeneration("project_001", "session_001", {
      expected_revision: 7,
      segment_ids: ["segment_001"],
      fields: ["caption"],
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/projects/project_001/editing-sessions/session_001/segments/segment_001/caption",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ expected_revision: 7, caption_text: "Updated caption" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/project_001/editing-sessions/session_001/segments/segment_001/broll?expected_revision=7",
      { method: "DELETE" },
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/projects/project_001/editing-sessions/session_001/partial-regeneration",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_revision: 7,
          segment_ids: ["segment_001"],
          fields: ["caption"],
        }),
      }),
    );
    vi.unstubAllGlobals();
  });

  it("loads editor presets and toggles canonical media favorites", async () => {
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(JSON.stringify([]), { status: 200 })),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.listEditorPresets("project_001");
    await api.toggleEditorFavorite("project_001", "pack:starter:asset_001", {
      favorite_type: "media",
      enabled: true,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/project_001/editor-library/presets", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/project_001/editor-library/favorites/pack:starter:asset_001",
      expect.objectContaining({ method: "PUT" }),
    );
    vi.unstubAllGlobals();
  });
});
