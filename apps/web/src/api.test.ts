import { describe, expect, it, vi } from "vitest";
import {
  ApiConflictError,
  api,
  type CapCutDraftExportArtifact,
  type CapCutDraftHandoff,
  type DirectorProposal,
  type FinalRenderArtifact,
  type ReviewApproval,
  type SubtitleArtifact,
  type TimelinePayload,
} from "./api";

describe("caption style API conflicts", () => {
  const memoryCandidate = {
    candidate_id: "memory-candidate-1",
    project_id: "project/1",
    conversation_id: "conversation:1",
    client_request_id: "request-1",
    source_message_ids: ["message-1"],
    memory_scope: "creator",
    category: "pacing",
    proposed_text: "빠른 컷 편집을 선호합니다.",
    status: "pending",
    storage_status: "not_requested",
    retryable: false,
    created_at: "2026-07-30T12:00:00Z",
    updated_at: "2026-07-30T12:00:00Z",
  } as const;

  it("creates one typed conversation-owned memory candidate with the existing POST", async () => {
    const createdMemoryCandidate = {
      ...memoryCandidate,
      client_request_id: "memory-create-request-1",
      source_message_ids: ["message-1", "message-2"],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(createdMemoryCandidate), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.createYujinMemoryCandidate("project/1", {
      conversation_id: "conversation:1",
      client_request_id: "memory-create-request-1",
      source_message_ids: ["message-1", "message-2"],
      memory_scope: "creator",
      category: "pacing",
      proposed_text: "빠른 컷 편집을 선호합니다.",
    })).resolves.toEqual(createdMemoryCandidate);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project%2F1/director/memory-candidates",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        redirect: "error",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: "conversation:1",
          client_request_id: "memory-create-request-1",
          source_message_ids: ["message-1", "message-2"],
          memory_scope: "creator",
          category: "pacing",
          proposed_text: "빠른 컷 편집을 선호합니다.",
        }),
      }),
    );
    vi.unstubAllGlobals();
  });

  it("uses strict conversation-scoped memory candidate actions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        candidates: [memoryCandidate],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...memoryCandidate,
        status: "approved",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...memoryCandidate,
        status: "rejected",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        candidate_id: memoryCandidate.candidate_id,
        status: "approved",
        storage_status: "stored",
        retryable: false,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        candidate_id: memoryCandidate.candidate_id,
        status: "approved",
        storage_status: "deleted",
        retryable: false,
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api.listYujinMemoryCandidates("project/1", "conversation:1"),
    ).resolves.toEqual([memoryCandidate]);
    await api.approveYujinMemoryCandidate(
      "project/1", memoryCandidate.candidate_id,
    );
    await api.rejectYujinMemoryCandidate(
      "project/1", memoryCandidate.candidate_id,
    );
    await api.storeYujinMemoryCandidate(
      "project/1",
      memoryCandidate.candidate_id,
      "store-request-1",
    );
    await api.deleteYujinMemoryCandidate(
      "project/1", memoryCandidate.candidate_id,
    );

    const base = (
      "/api/projects/project%2F1/director/memory-candidates"
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `${base}?conversation_id=conversation%3A1`,
      expect.objectContaining({
        credentials: "same-origin",
        redirect: "error",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `${base}/memory-candidate-1/approve`,
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        redirect: "error",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      `${base}/memory-candidate-1/reject`,
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        redirect: "error",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      `${base}/memory-candidate-1/store`,
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        redirect: "error",
        body: JSON.stringify({ client_request_id: "store-request-1" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      `${base}/memory-candidate-1/stored-memory`,
      expect.objectContaining({
        method: "DELETE",
        credentials: "same-origin",
        redirect: "error",
      }),
    );
    vi.unstubAllGlobals();
  });

  it.each([
    { ...memoryCandidate, status: "stored" },
    { ...memoryCandidate, category: "provider_internal" },
    { ...memoryCandidate, provider_ref: "private" },
    {
      ...memoryCandidate,
      source_message_ids: ["message-1", "message-1"],
    },
    { ...memoryCandidate, candidate_id: "memory/candidate" },
    { ...memoryCandidate, project_id: "p".repeat(257) },
    { ...memoryCandidate, conversation_id: "conversation/unsafe" },
    { ...memoryCandidate, client_request_id: "request unsafe" },
    { ...memoryCandidate, source_message_ids: ["message/unsafe"] },
    { ...memoryCandidate, proposed_text: "가".repeat(281) },
    { ...memoryCandidate, proposed_text: "빠른\u200b편집" },
    {
      ...memoryCandidate,
      created_at: "2026-07-30T12:00:00+09:00",
    },
    {
      ...memoryCandidate,
      created_at: "2026-99-99T12:00:00Z",
    },
    {
      ...memoryCandidate,
      created_at: "2026-07-30T12:00:01Z",
      updated_at: "2026-07-30T12:00:00Z",
    },
    {
      ...memoryCandidate,
      status: "approved",
      storage_status: "not_requested",
      retryable: true,
    },
  ])("rejects unknown memory candidate status, category, or fields", async (candidate) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ candidates: [candidate] }), {
        status: 200,
      }),
    ));

    await expect(
      api.listYujinMemoryCandidates("project/1", "conversation:1"),
    ).rejects.toThrow("yujin_memory_candidate_invalid");
    vi.unstubAllGlobals();
  });

  it("accepts an expired pre-call claim as retryable without private fields", async () => {
    const claimed = {
      ...memoryCandidate,
      status: "approved",
      storage_status: "claimed",
      retryable: true,
    } as const;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ candidates: [claimed] }), {
        status: 200,
      }),
    ));

    await expect(
      api.listYujinMemoryCandidates("project/1", "conversation:1"),
    ).resolves.toEqual([claimed]);
    vi.unstubAllGlobals();
  });

  it.each([
    { ...memoryCandidate, project_id: "another-project" },
    { ...memoryCandidate, conversation_id: "another-conversation" },
  ])("binds listed memory candidates to the requested scope", async (candidate) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ candidates: [candidate] }), {
        status: 200,
      }),
    ));

    await expect(
      api.listYujinMemoryCandidates("project/1", "conversation:1"),
    ).rejects.toThrow("yujin_memory_candidate_invalid");
    vi.unstubAllGlobals();
  });

  it("rejects provider fields in memory store results", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        candidate_id: "memory-candidate-1",
        status: "approved",
        storage_status: "stored",
        retryable: false,
        provider_ref: "private",
      }), { status: 200 }),
    ));

    await expect(api.storeYujinMemoryCandidate(
      "project-1",
      "memory-candidate-1",
      "store-request-1",
    )).rejects.toThrow("yujin_memory_store_result_invalid");
    vi.unstubAllGlobals();
  });

  it("reads the strict global Yujin status from the same-origin route", async () => {
    const status = {
      state: "chat_verified",
      http_ready: true,
      provider_ready: true,
      chat_verified: true,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: "2026-07-30T11:59:59+00:00",
      restart_available: false,
      status_basis: "application_path",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(status), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(api.getHermesYujinStatus(controller.signal)).resolves.toEqual(status);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/hermes-yujin/status",
      { signal: controller.signal },
    );
    vi.unstubAllGlobals();
  });

  it.each([
    {
      state: "ready",
      http_ready: true,
      provider_ready: true,
      chat_verified: true,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: null,
      restart_available: false,
      status_basis: "application_path",
    },
    {
      state: "http_ready",
      http_ready: true,
      provider_ready: false,
      chat_verified: false,
      checked_at: "2026-07-30T21:00:00+09:00",
      last_chat_verified_at: null,
      restart_available: false,
      status_basis: "application_path",
    },
    {
      state: "http_ready",
      http_ready: true,
      provider_ready: false,
      chat_verified: false,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: null,
      restart_available: true,
      status_basis: "application_path",
    },
    {
      state: "http_ready",
      http_ready: true,
      provider_ready: false,
      chat_verified: false,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: null,
      restart_available: false,
      status_basis: "docker_compose",
    },
    {
      state: "http_ready",
      http_ready: true,
      provider_ready: false,
      chat_verified: false,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: null,
      restart_available: false,
      status_basis: "application_path",
      internal_detail: "must be rejected",
    },
    {
      state: "chat_verified",
      http_ready: true,
      provider_ready: true,
      chat_verified: false,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: "2026-07-30T11:59:59Z",
      restart_available: false,
      status_basis: "application_path",
    },
    {
      state: "http_ready",
      http_ready: true,
      provider_ready: false,
      chat_verified: false,
      checked_at: "2026-02-30T12:00:00Z",
      last_chat_verified_at: null,
      restart_available: false,
      status_basis: "application_path",
    },
    {
      state: "chat_verified",
      http_ready: true,
      provider_ready: true,
      chat_verified: true,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: "2026-07-30T12:00:01Z",
      restart_available: false,
      status_basis: "application_path",
    },
    {
      state: "degraded",
      http_ready: true,
      provider_ready: true,
      chat_verified: false,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: "2026-07-30T11:59:59Z",
      restart_available: false,
      status_basis: "application_path",
    },
  ])("rejects a malformed or expanded Yujin status DTO", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(status), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api.getHermesYujinStatus()).rejects.toThrow(
      "hermes_yujin_status_invalid",
    );
    vi.unstubAllGlobals();
  });

  it.each([false, true])("accepts degraded status with HTTP=%s only when provider and chat are false", async (httpReady) => {
    const status = {
      state: "degraded",
      http_ready: httpReady,
      provider_ready: false,
      chat_verified: false,
      checked_at: "2026-07-30T12:00:00Z",
      last_chat_verified_at: "2026-07-30T11:59:59Z",
      restart_available: false,
      status_basis: "application_path",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(status), { status: 200 }),
      ),
    );

    await expect(api.getHermesYujinStatus()).resolves.toEqual(status);
    vi.unstubAllGlobals();
  });

  it("loads the editor manifest from the explicit project and session boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ session_id: "s" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.getEditorPlaybackManifest("project/1", "session/1");
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project%2F1/editing-sessions/session%2F1/playback-manifest", undefined);
    vi.unstubAllGlobals();
  });
  it("starts a fenced exact preview only through the local project/session route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "pending", generation_id: "g-1", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 4, fingerprint: "sha256:test" }), { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.startExactPreview("project/1", "session/1", { expected_revision: 4 });
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project%2F1/editing-sessions/session%2F1/exact-preview", expect.objectContaining({ method: "POST", body: JSON.stringify({ expected_revision: 4 }) }));
    vi.unstubAllGlobals();
  });
  it("uses project-scoped persisted creation brief routes and preserves creator answers", async () => {
    const created = {
      brief_id: "brief_1", project_id: "project_001", idempotency_key: "stable-key", script_filename: "intro.txt", script_text: "소개 영상",
      script_asset_id: null, capability_profile: { ai_execution: "disabled" }, questions: [{ question_id: "q_audience", field: "audience", prompt: "누구에게 보여줄까요?" }],
      answers: {}, current_step: 0, status: "interview", revision: 1, created_at: "now", updated_at: "now",
    };
    const answered = { ...created, answers: { audience: "처음 방문한 고객" }, current_step: 1, revision: 2 };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(created), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(answered), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(answered), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.createCreationBrief("project_001", { script_filename: "intro.txt", script_text: "소개 영상", idempotency_key: "stable-key", capability_profile: { ai_execution: "disabled" } });
    await api.answerCreationBriefQuestion("project_001", "brief_1", "q_audience", { answer: "처음 방문한 고객", expected_revision: 1 });
    await api.getCreationBrief("project_001", "brief_1");
    await api.deleteCreationBrief("project_001", "brief_1");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/project_001/creation-briefs", expect.objectContaining({ method: "POST", body: JSON.stringify({ script_filename: "intro.txt", script_text: "소개 영상", idempotency_key: "stable-key", capability_profile: { ai_execution: "disabled" } }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project_001/creation-briefs/brief_1/answers", expect.objectContaining({ method: "POST", body: JSON.stringify({ question_id: "q_audience", answer: "처음 방문한 고객", expected_revision: 1 }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/projects/project_001/creation-briefs/brief_1", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(4, "/api/projects/project_001/creation-briefs/brief_1", expect.objectContaining({ method: "DELETE" }));
    vi.unstubAllGlobals();
  });

  it("keeps summary approval and manual bypass project-scoped with an expected revision", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ brief_id: "brief_1", revision: 3, status: "approved" }), { status: 200 }),
    ));
    vi.stubGlobal("fetch", fetchMock);

    await api.updateCreationBriefSummary("project_001", "brief_1", { summary: "처음 방문한 고객에게 차분하게 소개", expected_revision: 2 });
    await api.approveCreationBrief("project_001", "brief_1", { expected_revision: 3 });
    await api.bypassCreationBriefInterview("project_001", "brief_1", { expected_revision: 2 });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/project_001/creation-briefs/brief_1", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ summary: "처음 방문한 고객에게 차분하게 소개", expected_revision: 2 }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project_001/creation-briefs/brief_1/approve", expect.objectContaining({ method: "POST", body: JSON.stringify({ expected_revision: 3 }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/projects/project_001/creation-briefs/brief_1/bypass", expect.objectContaining({ method: "POST", body: JSON.stringify({ expected_revision: 2 }) }));
    vi.unstubAllGlobals();
  });
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

  it("normalizes the real preflight 409 stale payload instead of throwing a generic conflict", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "stale_proposal", stale_reasons: ["session_revision_changed"], diff: { changed: ["seg-1"] } }), { status: 409 })));
    await expect(api.preflightDirectorProposal("p", "proposal-1")).resolves.toMatchObject({ status: "stale", code: "stale_proposal", stale_reasons: ["session_revision_changed"] });
    vi.unstubAllGlobals();
  });

  it("materializes the selected immutable candidate and constructs its preview route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ asset_id: "asset-1" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.materializeDirectorCandidate("p", "proposal-1", "candidate/1");
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/p/director/proposals/proposal-1/candidates/candidate%2F1/materialize", expect.objectContaining({ method: "POST" }));
    expect(api.directorCandidatePreviewUrl("p", "proposal-1", "candidate/1")).toBe("/api/projects/p/director/proposals/proposal-1/candidates/candidate%2F1/preview");
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

  it("preserves source session identity on output and approval API types", () => {
    const lineage = { source_session_id: "session-a", source_session_revision: 7 };
    const timeline = {
      timeline_id: "timeline-a", project_id: "project_a", version: "v7", output_mode: "short",
      review_status: "approved", tracks: [], review_flags: [], applied_recommendations: [],
      pending_recommendations: [], ...lineage,
    } satisfies TimelinePayload;
    const subtitle = {
      subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt",
      file_uri: "local://subtitle.srt", status: "succeeded", notes: [], is_current: true, ...lineage,
    } satisfies SubtitleArtifact;
    const finalRender = {
      export_id: "final-a", timeline_id: "timeline-a", export_type: "final_render",
      file_uri: "local://final.mp4", status: "succeeded", is_current: true, ...lineage,
    } satisfies FinalRenderArtifact;
    const handoff = {
      status: "ready", source_file_uri: "local://draft.zip", reused: false, ...lineage,
    } satisfies CapCutDraftHandoff;
    const capcut = {
      export_id: "capcut-a", timeline_id: "timeline-a", export_type: "capcut_draft",
      file_uri: "local://draft.zip", status: "succeeded", notes: [], handoff, is_current: true, ...lineage,
    } satisfies CapCutDraftExportArtifact;
    const approval = {
      timeline_id: "timeline-a", project_id: "project_a", review_status: "approved",
      approved_at: "now", updated_at: "now", is_current: true, invalidated_at: null,
      invalidated_reason: null, ...lineage,
    } satisfies ReviewApproval;

    expect([timeline, subtitle, finalRender, capcut, capcut.handoff, approval])
      .toSatisfy((items) => items.every((item) => item.source_session_id === "session-a"));
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

  it("keeps Starter Pack favorite and recent calls project-scoped", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ asset_ids: ["pack:music"] }), { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    await api.listProjectMediaLibraryFavorites("project_a");
    await api.listProjectRecentMediaLibraryAssetIds("project_a");
    await api.setProjectMediaLibraryFavorite("project_a", "pack:music", true);
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/project_a/media-library/favorites", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project_a/media-library/recent", undefined);
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/projects/project_a/media-library/assets/pack%3Amusic/favorite", expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: true }) }));
    vi.unstubAllGlobals();
  });

  it("preserves the durable in-progress CapCut handoff response as a typed error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "capcut_draft_handoff_in_progress" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    )));

    await expect(api.registerCapcutDraftHandoff("project_a", "capcut-a"))
      .rejects.toMatchObject({ code: "capcut_draft_handoff_in_progress" });
    vi.unstubAllGlobals();
  });
});
