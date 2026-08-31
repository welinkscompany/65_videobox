import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { RightDock } from "./RightDock";
import type { RightDockProposal } from "./rightDockTypes";

afterEach(cleanup);

/** 이 도크는 이제 두 탭(속성·추천)뿐이다(2026-08-30 후속: 유진 대화는
 *  `YujinPanel`로 완전히 빠졌다 -- `docs/reference/capcut-observed-2026-08-22.ko.md`
 *  §7, `YujinPanel.test.tsx` 참고). 기본 탭(속성) 밖의 내용은 그 탭을
 *  먼저 열어야 보인다. */
function openPane(label: "속성" | "추천") {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

const proposal: RightDockProposal = {
  proposalId: "proposal-1",
  status: "ready",
  baseSessionRevision: 7,
  currentRevision: 7,
  candidates: [
    {
      candidateId: "candidate-1", visibleReferenceCode: "B-001", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll_video", targetSegmentId: "segment-1",
      previewSummary: "첫 장면을 산책 영상으로 채웁니다.", supportedControls: { fit: "crop" },
      availability: "actionable", reviewStatus: "approved", actionable: true,
    },
    {
      candidateId: "candidate-2", visibleReferenceCode: "B-002", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "raw_video", targetSegmentId: "segment-1",
      previewSummary: "첫 장면을 원본 영상으로 채웁니다.", supportedControls: { fit: "fit" },
      availability: "actionable", reviewStatus: "approved", actionable: true,
    },
  ],
} as const;

/** 빈 장면 둘, 첫 장면에는 후보가 둘. 서버가 한 번에 받는 추천이다. */
const multiSceneProposal: RightDockProposal = {
  proposalId: "proposal-gaps",
  status: "ready",
  baseSessionRevision: 3,
  currentRevision: 3,
  allowsMultipleSelection: true,
  candidates: [
    {
      candidateId: "gap-1", visibleReferenceCode: "P02-B-01", displayName: "하늘 영상", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll", targetSegmentId: "segment-1", targetSceneLabel: "1번째 장면",
      previewSummary: "요약", supportedControls: {}, availability: "actionable", reviewStatus: "approved", actionable: true,
    },
    {
      candidateId: "gap-1-alt", visibleReferenceCode: "P02-B-02", displayName: "구름 영상", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll", targetSegmentId: "segment-1", targetSceneLabel: "1번째 장면",
      previewSummary: "요약", supportedControls: {}, availability: "actionable", reviewStatus: "approved", actionable: true,
    },
    {
      candidateId: "gap-2", visibleReferenceCode: "P02-B-03", displayName: "바다 영상", mediaType: "broll", previewUrl: null,
      kind: "broll", sourceMediaKind: "broll", targetSegmentId: "segment-2", targetSceneLabel: "2번째 장면",
      previewSummary: "요약", supportedControls: {}, availability: "actionable", reviewStatus: "approved", actionable: true,
    },
  ],
} as const;

function PersistentDock() {
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<readonly string[]>(["candidate-1"]);
  return <RightDock
    proposal={proposal}
    selectedCandidateIds={selectedCandidateIds}
    onSelectedCandidateIdsChange={setSelectedCandidateIds}
    inspectorTargets={[{ id: "segment-1", label: "세그먼트 1", kind: "caption" }]}
  />;
}

describe("RightDock", () => {
  it("shows the selected clip's properties first and already open", () => {
    // 캡컷은 클립을 누르면 속성이 이미 거기 있다. 우리는 `세부 정보` →
    // `편집 항목 열기` → `편집 대상` 셀렉트까지 **네 겹**을 지나야 속도에 닿았다.
    // 2026-08-17에 컷 도구에서 고친 것과 같은 병이 클립 속성에 남아 있었다 --
    // 탭으로 나뉜 뒤(2026-08-30)로는 "기본 탭이 속성"이라는 말이 그 자리를
    // 잇는다. 유진 대화와 같이 안 보이니 DOM 순서 대신 기본 탭을 확인한다.
    render(<PersistentDock />);

    expect(screen.getByRole("tab", { name: "속성" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("region", { name: "편집 항목" })).toBeInTheDocument();
  });

  it("offers only the approved shortform scene lengths for the selected scene", () => {
    const onSetSegmentRippleSpeed = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      selectedSegment={{
        segmentId: "segment-2", startSec: 4, endSec: 8, nextSegmentId: "segment-3",
        cutAction: "keep", draftApplied: false, ripplePlaybackRate: 1.5,
      }}
      onSetSegmentRippleSpeed={onSetSegmentRippleSpeed}
    />);

    const speed = screen.getByRole("group", { name: "장면 길이" });
    expect(speed).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1.5배" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "2배" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "2배" }));
    expect(onSetSegmentRippleSpeed).toHaveBeenCalledWith({ segmentId: "segment-2", rate: 2 });
  });

  it("offers a selected scene preview without changing the timeline", () => {
    const onPreviewSelectedRange = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      selectedSegment={{ segmentId: "segment-2", startSec: 4, endSec: 8, nextSegmentId: null, cutAction: "keep", draftApplied: false }}
      onPreviewSelectedRange={onPreviewSelectedRange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "선택 구간 미리보기" }));
    expect(onPreviewSelectedRange).toHaveBeenCalledWith({ segmentId: "segment-2", startSec: 4, endSec: 8 });
  });

  it("offers keyword shortcuts for video, captions, and screen elements", () => {
    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      inspectorTargets={[
        { id: "media-1", kind: "media", label: "영상", mediaKind: "broll", segmentId: "segment-1", fields: [], assetId: "asset-1", controls: {}, clearOnly: false },
        { id: "caption-1", kind: "caption", label: "자막", segmentId: "segment-1", fields: ["style"], style: {} as never },
        { id: "overlay-1", kind: "overlay", overlayKind: "shape", label: "화면 요소", segmentId: "segment-1", fields: [], value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" } },
      ]}
    />);

    expect(screen.getByRole("button", { name: "영상·소리" })).toBeVisible();
    expect(screen.getByRole("button", { name: "자막" })).toBeVisible();
    expect(screen.getByRole("button", { name: "화면 요소" })).toBeVisible();
  });

  it("still lets the creator fold the properties away", () => {
    // 항상 펴 두는 것과 접을 수 없는 것은 다르다 -- 탭으로 나뉜 뒤(2026-08-30)로는
    // 다른 탭으로 넘어가는 것 자체가 접는 것이다.
    render(<PersistentDock />);
    openPane("추천");
    expect(screen.queryByRole("region", { name: "편집 항목" })).not.toBeInTheDocument();
  });

  it("preserves the selected candidate while switching tabs away from and back to properties", () => {
    render(<PersistentDock />);
    openPane("추천");
    fireEvent.click(screen.getByRole("radio", { name: "B-002 선택" }));

    openPane("속성");
    expect(screen.queryByRole("region", { name: "편집 항목" })).toBeInTheDocument();
    openPane("추천");

    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();
  });

  it("names a candidate by its asset, because a code is not something a person can choose by", () => {
    // 2026-08-19 owner 지적: 후보 일곱 개가 전부 `P08-B-01 · 미디어`였다.
    // 실제로 재 보니 서로 다른 장면을 겨냥한 같은 자산이었고, 카드만 봐서는
    // 무엇을 고르는지 알 수 없었다. 이름이 오면 이름을 쓴다.
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={{
        proposalId: "proposal-1",
        status: "ready",
        baseSessionRevision: 1,
        currentRevision: 1,
        candidates: [{
          candidateId: "candidate:segment-1:asset-sea",
          visibleReferenceCode: "P01-B-01",
          displayName: "제주 바다 드론",
          mediaType: "broll",
          previewUrl: null,
          kind: "broll",
          sourceMediaKind: "broll_video",
          targetSegmentId: "segment-1",
          previewSummary: "요약",
          supportedControls: {},
          availability: "available",
          reviewStatus: "approved",
          actionable: true,
        }],
      }}
    />);
    openPane("추천");

    expect(screen.getByRole("radio", { name: "제주 바다 드론 선택" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /P01-B-01/ })).toBeNull();
  });

  it("says which scene each candidate is for, so the same asset twice is still two choices", () => {
    // 2026-08-20 owner 실측: 카드 열세 개가 전부 `20260612_091959 · 미디어`였다.
    // 서버는 후보마다 다른 `target_segment_id`를 실어 보내고 화면 코드도 그것을
    // 받는데, **카드가 그 값을 한 번도 쓰지 않았다.** 장면을 말하지 않으면
    // 같은 자산을 쓰는 후보들은 화면에서 구별할 방법이 없다.
    const sceneCandidate = (candidateId: string, targetSegmentId: string, targetSceneLabel: string) => ({
      candidateId,
      visibleReferenceCode: "P02-B-01",
      displayName: "20260612_091959",
      mediaType: "broll",
      previewUrl: null,
      kind: "broll",
      sourceMediaKind: "broll",
      targetSegmentId,
      targetSceneLabel,
      previewSummary: "요약",
      supportedControls: {},
      availability: "actionable",
      reviewStatus: "approved",
      actionable: true,
    });
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={{
        proposalId: "proposal-1",
        status: "ready",
        baseSessionRevision: 1,
        currentRevision: 1,
        candidates: [
          sceneCandidate("candidate-1", "segment-1", "1번째 장면 · 안녕하세요, 제주입니다"),
          sceneCandidate("candidate-2", "segment-2", "2번째 장면 · 오름에 올라 봅니다"),
        ],
      }}
    />);
    openPane("추천");

    // 보이는 글자와 접근 이름이 **둘 다** 갈라져야 한다. 하나만 갈라지면
    // 눈으로 보거나 음성으로 듣는 사람 중 한쪽은 여전히 못 고른다.
    expect(screen.getByRole("radio", { name: "1번째 장면 · 안녕하세요, 제주입니다 — 20260612_091959 선택" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "2번째 장면 · 오름에 올라 봅니다 — 20260612_091959 선택" })).toBeInTheDocument();
    expect(screen.getByText(/1번째 장면 · 안녕하세요, 제주입니다/)).toBeVisible();
    expect(screen.getByText(/2번째 장면 · 오름에 올라 봅니다/)).toBeVisible();
  });

  it("keeps the old name when nothing is known about the scene, instead of inventing one", () => {
    // 장면을 모르면 아무 말도 하지 않는다. 지어낸 장면 이름은 코드보다 나쁘다.
    render(<RightDock draft="" onDraftChange={() => undefined} proposal={proposal} />);
    openPane("추천");

    expect(screen.getByRole("radio", { name: "B-001 선택" })).toBeInTheDocument();
  });

  it("lets several scenes be filled in one go when the server can apply them together", () => {
    // 2026-08-20 owner 실측: 빈 구간 열세 개를 채우려면 고르기·적용을 열세 번
    // 반복해야 했다. 후보 고르기가 라디오라 **한 번에 하나**만 됐기 때문이다.
    // `batch-apply`는 처음부터 여러 개를 한 번에 받아 **한 번의 편집**으로 쓴다.
    const onSelectedCandidateIdsChange = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    openPane("추천");

    fireEvent.click(screen.getByRole("checkbox", { name: "2번째 장면 — 바다 영상 선택" }));

    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["gap-1", "gap-2"]);
    expect(screen.queryByRole("radio")).toBeNull();
  });

  it("keeps one candidate per scene, because two candidates for one scene would overwrite each other", () => {
    // 한 장면에 둘을 고르면 서버는 둘 다 그 장면에 쓰고 **나중 것이 이긴다** --
    // 조용히 하나가 사라진다. 같은 장면의 다른 후보를 고르면 앞의 것을 대신한다.
    const onSelectedCandidateIdsChange = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1", "gap-2"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    openPane("추천");

    fireEvent.click(screen.getByRole("checkbox", { name: "1번째 장면 — 구름 영상 선택" }));

    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["gap-1-alt", "gap-2"]);
  });

  it("selects one candidate for every scene at once, and clears them again", () => {
    const onSelectedCandidateIdsChange = vi.fn();
    const rendered = render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={[]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    openPane("추천");

    fireEvent.click(screen.getByRole("button", { name: "장면마다 하나씩 모두 고르기" }));
    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["gap-1", "gap-2"]);

    rendered.rerender(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1", "gap-2"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    fireEvent.click(screen.getByRole("button", { name: "고른 추천 모두 끄기" }));
    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith([]);
  });

  it("applies every selected scene in one press, and says how many are going", () => {
    const onApplyProposal = vi.fn();
    render(<RightDock
      draft=""
      onDraftChange={() => undefined}
      proposal={multiSceneProposal}
      selectedCandidateIds={["gap-1", "gap-2"]}
      onSelectedCandidateIdsChange={vi.fn()}
      onApplyProposal={onApplyProposal}
    />);
    openPane("추천");

    fireEvent.click(screen.getByRole("button", { name: "고른 추천 2개 적용" }));

    expect(onApplyProposal).toHaveBeenCalledWith("proposal-gaps", ["gap-1", "gap-2"]);
    expect(onApplyProposal).toHaveBeenCalledTimes(1);
  });

  it("keeps a single-pick proposal on radios, because the server refuses to apply those together", () => {
    // 유진이 직접 실행하는 추천은 서버가 한 번에 하나만 받는다
    // (`reject_yujin_direct_apply`). 그런 추천까지 여러 개 고르게 하면
    // 고를 수는 있는데 적용이 거절되는 화면이 된다.
    render(<RightDock draft="" onDraftChange={() => undefined} proposal={proposal} />);
    openPane("추천");

    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "장면마다 하나씩 모두 고르기" })).toBeNull();
  });

  it("is a controlled adapter for candidate selection", () => {
    const onSelectedCandidateIdsChange = vi.fn();
    const rendered = render(<RightDock
      proposal={proposal}
      selectedCandidateIds={["candidate-2"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    openPane("추천");

    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "B-001 선택" }));
    expect(onSelectedCandidateIdsChange).toHaveBeenCalledWith(["candidate-1"]);
    expect(screen.getByRole("radio", { name: "B-002 선택" })).toBeChecked();

    rendered.rerender(<RightDock
      proposal={proposal}
      selectedCandidateIds={["candidate-1"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
    />);
    openPane("추천");
    expect(screen.getByRole("radio", { name: "B-001 선택" })).toBeChecked();
  });

  it("never mounts an audio or video player and only exposes explicit apply for a ready proposal", () => {
    const onApplyProposal = vi.fn();
    const { container } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={proposal}
      selectedCandidateIds={["candidate-1"]}
      onSelectedCandidateIdsChange={vi.fn()}
      onApplyProposal={onApplyProposal}
    />);
    openPane("추천");

    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "선택한 추천 적용" }));
    expect(onApplyProposal).toHaveBeenCalledWith("proposal-1", ["candidate-1"]);
  });

  it("shows typed media details without mutation and disables stale or deferred choices", () => {
    const onApplyProposal = vi.fn();
    const onSelectedCandidateIdsChange = vi.fn();
    const stale: RightDockProposal = {
      ...proposal,
      baseSessionRevision: 6,
      currentRevision: 7,
      candidates: [
        proposal.candidates[0],
        {
          ...proposal.candidates[1],
          candidateId: "deferred-image",
          visibleReferenceCode: "B-003",
          sourceMediaKind: "image",
          availability: "candidate_only",
          reviewStatus: "pending",
          actionable: false,
        },
      ],
    };

    const { container } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={stale}
      selectedCandidateIds={["candidate-1"]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
      onApplyProposal={onApplyProposal}
    />);
    openPane("추천");

    expect(screen.getByText("첫 장면을 산책 영상으로 채웁니다.")).toBeVisible();
    expect(screen.getByText("영상")).toBeVisible();
    // 내부 세그먼트 식별자는 owner에게 뜻이 없다. 화면에는 나오지 않아야 한다.
    expect(screen.queryAllByText("segment-1")).toHaveLength(0);
    expect(screen.getByText("화면 채우기")).toBeVisible();
    expect(screen.getByText("제안 기준 편집본 6")).toBeVisible();
    expect(screen.getByText("현재 편집본 7")).toBeVisible();
    expect(screen.getByText("후보 상태: 적용 가능")).toBeVisible();
    expect(screen.getByText("후보 상태: 수동 적용")).toBeVisible();
    expect(screen.getByRole("radio", { name: "B-003 선택" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(onSelectedCandidateIdsChange).not.toHaveBeenCalled();
    expect(onApplyProposal).not.toHaveBeenCalled();
  });

  it("shows candidate-only references without preview, materialize, or apply controls", () => {
    const onPreviewCandidate = vi.fn();
    const onApplyProposal = vi.fn();
    const candidateOnly: RightDockProposal = {
      proposalId: "candidate-only-proposal",
      status: "candidate_only",
      baseSessionRevision: 7,
      currentRevision: 7,
      candidates: [{
        candidateId: "candidate-only-1",
        visibleReferenceCode: "P01-B-01",
        mediaType: "broll",
        previewUrl: "https://must-not-preview.invalid/candidate.mp4",
        kind: "broll",
        sourceMediaKind: "image",
        targetSegmentId: "segment-1",
        previewSummary: "이미지는 아직 직접 적용할 수 없습니다.",
        supportedControls: {},
        availability: "candidate_only",
        reviewStatus: "pending",
        actionable: false,
      }],
    };

    const { container } = render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={candidateOnly}
      selectedCandidateIds={["candidate-only-1"]}
      onSelectedCandidateIdsChange={vi.fn()}
      onPreviewCandidate={onPreviewCandidate}
      onApplyProposal={onApplyProposal}
    />);
    openPane("추천");

    expect(screen.getByRole("radio", { name: "P01-B-01 선택" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "P01-B-01 미리 보기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "선택한 추천 적용" })).toBeNull();
    expect(container.querySelectorAll("audio, video")).toHaveLength(0);
    expect(onPreviewCandidate).not.toHaveBeenCalled();
    expect(onApplyProposal).not.toHaveBeenCalled();
  });

  it("keeps output findings separate and never selectable or applicable", () => {
    const mixed: RightDockProposal = {
      ...proposal,
      candidates: [
        proposal.candidates[0],
        {
          candidateId: "finding-gaps",
          visibleReferenceCode: "P01-CHECK-01",
          mediaType: "output_check",
          previewUrl: null,
          kind: "output_check",
          sourceMediaKind: "output_check",
          targetSegmentId: "",
          previewSummary: "미디어, 미리보기, 내보내기 준비가 모두 끝났습니다.",
          supportedControls: { check: "timeline_gaps", gap_count: 2 },
          availability: "read_only",
          reviewStatus: "not_applicable",
          actionable: false,
          readOnlyFinding: true,
        },
      ],
    };
    const onApplyProposal = vi.fn();
    const onSelectedCandidateIdsChange = vi.fn();

    render(<RightDock
      draft=""
      onDraftChange={vi.fn()}
      proposal={mixed}
      selectedCandidateIds={[]}
      onSelectedCandidateIdsChange={onSelectedCandidateIdsChange}
      onApplyProposal={onApplyProposal}
    />);
    openPane("추천");

    const finding = screen.getByRole("region", { name: "검사 결과" });
    expect(finding).toHaveTextContent("빈 구간 2개");
    expect(finding).not.toHaveTextContent("미디어, 미리보기, 내보내기 준비가 모두 끝났습니다.");
    expect(screen.queryByRole("radio", { name: "P01-CHECK-01 선택" })).toBeNull();
    expect(screen.getByRole("button", { name: "선택한 추천 적용" })).toBeDisabled();
    expect(onSelectedCandidateIdsChange).not.toHaveBeenCalled();
    expect(onApplyProposal).not.toHaveBeenCalled();
  });
});

describe("찾은 방식 표시", () => {
  function renderWithMode(matchMode: string | undefined) {
    const rendered = render(<RightDock
      proposal={{ ...proposal, matchMode } as never}
      selectedCandidateIds={[]}
      onSelectedCandidateIdsChange={() => {}}
      inspectorTargets={[]}
    />);
    openPane("추천");
    return rendered;
  }

  it("단어로만 찾았으면 그 사실을 말한다", () => {
    // 임베딩 조회가 실패하면 조용히 단어 매칭으로 떨어졌다. 추천이 갑자기
    // 나빠져도 owner는 원인을 알 수 없었다.
    renderWithMode("word");

    expect(screen.getByText("단어로만 찾음")).toBeVisible();
  });

  it("뜻으로 찾았으면 그렇게 말한다", () => {
    renderWithMode("semantic");

    expect(screen.getByText("뜻으로 찾음")).toBeVisible();
  });

  it("모르면 지어내지 않는다", () => {
    renderWithMode(undefined);

    expect(screen.queryByText(/찾음/)).toBeNull();
  });
});
