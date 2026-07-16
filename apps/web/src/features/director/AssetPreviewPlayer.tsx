import { useEffect, useRef, useState } from "react";

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
  return <section aria-label="후보 미리보기" aria-live="polite"><div><button type="button" aria-pressed={narrationMuted} onClick={() => setNarrationMuted((value) => !value)}>나레이션 컨텍스트 음소거</button><button type="button" aria-pressed={narrationSolo} onClick={() => setNarrationSolo((value) => !value)}>나레이션 컨텍스트 solo</button><span>audition 전용 · 타임라인 gain은 변경하지 않습니다.</span></div>
    {narrationPreviewUrl ? <audio ref={narrationContext} data-testid="director-narration-context-preview" preload="metadata" src={narrationPreviewUrl} /> : null}
    {candidates.map((candidate) => {
      const audio = candidate.mediaType === "bgm" || candidate.mediaType === "music" || candidate.mediaType === "sfx";
      const inSec = Number(candidate.controls.in_sec ?? 0); const outSec = Number(candidate.controls.out_sec ?? 0);
      const onTimeUpdate = (event: React.SyntheticEvent<HTMLMediaElement>) => { const node = event.currentTarget; if (!audio && outSec > inSec && node.currentTime >= outSec) node.currentTime = inSec; };
      return <div key={candidate.candidateId}><button type="button" onClick={() => activate(candidate, true)}>{candidate.referenceCode} {audio ? "미리듣기" : "미리보기"}</button>
        {audio ? <audio ref={(node) => { media.current[candidate.candidateId] = node; }} data-testid="director-audio-preview" controls src={previewUrl(candidate.candidateId)} onPlay={() => activate(candidate, false)} /> : <video ref={(node) => { media.current[candidate.candidateId] = node; }} controls src={previewUrl(candidate.candidateId)} onPlay={() => activate(candidate, false)} onTimeUpdate={onTimeUpdate} />}
      </div>;
    })}<p>{active ? `${active} 미리보기 중` : "미리보기 선택 없음"}</p>
  </section>;
}
