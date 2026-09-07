import type { LibraryAsset } from "../../api"

/**
 * Builtin pack assets carry `duration_seconds` at the top level; ingested user
 * assets carry it in `technical_metadata` once probing has run.
 *
 * "길이 확인 중" is only honest while something is actually analysing the asset.
 * Assets ingested before probing existed are ready and simply have no duration,
 * so they say so instead of claiming a check that will never finish.
 */
export function assetDurationLabel(asset: LibraryAsset): string {
  const raw = asset.duration_seconds ?? asset.technical_metadata?.duration_seconds
  if (typeof raw === "number" && Number.isFinite(raw)) return `${Math.round(raw)}초`
  return asset.lifecycle === "processing" ? "길이 확인 중" : "길이 정보 없음"
}
