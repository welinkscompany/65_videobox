import { createServer } from "node:http";

const host = "127.0.0.1";
const port = 8000;
const project = {
  project_id: "local-draft",
  name: "여름 여행 영상",
  status: "active",
  root_storage_uri: "local://videobox/local-draft",
};
const approvedBrief = { brief_id: "brief-e2e", project_id: "local-draft", idempotency_key: "e2e", script_filename: "script.txt", script_text: "여름 여행을 소개합니다.", script_asset_id: "asset-script", capability_profile: {}, questions: [], answers: {}, current_step: 0, status: "approved", revision: 5, summary: "여름 여행", created_at: "now", updated_at: "now" };
const readiness = { readiness_id: "readiness_e2e", project_id: "local-draft", brief_id: "brief-e2e", status: "needs_assets", revision: 1, result: { gap_slots: [{ gap_slot_id: "gap-1", reason: "장면 영상이 없어요." }] } };
let uploadedBroll = false;

function sendJson(response, status, payload) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${host}:${port}`);
  if (url.pathname === "/health") return sendJson(response, 200, { status: "ok", mode: "e2e-local" });
  if (url.pathname === "/api/projects" && request.method === "GET") return sendJson(response, 200, { projects: [project] });
  if (url.pathname === "/api/projects/local-draft/creation-briefs/brief-e2e" && request.method === "GET") return sendJson(response, 200, approvedBrief);
  if (url.pathname === "/api/projects/local-draft/draft-readiness/narration-options" && request.method === "GET") return sendJson(response, 200, { assets: [] });
  if (url.pathname === "/api/projects/local-draft/draft-readiness" && request.method === "POST") return sendJson(response, 201, readiness);
  if (url.pathname === "/api/projects/local-draft/draft-readiness/readiness_e2e/retry" && request.method === "POST") { readiness.status = "planning"; readiness.revision += 1; return sendJson(response, 200, readiness); }
  if (url.pathname === "/api/projects/local-draft/draft-readiness/readiness_e2e/complete" && request.method === "POST") { readiness.status = uploadedBroll ? "ready" : "needs_assets"; readiness.revision += 1; readiness.result = uploadedBroll ? { broll_candidates: [{ asset_id: "broll-e2e", label: "해변 장면", target_range: { start_sec: 0, end_sec: 5 } }], gap_slots: [] } : { gap_slots: [{ gap_slot_id: "gap-1", reason: "장면 영상이 없어요." }] }; return sendJson(response, 200, readiness); }
  if (url.pathname === "/api/projects/local-draft/draft-readiness/broll/upload" && request.method === "POST") { uploadedBroll = true; return sendJson(response, 201, { asset_id: "broll-e2e", asset_type: "broll_video", scan_status: "local_ready" }); }
  if (url.pathname === "/api/projects/local-draft/draft-readiness/readiness_e2e" && request.method === "GET") return sendJson(response, 200, readiness);
  if (/^\/api\/projects\/[^/]+\/providers\/gemini\/keys$/.test(url.pathname) && request.method === "GET") {
    return sendJson(response, 200, { keys: [] });
  }
  return sendJson(response, 404, { detail: "The local E2E server only provides deterministic project catalog data." });
}).listen(port, host, () => {
  console.log(`VideoBox E2E fake API listening at http://${host}:${port}`);
});
