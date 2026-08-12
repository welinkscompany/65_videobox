export const globalDestinations = ["projects", "library", "footage", "settings"] as const;

export type GlobalDestination = (typeof globalDestinations)[number];

export const projectStages = ["plan", "assets", "edit", "review", "output"] as const;

export type ProjectStage = (typeof projectStages)[number];

/**
 * These are the route names owned by the pre-workspace-overhaul shell. Keep
 * them as an input compatibility contract while new navigation uses stages.
 */
export const workspaceSections = ["home", "create", "timeline", "review", "editing", "settings", "media", "outputs"] as const;

export type WorkspaceSection = (typeof workspaceSections)[number];

const legacyStageAliases: Readonly<Record<string, { stage: ProjectStage; legacy: boolean }>> = {
  plan: { stage: "plan", legacy: false },
  assets: { stage: "assets", legacy: false },
  edit: { stage: "edit", legacy: false },
  review: { stage: "review", legacy: false },
  output: { stage: "output", legacy: false },
  home: { stage: "plan", legacy: true },
  create: { stage: "plan", legacy: true },
  media: { stage: "assets", legacy: true },
  editing: { stage: "edit", legacy: true },
  editor: { stage: "edit", legacy: true },
  timeline: { stage: "review", legacy: true },
  outputs: { stage: "output", legacy: true },
};

export function resolveGlobalLocation(destination: GlobalDestination) {
  // Settings currently has a sectioned owner, so keep the global destination
  // useful by resolving it to the existing general settings entry point.
  return destination === "settings" ? "/settings/general" : `/${destination}`;
}

export function resolveProjectStage(projectId: string, stage: ProjectStage) {
  return `/projects/${encodeURIComponent(projectId)}/${stage}`;
}

export function resolveWorkspaceLocation(projectId: string, section: WorkspaceSection = "home") {
  const canonicalSection = section === "editing" ? "editor" : section;
  return `/projects/${encodeURIComponent(projectId)}/${canonicalSection}`;
}

export function isWorkspaceSection(value: string): value is WorkspaceSection {
  return (workspaceSections as readonly string[]).includes(value);
}

export function isProjectStage(value: string): value is ProjectStage {
  return (projectStages as readonly string[]).includes(value);
}

export type ParsedWorkspaceLocation = {
  projectId: string;
  stage: ProjectStage;
  legacy: boolean;
};

export function parseWorkspaceLocation(pathname: string): ParsedWorkspaceLocation | null {
  const match = /^\/projects\/([^/]+)\/([^/]+)$/.exec(pathname);
  if (!match) return null;
  const resolved = legacyStageAliases[match[2]];
  if (!resolved) return null;
  return { projectId: decodeURIComponent(match[1]), ...resolved };
}
