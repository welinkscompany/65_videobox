const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"])

export function isAllowedLocalUrl(value: string | URL): boolean {
  const raw = String(value)
  if (raw.startsWith("/") && !raw.startsWith("//")) return true
  try {
    const url = new URL(raw)
    return (url.protocol === "http:" || url.protocol === "https:") && LOOPBACK_HOSTS.has(url.hostname)
  } catch { return false }
}

export function assertLocalNetwork(value: string | URL): void {
  if (!isAllowedLocalUrl(value)) throw new Error(`External network is blocked in local/test: ${String(value)}`)
}

export function installNetworkGuard(): void {
  const nativeFetch = globalThis.fetch
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const value = input instanceof Request ? input.url : input
    assertLocalNetwork(value)
    return nativeFetch(input, init)
  }) as typeof fetch
  const NativeXhr = globalThis.XMLHttpRequest
  if (NativeXhr) {
    class GuardedXMLHttpRequest extends NativeXhr {
      open(method: string, url: string | URL, async?: boolean, username?: string | null, password?: string | null): void {
        assertLocalNetwork(url)
        super.open(method, String(url), async ?? true, username ?? undefined, password ?? undefined)
      }
    }
    globalThis.XMLHttpRequest = GuardedXMLHttpRequest
  }
  for (const name of ["WebSocket", "EventSource"] as const) {
    const Native = globalThis[name]
    if (!Native) continue
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value: class extends (Native as unknown as new (...args: any[]) => object) {
      constructor(url: string | URL, ...args: any[]) { assertLocalNetwork(url); super(url, ...args) }
    } })
  }
  if (globalThis.navigator?.sendBeacon) {
    const nativeBeacon = globalThis.navigator.sendBeacon.bind(globalThis.navigator)
    globalThis.navigator.sendBeacon = (url, data) => { assertLocalNetwork(url); return nativeBeacon(url, data) }
  }
}
