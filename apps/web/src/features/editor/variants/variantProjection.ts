export type VariantKind = "master" | "horizontal" | "vertical_full" | "vertical_highlight";
export type VariantConflict = Readonly<{ field: string; reason: string }>;
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
