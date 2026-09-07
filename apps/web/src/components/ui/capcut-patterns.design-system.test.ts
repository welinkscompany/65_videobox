import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

/** `theme-tokens.test.ts`가 지키는 네 스타일시트에 이 새 파일은 안 들어 있다.
 *  같은 규율을 여기서 스스로 지킨다 -- 안 그러면 다음 사람이 이 파일에서
 *  다시 자기 숫자를 고르고, 척도가 또 갈린다. */
const source = readFileSync(
  resolve(process.cwd(), "src/components/ui/capcut-patterns.css"),
  "utf8",
)
// 주석에는 캡컷 실측값과 선택자가 그대로 적혀 있다(왜 그 값인지 남기려고).
// 실제로 브라우저가 읽는 것만 재려면 주석을 먼저 걷어내야 한다.
const css = source.replace(/\/\*[\s\S]*?\*\//g, "")

describe("공용 부품 스타일시트는 척도에서만 값을 꺼낸다", () => {
  it("색을 직접 적지 않는다", () => {
    // 팔레트는 owner 승인 대상이다(`CLAUDE.md` §6). `var(--x)`와
    // `color-mix(in srgb, var(--x) 75%, transparent)`는 날색이 없어 안 걸린다.
    const HARDCODED_COLOR = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/g
    expect(css.match(HARDCODED_COLOR) ?? []).toEqual([])
  })

  it("간격을 척도에서 꺼낸다", () => {
    const RAW_SPACE = /(?:gap|padding|margin)[a-z-]*:\s*(?!0\b)[0-9.]+rem/g
    expect(css.match(RAW_SPACE) ?? []).toEqual([])
  })

  it("글자 크기를 척도에서 꺼낸다", () => {
    const RAW_TYPE = /font-size:\s*[0-9.]+(?:rem|px)/g
    expect(css.match(RAW_TYPE) ?? []).toEqual([])
  })

  it("모서리를 척도에서 꺼낸다 — 알약(999px)만 예외다", () => {
    const RAW_RADIUS = /border-radius:\s*(?!0\b|999px|9999px)[0-9.]+(?:rem|px)/g
    expect(css.match(RAW_RADIUS) ?? []).toEqual([])
  })

  it("완성색 토큰을 hsl()로 감싸지 않는다", () => {
    expect(css.match(/hsl\(\s*var\(/g) ?? []).toEqual([])
  })

  it("단추 높이 32px를 새로 만들지 않는다", () => {
    // `product-shell.css`가 `[data-slot=button]`에 32px를 못박아 놨다
    // (캡컷 실측, 2026-09-04). 여기서 또 적으면 값이 두 벌이 된다.
    expect(css).not.toMatch(/height:\s*32px/)
    expect(css).not.toContain("data-slot=button")
  })

  it("여기서 쓰는 px 높이는 캡컷 실측 컨트롤 높이뿐이다", () => {
    // 검색 34, 칩 28, 숫자칸 30, `▸` 24. 새 값이 늘면 여기서 걸린다.
    const heights = new Set(
      (css.match(/(?:^|[^-a-z])height:\s*(\d+)px/g) ?? []).map((match) =>
        match.replace(/\D/g, ""),
      ),
    )
    expect([...heights].sort()).toEqual(["24", "28", "30", "34"])
  })
})
