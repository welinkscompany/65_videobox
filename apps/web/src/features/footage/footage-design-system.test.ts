import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const footageCss = readFileSync(
  resolve(process.cwd(), "src/features/footage/footage.css"),
  "utf8",
)
const productShellCss = readFileSync(
  resolve(process.cwd(), "src/styles/product-shell.css"),
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

  it("keeps editor transport and timeline actions at the intranet h-8 role height", () => {
    expect(footageCss).toContain(".vb-footage-transport button,.vb-footage-timeline__actions button,.vb-footage-actions button { min-height:32px")
    expect(footageCss).not.toContain(".vb-footage-transport button{min-width:2.25rem;min-height:32px")
  })

  it("keeps all four panes internally bounded", () => {
    expect(footageCss).toContain(".vb-footage-suggestions,.vb-footage-actions{overflow:auto}")
    expect(footageCss).toContain(".vb-footage-source-scroll")
    expect(footageCss).toContain("overflow:auto")
  })

  it("gives the Yujin candidate a bounded semantic surface", () => {
    expect(footageCss).toContain(".vb-footage-yujin-candidate{display:grid")
    expect(footageCss).toContain("box-shadow:0 0 0 1px var(--vb-accent-border)")
    expect(footageCss).toContain("overflow-wrap:anywhere")
  })

  it("uses the intranet control, filled-input, and focus-ring contract", () => {
    expect(productShellCss).toMatch(/\.vb-product-shell \[data-slot=button\] \{ min-height:32px/)
    expect(footageCss).toContain("min-height:32px; border:1px solid transparent; border-radius:var(--radius-2xl)")
    expect(footageCss).toContain("background:color-mix(in srgb,var(--input) 50%,transparent)")
    expect(footageCss).toContain("box-shadow:0 0 0 3px color-mix(in srgb,var(--ring) 30%,transparent)")
  })

  it("keeps catalog content inside the 1280px desktop shell", () => {
    // 폭 상한과 페이지 여백은 **껍데기가 정한다**(2026-08-19). 예전에는 카탈로그가
    // 같은 값을 한 벌 더 걸어서 여백이 두 겹이 됐다 -- 제목이 왼쪽에서 80px,
    // 위에서 91px까지 밀렸다. 상한이 사라진 게 아니라 임자가 하나로 정리된 것이다.
    expect(productShellCss).toMatch(/\.vb-product-content \{[^}]*max-width:1200px/)
    expect(productShellCss).toMatch(/\.vb-catalog \{[^}]*width:100%;\s*box-sizing:border-box;\s*min-width:0;\s*overflow-x:hidden/)
    expect(productShellCss).toMatch(/\.vb-catalog-grid \{ min-width:0/)
    expect(productShellCss).toMatch(/\.vb-catalog-card \{ box-sizing:border-box;\s*min-width:0;\s*overflow-wrap:anywhere/)
  })

  it("uses ring surfaces and token radii for sequence controls", () => {
    expect(footageCss).toContain(".vb-footage-sequence{display:grid")
    expect(footageCss).toContain("box-shadow:0 0 0 1px var(--vb-accent-border)")
    expect(footageCss).toContain("border-radius:var(--radius-lg)")
    expect(footageCss).toMatch(/\.vb-footage-sequence__controls \{ display:flex; flex-wrap:wrap; gap:\.3rem/)
  })
})
