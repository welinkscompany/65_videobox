import { useEffect, useRef, useState } from "react";
import { mediaReferenceLabel } from "./MediaReferenceBadge";

export type PreviewCandidate = { candidateId: string; referenceCode: string; mediaType: string; controls: Record<string, unknown> };
export function AssetPreviewPlayer({ proposalId: _proposalId, candidates, previewUrl, auditionGainDb = 0, narrationPreviewUrl }: { proposalId: string; candidates: PreviewCandidate[]; previewUrl: (candidateId: string) => string; auditionGainDb?: number; narrationPreviewUrl?: string }) {
  const media = useRef<Record<string, HTMLMediaElement | null>>({});
  const narrationContext = useRef<HTMLAudioElement | null>(null);
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => { candidates.forEach((candidate) => { const node = media.current[candidate.candidateId]; const candidateGain = Number(candidate.controls.audition_gain_db); const gainDb = Number.isFinite(candidateGain) ? candidateGain : auditionGainDb; if (node) node.volume = Math.max(0, Math.min(1, 1 + gainDb / 60)); }); }, [auditionGainDb, candidates]);
  const activate = (candidate: PreviewCandidate, startPlayback: boolean) => {
    Object.entries(media.current).forEach(([id, element]) => { if (id !== candidate.candidateId) element?.pause(); });
    setActive(candidate.candidateId);
    const node = media.current[candidate.candidateId];
    const inSec = Number(candidate.controls.in_sec ?? 0);
    if (node && candidate.mediaType !== "bgm" && candidate.mediaType !== "music" && candidate.mediaType !== "sfx" && Number.isFinite(inSec) && inSec > 0) node.currentTime = inSec;
    if (startPlayback) { const playback = node?.play(); if (playback) void playback.catch(() => undefined); }
  };
  const [narrationMuted, setNarrationMuted] = useState(false); const [narrationSolo, setNarrationSolo] = useState(false);
  useEffect(() => { if (narrationContext.current) { narrationContext.current.muted = narrationMuted; narrationContext.current.volume = narrationSolo ? 1 : 0.65; } }, [narrationMuted, narrationSolo]);
  const activeCandidate = candidates.find((candidate) => candidate.candidateId === active);
  return <section aria-label="추천 미리보기" aria-live="polite"><div><button type="button" aria-pressed={narrationMuted} onClick={() => setNarrationMuted((value) => !value)}>나레이션 미리듣기 음소거</button><button type="button" aria-pressed={narrationSolo} onClick={() => setNarrationSolo((value) => !value)}>나레이션만 듣기</button><span>미리듣기 설정은 편집본의 음량을 바꾸지 않아요.</span></div>
    {narrationPreviewUrl ? <audio ref={narrationContext} data-testid="director-narration-context-preview" preload="metadata" src={narrationPreviewUrl} /> : null}
    {candidates.map((candidate) => {
      const audio = candidate.mediaType === "bgm" || candidate.mediaType === "music" || candidate.mediaType === "sfx";
      const inSec = Number(candidate.controls.in_sec ?? 0); const outSec = Number(candidate.controls.out_sec ?? 0);
      const onTimeUpdate = (event: React.SyntheticEvent<HTMLMediaElement>) => { const node = event.currentTarget; if (!audio && outSec > inSec && node.currentTime >= outSec) node.currentTime = inSec; };
      const label = /[가-힣\s]/.test(candidate.referenceCode) ? candidate.referenceCode : mediaReferenceLabel(candidate.referenceCode, "proposal");
      return <div key={candidate.candidateId}><button type="button" onClick={() => activate(candidate, true)}>{label} {audio ? "미리듣기" : "미리보기"}</button>
        {audio ? <audio ref={(node) => { media.current[candidate.candidateId] = node; }} data-testid="director-audio-preview" controls src={previewUrl(candidate.candidateId)} onPlay={() => activate(candidate, false)} /> : <video ref={(node) => { media.current[candidate.candidateId] = node; }} controls src={previewUrl(candidate.candidateId)} onPlay={() => activate(candidate, false)} onTimeUpdate={onTimeUpdate} />}
      </div>;
    })}<p>{activeCandidate ? `${mediaReferenceLabel(activeCandidate.referenceCode, "proposal")} 미리보기 중` : "미리보기 선택 없음"}</p>
  </section>;
}
