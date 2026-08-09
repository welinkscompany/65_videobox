import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "./api";

describe("본문이 없는 응답", () => {
  afterEach(() => vi.restoreAllMocks());

  it("204를 성공으로 다룬다", async () => {
    // 대화 삭제가 실제로는 지워졌는데 화면은 실패로 표시했다. 서버는 204를
    // 돌려줬고, 본문 없는 응답을 JSON으로 읽으려다 터진 것이다.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    ));

    await expect(request<void>("/api/anything", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("본문이 있는 응답은 그대로 읽는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
    ));

    await expect(request<{ ok: boolean }>("/api/anything")).resolves.toEqual({ ok: true });
  });
});
