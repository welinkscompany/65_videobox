import type { VariantRenderItem } from "../../api";

export function mergeVariantRenderItems(
  current: readonly VariantRenderItem[],
  next: readonly VariantRenderItem[],
  requestedVariantIds: readonly string[],
): VariantRenderItem[] {
  const requested = new Set(requestedVariantIds);
  const replacementById = new Map(next.map((item) => [item.variant_id, item]));
  const merged = current.map((item) => replacementById.get(item.variant_id) ?? item);
  const known = new Set(current.map((item) => item.variant_id));
  for (const item of next) {
    if (!known.has(item.variant_id) && requested.has(item.variant_id)) merged.push(item);
  }
  return merged;
}

export function variantLabel(kind: string | null | undefined): string {
  if (kind === "vertical_full") return "세로 영상";
  if (kind === "vertical_highlight") return "세로 하이라이트";
  return "가로 영상";
}

export function isVariantPlayable(item: VariantRenderItem): boolean {
  return item.status === "succeeded" && Boolean(item.job_id);
}

export function variantContentUrl(projectId: string, item: VariantRenderItem): string | null {
  return isVariantPlayable(item) && item.job_id
    ? `/api/projects/${encodeURIComponent(projectId)}/final-renders/${encodeURIComponent(item.job_id)}/content`
    : null;
}

export function variantRenderSummary(items: readonly VariantRenderItem[]): string {
  if (!items.length) return "출력 변형을 아직 만들지 않았어요.";
  const succeeded = items.filter((item) => item.status === "succeeded").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const running = items.filter((item) => item.status === "running" || item.status === "pending").length;
  if (failed) return `${succeeded}개 완료 · ${failed}개 확인 필요${running ? ` · ${running}개 진행 중` : ""}`;
  if (running) return `${succeeded}개 완료 · ${running}개 만드는 중`;
  return `${succeeded}개 출력 확인 가능`;
}
