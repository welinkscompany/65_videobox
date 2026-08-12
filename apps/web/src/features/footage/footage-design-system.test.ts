import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const footageCss = readFileSync(
  resolve(process.cwd(), "src/features/footage/footage.css"),
  "utf8",
)

const LITERAL_COLOR = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/g

describe("footage organizer design-system contract", () => {
  it("keeps screen CSS on semantic color tokens", () => {
    expect(footageCss.match(LITERAL_COLOR) ?? []).toEqual([])
    expect(footageCss).toContain("var(--vb-preview)")
    expect(footageCss).not.toContain("background:#")
  })

  it("uses the semantic surface ring and radius scale", () => {
    expect(footageCss).toContain("var(--vb-surface-ring)")
    expect(footageCss).toContain("var(--radius-")
    expect(footageCss).not.toMatch(/border-radius:\s*[0-9.]+(px|rem)/)
    expect(footageCss).not.toMatch(/border:\s*1px\s+solid\s+var\(--vb-border\)/)
  })

  it("keeps editor transport and timeline actions at the 40px role height", () => {
    expect(footageCss).toMatch(
      /\.vb-footage-transport button,\.vb-footage-timeline__actions button,\.vb-footage-actions button\{[^}]*min-height:40px/,
    )
    expect(footageCss).not.toContain(".vb-footage-transport button{min-width:2.25rem;min-height:32px")
  })

  it("keeps all four panes internally bounded", () => {
    expect(footageCss).toContain(".vb-footage-suggestions,.vb-footage-actions{overflow:auto}")
    expect(footageCss).toContain(".vb-footage-source-scroll")
    expect(footageCss).toContain("overflow:auto")
  })
})
