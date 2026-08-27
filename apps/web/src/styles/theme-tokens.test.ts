import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync } from "node:fs"
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

  it("never wraps a color token in hsl() -- the tokens are complete colors", () => {
    // `--border` 같은 토큰은 `#EAEAEC` 같은 **완성색**이다. `hsl(var(--border))`는
    // `hsl(#EAEAEC)`가 되어 무효 선언이고, 브라우저는 그 속성을 통째로 버린다.
    // 이렇게 17곳(선언 13줄)이 조용히 죽어 있었다 -- 화면은 뜨지만 그 테두리·색만
    // 사라진다. 두 파일만 지키면 다음 파일에서 또 죽으니 css 전부를 훑는다.
    const sourceRoot = resolve(process.cwd(), "src")
    const cssFiles = (readdirSync(sourceRoot, { recursive: true }) as string[])
      .filter((file) => String(file).endsWith(".css"))
    expect(cssFiles.length).toBeGreaterThan(2)
    for (const file of cssFiles) {
      const css = readFileSync(resolve(sourceRoot, String(file)), "utf8")
      const matches = css.match(/hsl\(\s*var\(/g) ?? []
      expect(matches, `${file} wraps complete color tokens in hsl()`).toEqual([])
    }
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

/** owner(2026-08-27): "위에 페이지 모두다 디자인 톤앤매너, 패키지디자인이 모두 다
 *  달라. 이것도 디자인을 통일해야지"
 *
 *  재 보니 색은 문제가 아니었다 -- `--vb-panel`과 `--card`는 **이미 같은 값**이다
 *  (`#FFFFFF`). 실제로 달라 보이게 만든 것은 **모서리**였다. 네 스타일시트에
 *  값이 **15가지**로 흩어져 있었다(0.25 ~ 1rem). 반지름 토큰은 이미 있었는데
 *  아무도 쓰지 않았다.
 *
 *  여기서 지키는 것은 **한 벌에서만 값을 꺼내 쓴다**이다. 승인된 색은 건드리지
 *  않는다(`docs/decisions/2026-08-05-dashboard-white-orange-direction.ko.md`).
 *  새 모서리 값을 쓰고 싶으면 척도를 늘리기 전에 먼저 물어라 -- 척도가 늘면
 *  다시 15가지가 된다. */
describe("모서리는 한 벌에서만 나온다", () => {
  const RAW_RADIUS = /border-radius:\s*(?!0\b|999|9999)[0-9.]+rem/g;
  const sheets = {
    "product-shell.css": productShellCss,
    "editor-workbench.css": editorWorkbenchCss,
    "library.css": readFileSync(resolve(process.cwd(), "src/features/library/library.css"), "utf8"),
    "footage.css": readFileSync(resolve(process.cwd(), "src/features/footage/footage.css"), "utf8"),
  };

  for (const [name, css] of Object.entries(sheets)) {
    it(`${name}은 모서리를 토큰으로만 정한다`, () => {
      expect(css.match(RAW_RADIUS) ?? []).toEqual([]);
    });
  }

  it("척도는 셋뿐이다 — 늘리기 전에 먼저 묻는다", () => {
    const uiSystem = readFileSync(resolve(process.cwd(), "src/ui-system.css"), "utf8");
    for (const token of ["--vb-radius-sm", "--vb-radius-md", "--vb-radius-lg"]) {
      expect(uiSystem, `${token}가 정의돼 있어야 한다`).toContain(`${token}:`);
    }
    expect(uiSystem.match(/--vb-radius-[a-z]+:/g) ?? []).toHaveLength(3);
  });
});
