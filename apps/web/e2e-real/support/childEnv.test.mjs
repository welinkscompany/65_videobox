import assert from "node:assert/strict";
import { test } from "node:test";

import { buildChildEnv } from "./childEnv.mjs";

test("소유자 셸의 VIDEOBOX_* 와 토큰류는 자식 환경에 없다", () => {
  const child = buildChildEnv({
    PATH: "p", SystemRoot: "C:\Windows",
    VIDEOBOX_MEDIA_INBOX_WATCH_PATH: "D:\inbox",
    VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN: "t",
    VIDEOBOX_BRIDGE_TOKEN: "t",
    VIDEOBOX_DATABASE_URL: "postgres://real",
    VIDEOBOX_DATA_ROOT: "D:\real",
    OPENAI_API_KEY: "k",
  });
  assert.equal(child.PATH, "p");
  assert.equal(child.SystemRoot, "C:\Windows");
  for (const name of ["VIDEOBOX_MEDIA_INBOX_WATCH_PATH", "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN", "VIDEOBOX_BRIDGE_TOKEN", "VIDEOBOX_DATABASE_URL", "VIDEOBOX_DATA_ROOT", "OPENAI_API_KEY"]) {
    assert.equal(name in child, false, name);
  }
  assert.equal(child.VIDEOBOX_E2E_PROTECT_ROOT, "D:\real");
});
