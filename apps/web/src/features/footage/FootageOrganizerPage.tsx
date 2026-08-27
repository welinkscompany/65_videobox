import { useEffect, useMemo, useRef, useState } from "react";
import { api, type FootageProposal, type FootageProposalPreview, type FootageSegment, type FootageSequence, type FootageSequencePreview, type LibraryAsset, type YujinFootageInterpretation } from "../../api";
import { Button } from "../../components/ui/button";
import { FootagePreview } from "./FootagePreview";
import { FootageSourceList } from "./FootageSourceList";
import { FootageSuggestions } from "./FootageSuggestions";
import { SceneTimeline } from "./SceneTimeline";
import "./footage.css";

const FRAME_STEP = 1 / 30;

export function FootageOrganizerPage() {
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<LibraryAsset | null>(null);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [proposal, setProposal] = useState<FootageProposal | null>(null);
  const [proposalPreview, setProposalPreview] = useState<FootageProposalPreview | null>(null);
  const [previewUnavailable, setPreviewUnavailable] = useState(false);
  const [sequence, setSequence] = useState<FootageSequence | null>(null);
  const [sequencePreview, setSequencePreview] = useState<FootageSequencePreview | null>(null);
  const [selectedSequencePreviewItemId, setSelectedSequencePreviewItemId] = useState<string | null>(null);
  const [selectedSequenceItemId, setSelectedSequenceItemId] = useState<string | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [selectedSegmentIds, setSelectedSegmentIds] = useState<string[]>([]);
  const [playhead, setPlayhead] = useState(0);
  const [request, setRequest] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [yujinCandidate, setYujinCandidate] = useState<YujinFootageInterpretation | null>(null);
  // A cross-entry link (e.g. from the library) names the source it wants
  // selected. Only the first successful load honors it, so a later "다시
  // 시도" reload never overrides a choice the owner made in the meantime.
  const requestedAssetId = useRef<string | null>(new URLSearchParams(window.location.search).get("library_asset_id"));

  const loadAssets = async () => {
    setLoading(true); setError(null);
    try {
      const result = await api.listLibraryAssets({ mediaType: "broll", limit: 100 });
      const ready = result.assets.filter((asset) => asset.lifecycle === "ready");
      setAssets(ready);
      const requestedId = requestedAssetId.current;
      requestedAssetId.current = null;
      const requested = requestedId ? ready.find((asset) => asset.library_asset_id === requestedId) : null;
      if (requested) selectAsset(requested);
    } catch { setError("촬영본을 불러오지 못했습니다."); } finally { setLoading(false); }
  };
  useEffect(() => { void loadAssets(); }, []);

  const duration = selectedAsset?.duration_seconds ?? Number(selectedAsset?.technical_metadata?.duration_seconds ?? proposal?.machine_fields.total_duration ?? 0);
  const selectedSegment = proposal?.segments.find((segment) => segment.segment_id === selectedSegmentId) ?? null;
  const sequenceItems = useMemo(() => {
    return (proposal?.segments.filter((segment) => selectedSegmentIds.includes(segment.segment_id)) ?? []).map((segment, index) => ({ source_segment_id: segment.source_segment_id, item_order: index + 1, start_sec: segment.start_sec, end_sec: segment.end_sec }));
  }, [proposal, selectedSegmentIds]);

  function selectAsset(asset: LibraryAsset, extend = false) {
    if (extend) {
      setSelectedSourceIds((current) => current.includes(asset.library_asset_id) ? current.filter((id) => id !== asset.library_asset_id) : [...current, asset.library_asset_id]);
      setNotice("여러 촬영본을 선택했어요. 가상 묶음은 각 원본 연결을 유지해요.");
      return;
    }
    setSelectedSourceIds([asset.library_asset_id]); setSelectedAsset(asset); setProposal(null); setProposalPreview(null); setYujinCandidate(null); setPreviewUnavailable(false); setSequence(null); setSequencePreview(null); setSelectedSequencePreviewItemId(null); setSelectedSequenceItemId(null); setSelectedSegmentId(null); setSelectedSegmentIds([]); setPlayhead(0); setNotice(null);
  }
  async function startProposal() {
    if (!selectedAsset) return;
    setBusy("분석"); setNotice(null);
    try {
      const result = await api.proposeFootage({ library_asset_id: selectedAsset.library_asset_id, idempotency_key: `footage-ui-${selectedAsset.library_asset_id}-${Date.now()}` });
      setProposal(result); setYujinCandidate(null); setProposalPreview(null); setPreviewUnavailable(false); setSelectedSegmentId(result.segments[0]?.segment_id ?? null); setSelectedSegmentIds(result.segments[0]?.segment_id ? [result.segments[0].segment_id] : []); setNotice("제안이 준비됐어요. 타임라인을 확인하세요. Shift+클릭으로 여러 장면을 선택할 수 있어요.");
    } catch { setNotice("제안을 만들지 못했습니다. 다시 시도하세요."); } finally { setBusy(null); }
  }
  async function editProposal(payload: Parameters<typeof api.editFootageProposal>[1]) {
    if (!proposal) return;
    setBusy("편집");
    try {
      const previous = proposal;
      const next = await api.editFootageProposal(proposal.proposal_id, payload);
      const selectedSources = selectedSegmentIds.map((id) => previous.segments.find((segment) => segment.segment_id === id)?.source_segment_id).filter(Boolean);
      const remapped = next.segments.filter((segment) => selectedSources.includes(segment.source_segment_id)).map((segment) => segment.segment_id);
      const fallback = remapped.length ? remapped : (next.segments[0]?.segment_id ? [next.segments[0].segment_id] : []);
      setProposal(next); setSelectedSegmentIds(fallback); setSelectedSegmentId(fallback[0] ?? null); setProposalPreview(null); setPreviewUnavailable(false); setNotice("제안이 바뀌었어요. 다시 미리보기한 뒤 적용하세요.");
    } catch { setNotice("변경을 저장하지 못했습니다. 최신 제안을 다시 확인하세요."); } finally { setBusy(null); }
  }
  function moveBoundary(segment: FootageSegment, edge: "start" | "end", delta: number) {
    const value = edge === "start" ? Math.max(0, segment.start_sec + delta) : Math.min(duration || segment.end_sec + delta, segment.end_sec + delta);
    void editProposal({ operation: "move_boundary", expected_revision: proposal?.revision ?? 1, segment_id: segment.segment_id, boundary_sec: value });
  }
  function split() { if (!proposal || !selectedSegment) return; const splitSec = Math.min(selectedSegment.end_sec - FRAME_STEP, Math.max(selectedSegment.start_sec + FRAME_STEP, playhead)); void editProposal({ operation: "split", expected_revision: proposal.revision, segment_id: selectedSegment.segment_id, split_sec: splitSec }); }
  function merge() { if (!proposal || !selectedSegment) return; const index = proposal.segments.findIndex((segment) => segment.segment_id === selectedSegment.segment_id); const next = proposal.segments[index + 1]; if (next) void editProposal({ operation: "merge", expected_revision: proposal.revision, segment_ids: [selectedSegment.segment_id, next.segment_id] }); }
  function exclude() { if (proposal && selectedSegment) void editProposal({ operation: "exclude", expected_revision: proposal.revision, segment_id: selectedSegment.segment_id }); }
  function selectSegment(segment: FootageSegment, extend: boolean) {
    setSelectedSegmentIds((current) => {
      const next = extend ? (current.includes(segment.segment_id) ? current.filter((id) => id !== segment.segment_id) : [...current, segment.segment_id]) : [segment.segment_id];
      setSelectedSegmentId(next.includes(segment.segment_id) ? segment.segment_id : next[0] ?? null);
      return next;
    });
    setPlayhead(segment.start_sec);
  }
  async function previewProposal() { if (!proposal) return; setBusy("미리보기"); try { const result = await api.previewFootageProposal(proposal.proposal_id, { expected_revision: proposal.revision }); setProposalPreview(result); setPreviewUnavailable(false); setNotice("제안 미리보기를 준비했어요. 원본은 그대로예요."); } catch { setProposalPreview(null); setPreviewUnavailable(true); setNotice("미리보기를 준비하지 못했습니다. 장면을 다시 확인하세요."); } finally { setBusy(null); } }
  async function cancelProposal() { if (!proposal) return; setBusy("취소"); try { await api.cancelFootageProposal(proposal.proposal_id); setProposal(null); setProposalPreview(null); setSequence(null); setSequencePreview(null); setSelectedSequencePreviewItemId(null); setNotice("제안을 취소했어요. 원본은 변경되지 않았어요."); } finally { setBusy(null); } }
  async function approveProposal() { if (!proposal) return; setBusy("적용"); try { const result = await api.approveFootageProposal(proposal.proposal_id, { expected_revision: proposal.revision, idempotency_key: `approve-${proposal.proposal_id}` }); setProposal(result); setNotice("제안을 적용했어요. 촬영본 원본은 보존돼요."); } catch { setNotice("제안을 적용하지 못했습니다. 최신 상태를 확인하세요."); } finally { setBusy(null); } }
  async function interpretYujin() { if (!proposal || !request.trim()) return; setBusy("유진 제안"); try { const result = await api.interpretYujinFootageProposal(proposal.proposal_id, { instruction: request.trim() }); setYujinCandidate(result); if (result.status === "candidate_only") { setProposalPreview({ status: "ready", proposal_id: proposal.proposal_id, revision: proposal.revision, source_id: proposal.source_id, preview_url: result.preview.preview_url, segments: proposal.segments }); setNotice("유진 후보를 미리보기로 준비했어요. 적용은 별도 승인에서만 실행돼요."); } else if (result.status === "clarification") setNotice(result.clarification); else setNotice("유진 제안을 적용하지 못했어요."); } catch { setYujinCandidate(null); setNotice("유진 제안을 준비하지 못했어요."); } finally { setBusy(null); } }
  async function createSequence() {
    if (!proposal || sequenceItems.length === 0 || selectedSourceIds.length === 0) return;
    setBusy("묶음");
    try {
      const selectedAssets = assets.filter((asset) => selectedSourceIds.includes(asset.library_asset_id));
      const proposals = await Promise.all(selectedAssets.map(async (asset) => {
        if (asset.library_asset_id === selectedAsset?.library_asset_id && proposal) return proposal;
        return api.proposeFootage({ library_asset_id: asset.library_asset_id, idempotency_key: `sequence-source-${asset.library_asset_id}-${Date.now()}` });
      }));
      const multiSource = proposals.length > 1;
      const items = proposals.flatMap((sourceProposal) => {
        const sourceSegments = sourceProposal.proposal_id === proposal.proposal_id && !multiSource
          ? sourceProposal.segments.filter((segment) => selectedSegmentIds.includes(segment.segment_id))
          : sourceProposal.segments;
        return sourceSegments.map((segment) => ({ source_segment_id: segment.source_segment_id, ...(multiSource ? { source_id: sourceProposal.source_id } : {}), item_order: 0, start_sec: segment.start_sec, end_sec: segment.end_sec }));
      }).map((item, index) => ({ ...item, item_order: index + 1 }));
      const result = await api.createFootageSequence({ source_id: proposals[0].source_id, name: multiSource ? "선택한 촬영본 가상 묶음" : "새 가상 묶음", items, idempotency_key: `sequence-${proposal.proposal_id}-${selectedSourceIds.join("-")}` });
      setSequence(result); setSequencePreview(null); setSelectedSequencePreviewItemId(null); setSelectedSequenceItemId(result.items[0]?.item_id ?? null); setNotice("가상 묶음을 만들었어요. 원본별 연결을 유지한 채 순서를 바꿀 수 있어요.");
    } catch { setNotice("가상 묶음을 만들지 못했습니다."); } finally { setBusy(null); }
  }
  async function moveSequence(delta: number) { if (!sequence || !selectedSequenceItemId) return; const index = sequence.items.findIndex((item) => item.item_id === selectedSequenceItemId); const target = index + delta; if (index < 0 || target < 0 || target >= sequence.items.length) return; const ids = sequence.items.map((item) => item.item_id); [ids[index], ids[target]] = [ids[target], ids[index]]; setBusy("순서"); try { setSequence(await api.reorderFootageSequence(sequence.sequence_id, { expected_revision: sequence.revision, item_ids: ids })); } finally { setBusy(null); } }
  async function previewSequence() { if (!sequence) return; setBusy("묶음 미리보기"); try { const result = await api.previewFootageSequence(sequence.sequence_id); setSequencePreview(result); setSelectedSequencePreviewItemId(result.preview_items[0]?.item_id ?? null); setNotice("가상 묶음 미리보기를 준비했어요. 승인 전에는 인덱스가 바뀌지 않아요."); } catch { setNotice("가상 묶음 미리보기를 준비하지 못했어요."); } finally { setBusy(null); } }
  async function cancelSequence() { if (!sequence) return; setBusy("묶음 취소"); try { await api.cancelFootageSequence(sequence.sequence_id); setSequencePreview(null); setSelectedSequencePreviewItemId(null); setNotice("가상 묶음 미리보기를 취소했어요. 원본과 인덱스는 그대로예요."); } finally { setBusy(null); } }
  async function reloadSequence() { if (!sequence) return; setBusy("묶음 새로고침"); try { const result = await api.getFootageSequence(sequence.sequence_id); setSequence(result); setSequencePreview(null); setSelectedSequencePreviewItemId(null); setSelectedSequenceItemId(result.items[0]?.item_id ?? null); setNotice("최신 가상 묶음 순서를 불러왔어요."); } finally { setBusy(null); } }
  async function approveSequence() { if (!sequence) return; setBusy("묶음 승인"); try { const result = await api.approveFootageSequence(sequence.sequence_id, { idempotency_key: `approve-sequence-${sequence.sequence_id}` }); setSequence(result); setNotice("가상 묶음을 승인했어요. 원본은 보존되고 승인된 구간만 검색 인덱스에 등록돼요."); } catch { setNotice("가상 묶음을 승인하지 못했어요. 최신 상태를 확인하세요."); } finally { setBusy(null); } }

  return <main className="vb-footage-page" data-testid="footage-workspace" data-layout="four-pane">
    {/* `VideoBox` 이름표를 뺐다 -- 위 띠가 이미 말한다(2026-08-22 카탈로그
        화면과 같은 정리, `capcut-observed` 기록: 캡컷 홈에도 가운데에 제품
        이름이 또 적혀 있지 않다). 이 화면만 빠뜨리고 있었다. */}
    <header className="vb-footage-header"><div><h1 data-testid="global-footage-page">촬영본 정리</h1><p>원본은 그대로 두고, 장면을 나누고 묶어 다음 단계에 보낼 수 있어요.</p></div><span className="vb-footage-status">{busy ? `${busy} 중…` : notice ?? "명시적으로 적용하기 전에는 저장되지 않아요."}</span></header>
    {loading ? <div className="vb-footage-state" role="status">촬영본을 불러오는 중…</div> : error ? <div className="vb-footage-state" role="alert"><p>{error}</p><Button type="button" variant="outline" onClick={() => void loadAssets()}>다시 시도</Button></div> : <div className="vb-footage-grid">
      <FootageSourceList assets={assets} selectedIds={selectedSourceIds} onSelect={selectAsset} />
      <div className="vb-footage-center"><FootagePreview asset={selectedAsset} previewUrl={sequencePreview?.preview_url ?? sequencePreview?.preview_items.find((item) => item.item_id === selectedSequencePreviewItemId)?.preview_url ?? proposalPreview?.preview_url} previewRanges={proposalPreview?.segments} previewUnavailable={previewUnavailable} currentTime={playhead} duration={duration} frameStep={FRAME_STEP} onTimeChange={setPlayhead} onPreviewError={() => { setProposalPreview(null); setSequencePreview(null); setSelectedSequencePreviewItemId(null); setPreviewUnavailable(true); setNotice("미리보기를 재생하지 못했습니다. 다시 준비하세요."); }} onFrameStep={(delta) => setPlayhead((time) => Math.max(0, Math.min(duration || Infinity, time + delta * FRAME_STEP)))} /><SceneTimeline proposal={proposal} playhead={playhead} selectedSegmentId={selectedSegmentId} selectedSegmentIds={selectedSegmentIds} onSelectSegment={selectSegment} onSplit={split} onMerge={merge} onExclude={exclude} onBoundary={moveBoundary} /></div>
      <FootageSuggestions value={request} onChange={setRequest} onInterpret={() => void interpretYujin()} disabled={!proposal || Boolean(busy)} />
      <aside className="vb-footage-pane vb-footage-actions" data-testid="footage-actions"><div className="vb-footage-pane__heading"><div><p className="vb-eyebrow">할 일</p><h2>검토와 적용</h2></div></div>{yujinCandidate?.status === "candidate_only" ? <div className="vb-footage-yujin-candidate" data-testid="yujin-candidate"><strong>유진 후보</strong><span>{yujinCandidate.reply_text}</span><small>{yujinCandidate.candidate.operations.map((operation) => operation.intent).join(" · ")}</small></div> : null}<Button className="vb-footage-primary" type="button" onClick={() => void startProposal()} disabled={!selectedAsset || Boolean(busy)}>분석 시작</Button><Button type="button" variant="outline" onClick={() => void previewProposal()} disabled={!proposal || Boolean(busy)}>제안 미리보기</Button><Button type="button" variant="outline" onClick={() => void cancelProposal()} disabled={!proposal || Boolean(busy)}>제안 취소</Button><Button className="vb-footage-apply" type="button" onClick={() => void approveProposal()} disabled={!proposal || proposal.status !== "draft" || Boolean(busy)}>제안 적용</Button><hr /><p className="vb-footage-selection-count" aria-live="polite">{selectedSourceIds.length}개 촬영본 선택됨</p><Button type="button" variant="outline" onClick={() => void createSequence()} disabled={!proposal || sequenceItems.length === 0 || Boolean(busy)}>{selectedSourceIds.length > 1 ? "선택한 촬영본으로 가상 묶음 만들기" : "선택 장면으로 가상 묶음 만들기"}</Button>{sequence ? <div className="vb-footage-sequence"><strong>{sequence.name}</strong><span>{sequence.items.length}개 장면</span><div className="vb-footage-sequence__items">{sequence.items.map((item) => <Button key={item.item_id} type="button" variant="ghost" aria-pressed={selectedSequenceItemId === item.item_id} onClick={() => setSelectedSequenceItemId(item.item_id)}>묶음 항목 {item.item_order}</Button>)}</div><div className="vb-footage-sequence__controls"><Button type="button" variant="outline" onClick={() => void moveSequence(-1)} disabled={Boolean(busy) || !selectedSequenceItemId}>위로</Button><Button type="button" variant="outline" onClick={() => void moveSequence(1)} disabled={Boolean(busy) || !selectedSequenceItemId}>아래로</Button></div><div className="vb-footage-sequence__controls"><Button type="button" variant="outline" onClick={() => void previewSequence()} disabled={Boolean(busy)}>가상 묶음 미리보기</Button><Button type="button" variant="outline" onClick={() => void cancelSequence()} disabled={Boolean(busy)}>가상 묶음 취소</Button><Button type="button" variant="outline" onClick={() => void reloadSequence()} disabled={Boolean(busy)}>가상 묶음 새로고침</Button><Button className="vb-footage-apply" type="button" onClick={() => void approveSequence()} disabled={Boolean(busy)}>가상 묶음 승인</Button></div>{sequencePreview ? <><small className="vb-footage-sequence__preview-status" role="status">{sequencePreview.preview_url ? "단일 원본 미리보기 준비됨" : `${sequencePreview.preview_items.length}개 원본 미리보기 준비됨`}</small>{sequencePreview.preview_items.length > 1 ? <div className="vb-footage-sequence__preview-items" aria-label="원본별 미리보기">{sequencePreview.preview_items.map((item, index) => <Button key={item.item_id} type="button" variant="ghost" aria-pressed={selectedSequencePreviewItemId === item.item_id} onClick={() => setSelectedSequencePreviewItemId(item.item_id)}>원본 {index + 1} 미리보기</Button>)}</div> : null}</> : null}</div> : null}<p className="vb-footage-disclaimer">적용은 명시적인 승인 요청에서만 원본 인덱스에 반영돼요.</p></aside>
    </div>}
  </main>;
}
