import { createContext, useContext } from "react";

import type { Project } from "../api";
import type { WorkspaceSection } from "./routeManifest";

export type ProjectWorkspace = {
  projectId: string;
  section: WorkspaceSection;
  projects: Project[];
};

const ProjectWorkspaceContext = createContext<ProjectWorkspace | null>(null);

export function ProjectWorkspaceProvider({ value, children }: { value: ProjectWorkspace; children: React.ReactNode }) {
  return <ProjectWorkspaceContext.Provider value={value}>{children}</ProjectWorkspaceContext.Provider>;
}

export function useProjectWorkspace() {
  const workspace = useContext(ProjectWorkspaceContext);
  if (!workspace) throw new Error("ProjectWorkspaceProvider is required for a project route");
  return workspace;
}

export function resolveLastValidProjectId(
  savedProjectId: string | null,
  projects: ReadonlyArray<Pick<ProjectWorkspace["projects"][number], "project_id">>,
) {
  return savedProjectId && projects.some((project) => project.project_id === savedProjectId)
    ? savedProjectId
    : null;
}
