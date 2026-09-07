import { OutputsPage } from "../../app/OutputsPage";
import { TimelineReviewSections } from "./TimelineReviewPage";
import { useTimelineReviewState } from "./useTimelineReviewState";

type OpenSegmentInput = Readonly<{ projectId: string; sessionId: string; segmentId: string }>;

/** 검토와 출력을 한 단계로 묶는다.
 *
 * 둘은 같은 것을 두 번 묻고 있었다 -- 같은 편집본, 같은 작업 목록, 같은 타임라인,
 * 같은 검토본, 같은 승인 기록. owner 입장에서도 "승인하고 → 내보낸다"는 한 호흡인데
 * 화면이 갈라져 있어서 승인한 뒤 다시 다른 단계로 옮겨가야 했다.
 *
 * **읽기는 한 번이다.** 두 영역을 그냥 나란히 놓으면 요청이 두 배가 되고, 더 나쁘게는
 * 두 영역이 서로 다른 시점의 사실을 볼 수 있다. 그래서 여기서 한 번 읽고 양쪽에 준다.
 *
 * **판정은 합치지 않았다.** 검토 쪽은 변형(variant) 일치까지 확인하고, 출력 쪽은
 * 거기에 더해 "승인됨"과 "확인할 항목 0건"을 요구한다. 비슷해 보인다고 하나로 묶으면
 * 무엇을 언제 내보낼 수 있는지가 조용히 바뀐다.
 */
export function ReviewAndOutputPage({
  projectId,
  onOpenEditor,
  onOpenSegment,
}: {
  projectId: string;
  onOpenEditor: () => void;
  onOpenSegment?: (input: OpenSegmentInput) => void;
}) {
  const { state, data, refresh } = useTimelineReviewState(projectId);

  return (
    <div className="vb-review-output" data-testid="review-and-output-page">
      <TimelineReviewSections projectId={projectId} state={state} refresh={refresh} onOpenSegment={onOpenSegment} />
      <OutputsPage projectId={projectId} onOpenEditor={onOpenEditor} shared={data} onSharedRefresh={refresh} reviewInline />
    </div>
  );
}
