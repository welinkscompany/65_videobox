export const workspaceSections = ["home", "create", "timeline", "review", "editing", "settings", "media", "outputs"] as const;

export type WorkspaceSection = (typeof workspaceSections)[number];

export function resolveWorkspaceLocation(projectId: string, section: WorkspaceSection = "home") {
  const canonicalSection = section === "editing" ? "editor" : section;
  return `/projects/${encodeURIComponent(projectId)}/${canonicalSection}`;
}

export function isWorkspaceSection(value: string): value is WorkspaceSection {
  return (workspaceSections as readonly string[]).includes(value);
}

export function parseWorkspaceLocation(pathname: string): { projectId: string; section: WorkspaceSection } | null {
  const match = /^\/projects\/([^/]+)\/([^/]+)$/.exec(pathname);
  if (!match) return null;
  const section = match[2] === "editor" ? "editing" : match[2];
  if (!isWorkspaceSection(section)) return null;
  return { projectId: decodeURIComponent(match[1]), section };
}
