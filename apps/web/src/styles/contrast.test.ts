import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const uiSystemCss = readFileSync(resolve(process.cwd(), "src/ui-system.css"), "utf8")

function readToken(name: string): string {
  const match = uiSystemCss.match(new RegExp(`${name}:\\s*(#[0-9A-Fa-f]{6})`))
  if (!match) throw new Error(`token ${name} not found in ui-system.css`)
  return match[1]
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(1 + i, 3 + i), 16) / 255)
  const linear = (channel: number) =>
    channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  const [lr, lg, lb] = [r, g, b].map(linear)
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb
}

function contrastRatio(hexA: string, hexB: string): number {
  const lumA = relativeLuminance(hexA)
  const lumB = relativeLuminance(hexB)
  const lighter = Math.max(lumA, lumB)
  const darker = Math.min(lumA, lumB)
  return (lighter + 0.05) / (darker + 0.05)
}

// docs/decisions/2026-08-05-dashboard-white-orange-direction.ko.md
const APPROVED = {
  canvas: "#FAFAFA",
  panel: "#FFFFFF",
  border: "#EAEAEC",
  borderStrong: "#DCDCE0",
  text: "#1C1C1E",
  muted: "#6E6E73",
  faint: "#727279",
  accent: "#C2410C",
  accentBg: "#FFF1E7",
  accentBorder: "#F5C9AC",
  preview: "#18181B",
  success: "#15803D",
  successBg: "#ECFDF3",
}

describe("approved white-orange palette contrast", () => {
  it("only uses hex values recorded in the approval doc (no invented values)", () => {
    expect(readToken("--vb-canvas")).toBe(APPROVED.canvas)
    expect(readToken("--vb-panel")).toBe(APPROVED.panel)
    expect(readToken("--vb-border")).toBe(APPROVED.border)
    expect(readToken("--vb-text")).toBe(APPROVED.text)
    expect(readToken("--vb-muted")).toBe(APPROVED.muted)
    expect(readToken("--vb-accent")).toBe(APPROVED.accent)
    expect(readToken("--vb-preview")).toBe(APPROVED.preview)
  })

  it("body text on panel clears 4.5:1", () => {
    expect(contrastRatio(APPROVED.text, APPROVED.panel)).toBeGreaterThanOrEqual(4.5)
  })

  it("secondary (muted) text on panel clears 4.5:1", () => {
    expect(contrastRatio(APPROVED.muted, APPROVED.panel)).toBeGreaterThanOrEqual(4.5)
  })

  it("faint text on panel clears 4.5:1", () => {
    expect(contrastRatio(APPROVED.faint, APPROVED.panel)).toBeGreaterThanOrEqual(4.5)
  })

  it("accent text/focus colour on panel clears 3:1 (non-text) and 4.5:1 (as text)", () => {
    const ratio = contrastRatio(APPROVED.accent, APPROVED.panel)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it("success state text on its own background clears 4.5:1", () => {
    expect(contrastRatio(APPROVED.success, APPROVED.successBg)).toBeGreaterThanOrEqual(4.5)
  })
})
