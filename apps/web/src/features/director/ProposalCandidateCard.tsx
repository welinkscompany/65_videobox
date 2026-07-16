import type { DirectorCandidate } from "../../api";
import { MediaReferenceBadge } from "./MediaReferenceBadge";

export function ProposalCandidateCard({ candidate, selected, onToggle, onPreference }: { candidate: DirectorCandidate; selected: boolean; onToggle: (candidateId: string) => void; onPreference?: (kind: "pin_asset" | "exclude_asset" | "exclude_creator" | "exclude_tag", value: string) => void }) {
  const creator = typeof candidate.canonical_metadata.creator === "string" ? candidate.canonical_metadata.creator : "";
  const tag = Array.isArray(candidate.canonical_metadata.tags) && typeof candidate.canonical_metadata.tags[0] === "string" ? candidate.canonical_metadata.tags[0] : "";
  return <article aria-label={`${candidate.visible_reference_code} 후보`}>
    <label><input aria-label={`${candidate.visible_reference_code} 선택`} type="checkbox" checked={selected} onChange={() => onToggle(candidate.candidate_id)} /><MediaReferenceBadge code={candidate.visible_reference_code} kind="proposal" /></label>
    <p>{candidate.reason_chips.map((chip) => <span key={chip}>{chip} </span>)}</p>
    <p>{candidate.availability} · {candidate.license_policy} · {candidate.review_status}</p>
    {candidate.warning_provenance.includes("copyright_confirmation_required") ? <p role="alert">저작권 확인 필요: 사용자 소유 권리 상태를 확인하세요.</p> : null}
    {onPreference ? <p><button type="button" onClick={() => onPreference("pin_asset", candidate.asset_id)}>고정</button><button type="button" onClick={() => onPreference("exclude_asset", candidate.asset_id)}>에셋 제외</button>{creator ? <button type="button" onClick={() => onPreference("exclude_creator", creator)}>제작자 제외</button> : null}{tag ? <button type="button" onClick={() => onPreference("exclude_tag", tag)}>태그 제외</button> : null}</p> : null}
  </article>;
}
