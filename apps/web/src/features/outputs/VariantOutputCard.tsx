import type { VariantRenderItem } from "../../api";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { isVariantPlayable, variantContentUrl, variantLabel } from "./variantOutputState";

export function VariantOutputCard({
  projectId,
  item,
  onRetry,
  confirmed = false,
  onConfirm,
}: {
  projectId: string;
  item: VariantRenderItem;
  onRetry: () => void;
  confirmed?: boolean;
  onConfirm?: () => void;
}) {
  const label = variantLabel(item.variant_kind);
  const playable = isVariantPlayable(item);
  const contentUrl = variantContentUrl(projectId, item);
  return (
    <Card data-testid={`variant-output-${item.variant_id}`}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardDescription>
          {playable ? (confirmed ? "결과 확인됨 · 다시 재생할 수 있어요." : "실제 결과를 재생한 뒤 확인해 주세요.") : item.status === "failed" ? "이 출력만 다시 확인해 주세요." : item.status === "running" || item.status === "pending" ? "출력을 만드는 중이에요." : "출력 대기"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {contentUrl ? <video className="vb-output-video" aria-label={`${label} 재생`} controls preload="metadata" src={contentUrl}>이 브라우저에서는 영상을 재생할 수 없어요.</video> : null}
        {playable && !confirmed ? <Button variant="outline" onClick={onConfirm}>결과 확인</Button> : null}
        {item.error_code ? <p role="status">사유: {item.error_code}</p> : null}
        {item.status === "failed" ? <Button variant="outline" onClick={onRetry}>이 출력 다시 만들기</Button> : null}
      </CardContent>
    </Card>
  );
}
