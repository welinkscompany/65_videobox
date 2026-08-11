import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { Dialog, DialogContent, DialogTitle } from "../components/ui/dialog";
import { ProductShell } from "../app/ProductShell";

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: () => ({ matches: false, media: "", onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false }),
  });
});

afterEach(() => cleanup());

describe("desktop visual contracts", () => {
  it("marks the product shell as a bounded desktop surface", () => {
    const { container } = render(
      <ProductShell
        projectId="project-a"
        projects={[{ project_id: "project-a", name: "프로젝트", status: "draft", root_storage_uri: "local://project-a" }]}
        section="home"
        onNavigate={() => undefined}
        onOpenSettings={() => undefined}
      >
        <p>본문</p>
      </ProductShell>,
    );

    expect(container.querySelector("[data-vb-desktop-shell]")).toBeInTheDocument();
  });

  it("marks dialog content with an explicit containment contract and labelled close control", () => {
    render(
      <Dialog open>
        <DialogContent className="vb-dialog-content">
          <DialogTitle>작업 상태</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    expect(document.querySelector(".vb-dialog-content")).toHaveClass("vb-dialog-content");
    expect(screen.getByRole("button", { name: "Close" })).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
  });
});
