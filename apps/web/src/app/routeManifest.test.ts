import { describe, expect, it } from "vitest";

import {
  parseWorkspaceLocation,
  resolveNavigationContext,
  resolveGlobalLocation,
  resolveProjectStage,
  resolveWorkspaceLocation,
} from "./routeManifest";

describe("workspace route manifest", () => {
  it("keeps global destinations separate from project stages", () => {
    expect(resolveGlobalLocation("projects")).toBe("/projects");
    expect(resolveGlobalLocation("library")).toBe("/library");
    expect(resolveGlobalLocation("footage")).toBe("/footage");
    expect(resolveGlobalLocation("settings")).toBe("/settings/general");
    expect(resolveProjectStage("p1", "assets")).toBe("/projects/p1/assets");
  });

  it("maps editing to /editor while retaining the previous address as input-only compatibility", () => {
    expect(resolveWorkspaceLocation("project_a", "editing")).toBe("/projects/project_a/editor");
    expect(parseWorkspaceLocation("/projects/project_a/editor")).toMatchObject({ projectId: "project_a", stage: "edit", legacy: true });
    expect(parseWorkspaceLocation("/projects/project_a/editing")).toMatchObject({ projectId: "project_a", stage: "edit", legacy: true });
  });

  it("maps legacy workspace sections to canonical stages", () => {
    expect(parseWorkspaceLocation("/projects/p1/media")).toMatchObject({ projectId: "p1", stage: "assets", legacy: true });
    expect(parseWorkspaceLocation("/projects/p1/outputs")).toMatchObject({ projectId: "p1", stage: "output", legacy: true });
    expect(parseWorkspaceLocation("/projects/p1/plan")).toMatchObject({ projectId: "p1", stage: "plan", legacy: false });
  });

  it("rejects a project URL without a canonical section", () => {
    expect(parseWorkspaceLocation("/projects/project_a/unknown")).toBeNull();
  });

  it("rejects inherited object keys instead of treating them as route aliases", () => {
    for (const section of ["__proto__", "constructor", "toString"]) {
      expect(parseWorkspaceLocation(`/projects/project_a/${section}`)).toBeNull();
    }
  });

  it("decodes direct project URLs without inventing selected state", () => {
    expect(parseWorkspaceLocation("/projects/project_a/review")).toEqual({
      projectId: "project_a",
      stage: "review",
      legacy: false,
    });
  });
});

describe("navigation context", () => {
  it("gives the library a stable breadcrumb and project-list fallback", () => {
    expect(resolveNavigationContext({ pathname: "/library" })).toEqual({
      screenName: "내 라이브러리",
      fallbackHref: "/projects",
      crumbs: [
        { label: "프로젝트", href: "/projects" },
        { label: "내 라이브러리" },
      ],
    });
  });

  it("keeps a project edit page in its project breadcrumb and returns to materials", () => {
    expect(resolveNavigationContext({ pathname: "/projects/p1/editor", projectName: "첫 영상" })).toEqual({
      screenName: "편집",
      fallbackHref: "/projects/p1/media",
      crumbs: [
        { label: "프로젝트", href: "/projects" },
        { label: "첫 영상", href: "/projects/p1/home" },
        { label: "편집" },
      ],
    });
  });

  it("normalizes legacy project routes before describing them", () => {
    expect(resolveNavigationContext({ pathname: "/projects/p1/outputs", projectName: "첫 영상" })).toMatchObject({
      screenName: "확인과 내보내기",
      fallbackHref: "/projects/p1/editor",
    });
  });
});
