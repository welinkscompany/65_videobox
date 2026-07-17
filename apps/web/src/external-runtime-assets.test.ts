import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

describe("external runtime assets", () => {
  it("does not import remote CSS or font URLs", () => {
    const css = readFileSync(resolve(process.cwd(), "src/ui-system.css"), "utf8")
    expect(css).not.toMatch(/https?:|\/\//)
    expect(css).toMatch(/PretendardVariable\.woff2/)
  })

  it("installs the runtime network guard and ships a same-origin CSP", () => {
    const main = readFileSync(resolve(process.cwd(), "src/main.tsx"), "utf8")
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8")
    expect(main).toMatch(/installNetworkGuard\(\)/)
    expect(html).toMatch(/Content-Security-Policy/)
    expect(html).toMatch(/default-src 'self'/)
  })
})
