import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const productShellCss = readFileSync(
  resolve(process.cwd(), "src/styles/product-shell.css"),
  "utf8",
)
const editorWorkbenchCss = readFileSync(
  resolve(process.cwd(), "src/styles/editor-workbench.css"),
  "utf8",
)

// Matches a literal color: 3/4/6/8-digit hex, or rgb()/rgba() with numeric
// channels. `var(--x)` and `color-mix(in srgb, var(--x) 4%, transparent)`
// do not match because they have no bare hex/rgb() token of their own.
const HARDCODED_COLOR = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/g

describe("shell theme tokens", () => {
  it("has no hardcoded colors left in product-shell.css", () => {
    const matches = productShellCss.match(HARDCODED_COLOR) ?? []
    expect(matches).toEqual([])
  })

  it("drives the default button background from --primary", () => {
    const defaultButtonRule = productShellCss.match(
      /\[data-variant="default"\]\s*\{[^}]*\}/,
    )?.[0]
    expect(defaultButtonRule).toBeDefined()
    expect(defaultButtonRule).toContain("background:var(--primary)")
  })

  it("drives the default button text from --primary-foreground", () => {
    const defaultButtonRule = productShellCss.match(
      /\[data-variant="default"\]\s*\{[^}]*\}/,
    )?.[0]
    expect(defaultButtonRule).toContain("color:var(--primary-foreground)")
  })

  it("has no hardcoded colors left in the preview shell of editor-workbench.css", () => {
    const previewShellRule = editorWorkbenchCss.match(
      /\.vb-preview-stage__media-shell\s*\{[^}]*\}/,
    )?.[0]
    expect(previewShellRule).toBeDefined()
    const matches = previewShellRule?.match(HARDCODED_COLOR) ?? []
    expect(matches).toEqual([])
    expect(previewShellRule).toContain("var(--vb-preview)")
  })
})
