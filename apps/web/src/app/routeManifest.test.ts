import { describe, expect, it } from "vitest";

import { parseWorkspaceLocation, resolveWorkspaceLocation } from "./routeManifest";

describe("workspace route manifest", () => {
  it("maps editing to /editor while retaining the previous address as input-only compatibility", () => {
    expect(resolveWorkspaceLocation("project_a", "editing")).toBe("/projects/project_a/editor");
    expect(parseWorkspaceLocation("/projects/project_a/editor")).toEqual({ projectId: "project_a", section: "editing" });
    expect(parseWorkspaceLocation("/projects/project_a/editing")).toEqual({ projectId: "project_a", section: "editing" });
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
