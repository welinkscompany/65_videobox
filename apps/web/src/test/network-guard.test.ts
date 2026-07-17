import { describe, expect, it, vi } from "vitest"
import { assertLocalNetwork, installNetworkGuard, isAllowedLocalUrl } from "@/lib/network-guard"

describe("local network guard", () => {
  it("allows relative and explicit loopback URLs only", () => {
    expect(isAllowedLocalUrl("/api/projects")).toBe(true)
    expect(isAllowedLocalUrl("http://127.0.0.1:8000/health")).toBe(true)
    expect(() => assertLocalNetwork("https://example.com/font.woff2")).toThrow("External network is blocked")
    expect(() => assertLocalNetwork("//example.com/x")).toThrow("External network is blocked")
  })

  it("denies a remote XMLHttpRequest while retaining local endpoints", () => {
    const remote = new XMLHttpRequest()
    expect(() => remote.open("GET", "https://example.com/data")).toThrow("External network is blocked")
    const local = new XMLHttpRequest()
    expect(() => local.open("GET", "/api/projects")).not.toThrow()
    expect(() => local.open("GET", "http://127.0.0.1:8000/health")).not.toThrow()
  })

  it("invokes the fetch wrapper and rejects remote requests", async () => {
    expect(() => fetch("https://example.com/data")).toThrow("External network is blocked")
  })

  it("wraps WebSocket and EventSource constructors when the browser exposes them", () => {
    const originalWebSocket = globalThis.WebSocket
    const originalEventSource = globalThis.EventSource
    class FakeSocket { constructor(_url: string) {} }
    class FakeEventSource { constructor(_url: string) {} }
    Object.defineProperty(globalThis, "WebSocket", { configurable: true, writable: true, value: FakeSocket })
    Object.defineProperty(globalThis, "EventSource", { configurable: true, writable: true, value: FakeEventSource })
    installNetworkGuard()
    expect(() => new WebSocket("https://example.com/socket")).toThrow("External network is blocked")
    expect(() => new EventSource("https://example.com/events")).toThrow("External network is blocked")
    Object.defineProperty(globalThis, "WebSocket", { configurable: true, writable: true, value: originalWebSocket })
    Object.defineProperty(globalThis, "EventSource", { configurable: true, writable: true, value: originalEventSource })
    vi.restoreAllMocks()
  })
})
