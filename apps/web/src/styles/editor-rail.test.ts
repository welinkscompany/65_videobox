import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8")
const jsx = readFileSync(resolve(process.cwd(), "src/features/editor/workbench/EditorWorkbench.tsx"), "utf8")

/** 계획서 3단계 — 편집기 골격을 캡컷의 **세로 아이콘 띠**로 바꾼다.
 *
 *  캡컷 실측(2026-09-04): 왼쪽 띠 폭 72px, 항목 62px 간격, 아이콘 + 10px 라벨.
 *  패널은 그 옆 293px이고, 고른 띠 항목의 내용만 보여 준다.
 *
 *  우리는 패널 탭이 **위쪽 도구줄에 가로로** 있었다(2026-08-30 결정). 가로 탭은
 *  가로 폭을 쓰는데 편집기에서 모자란 건 **세로**다 -- 그래서 패널 내용이
 *  보이는 높이의 2.42배로 쌓여 스크롤이 났다. 이동을 세로로 옮기면 패널 높이가
 *  통째로 살아난다. owner가 "스크롤 내리지 말고 탭으로 정리하라"고 한 것의
 *  구조적 해답이 이것이다. */
describe("편집기 왼쪽 이동은 세로 띠다", () => {
  it("세로 띠가 본문 안에 있다 — 도구줄이 아니라", () => {
    // 도구줄에 있으면 가로로 눕고, 패널 높이를 못 살린다.
    expect(jsx).toContain("vb-editor-workbench__rail")
    const toolbarStart = jsx.indexOf("vb-editor-workbench__toolbar")
    const bodyStart = jsx.indexOf("vb-editor-workbench__body")
    const railAt = jsx.indexOf("vb-editor-workbench__rail")
    expect(bodyStart, "본문을 못 찾았다").toBeGreaterThan(-1)
    expect(railAt, "세로 띠가 본문보다 앞에 있다 — 도구줄에 남아 있는 것이다").toBeGreaterThan(bodyStart)
    expect(toolbarStart).toBeLessThan(bodyStart)
  })

  it("옛 가로 탭 묶음은 사라졌다", () => {
    // 둘 다 남으면 같은 일을 하는 자리가 두 곳이 된다.
    expect(jsx).not.toContain("vb-editor-workbench__panes")
  })

  it("띠 폭이 캡컷과 같은 72px다", () => {
    const rule = css.match(/\.vb-editor-workbench__rail\s*\{[^}]*\}/)?.[0]
    expect(rule, "세로 띠 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/width:\s*72px/)
    expect(rule).toMatch(/flex-direction:\s*column/)
  })

  it("띠 라벨이 척도의 제일 작은 칸(10px)이다", () => {
    const rule = css.match(/\.vb-editor-workbench__rail-label\s*\{[^}]*\}/)?.[0]
    expect(rule, "띠 라벨 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/font-size:\s*var\(--vb-text-xs\)/)
  })

  it("본문이 가로 배치라 띠와 패널이 나란히 선다", () => {
    const rule = css.match(/\.vb-editor-workbench__body\s*\{[^}]*\}/)?.[0]
    expect(rule, "본문 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/display:\s*flex/)
  })
})
