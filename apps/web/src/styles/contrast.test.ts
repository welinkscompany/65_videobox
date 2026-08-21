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
    expect(readToken("--vb-border-strong")).toBe(APPROVED.borderStrong)
    expect(readToken("--vb-faint")).toBe(APPROVED.faint)
    expect(readToken("--vb-accent-bg")).toBe(APPROVED.accentBg)
    expect(readToken("--vb-accent-border")).toBe(APPROVED.accentBorder)
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

  it("accent text/focus colour on panel clears 3:1 (non-text) and 4.5:1 (as text)", () => {
    const ratio = contrastRatio(APPROVED.accent, APPROVED.panel)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it("success state text on its own background clears 4.5:1", () => {
    expect(contrastRatio(APPROVED.success, APPROVED.successBg)).toBeGreaterThanOrEqual(4.5)
  })
})

// docs/decisions/2026-08-20-editor-dark-surface.ko.md
//
// **편집 화면만** 어둡다. 나머지 화면은 위의 흰 팔레트 그대로다. 그래서 어두운
// 값은 `:root`가 아니라 편집 작업판 뿌리에만 얹는다 -- `readToken`이 파일에서
// 처음 만나는 값을 읽으므로 위 검사들은 그대로 흰 값을 본다.
const EDITOR_SURFACE = ".vb-editor-workbench"

function readScopedToken(selector: string, name: string): string {
  // 정규식을 쓰지 않는다 -- 이 파일을 셸로 만들다 역슬래시가 먹혀서 패턴이
  // 조용히 다른 것이 된 적이 있다. 자르는 일에 정규식이 꼭 필요하지도 않다.
  const start = uiSystemCss.indexOf(selector + " {")
  if (start < 0) throw new Error(`${selector} 블록이 ui-system.css에 없다`)
  const block = uiSystemCss.slice(start, uiSystemCss.indexOf("}", start))
  const at = block.indexOf(name + ":")
  if (at < 0) throw new Error(`${selector} 안에 ${name}이 없다`)
  const line = block.slice(at, block.indexOf(";", at))
  return line.slice(line.indexOf(":") + 1).replace(";", "").trim()
}

describe("편집 화면도 흰 톤이다 — owner 결정 2026-08-21", () => {
  // 2026-08-20에 편집 화면만 어둡게 했다가 owner가 써 보고 되돌렸다
  // (`docs/decisions/2026-08-21-editor-back-to-light.ko.md`).
  //
  // 되돌린 방식이 중요하다. 어두운 값을 흰 값으로 **다시 칠한** 것이 아니라
  // 편집 화면 전용 블록을 **없앴다.** 그래야 편집 화면이 승인된 팔레트를 다른
  // 화면과 같은 한 벌로 쓴다 -- 색 값이 두 벌이 되면 한쪽이 조용히 낡는다.

  it("편집 화면 전용 색 블록이 남아 있지 않다", () => {
    expect(uiSystemCss).not.toContain('[data-shell-section="editing"] {')
    expect(uiSystemCss).not.toContain(".vb-editor-workbench {")
    // 어두운 값 자체가 파일에 남아 있으면 안 된다. 남겨 두면 다음 사람이
    // "쓰는 데가 있나" 하고 되살린다.
    for (const dead of ["#141416", "#1C1C1F", "#E8613A", "#2A1710", "#A9A9B2"]) {
      expect(uiSystemCss).not.toContain(dead)
    }
  })

  it("편집 화면도 승인된 밝은 팔레트를 그대로 쓴다", () => {
    expect(readToken("--vb-canvas")).toBe(APPROVED.canvas)
    expect(readToken("--vb-panel")).toBe(APPROVED.panel)
    expect(readToken("--vb-accent")).toBe(APPROVED.accent)
  })

  it("미리보기 무대는 그대로 어둡다", () => {
    // 이 값은 2026-08-05 승인표에 있던 것이고 이번 되돌림과 무관하다.
    // 영상을 보는 자리라 어두운 편이 맞다.
    expect(readToken("--vb-preview")).toBe(APPROVED.preview)
  })
})
