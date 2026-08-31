import { useEffect, useRef, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import { InspectorControls, type ApprovedTtsCandidate, type InspectorAction, type PartialRegenerationControls } from "../inspector/InspectorControls";
import type { InspectorTarget } from "../inspector/inspectorRegistry";
import type { RightDockCandidate, RightDockProposal } from "./rightDockTypes";

export type { InspectorTarget } from "../inspector/inspectorRegistry";

const staleProposalMessage = "편집본이 바뀌어서 이 추천은 그대로 적용할 수 없어요.";

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
  state?: "script_required" | "idle" | "analysis_running" | "proposal_ready" | "applying" | "blocked" | "error";
  proposal?: RightDockProposal | null;
  selectedCandidateIds?: readonly string[];
  onSelectedCandidateIdsChange?: (candidateIds: readonly string[]) => void;
  selectedSegment?: SelectedSegment;
  inspectorTargets?: readonly InspectorTarget[];
  inspectorDisabled?: boolean;
  partialRegeneration?: PartialRegenerationControls;
  loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>;
  ttsCandidateScopeKey?: string;
  onInspectorAction?: (action: InspectorAction) => void | Promise<void>;
  onSetSegmentRippleSpeed?: (input: { segmentId: string; rate: 1 | 1.5 | 2 }) => void | Promise<void>;
  onPreviewSelectedRange?: (input: { segmentId: string; startSec: number; endSec: number }) => void | Promise<void>;
  onApplyProposal?: (proposalId: string, candidateIds: readonly string[]) => void | Promise<void>;
  onRefreshProposal?: () => void | Promise<void>;
  onPreviewCandidate?: (candidate: RightDockCandidate) => void;
}>;

/** 후보를 **부르는 이름**. 코드는 사람이 고르는 근거가 못 된다 -- 2026-08-19에
 *  owner 화면의 후보 일곱 개가 전부 `P08-B-01 · 미디어`였고, 실제로는 서로 다른
 *  장면을 겨냥한 같은 자산이었다. 이름이 오면 이름을, 없으면 코드를 쓴다.
 *
 *  **종류는 여기 넣지 않는다.** 접근 이름은 부르는 말이고, 종류는 카드가 `미디어`
 *  줄로 이미 말한다. 넣었더니 음성으로 부르는 이름이 통째로 바뀌었다. */
function candidateAssetLabel(candidate: RightDockCandidate): string {
  return candidate.displayName?.trim() || candidate.visibleReferenceCode;
}

/** 부르는 이름에 **장면이 먼저 온다.** 같은 자산을 여러 장면에 추천하는 일이
 *  흔해서(빈 구간을 한 자산으로 메우는 경우가 그렇다) 자산 이름만으로는 열세
 *  개가 전부 같은 이름이 된다. 장면을 모르면 예전처럼 자산 이름만 쓴다. */
function candidateLabel(candidate: RightDockCandidate): string {
  const scene = candidate.targetSceneLabel?.trim();
  return scene ? `${scene} — ${candidateAssetLabel(candidate)}` : candidateAssetLabel(candidate);
}

/** 카드에 보이는 글자. 이름 옆에 종류를 붙여 한눈에 구분되게 한다. */
function candidateTitle(candidate: RightDockCandidate): string {
  return `${candidateAssetLabel(candidate)} · ${mediaKindLabel(candidate.sourceMediaKind)}`;
}

/** 이 도크를 **탭으로 나눈다**(owner 지시 2026-08-30: "구분해서 탭으로
 *  정리하라고 했더니 하나도 안 하고 다 때려박아 넣었다"). 왼쪽 패널을
 *  캡컷 콘텐츠 탭으로 승격한 것(2단계, 2026-08-30)과 같은 자리. 기본은
 *  `속성`이다 -- 캡컷의 `세부 정보`가 그렇듯, 클립을 고르면 그 속성이
 *  바로 보이는 게 우선이다.
 *
 *  **`기억`은 따로 탭을 만들지 않는다.** 처음엔 네 번째 탭으로 뒀는데,
 *  유진 대화 스크롤·작성 중인 요청과 기억 패널을 **같이** 다루는 흐름이
 *  실제로 많았다(기억 후보는 유진 대화에서 나온다) -- 둘을 다른 탭에
 *  두면 오히려 왔다 갔다 해야 했다.
 *
 *  **`유진`은 2026-08-30 후속 지시로 이 탭 줄에서 다시 빠졌다** — "우리
 *  유진 대화창도 캡컷처럼 해도 되"(`docs/reference/capcut-observed-2026-08-22.ko.md`
 *  §7: 캡컷 EditPilot은 이 속성 도크의 탭이 아니라 화면 구석에 따로 뜨는
 *  독립 패널이다). 유진 대화·기억은 `YujinPanel.tsx`로 옮겼고,
 *  `EditorWorkbench`가 도크와 무관하게 따로 열고 닫는다. */
type RightDockPane = "properties" | "recommendations";
const rightDockPanes: readonly Readonly<{ pane: RightDockPane; label: string }>[] = [
  { pane: "properties", label: "속성" },
  { pane: "recommendations", label: "추천" },
];

export function RightDock({
  projectId,
  state = "idle",
  proposal = null,
  selectedCandidateIds,
  onSelectedCandidateIdsChange,
  selectedSegment,
  inspectorTargets = [],
  inspectorDisabled = false,
  partialRegeneration,
  loadApprovedTtsCandidates,
  ttsCandidateScopeKey,
  onInspectorAction,
  onSetSegmentRippleSpeed,
  onPreviewSelectedRange,
  onApplyProposal,
  onRefreshProposal,
  onPreviewCandidate,
}: RightDockProps) {
  // 탭 자체가 이제 이 구역의 열고 닫기다(`rightDockPanes` 참고) -- 접었다
  // 펴는 단추를 안에 하나 더 두면 캡컷은 클립을 누르면 속성이 이미 거기
  // 있다. `유진과 편집 항목` → `편집 항목 열기` → `편집 대상`까지 네 겹을
  // 지나야 속도·소리에 닿던 문제(2026-08-17)는 탭이 이미 열려 있는 것으로
  // 해결된다 -- 두 벌 토글이 된다.
  const [pane, setPane] = useState<RightDockPane>("properties");
  const [selectedInspectorTargetId, setSelectedInspectorTargetId] = useState<string | null>(null);
  const inspectorTargetIdentity = inspectorTargets.map((target) => target.id).join("|");
  /** 한 번에 그리는 추천 카드 수. 왼쪽 자산 내역과 같은 기준이다. */
  const CANDIDATE_PAGE = 4;
  const [shownCandidates, setShownCandidates] = useState(CANDIDATE_PAGE);

  useEffect(() => {
    setSelectedInspectorTargetId((current) => inspectorTargets.some((target) => target.id === current)
      ? current
      : inspectorTargets[0]?.id ?? null);
  }, [inspectorTargetIdentity, inspectorTargets]);

  const proposalIsReady = proposal?.status === "ready";
  const proposalIsCurrent = proposalIsReady
    && proposal.baseSessionRevision === proposal.currentRevision;
  // 편집본이 앞서 나가면 이 추천은 적용할 수 없다. 그 사실을 말하지 않으면
  // 적용 단추가 이유 없이 꺼져 있는 것처럼만 보인다.
  // **보고 있을 때는 대신 물어본다.** 편집본이 바뀌면 추천이 무효가 되는 것은
  // 백엔드가 여러 겹으로 지키는 계약이라 그대로 둔다. 문제는 그다음이었다 --
  // 죽은 카드와 단추만 남고, 창작자가 그걸 눈치채고 눌러야 대화가 이어졌다.
  //
  // **낡으면 자동으로 다시 묻는 효과는 이제 여기 없다.** 이 도크는 도크와
  // 무관하게 열리는 `YujinPanel`과 달리 오른쪽 도크가 닫히면 통째로
  // 마운트 해제된다 -- 자동 재요청 효과를 여기 두면 도크가 닫혀 있을 때는
  // 안 도는데, 그게 "안 보는 화면이면 안 돈다"는 원래 의도와 맞았다.
  // 다만 이제 유진 대화는 도크 밖에서도 열 수 있어서, 그 효과는
  // `YujinPanel`로 옮겨 도크 상태와 무관하게 한 번만 돌게 했다. 여기
  // "추천" 탭은 낡음을 보여 주고 **수동** 다시 추천받기 단추만 그대로 둔다.
  const proposalIsOutOfDate = Boolean(
    proposal && proposal.baseSessionRevision !== proposal.currentRevision,
  );
  const activeCandidateIds = selectedCandidateIds
    ?? (proposal?.candidates[0] ? [proposal.candidates[0].candidateId] : []);
  // 빈 구간이 열두 개면 고르기·적용을 열두 번 반복해야 했다. `batch-apply`는
  // 처음부터 여러 개를 받아 **한 번의 편집**으로 쓰므로(되돌리기도 한 번),
  // 서버가 함께 받는 추천에서는 카드도 여러 개 고를 수 있어야 한다.
  const allowsMultipleSelection = proposal?.allowsMultipleSelection === true;
  const candidateIsChoosable = (candidate: RightDockCandidate) => (
    candidate.actionable
    && candidate.availability === "actionable"
    && candidate.reviewStatus === "approved"
  );
  const selectedCandidatesAreActionable = Boolean(
    proposalIsCurrent
    && activeCandidateIds.length >= 1
    && (allowsMultipleSelection || activeCandidateIds.length === 1)
    && activeCandidateIds.every((candidateId) => proposal?.candidates.some((candidate) => (
      candidate.candidateId === candidateId && candidateIsChoosable(candidate)
    ))),
  );
  // 같은 장면에 둘을 고르면 서버는 둘 다 그 장면에 쓰고 **나중 것이 이긴다** --
  // 조용히 하나가 사라진다. 장면당 하나로 묶어 그 일이 일어나지 않게 한다.
  const sceneKey = (candidate: RightDockCandidate) => candidate.targetSegmentId || candidate.candidateId;
  const chooseCandidate = (candidate: RightDockCandidate, chosen: boolean) => {
    if (!allowsMultipleSelection) {
      onSelectedCandidateIdsChange?.([candidate.candidateId]);
      return;
    }
    const dropped = new Set(
      (proposal?.candidates ?? [])
        .filter((other) => sceneKey(other) === sceneKey(candidate))
        .map((other) => other.candidateId),
    );
    const kept = activeCandidateIds.filter((candidateId) => !dropped.has(candidateId));
    const next = chosen ? [...kept, candidate.candidateId] : kept;
    // 카드 순서를 그대로 지킨다. 고른 순서로 보내면 적용 순서가 화면과 달라져
    // 무엇이 어디에 들어갔는지 되짚기 어렵다.
    const order = (proposal?.candidates ?? []).map((item) => item.candidateId);
    onSelectedCandidateIdsChange?.([...next].sort((left, right) => order.indexOf(left) - order.indexOf(right)));
  };
  const selectedInspectorTarget = inspectorTargets.find((target) => target.id === selectedInspectorTargetId) ?? null;
  const inspectorGroups = [
    { id: "media", label: "영상·소리", target: inspectorTargets.find((target) => target.kind === "media") },
    { id: "caption", label: "자막", target: inspectorTargets.find((target) => target.kind === "caption") },
    { id: "overlay", label: "화면 요소", target: inspectorTargets.find((target) => target.kind === "overlay") },
  ] as const;

  const recommendationCandidates = proposal?.candidates.filter((candidate) => !candidate.readOnlyFinding) ?? [];
  const readOnlyFindings = proposal?.candidates.filter((candidate) => candidate.readOnlyFinding) ?? [];

  // **선택한 것의 속성이 맨 앞에 온다.** 기본 탭이 `속성`인 이유가 이것이다 --
  // 2026-08-17에 컷 도구가 접힌 속성 뒤에 숨어 있던 문제와 같은 원칙.
  return <div className="vb-editor-right-dock">
    <div className="vb-editor-assets__tabs" role="tablist" aria-label="세부 정보">
      {rightDockPanes.map((item) => <Button key={item.pane} variant="ghost" className="vb-editor-assets__tab" type="button" role="tab" aria-selected={pane === item.pane} onClick={() => setPane(item.pane)}>{item.label}</Button>)}
    </div>
    {pane === "properties" ? <section className="vb-editor-workbench__summary">
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
    </section> : null}

    {pane === "recommendations" ? <section aria-label="추천" className="vb-editor-workbench__summary">
      <h2>추천</h2>
      {proposal ? <div aria-label="제안 편집본">
        <p>{`제안 기준 편집본 ${proposal.baseSessionRevision}`}</p>
        <p>{`현재 편집본 ${proposal.currentRevision}`}</p>
        {matchModeLabel(proposal.matchMode) ? <p>{matchModeLabel(proposal.matchMode)}</p> : null}
        {proposalIsOutOfDate && state !== "blocked" && state !== "error" ? <>
          <p role="status">{staleProposalMessage}</p>
          {onRefreshProposal ? <Button type="button" disabled={state === "analysis_running" || state === "applying"} onClick={() => void onRefreshProposal()}>지금 편집본으로 다시 추천받기</Button> : null}
        </> : null}
      </div> : null}
      {recommendationCandidates.length && allowsMultipleSelection ? <div className="vb-editor-right-dock__bulk-pick">
        <Button type="button" onClick={() => {
          const bySceneFirst = new Map<string, string>();
          for (const candidate of recommendationCandidates) {
            if (!candidateIsChoosable(candidate)) continue;
            if (!bySceneFirst.has(sceneKey(candidate))) bySceneFirst.set(sceneKey(candidate), candidate.candidateId);
          }
          onSelectedCandidateIdsChange?.([...bySceneFirst.values()]);
        }}>장면마다 하나씩 모두 고르기</Button>
        <Button type="button" variant="outline" disabled={!activeCandidateIds.length} onClick={() => onSelectedCandidateIdsChange?.([])}>고른 추천 모두 끄기</Button>
      </div> : null}
      {recommendationCandidates.length ? <div role={allowsMultipleSelection ? "group" : "radiogroup"} aria-label="추천 후보">
        {/* owner: 오른쪽 도크도 스크롤이 길다. 유진 대화는 이미 14rem으로 묶여
            있고, 길게 만드는 것은 이 추천 카드다 -- 한 장면에 13개까지 나오고
            카드마다 이유·구간·단추가 붙는다. 왼쪽 자산 내역과 같은 방식으로
            한 화면에서 훑을 만큼만 그리고 나머지는 눌러서 편다. */}
        {recommendationCandidates.slice(0, shownCandidates).map((candidate) => {
          const candidateDeclaresActionable = candidate.actionable === undefined
            ? proposalIsReady
            : (
              candidate.actionable
              && candidate.availability === "actionable"
              && candidate.reviewStatus === "approved"
            );
          const candidateIsActionable = Boolean(
            proposalIsCurrent
            && candidateDeclaresActionable,
          );
          return <article key={candidate.candidateId}>
            <label><Input
              type={allowsMultipleSelection ? "checkbox" : "radio"}
              name={allowsMultipleSelection ? undefined : "vb-eugene-candidate"}
              aria-label={`${candidateLabel(candidate)} 선택`}
              checked={activeCandidateIds.includes(candidate.candidateId)}
              disabled={!candidateIsActionable}
              onChange={(event) => {
                if (candidateIsActionable) chooseCandidate(candidate, event.target.checked);
              }}
            />{candidate.targetSceneLabel?.trim()
              ? <><strong className="vb-editor-right-dock__candidate-scene">{candidate.targetSceneLabel.trim()}</strong>{" "}<span>{candidateTitle(candidate)}</span></>
              : candidateTitle(candidate)}</label>
            <p>{candidate.previewSummary}</p>
            <p>{`후보 상태: ${candidateDeclaresActionable ? "적용 가능" : "수동 적용"}`}</p>
            <dl>
              <dt>미디어</dt><dd>{mediaKindLabel(candidate.sourceMediaKind)}</dd>
              <dt>적용 설정</dt><dd>{controlSummary(candidate.supportedControls ?? {})}</dd>
            </dl>
            {candidateIsActionable && candidate.previewUrl && onPreviewCandidate ? <Button type="button" aria-label={`${candidateLabel(candidate)} ${previewVerb(candidate.sourceMediaKind)}`} onClick={() => onPreviewCandidate(candidate)}>{previewVerb(candidate.sourceMediaKind)}</Button> : null}
          </article>;
        })}
      {recommendationCandidates.length > shownCandidates ? <Button type="button" variant="outline" onClick={() => setShownCandidates((count) => count + CANDIDATE_PAGE)}>{`추천 ${recommendationCandidates.length - shownCandidates}개 더 보기`}</Button> : null}</div> : <p>아직 추천이 없어요. 직접 편집을 계속하거나 유진에게 요청할 수 있어요.</p>}
      {proposal && proposalIsReady && onApplyProposal ? <Button type="button" disabled={state === "applying" || !selectedCandidatesAreActionable} onClick={() => void onApplyProposal(proposal.proposalId, activeCandidateIds)}>{activeCandidateIds.length > 1 ? `고른 추천 ${activeCandidateIds.length}개 적용` : "선택한 추천 적용"}</Button> : null}
      {readOnlyFindings.length ? <section aria-label="검사 결과">
        <h2>검사 결과</h2>
        {readOnlyFindings.map((finding) => <article key={finding.candidateId}>
          {finding.supportedControls.check === "timeline_gaps"
            ? <p>{`빈 구간 ${String(finding.supportedControls.gap_count ?? 0)}개`}</p>
            : null}
        </article>)}
      </section> : null}
    </section> : null}

  </div>;
}


// 백엔드가 내는 값은 `semantic` / `word` 원값이다. 모르는 값이면 아무 말도
// 하지 않는다 -- 지어내는 것보다 침묵이 낫다.
const matchModeWords: Readonly<Record<string, string>> = {
  semantic: "뜻으로 찾음",
  word: "단어로만 찾음",
};

function matchModeLabel(mode: string | undefined): string | null {
  return mode ? matchModeWords[mode] ?? null : null;
}

// 소리만 있는 추천은 듣는 것이고 영상·이미지는 보는 것이다. 하나로 뭉뚱그리면
// owner는 영상 추천에 "미리 듣기"라고 적힌 단추를 누르게 된다.
function previewVerb(kind: RightDockCandidate["sourceMediaKind"]): string {
  return kind === "bgm" || kind === "sfx" ? "미리 듣기" : "미리 보기";
}

function mediaKindLabel(kind: RightDockCandidate["sourceMediaKind"]) {
  return {
    raw_video: "원본 영상",
    // `source_media_kind`가 없는 후보는 `media_type`으로 떨어진다. 그 값은
    // `broll`이라 사전에 없었고, B-roll 후보가 전부 `미디어`로 보였다.
    broll: "영상",
    broll_video: "영상",
    image: "이미지",
    bgm: "배경 음악",
    sfx: "효과음",
    output_variant: "출력 변형",
  }[kind] ?? "미디어";
}

function controlSummary(controls: Readonly<Record<string, unknown>>) {
  const labels = Object.entries(controls).map(([name, value]) => {
    if (name === "fit") return value === "crop" ? "화면 채우기" : "화면 안에 맞추기";
    if (name === "volume") return `음량 ${value}`;
    if (name === "fade_in_sec") return `시작 전환 ${value}초`;
    if (name === "fade_out_sec") return `끝 전환 ${value}초`;
    if (name === "text") return "문구 변경";
    if (name === "style") return "자막 모양 변경";
    if (name === "candidate_id") return "승인한 음성";
    if (name === "overlay_kind") return "오버레이 변경";
    return null;
  }).filter((value): value is string => value !== null);
  return labels.join(", ") || "기본 설정";
}
