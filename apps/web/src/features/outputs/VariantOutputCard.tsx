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
        {/* task-2-brief.md: 재생만 되고 가져가는 문이 없어서 만든 변형본이 화면
            안에 갇혔다. `SRT 자막 파일 내려받기`·`완성본 영상 내려받기`와 같은
            모양(`<a download>`)을 그대로 따른다 -- 주소는 이미
            variantOutputState.ts가 계산해 둔 `contentUrl`을 그대로 쓴다.
            낡음 가림은 여기서 새로 만들지 않는다: 완성본의 낡음 판정
            (masterFinalRender.ts)은 렌더가 "지금 세션 리비전"에서 나왔는지를
            export 레코드의 `source_session_id`/`source_session_revision`으로
            잰다. 변형본은 그 값이 서버에서 의도적으로 비어 있다
            (local_pipeline.py의 `is_derived_variant_timeline` 분기 주석) --
            변형본은 그 대신 렌더를 "시작하는" 순간에 막힌다
            (`_materialize_variant_for_output`의 `stale_master_revision`):
            지금 세션 리비전이 변형 후보를 만들 때의 리비전과 다르면 렌더
            자체가 실패로 끝나 `item.status === "failed"` 재시도 문으로
            이미 나타난다. 그래서 완성본의 규칙을 여기 그대로 가져다 쓰면
            "항상 낡음"으로 잘못 나와서 이 기능 자체가 죽는다. */}
        {contentUrl ? <a className="vb-action-link" download href={contentUrl}>{label} 내려받기</a> : null}
        {playable && !confirmed ? <Button variant="outline" onClick={onConfirm}>결과 확인</Button> : null}
        {item.error_code ? <p role="status">사유: {item.error_code}</p> : null}
        {item.status === "failed" ? <Button variant="outline" onClick={onRetry}>이 출력 다시 만들기</Button> : null}
      </CardContent>
    </Card>
  );
}
