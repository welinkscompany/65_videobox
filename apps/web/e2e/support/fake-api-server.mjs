import { createServer } from "node:http";

const host = "127.0.0.1";
const port = Number.parseInt(process.env.PLAYWRIGHT_FAKE_API_PORT ?? "8000", 10);
const validTinyPlayableMp4 = Buffer.from("AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAMtbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAAHgAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAld0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAAHgAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAABAAAAAQAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAB4AAAAAAABAAAAAAHPbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAyAAAABgBVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABem1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAATpzdGJsAAAAtnN0c2QAAAAAAAAAAQAAAKZhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAABAAEABIAAAASAAAAAAAAAABFUxhdmM2Mi4yOC4xMDEgbGlieDI2NAAAAAAAAAAAAAAAGP//AAAALGF2Y0MBQsAK/+EAFWdCwAraewEQAAADABAAAAMDIPEiagEABGjOD8gAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAClGgAAAAAAAAAYc3R0cwAAAAAAAAABAAAAAwAAAgAAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAAAAEAAAABAAAAAwAAAAEAAAAgc3RzegAAAAAAAAAAAAAAAwAAAmgAAAAJAAAACQAAABRzdGNvAAAAAAAAAAEAAANdAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExhdmY2Mi4xMi4xMDEAAAAIZnJlZQAAAoJtZGF0AAACVgYF//9S3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NSByMzIyMyAwNDgwY2IwIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTAgcmVmPTEgZGVibG9jaz0wOi0zOi0zIGFuYWx5c2U9MDowIG1lPWRpYSBzdWJtZT0wIHBzeT0xIHBzeV9yZD0yLjAwOjAuNzAgbWl4ZWRfcmVmPTAgbWVfcmFuZ2U9MTYgY2hyb21hX21lPTEgdHJlbGxpcz0wIDh4OGRjdD0wIGNxbT0wIGRlYWR6b25lPTIxLDExIGZhc3RfcHNraXA9MSBjaHJvbWFfcXBfb2Zmc2V0PTAgdGhyZWFkcz0xIGxvb2thaGVhZF90aHJlYWRzPTEgc2xpY2VkX3RocmVhZHM9MCBucj0wIGRlY2ltYXRlPTEgaW50ZXJsYWNlZD0wIGJsdXJheV9jb21wYXQ9MCBjb25zdHJhaW5lZF9pbnRyYT0wIGJmcmFtZXM9MCB3ZWlnaHRwPTAga2V5aW50PTI1MCBrZXlpbnRfbWluPTI1IHNjZW5lY3V0PTAgaW50cmFfcmVmcmVzaD0wIHJjPWNyZiBtYnRyZWU9MCBjcmY9MjMuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBzdGVwPTQgaXBfcmF0aW89MS40MCBhcT0wAIAAAAAKZYiEOiYoAAj2YAAAAAVBmiAmlAAAAAVBmkAqlA==", "base64");
const tinyPlayableMp4 = Buffer.from("AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAABA1tZGF0AAACrgYF//+q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NSByMzIyMyAwNDgwY2IwIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTI1IHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAAAFGWIhAA7//73Tr8Cm0WXagNYle7xAAAACEGaJGxDf/6r3gIATGF2YzYyLjI4LjEwMQBCIAjBGDgAAAAIQZ5CeIX/VcEhEARgjBwhEARgjBwAAAAIAZ5hdEK/WsAhEARgjBwhEARgjBwAAAAIAZ5jakK/WsEhEARgjBwhEARgjBwAAAAOQZpoSahBaJlMCGf//qchEARgjBwAAAAKQZ6G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", "base64");
const project = {
  project_id: "local-draft",
  name: "여름 여행 영상",
  status: "active",
  root_storage_uri: "local://videobox/local-draft",
};
const approvedBrief = { brief_id: "brief-e2e", project_id: "local-draft", idempotency_key: "e2e", script_filename: "script.txt", script_text: "여름 여행을 소개합니다.", script_asset_id: "asset-script", capability_profile: {}, questions: [], answers: {}, current_step: 0, status: "approved", revision: 5, summary: "여름 여행", created_at: "now", updated_at: "now" };
const readiness = { readiness_id: "readiness_e2e", project_id: "local-draft", brief_id: "brief-e2e", status: "needs_assets", revision: 1, result: { gap_slots: [{ gap_slot_id: "gap-1", reason: "장면 영상이 없어요." }] } };
let uploadedBroll = false;
let bundleSequence = 0;
let latestBundle = null;
const atomicSession = { session_id: "editing_session_e2e", project_id: "local-draft", timeline_id: "timeline_e2e", session_revision: 1, history: [], undo_count: 0, redo_count: 0, segments: [{ segment_id: "segment-e2e", caption_text: "여름 여행을 소개합니다.", start_sec: 0, end_sec: 1, cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [], music_override: null, sfx_override: null, tts_replacement: null }] };
const jobs = { jobs: [{ job_id: "timeline_build_e2e", project_id: "local-draft", job_type: "timeline_build", status: "succeeded", input_ref: "readiness_e2e", output_ref: "timeline_e2e", error_message: null, started_at: "now", finished_at: "now" }, { job_id: "final-e2e", project_id: "local-draft", job_type: "final_render", status: "succeeded", input_ref: "timeline_build_e2e", output_ref: "final-export-e2e", error_message: null, started_at: "now", finished_at: "now" }] };

function sendJson(response, status, payload) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

function resetDraftScenario() {
  uploadedBroll = false;
  readiness.status = "needs_assets";
  readiness.revision = 1;
  readiness.result = { gap_slots: [{ gap_slot_id: "gap-1", reason: "장면 영상이 없어요." }] };
  latestBundle = null;
  jobs.jobs = [];
}

function resetReviewScenario() {
  uploadedBroll = false;
  bundleSequence = 0;
  latestBundle = null;
  readiness.status = "needs_assets";
  readiness.revision = 1;
  readiness.result = { gap_slots: [{ gap_slot_id: "gap-1", reason: "장면 영상이 없어요." }] };
  atomicSession.session_id = "editing_session_e2e";
  atomicSession.project_id = "local-draft";
  atomicSession.timeline_id = "timeline_e2e";
  atomicSession.session_revision = 1;
  atomicSession.history = [];
  atomicSession.undo_count = 0;
  atomicSession.redo_count = 0;
  atomicSession.segments = [{ segment_id: "segment-e2e", caption_text: "여름 여행을 소개합니다.", start_sec: 0, end_sec: 1, cut_action: "keep", review_required: false, broll_override: null, visual_overlays: [], music_override: null, sfx_override: null, tts_replacement: null }];
  jobs.jobs = [
    { job_id: "timeline_build_e2e", project_id: "local-draft", job_type: "timeline_build", status: "succeeded", input_ref: "readiness_e2e", output_ref: "timeline_e2e", error_message: null, started_at: "now", finished_at: "now" },
    { job_id: "final-e2e", project_id: "local-draft", job_type: "final_render", status: "succeeded", input_ref: "timeline_build_e2e", output_ref: "final-export-e2e", error_message: null, started_at: "now", finished_at: "now" },
  ];
}

function createBundle() {
  bundleSequence += 1;
  const suffix = String(bundleSequence);
  const isGapOnly = readiness.status === "needs_assets";
  latestBundle = {
    bundle_id: `bundle-e2e-${suffix}`,
    session_id: `editing_session_e2e_${suffix}`,
    timeline_id: `timeline_e2e_${suffix}`,
    timeline_job_id: `timeline_build_e2e_${suffix}`,
    segment_ids: [`segment-e2e-${suffix}`], asset_ids: ["asset-silence", ...(isGapOnly ? [`asset-gap-${suffix}`] : ["broll-e2e"])],
    clip_ids: [`clip-caption-${suffix}`, ...(isGapOnly ? [`clip-gap-${suffix}`] : [`clip-broll-${suffix}`])],
    gap_slots: isGapOnly ? readiness.result.gap_slots : [], output_blocked: isGapOnly,
  };
  atomicSession.session_id = latestBundle.session_id; atomicSession.timeline_id = latestBundle.timeline_id;
  jobs.jobs = [{ job_id: latestBundle.timeline_job_id, project_id: "local-draft", job_type: "timeline_build", status: "succeeded", input_ref: "readiness_e2e", output_ref: latestBundle.timeline_id, error_message: null, started_at: "now", finished_at: "now" }];
  if (!isGapOnly) jobs.jobs.push({ job_id: `final-e2e-${suffix}`, project_id: "local-draft", job_type: "final_render", status: "succeeded", input_ref: latestBundle.timeline_job_id, output_ref: `final-export-e2e-${suffix}`, error_message: null, started_at: "now", finished_at: "now" });
  return latestBundle;
}

createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${host}:${port}`);
  if (url.pathname === "/health") return sendJson(response, 200, { status: "ok", mode: "e2e-local" });
  if (url.pathname === "/__e2e/reset-draft" && request.method === "POST") { resetDraftScenario(); return sendJson(response, 200, { status: "reset" }); }
  if (url.pathname === "/__e2e/reset-review" && request.method === "POST") { resetReviewScenario(); return sendJson(response, 200, { status: "reset" }); }
  if (url.pathname === "/__e2e/draft-state" && request.method === "GET") return sendJson(response, 200, {
    uploaded_broll: uploadedBroll,
    bundle_sequence: bundleSequence,
    latest_bundle: latestBundle,
    readiness,
    atomic_session: atomicSession,
    jobs: jobs.jobs,
  });
  if (url.pathname === "/api/projects" && request.method === "GET") return sendJson(response, 200, { projects: [project] });
  if (url.pathname === "/api/projects/local-draft" && request.method === "GET") return sendJson(response, 200, project);
  if (url.pathname === "/api/projects/local-draft/jobs" && request.method === "GET") return sendJson(response, 200, jobs);
  if (/^\/api\/projects\/local-draft\/editing-sessions\/[^/]+\/playback-manifest$/.test(url.pathname) && request.method === "GET") {
    const sessionId = url.pathname.split("/")[5];
    const activeSessionId = latestBundle?.session_id ?? atomicSession.session_id;
    const activeTimelineId = latestBundle?.timeline_id ?? atomicSession.timeline_id;
    if (sessionId !== activeSessionId) return sendJson(response, 404, { detail: "session_not_found" });
    const isCurrent = !latestBundle?.output_blocked;
    const reviewSegmentId = latestBundle?.segment_ids[0] ?? "segment-e2e";
    return sendJson(response, 200, {
      project_id: "local-draft", session_id: activeSessionId, timeline_id: activeTimelineId, session_revision: 1, timeline_version: "v1",
      timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 },
      tracks: latestBundle ? [] : [{ track_id: "narration", track_type: "narration", clips: [{ clip_id: "narration-e2e", segment_id: reviewSegmentId, clip_type: "narration", asset_id: null, asset_uri: null, start_sec: 0, end_sec: 1, media_controls: {} }] }],
      captions: [], gap_slots: (latestBundle?.gap_slots ?? []).map((gap) => ({ gap_id: gap.gap_slot_id, segment_id: reviewSegmentId, start_sec: 0, end_sec: 1, reason: gap.reason })),
      source_status: { status: "current", source_session_id: activeSessionId, source_session_revision: 1 }, audition: { asset_urls: {} },
      exact_preview: isCurrent && latestBundle
        ? { status: "current", url: `/api/projects/local-draft/final-renders/final-e2e-${bundleSequence}/content`, source_session_id: activeSessionId, source_session_revision: 1, artifact_revision: 1 }
        : { status: "unavailable", url: null, source_session_id: activeSessionId, source_session_revision: 1 },
    });
  }
  if (url.pathname.startsWith("/api/projects/local-draft/editing-sessions/") && request.method === "GET") return sendJson(response, 200, atomicSession);
  if (url.pathname === "/api/projects/local-draft/editing-sessions/latest" && request.method === "GET") return sendJson(response, 200, atomicSession);
  if (url.pathname.startsWith("/api/projects/local-draft/timelines/") && request.method === "GET") return sendJson(response, 200, { job_id: latestBundle?.timeline_job_id ?? "timeline_build_e2e", status: "succeeded", timeline: { timeline_id: latestBundle?.timeline_id ?? "timeline_e2e", project_id: "local-draft", version: "v1", output_mode: "review", review_status: latestBundle?.output_blocked ? "blocked" : "draft", tracks: [], applied_recommendations: [], review_flags: latestBundle?.output_blocked ? [{ code: "draft_gap_placeholder", segment_id: latestBundle.segment_ids[0], message: "장면 영상을 확인해 주세요." }] : [], pending_recommendations: [] } });
  if (url.pathname.startsWith("/api/projects/local-draft/review-snapshots/") && request.method === "GET") return sendJson(response, 200, { project_id: "local-draft", timeline_id: latestBundle?.timeline_id ?? "timeline_e2e", review_status: latestBundle?.output_blocked ? "blocked" : "draft", segments: latestBundle ? [] : [{ segment_id: "segment-e2e", text: "여름 여행을 소개합니다.", start_sec: 0, end_sec: 1, confidence: 1, review_required: false, cleanup_decision: "keep" }], applied_recommendations: [], pending_recommendations: [], review_flags: [] });
  if (/^\/api\/projects\/local-draft\/review-approvals\/timelines\/[^/]+$/.test(url.pathname) && request.method === "GET") return sendJson(response, 200, { project_id: "local-draft", timeline_id: latestBundle?.timeline_id ?? "timeline_e2e", review_status: "draft", approved_at: null, updated_at: "now", source_session_revision: 1, is_current: true, invalidated_at: null, invalidated_reason: null });
  if (url.pathname.startsWith("/api/projects/local-draft/final-renders/") && url.pathname.endsWith("/content") && request.method === "GET") { response.writeHead(200, { "content-type": "video/mp4", "accept-ranges": "bytes", "content-length": validTinyPlayableMp4.length }); return response.end(validTinyPlayableMp4); }
  if (url.pathname.startsWith("/api/projects/local-draft/final-renders/") && request.method === "GET") return sendJson(response, latestBundle?.output_blocked ? 400 : 200, latestBundle?.output_blocked ? { detail: "gap_blocks_final_output" } : { job_id: `final-e2e-${bundleSequence}`, status: "succeeded", render: { export_id: `final-export-e2e-${bundleSequence}`, timeline_id: latestBundle?.timeline_id, export_type: "final_render", file_uri: "local://final-e2e.mp4", status: "succeeded", source_session_revision: 1, is_current: true } });
  if (url.pathname === "/api/projects/local-draft/creation-briefs/brief-e2e" && request.method === "GET") return sendJson(response, 200, approvedBrief);
  if (url.pathname === "/api/projects/local-draft/draft-readiness/narration-options" && request.method === "GET") return sendJson(response, 200, { assets: [] });
  if (url.pathname === "/api/projects/local-draft/draft-readiness" && request.method === "POST") return sendJson(response, 201, readiness);
  if (url.pathname === "/api/projects/local-draft/draft-readiness/readiness_e2e/retry" && request.method === "POST") { readiness.status = "planning"; readiness.revision += 1; return sendJson(response, 200, readiness); }
  if (url.pathname === "/api/projects/local-draft/draft-readiness/readiness_e2e/complete" && request.method === "POST") { readiness.status = uploadedBroll ? "ready" : "needs_assets"; readiness.revision += 1; readiness.result = uploadedBroll ? { broll_candidates: [{ asset_id: "broll-e2e", label: "해변 장면", target_range: { start_sec: 0, end_sec: 5 } }], gap_slots: [] } : { gap_slots: [{ gap_slot_id: "gap-1", reason: "장면 영상이 없어요." }] }; return sendJson(response, 200, readiness); }
  if (url.pathname === "/api/projects/local-draft/draft-readiness/broll/upload" && request.method === "POST") { uploadedBroll = true; return sendJson(response, 201, { asset_id: "broll-e2e", asset_type: "broll_video", scan_status: "local_ready" }); }
  if (url.pathname === "/api/projects/local-draft/draft-readiness/readiness_e2e" && request.method === "GET") return sendJson(response, 200, readiness);
  if (url.pathname === "/api/projects/local-draft/draft-bundles" && request.method === "POST") return sendJson(response, 201, createBundle());
  if (url.pathname === "/api/projects/local-draft/jobs/final-render" && request.method === "POST") return sendJson(response, latestBundle?.output_blocked ? 400 : 201, latestBundle?.output_blocked ? { detail: "gap_blocks_final_output" } : { job_id: `final-e2e-${bundleSequence}`, status: "succeeded" });
  if (url.pathname === "/api/projects/local-draft/jobs/capcut-draft-export" && request.method === "POST") return sendJson(response, latestBundle?.output_blocked ? 400 : 201, latestBundle?.output_blocked ? { detail: "gap_blocks_capcut_output" } : { job_id: `capcut-e2e-${bundleSequence}`, status: "succeeded" });
  if (url.pathname === "/api/projects/local-draft/capcut-draft-exports/capcut-e2e/handoff" && request.method === "POST") return sendJson(response, 200, { handoff: { status: "registered", source_file_uri: "local://draft", registered_project_path: "C:/mock/draft", error_message: null, registered_at: "now", reused: false } });
  return sendJson(response, 404, { detail: "The local E2E server only provides deterministic project catalog data." });
}).listen(port, host, () => {
  console.log(`VideoBox E2E fake API listening at http://${host}:${port}`);
});
