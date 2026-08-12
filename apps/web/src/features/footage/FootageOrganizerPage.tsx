import { useEffect, useMemo, useState } from "react";
import { api, type FootageProposal, type FootageSegment, type FootageSequence, type LibraryAsset } from "../../api";
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
  const [proposal, setProposal] = useState<FootageProposal | null>(null);
  const [sequence, setSequence] = useState<FootageSequence | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [request, setRequest] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadAssets = async () => {
    setLoading(true); setError(null);
    try {
      const result = await api.listLibraryAssets({ mediaType: "broll", limit: 100 });
      setAssets(result.assets.filter((asset) => asset.lifecycle === "ready"));
    } catch { setError("촬영본을 불러오지 못했습니다."); } finally { setLoading(false); }
  };
  useEffect(() => { void loadAssets(); }, []);

  const duration = selectedAsset?.duration_seconds ?? Number(selectedAsset?.technical_metadata?.duration_seconds ?? proposal?.machine_fields.total_duration ?? 0);
  const selectedSegment = proposal?.segments.find((segment) => segment.segment_id === selectedSegmentId) ?? null;
  const sequenceItems = useMemo(() => proposal?.segments.map((segment, index) => ({ source_segment_id: segment.source_segment_id, item_order: index + 1, start_sec: segment.start_sec, end_sec: segment.end_sec })) ?? [], [proposal]);

  function selectAsset(asset: LibraryAsset) { setSelectedAsset(asset); setProposal(null); setSequence(null); setSelectedSegmentId(null); setPlayhead(0); setNotice(null); }
  async function startProposal() {
    if (!selectedAsset) return;
    setBusy("분석"); setNotice(null);
    try {
      const result = await api.proposeFootage({ library_asset_id: selectedAsset.library_asset_id, idempotency_key: `footage-ui-${selectedAsset.library_asset_id}-${Date.now()}`, analysis: request.trim() ? { instruction: request.trim() } : undefined });
      setProposal(result); setSelectedSegmentId(result.segments[0]?.segment_id ?? null); setNotice("제안이 준비됐어요. 타임라인을 확인하세요.");
    } catch { setNotice("제안을 만들지 못했습니다. 다시 시도하세요."); } finally { setBusy(null); }
  }
  async function editProposal(payload: Parameters<typeof api.editFootageProposal>[1]) {
    if (!proposal) return;
    setBusy("편집");
    try { setProposal(await api.editFootageProposal(proposal.proposal_id, payload)); } catch { setNotice("변경을 저장하지 못했습니다. 최신 제안을 다시 확인하세요."); } finally { setBusy(null); }
  }
  function moveBoundary(segment: FootageSegment, edge: "start" | "end", delta: number) {
    const value = edge === "start" ? Math.max(0, segment.start_sec + delta) : Math.min(duration || segment.end_sec + delta, segment.end_sec + delta);
    void editProposal({ operation: "move_boundary", expected_revision: proposal?.revision ?? 1, segment_id: segment.segment_id, boundary_sec: value });
  }
  function split() { if (!proposal || !selectedSegment) return; const splitSec = Math.min(selectedSegment.end_sec - FRAME_STEP, Math.max(selectedSegment.start_sec + FRAME_STEP, playhead)); void editProposal({ operation: "split", expected_revision: proposal.revision, segment_id: selectedSegment.segment_id, split_sec: splitSec }); }
  function merge() { if (!proposal || !selectedSegment) return; const index = proposal.segments.findIndex((segment) => segment.segment_id === selectedSegment.segment_id); const next = proposal.segments[index + 1]; if (next) void editProposal({ operation: "merge", expected_revision: proposal.revision, segment_ids: [selectedSegment.segment_id, next.segment_id] }); }
  function exclude() { if (proposal && selectedSegment) void editProposal({ operation: "exclude", expected_revision: proposal.revision, segment_id: selectedSegment.segment_id }); }
  async function previewProposal() { if (!proposal) return; setBusy("미리보기"); try { await api.previewFootageProposal(proposal.proposal_id, { expected_revision: proposal.revision }); setNotice("제안 미리보기를 준비했어요. 원본은 그대로예요."); } catch { setNotice("미리보기를 준비하지 못했습니다."); } finally { setBusy(null); } }
  async function cancelProposal() { if (!proposal) return; setBusy("취소"); try { await api.cancelFootageProposal(proposal.proposal_id); setProposal(null); setSequence(null); setNotice("제안을 취소했어요. 원본은 변경되지 않았어요."); } finally { setBusy(null); } }
  async function approveProposal() { if (!proposal) return; setBusy("적용"); try { const result = await api.approveFootageProposal(proposal.proposal_id, { expected_revision: proposal.revision, idempotency_key: `approve-${proposal.proposal_id}` }); setProposal(result); setNotice("제안을 적용했어요. 촬영본 원본은 보존돼요."); } catch { setNotice("제안을 적용하지 못했습니다. 최신 상태를 확인하세요."); } finally { setBusy(null); } }
  async function createSequence() { if (!proposal || sequenceItems.length === 0) return; setBusy("묶음"); try { const result = await api.createFootageSequence({ source_id: proposal.source_id, name: "새 가상 묶음", items: sequenceItems, idempotency_key: `sequence-${proposal.proposal_id}` }); setSequence(result); setNotice("가상 묶음을 만들었어요. 순서를 바꾼 뒤 다시 저장하세요."); } catch { setNotice("가상 묶음을 만들지 못했습니다."); } finally { setBusy(null); } }
  async function moveSequence(delta: number) { if (!sequence) return; const index = sequence.items.findIndex((item) => item.item_id === sequence.items[0]?.item_id); const target = index + delta; if (target < 0 || target >= sequence.items.length) return; const ids = sequence.items.map((item) => item.item_id); [ids[index], ids[target]] = [ids[target], ids[index]]; setBusy("순서"); try { setSequence(await api.reorderFootageSequence(sequence.sequence_id, { expected_revision: sequence.revision, item_ids: ids })); } finally { setBusy(null); } }

  return <main className="vb-footage-page" data-testid="footage-workspace" data-layout="four-pane">
    <span data-testid="global-footage-page" className="sr-only">촬영본 정리</span>
    <header className="vb-footage-header"><div><p className="vb-eyebrow">VIDEObox / Wave-2</p><h1>촬영본 정리</h1><p>원본은 그대로 두고, 장면을 나누고 묶어 다음 단계에 보낼 수 있어요.</p></div><span className="vb-footage-status">{busy ? `${busy} 중…` : notice ?? "명시적으로 적용하기 전에는 저장되지 않아요."}</span></header>
    {loading ? <div className="vb-footage-state" role="status">촬영본을 불러오는 중…</div> : error ? <div className="vb-footage-state" role="alert"><p>{error}</p><Button type="button" variant="outline" onClick={() => void loadAssets()}>다시 시도</Button></div> : <div className="vb-footage-grid">
      <FootageSourceList assets={assets} selectedId={selectedAsset?.library_asset_id ?? null} onSelect={selectAsset} />
      <div className="vb-footage-center"><FootagePreview asset={selectedAsset} currentTime={playhead} duration={duration} frameStep={FRAME_STEP} onTimeChange={setPlayhead} onFrameStep={(delta) => setPlayhead((time) => Math.max(0, Math.min(duration || Infinity, time + delta * FRAME_STEP)))} /><SceneTimeline proposal={proposal} playhead={playhead} selectedSegmentId={selectedSegmentId} onSelectSegment={(segment) => { setSelectedSegmentId(segment.segment_id); setPlayhead(segment.start_sec); }} onSplit={split} onMerge={merge} onExclude={exclude} onBoundary={moveBoundary} /></div>
      <FootageSuggestions value={request} onChange={setRequest} />
      <aside className="vb-footage-pane vb-footage-actions" data-testid="footage-actions"><div className="vb-footage-pane__heading"><div><p className="vb-eyebrow">ACTIONS</p><h2>검토와 적용</h2></div></div><Button className="vb-footage-primary" type="button" onClick={() => void startProposal()} disabled={!selectedAsset || Boolean(busy)}>분석 시작</Button><Button type="button" variant="outline" onClick={() => void previewProposal()} disabled={!proposal || Boolean(busy)}>제안 미리보기</Button><Button type="button" variant="outline" onClick={() => void cancelProposal()} disabled={!proposal || Boolean(busy)}>제안 취소</Button><Button className="vb-footage-apply" type="button" onClick={() => void approveProposal()} disabled={!proposal || proposal.status !== "draft" || Boolean(busy)}>제안 적용</Button><hr /><Button type="button" variant="outline" onClick={() => void createSequence()} disabled={!proposal || Boolean(busy)}>선택 장면으로 가상 묶음 만들기</Button>{sequence ? <div className="vb-footage-sequence"><strong>{sequence.name}</strong><span>{sequence.items.length}개 장면</span><div><Button type="button" variant="outline" onClick={() => void moveSequence(-1)} disabled={Boolean(busy)}>위로</Button><Button type="button" variant="outline" onClick={() => void moveSequence(1)} disabled={Boolean(busy)}>아래로</Button></div></div> : null}<p className="vb-footage-disclaimer">적용은 명시적인 승인 요청에서만 원본 인덱스에 반영돼요.</p></aside>
    </div>}
  </main>;
}
