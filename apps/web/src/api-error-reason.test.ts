import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, request } from "./api";

describe("오류 이유 읽기", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("서버가 {reason} 모양으로 보낸 이유를 화면이 읽을 수 있게 넘긴다", async () => {
    // AK W1215-4: 업로드 승인 요청이 권리 미확인으로 막히면 서버는
    // {"detail": {"reason": "asset_rights_unconfirmed", ...}} 을 보낸다. 예전에는
    // 문자열이 아닌 detail을 버려서 화면이 "왜" 막혔는지 알 길이 없었다.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { reason: "asset_rights_unconfirmed", library_asset_ids: ["user_1"] } }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    )));

    const error = await request("/api/anything", { method: "POST" }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect((error as ApiRequestError).status).toBe(409);
    expect((error as ApiRequestError).reason).toBe("asset_rights_unconfirmed");
    expect((error as ApiRequestError).detail).toBeNull();
  });

  it("문자열 detail은 이유로도 그대로 쓴다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "media_type_unknown" }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    )));

    const error = await request("/api/anything").catch((caught: unknown) => caught);

    expect((error as ApiRequestError).detail).toBe("media_type_unknown");
    expect((error as ApiRequestError).reason).toBe("media_type_unknown");
  });
});
