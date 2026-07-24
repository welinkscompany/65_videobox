import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Button } from "@/components/ui/button"
import "@/styles/index.css"

describe("UI system", () => {
  it("uses local warm-white tokens without a global preflight reset", () => {
    render(<Button>영상 만들기</Button>)
    expect(screen.getByRole("button", { name: "영상 만들기" })).toHaveAttribute("data-slot", "button")
    expect(document.documentElement.style.getPropertyValue("--vb-canvas")).toBe("")
  })

  it("composes only canonical shell and editor styles", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles/index.css"), "utf8")
    expect(styles).toContain("./product-shell.css")
    expect(styles).toContain("./editor-workbench.css")
    expect(styles).not.toContain("legacy.css")
  })
})
