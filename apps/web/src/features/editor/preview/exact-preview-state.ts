export type ExactPreviewInput = Readonly<{
  status: "current" | "succeeded" | "pending" | "running" | "failed" | "stale" | "unavailable";
  url?: string | null;
  artifactRevision?: number | null;
  timelineStartSec?: number | null;
  timelineEndSec?: number | null;
}>;

export type ExactPreviewState =
  | Readonly<{ kind: "current"; label: "편집본 미리보기"; copy: string; action: "none"; url: string; timelineRange: { startSec: number; endSec: number } }>
  | Readonly<{ kind: "pending" | "running" | "failed" | "stale" | "unavailable"; label: "편집본 미리보기"; copy: string; action: "refresh" }>;

const recoveryCopy: Record<Exclude<ExactPreviewState["kind"], "current">, string> = {
  pending: "미리보기를 준비하고 있어요.",
  running: "편집본 미리보기를 만드는 중이에요.",
  failed: "미리보기를 만들지 못했어요.",
  stale: "이전 편집본 미리보기는 재생하지 않아요.",
  unavailable: "아직 편집본 미리보기가 없어요.",
};

/** Turns a fenced API artifact into an intentionally small, safe UI contract. */
export function toExactPreviewState(preview: ExactPreviewInput, expectedRevision: number): ExactPreviewState {
  const isCurrentArtifact = Boolean(preview.url) && isAllowedLocalUrl(preview.url!)
    && preview.artifactRevision === expectedRevision
    && (preview.status === "current" || preview.status === "succeeded");
  if (isCurrentArtifact) {
    const startSec = finiteOr(preview.timelineStartSec, 0);
    const endSec = Math.max(startSec, finiteOr(preview.timelineEndSec, startSec));
    return { kind: "current", label: "편집본 미리보기", copy: "현재 편집 내용이 반영된 영상이에요.", action: "none", url: preview.url!, timelineRange: { startSec, endSec } };
  }
  const kind: Exclude<ExactPreviewState["kind"], "current"> = preview.status === "succeeded" || preview.status === "current" ? "stale" : preview.status;
  return { kind, label: "편집본 미리보기", copy: recoveryCopy[kind], action: "refresh" };
}

function finiteOr(value: number | null | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
import { isAllowedLocalUrl } from "../../../lib/network-guard";
