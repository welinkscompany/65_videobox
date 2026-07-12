import { describe, expect, it, vi } from "vitest";
import { ApiConflictError, api } from "./api";

describe("caption style API conflicts", () => {
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
});
