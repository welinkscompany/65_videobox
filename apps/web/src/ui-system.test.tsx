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

  it("keeps the legacy dashboard namespace separate from a new primitive", () => {
    const style = document.createElement("style")
    style.textContent = readFileSync(resolve(process.cwd(), "src/styles/legacy.css"), "utf8").split("@scope")[0]
    document.head.append(style)
    render(
      <>
        <div className="vb-legacy"><button className="action-button primary">기존 작업</button></div>
        <Button>새 작업</Button>
      </>,
    )
    const legacy = screen.getByRole("button", { name: "기존 작업" })
    const primitive = screen.getByRole("button", { name: "새 작업" })
    expect(legacy.className).toContain("action-button")
    expect(primitive.className).not.toContain("action-button")
    expect(getComputedStyle(legacy).fontFamily).toContain("Space Grotesk")
    expect(getComputedStyle(primitive).fontFamily).not.toContain("Space Grotesk")
    style.remove()
  })
})
