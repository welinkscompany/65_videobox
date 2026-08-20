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

const DARK = {
  canvas: "#141416",
  panel: "#1C1C1F",
  text: "#F2F2F4",
  muted: "#A9A9B2",
  faint: "#94949E",
  accent: "#E8613A",
  accentBg: "#2A1710",
  success: "#4ADE80",
  successBg: "#10291B",
}

describe("어두운 편집 표면", () => {
  it("어두운 값은 편집 작업판 안에서만 정의된다", () => {
    for (const [token, expected] of [
      ["--vb-canvas", DARK.canvas], ["--vb-panel", DARK.panel], ["--vb-text", DARK.text],
      ["--vb-muted", DARK.muted], ["--vb-faint", DARK.faint], ["--vb-accent", DARK.accent],
    ] as const) {
      expect(readScopedToken(EDITOR_SURFACE, token)).toBe(expected)
      // 밖은 그대로여야 한다. 여기가 깨지면 편집기만 어둡게 한 게 아니다.
      expect(readToken(token)).not.toBe(expected)
    }
  })

  it("어두운 값은 편집 구간에만 걸린다", () => {
    // 편집판만 어둡게 하면 흰 껍데기가 검은 편집판을 액자처럼 감싼다. 승인 문구는
    // `편집 화면만 어둡게`였고, 편집 화면에는 위 띠와 왼쪽 줄도 들어간다.
    expect(uiSystemCss).toContain('.vb-product-shell[data-shell-section="editing"]')
    // 구간을 안 가리고 껍데기 전체를 어둡게 하면 대시보드까지 따라 어두워진다.
    expect(uiSystemCss).not.toContain(".vb-product-shell {")
  })

  it("본문·보조·희미한 글자가 어두운 패널에서 4.5:1을 넘는다", () => {
    // 어둡게 만들면서 읽기 어려워지면 고친 게 아니다 -- 승인 기록이 못박은 조건.
    expect(contrastRatio(DARK.text, DARK.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(DARK.muted, DARK.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(DARK.faint, DARK.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(DARK.text, DARK.canvas)).toBeGreaterThanOrEqual(4.5)
  })

  it("강조색은 어두운 바탕에서 글자로 읽힌다", () => {
    // 실측: 흰 배경용 `#C2410C`는 어두운 패널에서 3.28로 **기준 미달**이다.
    // 같은 색을 그대로 옮기면 오렌지가 글자로 안 읽힌다. 색조는 지키고 밝기만 올린다.
    expect(contrastRatio(APPROVED.accent, DARK.panel)).toBeLessThan(4.5)
    expect(contrastRatio(DARK.accent, DARK.panel)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(DARK.accent, DARK.accentBg)).toBeGreaterThanOrEqual(4.5)
  })

  it("채운 단추는 흰 글자를 얹은 원래 오렌지 그대로다", () => {
    // 단추 배경으로는 `#C2410C`가 흰 글자에서 5.18로 통과한다. 밝은 색조로
    // 바꾸면 오히려 흰 글자가 3.39로 떨어진다 -- 여기는 건드리지 않는다.
    expect(readScopedToken(EDITOR_SURFACE, "--primary")).toBe(APPROVED.accent)
    expect(contrastRatio("#FFFFFF", APPROVED.accent)).toBeGreaterThanOrEqual(4.5)
  })

  it("성공 상태도 어두운 바탕에서 읽힌다", () => {
    expect(contrastRatio(DARK.success, DARK.successBg)).toBeGreaterThanOrEqual(4.5)
  })
})
