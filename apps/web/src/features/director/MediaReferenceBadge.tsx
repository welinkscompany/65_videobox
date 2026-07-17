type Props = { code: string; kind: "proposal" | "timeline" };

export function mediaReferenceLabel(code: string, kind: Props["kind"]) {
  const match = code.match(/^([A-Z]+\d*(?:-\d+)?)-([BMS])-(\d+)$/) ?? code.match(/^([BMS])-(\d+)$/);
  const prefixed = match?.length === 4;
  const mediaCode = prefixed ? match?.[2] : match?.[1];
  const index = prefixed ? match?.[3] : match?.[2];
  const media = mediaCode === "B" ? "비롤" : mediaCode === "M" ? "배경음악" : mediaCode === "S" ? "효과음" : "미디어";
  const proposalNumber = prefixed ? match?.[1].match(/\d+/)?.[0] : undefined;
  if (kind === "proposal") {
    if (proposalNumber && index) return `유진 추천 ${Number(proposalNumber)}의 ${media} ${Number(index)}번`;
    if (mediaCode && index) return `유진 추천의 ${media} ${Number(index)}번`;
    return "유진 추천 항목";
  }
  if (index) return `편집 순서의 ${media} ${Number(index)}번`;
  return "편집 순서의 항목";
}

export function MediaReferenceBadge({ code, kind }: Props) {
  const label = mediaReferenceLabel(code, kind);
  return <span aria-label={label} data-reference-kind={kind}>{label}</span>;
}
