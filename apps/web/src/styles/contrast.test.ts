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

// docs/decisions/2026-08-29-capcut-full-structure-and-dark-theme.ko.md
const APPROVED = {
  canvas: "#0F0F11",
  panel: "#18181B",
  panelAlt: "#202024",
  border: "#2E2E33",
  borderStrong: "#3D3D44",
  text: "#F2F2F3",
  muted: "#A3A3AC",
  faint: "#8A8A93",
  accent: "#EA580C",
  accentBg: "#3A1F0F",
  accentBorder: "#7A3D18",
  preview: "#0B0B0C",
  success: "#4ADE80",
  successBg: "#0F2A18",
}

describe("approved dark palette contrast", () => {
  it("only uses hex values recorded in the approval doc (no invented values)", () => {
    expect(readToken("--vb-canvas")).toBe(APPROVED.canvas)
    expect(readToken("--vb-panel")).toBe(APPROVED.panel)
    expect(readToken("--vb-panel-alt")).toBe(APPROVED.panelAlt)
    expect(readToken("--vb-border")).toBe(APPROVED.border)
    expect(readToken("--vb-border-strong")).toBe(APPROVED.borderStrong)
    expect(readToken("--vb-text")).toBe(APPROVED.text)
    expect(readToken("--vb-muted")).toBe(APPROVED.muted)
    expect(readToken("--vb-faint")).toBe(APPROVED.faint)
    expect(readToken("--vb-accent")).toBe(APPROVED.accent)
    expect(readToken("--vb-accent-bg")).toBe(APPROVED.accentBg)
    expect(readToken("--vb-accent-border")).toBe(APPROVED.accentBorder)
    expect(readToken("--vb-preview")).toBe(APPROVED.preview)
    expect(readToken("--vb-success")).toBe(APPROVED.success)
    expect(readToken("--vb-success-bg")).toBe(APPROVED.successBg)
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

  it("accent text/focus colour on panel clears 4.5:1", () => {
    const ratio = contrastRatio(APPROVED.accent, APPROVED.panel)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it("success state text on its own background clears 4.5:1", () => {
    expect(contrastRatio(APPROVED.success, APPROVED.successBg)).toBeGreaterThanOrEqual(4.5)
  })
})

// docs/decisions/2026-08-29-capcut-full-structure-and-dark-theme.ko.md
//
// 이전엔 편집 화면만 어두웠다가(2026-08-20) owner가 되돌렸다(2026-08-21). 이번
// 결정은 그 범위를 넘어 **`:root` 팔레트 자체**를 다크로 바꿨다 -- 화면마다
// 다른 벌을 쓰지 않는다는 원칙(2026-08-21이 지킨 것)은 그대로 유지한 채, 그
// 한 벌의 값 자체를 다크로 바꾼 것이다.
describe("전체 화면이 다크다 — owner 결정 2026-08-29", () => {
  it("편집 화면 전용 색 블록을 따로 두지 않는다", () => {
    // 두 벌을 두면 한쪽이 조용히 낡는다는 교훈(2026-08-21)이 여전히 적용된다.
    expect(uiSystemCss).not.toContain('[data-shell-section="editing"] {')
    expect(uiSystemCss).not.toContain(".vb-editor-workbench {")
  })

  it("옛 흰 팔레트 값이 :root에 남아 있지 않다", () => {
    for (const stale of [
      "--vb-canvas: #FAFAFA",
      "--vb-panel: #FFFFFF",
      "--vb-accent: #C2410C",
      "--vb-text: #1C1C1E",
    ]) {
      expect(uiSystemCss).not.toContain(stale)
    }
  })

  it("미리보기 무대는 패널보다 한 단계 더 어둡다", () => {
    const previewLum = relativeLuminance(APPROVED.preview)
    const panelLum = relativeLuminance(APPROVED.panel)
    expect(previewLum).toBeLessThan(panelLum)
  })
})
