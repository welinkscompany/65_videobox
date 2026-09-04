import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const shellCss = readFileSync(resolve(process.cwd(), "src/styles/product-shell.css"), "utf8")

/** owner(2026-09-04): "인터페이스 들이 너무 복잡하고 (…) 헷깔려"
 *
 *  첫 화면을 재 보니 **누를 것 112개 중 102개가 카드 안 단추**였다
 *  (카드 34개 × 3개). 캡컷 `최근 프로젝트` 카드는 단추가 **0개**이고 카드를
 *  누르면 열린다.
 *
 *  **길은 없애지 않는다.** 카드의 두 링크는 목적이 다르다 -- 이름은 프로젝트를
 *  여는 문이고, `다음 할 일`은 `/plan`·`/review`로 가는 **유일한 길**이다.
 *  없애면 그 화면에 갈 방법이 사라진다(코드 주석이 그렇게 경고하고 있고,
 *  예전에 한 번 시도했다가 시험 셋이 막았다).
 *
 *  그래서 **소음만 줄인다**: `···`는 캡컷처럼 평소엔 숨고 마우스나 키보드 초점이
 *  왔을 때만 나온다. 키보드로도 닿아야 하므로 `visibility`나 `display`로 지우지
 *  않는다 -- 그러면 탭 순서에서 빠져 손으로만 쓸 수 있는 기능이 된다. */
describe("프로젝트 카드는 조용하다", () => {
  it("`···`는 평소에 안 보인다", () => {
    const rule = shellCss.match(/^\.vb-catalog-card__more\s*\{[^}]*\}/m)?.[0]
    expect(rule, "`···` 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/opacity:\s*0/)
  })

  it("마우스나 키보드 초점이 오면 보인다", () => {
    // 초점 규칙이 없으면 키보드 사용자는 이 기능을 영영 못 본다.
    expect(shellCss).toMatch(/\.vb-catalog-card:hover\s+\.vb-catalog-card__more[^{]*\{[^}]*opacity:\s*1/)
    expect(shellCss).toMatch(/\.vb-catalog-card__more:focus-visible\s*\{[^}]*opacity:\s*1/)
  })

  it("탭 순서에서 빼지 않는다", () => {
    // `display:none`이나 `visibility:hidden`으로 숨기면 초점 자체가 안 간다.
    const rule = shellCss.match(/^\.vb-catalog-card__more\s*\{[^}]*\}/m)?.[0] ?? ""
    expect(rule).not.toMatch(/display:\s*none/)
    expect(rule).not.toMatch(/visibility:\s*hidden/)
  })
})
