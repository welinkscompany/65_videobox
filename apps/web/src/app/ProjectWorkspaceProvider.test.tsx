import { describe, expect, it } from "vitest";

import { resolveLastValidProjectId } from "./ProjectWorkspaceProvider";

describe("route-owned project selection", () => {
  it("uses a saved project only when it remains in the loaded catalog", () => {
    expect(resolveLastValidProjectId("project_b", [
      { project_id: "project_a" },
      { project_id: "project_b" },
    ])).toBe("project_b");
    expect(resolveLastValidProjectId("project_removed", [{ project_id: "project_a" }])).toBeNull();
  });
});
