export const workspaceSections = ["home", "create", "timeline", "review", "editing", "settings", "media", "outputs"] as const;

export type WorkspaceSection = (typeof workspaceSections)[number];

export function resolveWorkspaceLocation(projectId: string, section: WorkspaceSection = "home") {
  return `/projects/${encodeURIComponent(projectId)}/${section}`;
}

export function isWorkspaceSection(value: string): value is WorkspaceSection {
  return (workspaceSections as readonly string[]).includes(value);
}

export function parseWorkspaceLocation(pathname: string): { projectId: string; section: WorkspaceSection } | null {
  const match = /^\/projects\/([^/]+)\/([^/]+)$/.exec(pathname);
  if (!match || !isWorkspaceSection(match[2])) return null;
  return { projectId: decodeURIComponent(match[1]), section: match[2] };
}
