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
    expect(footageCss).toContain("var(--vb-radius-")
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
    expect(footageCss).toContain("border-radius:var(--vb-radius-lg)")
    // **갱신 이유(2026-08-27).** 이 줄은 `gap:.3rem`이라는 **날값**을 박아 두고
    // 있었는데, 그것이 바로 owner가 말한 "화면마다 따로 논다"의 원인이었다 --
    // 이 화면만 간격 척도를 안 쓰고 있었다(날값 41개, 토큰 0개).
    // 지키려는 것은 "고리 표면과 토큰 모서리를 쓴다"이지 특정 간격 값이
    // 아니었으므로, 지키는 것은 두고 값만 척도에 맞춘다.
    expect(footageCss).toMatch(/\.vb-footage-sequence__controls \{ display:flex; flex-wrap:wrap; gap: var\(--vb-space-1\)/)
  })
})

/** owner(2026-08-27): "안에 들어 있는 내용과 기능들이 인터페이스가 너무 안좋아서
 *  어떻게 운영을 하고 뭘클릭을 하고, 사용하는지 전혀 가늠이 안되"
 *
 *  화면을 열어 보니 구역 머리말에 **영어 대문자가 그대로** 나오고 있었다 --
 *  `SOURCE · PREVIEW · ACTIONS · SUGGESTIONS · SCENES`. 창작자가 읽을 문구에
 *  개발 용어를 쓰지 않는다는 규정(`development-fast-path.ko.md` §10.13) 위반이고,
 *  무엇을 하는 자리인지 한국어로 말해 주지 않으니 "가늠이 안 된다"는 말이 나온다.
 *
 *  여기서 지키는 것은 **화면에 보이는 글자는 창작자의 말이다**이다. */
describe("촬영본 화면은 창작자의 말로 말한다", () => {
  const sources = [
    "FootageOrganizerPage.tsx",
    "FootageSourceList.tsx",
    "FootagePreview.tsx",
    "FootageSuggestions.tsx",
    "SceneTimeline.tsx",
  ];

  for (const file of sources) {
    it(`${file}의 구역 머리말에 영어가 남아 있지 않다`, () => {
      const source = readFileSync(resolve(process.cwd(), `src/features/footage/${file}`), "utf8");
      // `vb-eyebrow`는 구역 이름을 말하는 자리다. 여기 영어 대문자가 들어가면
      // 화면에 그대로 보인다.
      const englishEyebrows = source.match(/vb-eyebrow">[A-Z][A-Z ]+</g) ?? [];
      expect(englishEyebrows).toEqual([]);
    });
  }
});
