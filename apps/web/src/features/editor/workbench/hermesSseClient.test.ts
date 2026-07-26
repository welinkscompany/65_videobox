import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../../api";
import { parseHermesSse, type HermesSseEvent } from "./hermesSseClient";

afterEach(() => {
  vi.restoreAllMocks();
});

function sseResponse(chunks: readonly string[], contentType = "text/event-stream") {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  }), { headers: { "Content-Type": contentType } });
}

function event(id: number, eventType: HermesSseEvent["event_type"], text = "", retryable = false) {
  return `id: ${id}\nevent: ${eventType}\ndata: ${JSON.stringify({ event_id: id, event_type: eventType, text, retryable })}\n\n`;
}

describe("parseHermesSse", () => {
  it("parses split frames, emits only the allowlist, and ignores duplicate or old IDs", async () => {
    const received: HermesSseEvent[] = [];
    const wire = [
      event(1, "run_started"),
      event(2, "text_delta", "안"),
      event(2, "text_delta", "중복"),
      event(1, "run_started"),
      event(3, "text_delta", "녕하세요"),
      event(4, "run_completed", "안녕하세요"),
    ].join("");

    await parseHermesSse(
      sseResponse([wire.slice(0, 17), wire.slice(17, 83), wire.slice(83)]),
      { signal: new AbortController().signal, onEvent: (next) => received.push(next) },
    );

    expect(received.map((next) => [next.event_id, next.event_type, next.text])).toEqual([
      [1, "run_started", ""],
      [2, "text_delta", "안"],
      [3, "text_delta", "녕하세요"],
      [4, "run_completed", "안녕하세요"],
    ]);
  });

  it.each([
    event(1, "run_started") + "id: 2\nevent: tool_call\ndata: {\"event_id\":2,\"event_type\":\"tool_call\",\"text\":\"PRIVATE\",\"retryable\":false}\n\n",
    "id: 1\nevent: text_delta\ndata: {\"event_id\":2,\"event_type\":\"text_delta\",\"text\":\"PRIVATE\",\"retryable\":false}\n\n",
    "id: 1\nevent: text_delta\ndata: {\"event_id\":1,\"event_type\":\"text_delta\",\"text\":7,\"retryable\":false}\n\n",
  ])("rejects malformed or non-allowlisted events without reflecting payloads", async (wire) => {
    let captured: unknown;
    try {
      await parseHermesSse(
        sseResponse([wire]),
        { signal: new AbortController().signal, onEvent: vi.fn() },
      );
    } catch (error) {
      captured = error;
    }

    expect(captured).toBeInstanceOf(Error);
    expect(String(captured)).toContain("유진 응답을 이어받지 못했어요.");
    expect(String(captured)).not.toContain("PRIVATE");
  });

  it.each([
    `id: 1\nevent: text_delta\ndata: ${"x".repeat(256_001)}\n\n`,
    event(1, "text_delta", "x".repeat(32_001)),
    event(1, "text_delta", "x".repeat(20_000)) + event(2, "text_delta", "x".repeat(20_000)) + event(3, "text_delta", "x".repeat(20_000)) + event(4, "text_delta", "x".repeat(20_000)) + event(5, "text_delta", "x".repeat(20_000)) + event(6, "text_delta", "x".repeat(20_000)) + event(7, "text_delta", "x".repeat(20_000)) + event(8, "text_delta", "x".repeat(20_000)) + event(9, "text_delta", "x".repeat(20_000)) + event(10, "text_delta", "x".repeat(20_000)) + event(11, "text_delta", "x"),
  ])("fails closed when a line, delta, or accumulated text exceeds its cap", async (wire) => {
    await expect(parseHermesSse(
      sseResponse([wire]),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
  });

  it("honors AbortSignal and never turns an abort into a retry", async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(parseHermesSse(
      sseResponse([event(1, "run_started")]),
      { signal: controller.signal, onEvent: vi.fn() },
    )).rejects.toMatchObject({ name: "AbortError" });
  });

  it("requires a terminal event and rejects a non-SSE response", async () => {
    await expect(parseHermesSse(
      sseResponse([event(1, "run_started")]),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
    for (const contentType of ["application/json", "text/event-streamx"]) {
      await expect(parseHermesSse(
        sseResponse([event(1, "run_completed", "완료")], contentType),
        { signal: new AbortController().signal, onEvent: vi.fn() },
      )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
    }
  });

  it("decodes UTF-8 split across bytes and accepts CRLF framing", async () => {
    const received: HermesSseEvent[] = [];
    const wire = event(1, "run_started").replaceAll("\n", "\r\n")
      + event(2, "text_delta", "안녕").replaceAll("\n", "\r\n")
      + event(3, "run_completed", "안녕").replaceAll("\n", "\r\n");
    const encoded = new TextEncoder().encode(wire);
    const splitAt = encoded.findIndex((value, index) => index > 0 && value >= 0x80);
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoded.slice(0, splitAt + 1));
        controller.enqueue(encoded.slice(splitAt + 1, splitAt + 2));
        controller.enqueue(encoded.slice(splitAt + 2));
        controller.close();
      },
    }), { headers: { "Content-Type": "text/event-stream" } });

    await parseHermesSse(response, {
      signal: new AbortController().signal,
      onEvent: (next) => received.push(next),
    });

    expect(received.at(-1)).toMatchObject({ event_type: "run_completed", text: "안녕" });
  });

  it("rejects a second higher terminal frame but ignores an exact duplicate ID", async () => {
    const duplicate = event(1, "run_started")
      + event(2, "text_delta", "완료")
      + event(3, "run_completed", "완료")
      + event(3, "run_completed", "완료");
    await expect(parseHermesSse(
      sseResponse([duplicate]),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).resolves.toBeUndefined();

    const multiple = event(1, "run_started")
      + event(2, "text_delta", "완료")
      + event(3, "run_completed", "완료")
      + event(4, "blocked", "PRIVATE", true);
    await expect(parseHermesSse(
      sseResponse([multiple]),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
  });

  it("cancels and releases a pending reader exactly once when aborted", async () => {
    let finishRead!: () => void;
    const read = vi.fn(() => new Promise<{ done: true; value?: undefined }>((resolve) => {
      finishRead = () => resolve({ done: true });
    }));
    const cancel = vi.fn(async () => finishRead());
    const releaseLock = vi.fn();
    const response = {
      ok: true,
      headers: new Headers({ "Content-Type": "text/event-stream" }),
      body: { getReader: () => ({ read, cancel, releaseLock }) },
    } as unknown as Response;
    const controller = new AbortController();

    const pending = parseHermesSse(response, { signal: controller.signal, onEvent: vi.fn() });
    await Promise.resolve();
    controller.abort();

    await vi.waitFor(() => expect(cancel).toHaveBeenCalledOnce());
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(releaseLock).toHaveBeenCalledOnce();
  });

  it("rejects non-2xx, missing-body, and completion-mismatch responses", async () => {
    await expect(parseHermesSse(
      new Response(null, { status: 503, headers: { "Content-Type": "text/event-stream" } }),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
    await expect(parseHermesSse(
      new Response(null, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
    await expect(parseHermesSse(
      sseResponse([event(1, "run_started") + event(2, "text_delta", "일부") + event(3, "run_completed", "다른 최종")]),
      { signal: new AbortController().signal, onEvent: vi.fn() },
    )).rejects.toThrow("유진 응답을 이어받지 못했어요.");
  });
});

describe("Hermes browser API boundary", () => {
  it("creates a typed run and opens only its same-origin VideoBox SSE URL", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        run_id: "run-1",
        conversation_id: "conversation-1",
        events_url: "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events",
      }), { status: 201, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(sseResponse([event(1, "run_completed", "완료")]));

    const created = await api.createHermesRun("project-a", "conversation-1", {
      session_id: "session-a",
      client_message_id: "client-1",
      text: "안녕하세요",
    });
    const controller = new AbortController();
    const response = await api.openHermesRunEvents(
      "project-a",
      "conversation-1",
      created,
      controller.signal,
    );

    expect(created.run_id).toBe("run-1");
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/projects/project-a/director/conversations/conversation-1/hermes-runs",
      expect.objectContaining({ method: "POST", credentials: "same-origin" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      created.events_url,
      expect.objectContaining({ method: "GET", credentials: "same-origin", signal: controller.signal }),
    );
  });

  it("requires HTTP 201 and an exactly linked run before accepting creation", async () => {
    const payload = {
      run_id: "run-1",
      conversation_id: "conversation-1",
      events_url: "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events",
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...payload, conversation_id: "conversation-OTHER" }), { status: 201, headers: { "Content-Type": "application/json" } }));

    await expect(api.createHermesRun(
      "project-a",
      "conversation-1",
      { session_id: "session-a", client_message_id: "client-1", text: "요청" },
    )).rejects.toThrow("유진 응답을 시작하지 못했어요.");
    await expect(api.createHermesRun(
      "project-a",
      "conversation-1",
      { session_id: "session-a", client_message_id: "client-2", text: "요청" },
    )).rejects.toThrow("유진 응답을 시작하지 못했어요.");
  });

  it.each([
    "http://videobox-hermes-yujin:9120/api/ws",
    "http://videobox-agent-gateway:8081/internal/hermes/stream",
    "//evil.example/api/projects/p/director/conversations/c/hermes-runs/r/events",
    "/api/projects/p/director/conversations/c/hermes-runs/r/events?token=PRIVATE",
    "/api/projects/p/director/conversations/c/hermes-runs/r/events#PRIVATE",
  ])("rejects a direct or decorated upstream URL before browser fetch: %s", async (url) => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    await expect(api.openHermesRunEvents(
      "p",
      "c",
      { run_id: "r", conversation_id: "c", events_url: url },
      new AbortController().signal,
    ))
      .rejects.toThrow("유진 응답을 시작하지 못했어요.");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a same-origin events URL that does not exactly match the created run", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    await expect(api.openHermesRunEvents(
      "project-a",
      "conversation-1",
      {
        run_id: "run-1",
        conversation_id: "conversation-1",
        events_url: "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-OTHER/events",
      },
      new AbortController().signal,
    )).rejects.toThrow("유진 응답을 시작하지 못했어요.");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects redirected SSE responses", async () => {
    const redirected = sseResponse([event(1, "run_completed", "완료")]);
    Object.defineProperties(redirected, {
      redirected: { configurable: true, value: true },
      url: { configurable: true, value: "http://videobox-agent-gateway:8081/internal/hermes/stream" },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(redirected);

    await expect(api.openHermesRunEvents(
      "project-a",
      "conversation-1",
      {
        run_id: "run-1",
        conversation_id: "conversation-1",
        events_url: "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events",
      },
      new AbortController().signal,
    )).rejects.toThrow("유진 응답을 시작하지 못했어요.");
  });
});
