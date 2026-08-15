export type YujinStarterSurface = "plan" | "assets" | "footage" | "edit" | "review" | "output";
export type YujinStarterSelection = "none" | "segment" | "asset" | "proposal" | "variant";

export type YujinStarterContext = Readonly<{
  surface: YujinStarterSurface;
  selection?: YujinStarterSelection;
  blockers?: readonly string[];
  recentUsage?: Readonly<Record<string, number>>;
  includeRelated?: boolean;
}>;

export type YujinStarter = Readonly<{
  id: string;
  label: string;
  surfaces: readonly YujinStarterSurface[];
  selections: readonly YujinStarterSelection[];
  blockers: readonly string[];
}>;

const USAGE_STORAGE_KEY = "videobox.yujin.starter-usage.v1";

const registry: readonly YujinStarter[] = [
  {
    id: "broll-recommendation",
    label: "이 장면에 어울리는 B-roll 추천해 줘",
    surfaces: ["edit"],
    selections: ["none", "segment"],
    blockers: [],
  },
  {
    id: "edit-flow-review",
    label: "현재 편집 흐름 점검해 줘",
    surfaces: ["edit"],
    selections: ["none", "segment"],
    blockers: [],
  },
  {
    id: "caption-tighten",
    label: "자막을 더 간결하게 다듬어 줘",
    surfaces: ["edit"],
    selections: ["none", "segment"],
    blockers: [],
  },
  {
    id: "vertical-cut",
    label: "세로 영상용으로 바꿀 부분 찾아 줘",
    surfaces: ["edit"],
    selections: ["none", "segment"],
    blockers: [],
  },
  {
    id: "review-risk-segments",
    label: "검토할 위험 구간 알려 줘",
    surfaces: ["edit", "review"],
    selections: ["segment", "proposal", "none"],
    blockers: [],
  },
  {
    id: "review-approval-check",
    label: "이 추천을 승인하기 전에 확인할 점 알려 줘",
    surfaces: ["edit", "review"],
    selections: ["proposal", "none"],
    blockers: [],
  },
  {
    id: "output-duration-check",
    label: "이 편집본이 목표 길이에 맞는지 확인해 줘",
    surfaces: ["edit", "output"],
    selections: ["segment", "proposal", "none"],
    blockers: [],
  },
  {
    id: "output-vertical-check",
    label: "최종본의 세로 화면 구성을 점검해 줘",
    surfaces: ["edit", "output"],
    selections: ["proposal", "variant", "none"],
    blockers: [],
  },
  {
    id: "plan-format-recommendation",
    label: "이번 촬영으로 만들 만한 영상 형식 추천해 줘",
    surfaces: ["plan"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "plan-scene-selection",
    label: "이번 촬영에서 쓸 장면을 골라 줘",
    surfaces: ["plan"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "plan-target-duration",
    label: "목표 길이에 맞춰 구성해 줘",
    surfaces: ["plan", "output"],
    selections: ["none", "proposal"],
    blockers: [],
  },
  {
    id: "plan-vertical-scenes",
    label: "세로 영상으로 만들 만한 장면 알려 줘",
    surfaces: ["plan", "output"],
    selections: ["none", "proposal"],
    blockers: [],
  },
  {
    id: "footage-split-scenes",
    label: "장면 변화로 나누기",
    surfaces: ["footage"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "footage-select-process",
    label: "출근 과정만 고르기",
    surfaces: ["footage"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "footage-exclude-shaky",
    label: "흔들린 구간 찾기",
    surfaces: ["footage"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "footage-combine-similar",
    label: "짧은 영상 묶기",
    surfaces: ["footage"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "footage-select-vertical",
    label: "세로 장면 고르기",
    surfaces: ["footage"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "footage-target-duration",
    label: "30초 묶음 만들기",
    surfaces: ["footage"],
    selections: ["none"],
    blockers: [],
  },
  {
    id: "assets-missing-broll",
    label: "부족한 B-roll 자산을 찾아 줘",
    surfaces: ["assets"],
    selections: ["asset", "none"],
    blockers: ["needs_assets"],
  },
  {
    id: "assets-organize-sources",
    label: "이 프로젝트의 자산을 용도별로 정리해 줘",
    surfaces: ["assets"],
    selections: ["asset", "none"],
    blockers: [],
  },
];

export function getYujinStarters(context: YujinStarterContext): readonly YujinStarter[] {
  const selection = context.selection ?? "none";
  const blockers = new Set(context.blockers ?? []);
  const recentUsage = context.recentUsage ?? {};

  return registry
    .filter((starter) => starter.surfaces.includes(context.surface))
    .filter((starter) => context.includeRelated
      || context.surface !== "edit"
      || !starter.surfaces.some((surface) => surface === "review" || surface === "output"))
    .filter((starter) => starter.selections.includes(selection))
    .filter((starter) => starter.blockers.length === 0 || starter.blockers.some((blocker) => blockers.has(blocker)))
    .map((starter, index) => ({
      starter,
      index,
      usage: finiteUsage(recentUsage[starter.id]),
    }))
    .sort((left, right) => right.usage - left.usage || left.index - right.index)
    .map(({ starter }) => starter);
}

export function readYujinStarterUsage(storage?: Storage): Readonly<Record<string, number>> {
  const target = storage ?? defaultStorage();
  if (!target) return {};
  try {
    const parsed: unknown = JSON.parse(target.getItem(USAGE_STORAGE_KEY) ?? "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => Number.isFinite(value) && value >= 0),
    ) as Readonly<Record<string, number>>;
  } catch {
    return {};
  }
}

export function recordYujinStarterUse(starterId: string, storage?: Storage): void {
  const target = storage ?? defaultStorage();
  if (!target || !registry.some((starter) => starter.id === starterId)) return;
  const usage = readYujinStarterUsage(target);
  try {
    target.setItem(USAGE_STORAGE_KEY, JSON.stringify({
      ...usage,
      [starterId]: finiteUsage(usage[starterId]) + 1,
    }));
  } catch {
    // Usage promotion is optional; a denied or full browser store must not
    // block a starter from filling the composer.
  }
}

function finiteUsage(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

function defaultStorage(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}
