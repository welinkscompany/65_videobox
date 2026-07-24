import type { Project } from "../api";

export function resolveLastValidProjectId(
  savedProjectId: string | null,
  projects: ReadonlyArray<Pick<Project, "project_id">>,
) {
  return savedProjectId && projects.some((project) => project.project_id === savedProjectId)
    ? savedProjectId
    : null;
}
