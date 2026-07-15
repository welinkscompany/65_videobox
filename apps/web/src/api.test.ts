import { describe, expect, it, vi } from "vitest";
import { ApiConflictError, api, type DirectorProposal } from "./api";

describe("caption style API conflicts", () => {
  it("uses director conversation routes, preserves caller client id, and represents Retry-After as in-progress", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversation_id: "c-1", project_id: "project_001", session_id: "s-1" }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ messages: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "director_message_in_progress" }), { status: 202, headers: { "Retry-After": "3" } }));
    vi.stubGlobal("fetch", fetchMock);
    await api.createDirectorConversation("project_001", { session_id: "s-1" });
    await api.listDirectorMessages("project_001", "c-1", "s-1");
    const result = await api.sendDirectorMessage("project_001", "c-1", { session_id: "s-1", client_message_id: "stable-client-id", text: "3번 영상 교체" });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/project_001/director/conversations", expect.objectContaining({ method: "POST", body: JSON.stringify({ session_id: "s-1" }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project_001/director/conversations/c-1/messages?session_id=s-1", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/projects/project_001/director/conversations/c-1/messages", expect.objectContaining({ method: "POST", body: JSON.stringify({ session_id: "s-1", client_message_id: "stable-client-id", text: "3번 영상 교체" }) }));
    expect(result).toEqual({ kind: "in_progress", retryAfterSeconds: 3 });
    vi.unstubAllGlobals();
  });

  it("retries a prepared director submission with the identical client message id after 202", async () => {
    const exchange = { user_message: { message_id: "u", conversation_id: "c", project_id: "p", session_id: "s", role: "user", text: "교체", proposal_id: null, metadata: {}, client_message_id: "fixed-id", created_at: "now" }, assistant_message: { message_id: "a", conversation_id: "c", project_id: "p", session_id: "s", role: "assistant", text: "확인", proposal_id: null, metadata: {}, client_message_id: null, created_at: "now" } };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "director_message_in_progress" }), { status: 202, headers: { "Retry-After": "1" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(exchange), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const prepared = api.prepareDirectorMessage("p", "c", { session_id: "s", client_message_id: "fixed-id", text: "교체" });
    await expect(prepared.send()).resolves.toEqual({ kind: "in_progress", retryAfterSeconds: 1 });
    await expect(prepared.retry()).resolves.toEqual({ kind: "exchange", exchange });
    expect(fetchMock.mock.calls.map((call) => call[1]?.body)).toEqual([
      JSON.stringify({ session_id: "s", client_message_id: "fixed-id", text: "교체" }),
      JSON.stringify({ session_id: "s", client_message_id: "fixed-id", text: "교체" }),
    ]);
    vi.unstubAllGlobals();
  });

  it("consumes the real immutable proposal payload fields without inventing reference_code", () => {
    const proposal = {
      proposal_id: "proposal-12", revision_code: "P12", revision: 12, base_session_revision: 4, asset_index_revision: 9,
      source_session_id: "s-1", target_segment_ids: ["seg-1"], source_script_segment_ids: ["script-1"], status: "ready",
      diff: { placements: { add: [] } }, expires_at: "2026-07-16T00:00:00+00:00",
      candidates: [{ candidate_id: "candidate-1", visible_reference_code: "P12-B-03", media_type: "broll", asset_id: "asset-1", library_asset_id: null, reason_chips: ["scene"], scores: { semantic: 0.9 }, availability: "available", review_status: "approved", preview_uri: null, controls: { in_sec: 0 }, expected_content_sha256: "abc", media_revision: "revision-1", canonical_metadata: { title: "clip" }, license_policy: "verified", warning_provenance: [] }],
    } satisfies DirectorProposal;
    expect(proposal.candidates[0].visible_reference_code).toBe("P12-B-03");
    expect("reference_code" in proposal.candidates[0]).toBe(false);
  });

  it("does not send an unsupported apply scope to the current backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const staleCallerPayload = { candidate_ids: ["candidate-1"], expected_revision: 4, scope: "all" };
    await api.applyDirectorProposal("p", "proposal-1", staleCallerPayload);
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/p/director/proposals/proposal-1/apply", expect.objectContaining({
      method: "POST", body: JSON.stringify({ candidate_ids: ["candidate-1"], expected_revision: 4 }),
    }));
    vi.unstubAllGlobals();
  });

  it("types editing-session history metadata delivered by the API", () => {
    const session = {
      session_id: "s", project_id: "p", timeline_id: "t", session_revision: 3, segments: [], history: [{
        mutation_type: "caption_update", segment_id: "seg", action_id: "action-1", label: "자막 변경", created_at: "2026-07-16T00:00:00Z", reversible: true, blocked_reason: null,
      }],
    } satisfies import("./api").EditingSession;
    expect(session.history[0]).toMatchObject({ action_id: "action-1", label: "자막 변경", reversible: true });
  });

  it("returns a completed exchange without applying or mutating an editing session", async () => {
    const exchange = { user_message: { message_id: "u", conversation_id: "c-1", project_id: "p", session_id: "s", role: "user", text: "교체", proposal_id: null, metadata: {}, client_message_id: "stable-client-id", created_at: "now" }, assistant_message: { message_id: "a", conversation_id: "c-1", project_id: "p", session_id: "s", role: "assistant", text: "확인", proposal_id: null, metadata: {}, client_message_id: null, created_at: "now" }, action_intent: { action: "replace", target: { reference_code: "B-03", immutable_id: { segment_id: "seg-1", track_type: "broll" }, source: "timeline" }, proposal_preflight: null } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(exchange), { status: 200 })));
    await expect(api.sendDirectorMessage("p", "c-1", { session_id: "s", client_message_id: "stable-client-id", text: "교체" })).resolves.toEqual({ kind: "exchange", exchange });
    vi.unstubAllGlobals();
  });
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
