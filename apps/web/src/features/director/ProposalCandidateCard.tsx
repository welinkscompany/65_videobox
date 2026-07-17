import type { DirectorCandidate } from "../../api";
import { mediaReferenceLabel, MediaReferenceBadge } from "./MediaReferenceBadge";

function availabilityLabel(value: string) {
  return ({ available: "사용할 수 있어요", unavailable: "지금은 사용할 수 없어요" } as Record<string, string>)[value] ?? "확인이 필요해요";
}

function licenseLabel(value: string) {
  return ({ verified: "사용 권리 확인됨", ok: "사용 권리 확인됨", unknown_user_owned: "권리 확인 필요" } as Record<string, string>)[value] ?? "권리 확인 필요";
}

function reviewLabel(value: string) {
  return ({ approved: "확인됨", verified: "확인됨", pending: "확인 중" } as Record<string, string>)[value] ?? "확인이 필요해요";
}

function recommendationReason(chips: string[]) {
  const knownReason = chips.find((chip) => ({ "전환": "장면 전환에 어울려요.", "대안": "다른 분위기로 바꿔 볼 수 있어요." } as Record<string, string>)[chip]);
  return knownReason ? ({ "전환": "장면 전환에 어울려요.", "대안": "다른 분위기로 바꿔 볼 수 있어요." } as Record<string, string>)[knownReason] : "장면에 어울리는 추천이에요.";
}

export function ProposalCandidateCard({ candidate, selected, onToggle, onPreference }: { candidate: DirectorCandidate; selected: boolean; onToggle: (candidateId: string) => void; onPreference?: (kind: "pin_asset" | "exclude_asset" | "exclude_creator" | "exclude_tag", value: string) => void }) {
  const creator = typeof candidate.canonical_metadata.creator === "string" ? candidate.canonical_metadata.creator : "";
  const tag = Array.isArray(candidate.canonical_metadata.tags) && typeof candidate.canonical_metadata.tags[0] === "string" ? candidate.canonical_metadata.tags[0] : "";
  const referenceLabel = mediaReferenceLabel(candidate.visible_reference_code, "proposal");
  return <article aria-label={`${referenceLabel} 항목`}>
    <label><input aria-label={`${referenceLabel} 고르기`} type="checkbox" checked={selected} onChange={() => onToggle(candidate.candidate_id)} /><MediaReferenceBadge code={candidate.visible_reference_code} kind="proposal" /></label>
    <p>{recommendationReason(candidate.reason_chips)}</p>
    <p>{availabilityLabel(candidate.availability)} · {licenseLabel(candidate.license_policy)} · {reviewLabel(candidate.review_status)}</p>
    {candidate.warning_provenance.includes("copyright_confirmation_required") ? <p role="alert">사용하기 전에 이 미디어를 쓸 권리가 있는지 확인해 주세요.</p> : null}
    {onPreference ? <p><button type="button" onClick={() => onPreference("pin_asset", candidate.asset_id)}>이 추천 유지</button><button type="button" onClick={() => onPreference("exclude_asset", candidate.asset_id)}>이 미디어 빼기</button>{creator ? <button type="button" onClick={() => onPreference("exclude_creator", creator)}>이 제작자 빼기</button> : null}{tag ? <button type="button" onClick={() => onPreference("exclude_tag", tag)}>이 태그 빼기</button> : null}</p> : null}
  </article>;
}
