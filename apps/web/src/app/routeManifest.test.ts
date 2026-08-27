import { describe, expect, it } from "vitest";

import {
  parseWorkspaceLocation,
  projectStages,
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
    expect(resolveProjectStage("p1", "assets")).toBe("/projects/p1/media");
  });

  /** 링크를 만드는 곳은 하나여야 한다. 껍데기(`ProductShell`/`TopBar`)는 아직 옛
   *  이름으로 말하므로 `resolveWorkspaceLocation`이 남아 있는데, **두 함수가 같은
   *  단계에 다른 주소를 내면** 같은 화면으로 가는 링크가 두 벌이 된다. */
  it("emits one address per stage — the same one the shell's legacy names resolve to", () => {
    expect(resolveProjectStage("p1", "plan")).toBe(resolveWorkspaceLocation("p1", "create"));
    expect(resolveProjectStage("p1", "assets")).toBe(resolveWorkspaceLocation("p1", "media"));
    expect(resolveProjectStage("p1", "edit")).toBe(resolveWorkspaceLocation("p1", "editing"));
    expect(resolveProjectStage("p1", "review")).toBe(resolveWorkspaceLocation("p1", "review"));
    expect(resolveProjectStage("p1", "output")).toBe(resolveWorkspaceLocation("p1", "outputs"));
  });

  /** 내보내는 주소를 옛 이름으로 고정해도, 새 이름으로 **들어오는** 주소는 계속
   *  읽혀야 한다. 위 줄이 `/projects/p1/assets`를 더 이상 만들지 않게 되었으므로
   *  그 입력 호환을 여기서 따로 지킨다. */
  it("keeps every canonical stage name readable as an incoming address", () => {
    for (const stage of projectStages) {
      expect(parseWorkspaceLocation(`/projects/p1/${stage}`)).toMatchObject({ projectId: "p1", stage });
    }
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
