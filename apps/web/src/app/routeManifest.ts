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

export type NavigationCrumb = { label: string; href?: string };

export type NavigationContext = {
  screenName: string;
  fallbackHref: string;
  crumbs: readonly NavigationCrumb[];
};

export function parseWorkspaceLocation(pathname: string): ParsedWorkspaceLocation | null {
  const match = /^\/projects\/([^/]+)\/([^/]+)$/.exec(pathname);
  if (!match) return null;
  if (!Object.prototype.hasOwnProperty.call(legacyStageAliases, match[2])) return null;
  const resolved = legacyStageAliases[match[2]];
  return { projectId: decodeURIComponent(match[1]), ...resolved };
}

/**
 * 화면이 스스로 URL을 조립하지 않게 현재 위치와, 브라우저 이력이 없을 때 쓸
 * 안전한 이전 목적지를 한 곳에서 정한다. 이력은 실제로 사용자가 온 길을 가장
 * 잘 아니까 라우터가 먼저 쓰고, 이 값은 직접 주소로 들어온 경우의 대체다.
 */
export function resolveNavigationContext({
  pathname,
  projectName,
}: {
  pathname: string;
  projectName?: string;
}): NavigationContext {
  if (pathname === "/library") {
    return {
      screenName: "내 라이브러리",
      fallbackHref: resolveGlobalLocation("projects"),
      crumbs: [{ label: "프로젝트", href: resolveGlobalLocation("projects") }, { label: "내 라이브러리" }],
    };
  }
  if (pathname === "/footage") {
    return {
      screenName: "촬영본 정리",
      fallbackHref: resolveGlobalLocation("library"),
      crumbs: [{ label: "내 라이브러리", href: resolveGlobalLocation("library") }, { label: "촬영본 정리" }],
    };
  }
  if (pathname.startsWith("/settings/")) {
    return {
      screenName: "설정",
      fallbackHref: resolveGlobalLocation("projects"),
      crumbs: [{ label: "프로젝트", href: resolveGlobalLocation("projects") }, { label: "설정" }],
    };
  }

  const parsed = parseWorkspaceLocation(pathname);
  if (parsed) {
    const pathSegments = pathname.split("/");
    const currentSegment = pathSegments[pathSegments.length - 1];
    const screenName = parsed.stage === "plan" ? "이야기"
      : parsed.stage === "assets" ? "재료"
        : parsed.stage === "edit" ? "편집"
          : "확인과 내보내기";
    const fallbackHref = parsed.stage === "plan"
      ? currentSegment === "home" ? resolveGlobalLocation("projects") : resolveWorkspaceLocation(parsed.projectId, "home")
      : parsed.stage === "assets" ? resolveWorkspaceLocation(parsed.projectId, "create")
        : parsed.stage === "edit" ? resolveWorkspaceLocation(parsed.projectId, "media")
          : resolveWorkspaceLocation(parsed.projectId, "editing");
    return {
      screenName,
      fallbackHref,
      crumbs: [
        { label: "프로젝트", href: resolveGlobalLocation("projects") },
        { label: projectName ?? "프로젝트", href: resolveWorkspaceLocation(parsed.projectId, "home") },
        { label: screenName },
      ],
    };
  }

  return {
    screenName: "프로젝트",
    fallbackHref: resolveGlobalLocation("projects"),
    crumbs: [{ label: "프로젝트" }],
  };
}
