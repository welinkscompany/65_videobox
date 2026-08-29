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

/**
 * 단계마다 **실제로 내보내는 주소**다. 주소는 사람이 북마크하고 되돌아오는
 * 계약이라 이번 정리에서 바꾸지 않았다 -- 바꾸는 것은 코드가 쓰는 말이지
 * 주소가 아니다. 새 이름(`/plan`·`/assets`·`/edit`·`/output`)은 계속 **들어오는**
 * 주소로 읽힌다(`legacyStageAliases`).
 */
const stageAddresses: Readonly<Record<ProjectStage, string>> = {
  plan: "create",
  assets: "media",
  edit: "editor",
  review: "review",
  output: "outputs",
};

/** 우리 코드가 프로젝트 화면 링크를 만들 때 쓰는 **하나뿐인** 함수다. */
export function resolveProjectStage(projectId: string, stage: ProjectStage) {
  return `/projects/${encodeURIComponent(projectId)}/${stageAddresses[stage]}`;
}

/**
 * 껍데기(`ProductShell`/`TopBar`)와 `EditorWorkbenchRoute`는 아직 옛 이름으로
 * 말한다. 그 경계에서만 쓰는 어댑터다 -- **새 코드는 `resolveProjectStage`를 쓴다.**
 * `home`은 단계가 아니라 프로젝트 첫 화면이라 여기에만 있다.
 */
export function resolveWorkspaceLocation(projectId: string, section: WorkspaceSection) {
  const canonicalSection = section === "editing" ? "editor" : section;
  return `/projects/${encodeURIComponent(projectId)}/${canonicalSection}`;
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
      screenName: "미디어",
      fallbackHref: resolveGlobalLocation("projects"),
      crumbs: [{ label: "프로젝트", href: resolveGlobalLocation("projects") }, { label: "미디어" }],
    };
  }
  if (pathname === "/footage") {
    return {
      screenName: "촬영본 정리",
      fallbackHref: resolveGlobalLocation("library"),
      crumbs: [{ label: "미디어", href: resolveGlobalLocation("library") }, { label: "촬영본 정리" }],
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
      : parsed.stage === "assets" ? "미디어"
        : parsed.stage === "edit" ? "편집"
          : "확인과 내보내기";
    // 돌아갈 곳은 **한 단계 앞**이다. 앞 단계를 새 이름으로 적어야 이 표가
    // 무엇을 말하는지 읽힌다 -- 주소는 `resolveProjectStage`가 정한다.
    const fallbackHref = parsed.stage === "plan"
      ? currentSegment === "home" ? resolveGlobalLocation("projects") : resolveWorkspaceLocation(parsed.projectId, "home")
      : parsed.stage === "assets" ? resolveProjectStage(parsed.projectId, "plan")
        : parsed.stage === "edit" ? resolveProjectStage(parsed.projectId, "assets")
          : resolveProjectStage(parsed.projectId, "edit");
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
