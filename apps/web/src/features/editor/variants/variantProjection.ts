export type VariantKind = "master" | "horizontal" | "vertical_full" | "vertical_highlight";
export type VariantConflict = Readonly<{ field: string; reason: string }>;
export type ServerOutputVariant = Readonly<{
  variant_id: string;
  kind: Exclude<VariantKind, "master">;
  source_session_id: string;
  source_session_revision: number;
  variant_revision: number;
  overrides: Readonly<{
    crop: Record<string, unknown> | null;
    focal: Record<string, unknown> | null;
    caption: Record<string, unknown> | null;
    safe_area: Record<string, unknown> | null;
    audio: Record<string, unknown> | null;
  }>;
  locks: readonly Readonly<{ field: string; base_master_revision: number }>[];
  conflicts: readonly Readonly<{ field: string; reason: string; base_master_revision: number; current_master_revision: number }>[];
}>;
export type VariantProjection = {
  variantId: string;
  label: string;
  kind: VariantKind;
  aspectRatio: "16:9" | "9:16";
  playheadSec: number;
  durationSec: number;
  safeArea: string;
  crop: string;
  focalPoint: Readonly<{ x: number; y: number }>;
  captionLayout: string;
  lockedFields: readonly string[];
  conflicts: readonly VariantConflict[];
  ownsAudio: boolean;
};

type VariantProjectionInput = Readonly<{
  variantId: string;
  kind: Exclude<VariantKind, "master">;
  source: VariantProjection;
  overrides?: Readonly<{
    crop?: string;
    focalPoint?: Readonly<{ x: number; y: number }>;
    captionLayout?: string;
    safeArea?: string;
  }>;
  lockedFields?: readonly string[];
  conflicts?: readonly VariantConflict[];
}>;

export function projectVariant(input: VariantProjectionInput): VariantProjection {
  const overrides = input.overrides ?? {};
  const vertical = input.kind !== "horizontal";
  return {
    ...input.source,
    variantId: input.variantId,
    label: input.kind === "horizontal" ? "가로" : input.kind === "vertical_highlight" ? "세로 하이라이트" : "세로",
    kind: input.kind,
    aspectRatio: vertical ? "9:16" : "16:9",
    crop: overrides.crop ?? (vertical ? "세로 안전 크롭" : input.source.crop),
    focalPoint: overrides.focalPoint ?? input.source.focalPoint,
    captionLayout: overrides.captionLayout ?? input.source.captionLayout,
    safeArea: overrides.safeArea ?? input.source.safeArea,
    lockedFields: input.lockedFields ?? [],
    conflicts: input.conflicts ?? [],
    ownsAudio: false,
  };
}

function stringOverride(value: Record<string, unknown> | null, key: string): string | undefined {
  const candidate = value?.[key];
  return typeof candidate === "string" && candidate.trim() ? candidate : undefined;
}

function focalOverride(value: Record<string, unknown> | null): Readonly<{ x: number; y: number }> | undefined {
  const x = value?.x;
  const y = value?.y;
  return typeof x === "number" && Number.isFinite(x) && typeof y === "number" && Number.isFinite(y)
    ? { x, y }
    : undefined;
}

export function projectServerVariant(input: Readonly<{ variant: ServerOutputVariant; source: VariantProjection }>): VariantProjection {
  const { variant } = input;
  return projectVariant({
    variantId: variant.variant_id,
    kind: variant.kind,
    source: input.source,
    overrides: {
      crop: stringOverride(variant.overrides.crop, "mode"),
      focalPoint: focalOverride(variant.overrides.focal),
      captionLayout: stringOverride(variant.overrides.caption, "layout"),
      safeArea: stringOverride(variant.overrides.safe_area, "mode"),
    },
    lockedFields: variant.locks.map((lock) => lock.field),
    conflicts: variant.conflicts.map((conflict) => ({ field: conflict.field, reason: conflict.reason })),
  });
}

export function synchronizeVariantPlayhead(
  projections: readonly VariantProjection[],
  playheadSec: number,
): VariantProjection[] {
  const safeSeconds = Number.isFinite(playheadSec) ? Math.max(0, playheadSec) : 0;
  return projections.map((projection) => ({ ...projection, playheadSec: Math.min(safeSeconds, projection.durationSec) }));
}

export function resolveVariantConflict(
  projection: VariantProjection,
  field: string,
  decision: "keep_local" | "rebase_master",
): VariantProjection {
  const conflicts = projection.conflicts.filter((conflict) => conflict.field !== field);
  if (decision === "keep_local") return { ...projection, conflicts };
  return {
    ...projection,
    conflicts,
    lockedFields: projection.lockedFields.filter((lockedField) => lockedField !== field),
  };
}
