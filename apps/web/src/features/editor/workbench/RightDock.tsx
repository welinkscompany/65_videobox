import { useEffect, useState } from "react";

import { Button } from "../../../components/ui/button";
import { NativeSelect } from "../../../components/ui/native-select";
import { InspectorControls, type ApprovedTtsCandidate, type InspectorAction, type PartialRegenerationControls } from "../inspector/InspectorControls";
import type { InspectorTarget } from "../inspector/inspectorRegistry";

export type { InspectorTarget } from "../inspector/inspectorRegistry";

type SelectedSegment = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
  nextSegmentId: string | null;
  previousSegmentId?: string | null;
  cutAction: string;
  draftApplied: boolean;
  transitionIn?: Readonly<{ type: string; durationSec: number }> | null;
  ttsReplacement?: Readonly<{ candidateId: string; assetId: string }> | null;
  ripplePlaybackRate?: 1 | 1.5 | 2;
}>;

export type RightDockProps = Readonly<{
  /** 저장된 자막 모양을 읽으려면 필요하다. 없으면 그 절만 빠진다. */
  projectId?: string;
  selectedSegment?: SelectedSegment;
  inspectorTargets?: readonly InspectorTarget[];
  inspectorDisabled?: boolean;
  partialRegeneration?: PartialRegenerationControls;
  loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>;
  ttsCandidateScopeKey?: string;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
  onSetSegmentRippleSpeed?: (input: { segmentId: string; rate: 1 | 1.5 | 2 }) => void | Promise<void>;
  onPreviewSelectedRange?: (input: { segmentId: string; startSec: number; endSec: number }) => void | Promise<void>;
}>;

/** 이 도크는 이제 `속성` 하나뿐이다(2026-08-30 두 차례 후속). 유진 대화는
 *  `YujinPanel.tsx`로 빠진 지 오래고(owner: "우리 유진 대화창도 캡컷처럼
 *  해도 되"), 추천 후보까지 같은 이유로 그리로 옮겼다 — owner: "캡컷도
 *  화면공간이 필요해서 버튼들을 엄청 작게 만들었어. 그래서 나도 캡컷을
 *  벤치마킹하라고 한거잖아"(`docs/reference/capcut-observed-2026-08-22.ko.md`
 *  §7: 캡컷은 제안 카드를 EditPilot 대화 안에 둔다, 별도 탭이 아니다).
 *  탭이 하나만 남으면 탭 줄 자체가 의미 없다 -- 그냥 내용을 바로 그린다. */
export function RightDock({
  projectId,
  selectedSegment,
  inspectorTargets = [],
  inspectorDisabled = false,
  partialRegeneration,
  loadApprovedTtsCandidates,
  ttsCandidateScopeKey,
  onInspectorAction,
  onSetSegmentRippleSpeed,
  onPreviewSelectedRange,
}: RightDockProps) {
  const [selectedInspectorTargetId, setSelectedInspectorTargetId] = useState<string | null>(null);
  const inspectorTargetIdentity = inspectorTargets.map((target) => target.id).join("|");

  useEffect(() => {
    setSelectedInspectorTargetId((current) => inspectorTargets.some((target) => target.id === current)
      ? current
      : inspectorTargets[0]?.id ?? null);
  }, [inspectorTargetIdentity, inspectorTargets]);

  const selectedInspectorTarget = inspectorTargets.find((target) => target.id === selectedInspectorTargetId) ?? null;
  const inspectorGroups = [
    { id: "media", label: "영상·소리", target: inspectorTargets.find((target) => target.kind === "media") },
    { id: "caption", label: "자막", target: inspectorTargets.find((target) => target.kind === "caption") },
    { id: "overlay", label: "화면 요소", target: inspectorTargets.find((target) => target.kind === "overlay") },
  ] as const;

  return <div className="vb-editor-right-dock">
    <section className="vb-editor-workbench__summary">
      <div role="region" aria-label="편집 항목" className="vb-editor-right-dock__inspector">
        <h2>편집 항목</h2>
        {selectedSegment ? <p>{selectedSegment.startSec.toFixed(2)}–{selectedSegment.endSec.toFixed(2)}초 구간</p> : <p>선택한 구간이 없어요.</p>}
        {selectedSegment && onSetSegmentRippleSpeed ? <div role="group" aria-label="장면 길이">
          <p>장면 길이</p>
          {([1, 1.5, 2] as const).map((rate) => <Button
            aria-pressed={(selectedSegment.ripplePlaybackRate ?? 1) === rate}
            disabled={inspectorDisabled}
            key={rate}
            onClick={() => void onSetSegmentRippleSpeed({ segmentId: selectedSegment.segmentId, rate })}
            type="button"
            variant="outline"
          >{rate === 1 ? "기본" : `${rate}배`}</Button>)}
        </div> : null}
        {selectedSegment && onPreviewSelectedRange ? <Button
          type="button"
          variant="outline"
          disabled={inspectorDisabled}
          onClick={() => void onPreviewSelectedRange({
            segmentId: selectedSegment.segmentId,
            startSec: selectedSegment.startSec,
            endSec: selectedSegment.endSec,
          })}
        >선택 구간 미리보기</Button> : null}
        {inspectorTargets.length > 0 ? <div role="group" aria-label="편집 항목 종류 바로가기">
          {inspectorGroups.map((group) => <Button
            key={group.id}
            aria-pressed={selectedInspectorTarget?.kind === group.id}
            disabled={inspectorDisabled || !group.target}
            onClick={() => { if (group.target) setSelectedInspectorTargetId(group.target.id); }}
            type="button"
            variant="outline"
          >{group.label}</Button>)}
        </div> : null}
        {inspectorTargets.length > 1 ? <label>편집 대상<NativeSelect aria-label="편집 대상" value={selectedInspectorTargetId ?? ""} onChange={(event) => setSelectedInspectorTargetId(event.target.value)}>{inspectorTargets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}</NativeSelect></label> : null}
        {!inspectorTargets.length ? <p>이 명령이 다루는 항목 없음</p> : null}
        {onInspectorAction ? <InspectorControls
          disabled={inspectorDisabled}
          loadApprovedTtsCandidates={loadApprovedTtsCandidates}
          onAction={onInspectorAction}
          partialRegeneration={partialRegeneration}
          projectId={projectId}
          selectedSegment={selectedSegment ?? null}
          target={selectedInspectorTarget}
          ttsCandidateScopeKey={ttsCandidateScopeKey}
        /> : null}
      </div>
    </section>
  </div>;
}
