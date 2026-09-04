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
    expect(footageCss).toContain("min-height:32px; border:1px solid transparent; border-radius:var(--vb-radius-md)")
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

/* 2026-09-04 실측(촬영본 하나를 실제로 분석·묶고 미리보기까지 눌러서 잼):
 * `.vb-footage-sequence__preview-status`("단일 원본 미리보기 준비됨")에 CSS가
 * 하나도 없었다. `<small>`이라 부모(`.vb-footage-sequence`, `--vb-text-xs`=12px)에서
 * 한 번 더 줄어 **10px**로 나왔고 -- 이 화면 척도의 제일 작은 칸보다도 작다 --
 * 색도 `--foreground`(흰색) 그대로였다. 바로 옆 같은 성격의 안내문
 * `.vb-footage-disclaimer`는 `--vb-muted` + `--vb-text-xs`로 돼 있다. 같은 무늬로 맞춘다. */
describe("가상 묶음 미리보기 안내가 척도 밖으로 작아지지 않는다", () => {
  it(".vb-footage-sequence__preview-status가 척도 글자크기와 muted 색을 건다", () => {
    const rule = footageCss.match(/\.vb-footage-sequence__preview-status\s*\{[^}]*\}/)?.[0]
    expect(rule, ".vb-footage-sequence__preview-status 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/font-size:\s*var\(--vb-text-(xs|sm)\)/)
    expect(rule).toMatch(/color:\s*var\(--vb-muted\)/)
  })
})

/* 2026-09-04: 촬영본 한 칸(`.vb-footage-source`)은 shadcn `Button`이라 `h-9`(36px)이
 * 같이 걸리는데, 안에는 그림·파일이름·길이·`자료실에서 보기`가 여러 줄로 들어간다.
 * 실측하니 내용 55px이 상자 36px에 갇혀 잘리고 있었다. 전역 `border-box` 도입
 * 전에도 이미 12px 잘려 있었고(상자 54 / 내용 64) 도입이 그 격차를 21px로
 * 넓혔다. 고정 높이를 풀어야 열두 칸 전부가 안 잘린다. */
describe("촬영본 한 칸이 내용에 맞춰 늘어난다", () => {
  // 한 칸짜리 `.vb-footage-source{height:auto}`로는 안 된다 -- shadcn `Button`이
  // 같이 거는 `.h-9`가 특정도는 같고(0,1,0) 번들에서 더 뒤에 실려 이긴다.
  // 실기계에서 계산값이 그대로 36px인 것을 확인했다. 부모를 앞에 붙여야 이긴다.
  it(".vb-footage-source가 .h-9를 이기는 무게로 고정 높이를 푼다", () => {
    const rule = footageCss.match(/\.vb-footage-source-row\s+\.vb-footage-source\{[^}]*\}/)?.[0]
    expect(rule, "부모를 앞에 붙인 .vb-footage-source 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/height:\s*auto/)
  })
})
