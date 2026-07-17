import { describe, expect, it } from "vitest";

import { parseWorkspaceLocation, resolveWorkspaceLocation } from "./routeManifest";

describe("workspace route manifest", () => {
  it("maps a project and section to its canonical URL", () => {
    expect(resolveWorkspaceLocation("project_a", "editing")).toBe("/projects/project_a/editing");
  });

  it("rejects a project URL without a canonical section", () => {
    expect(parseWorkspaceLocation("/projects/project_a/unknown")).toBeNull();
  });

  it("decodes direct project URLs without inventing selected state", () => {
    expect(parseWorkspaceLocation("/projects/project_a/review")).toEqual({
      projectId: "project_a",
      section: "review",
    });
  });
});
