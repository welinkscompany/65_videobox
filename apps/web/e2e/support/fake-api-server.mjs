import { createServer } from "node:http";

const host = "127.0.0.1";
const port = 8000;
const project = {
  project_id: "local-draft",
  name: "여름 여행 영상",
  status: "active",
  root_storage_uri: "local://videobox/local-draft",
};

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
  if (/^\/api\/projects\/[^/]+\/providers\/gemini\/keys$/.test(url.pathname) && request.method === "GET") {
    return sendJson(response, 200, { keys: [] });
  }
  return sendJson(response, 404, { detail: "The local E2E server only provides deterministic project catalog data." });
}).listen(port, host, () => {
  console.log(`VideoBox E2E fake API listening at http://${host}:${port}`);
});
