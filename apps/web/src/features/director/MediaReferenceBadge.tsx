type Props = { code: string; kind: "proposal" | "timeline" };

function koreanLabel(code: string, kind: Props["kind"]) {
  const match = code.match(/^(?:P(\d+)-)?([BMS])-(\d+)$/);
  const media = match?.[2] === "B" ? "비롤" : match?.[2] === "M" ? "배경음악" : "효과음";
  const index = match?.[3] ? Number(match[3]) : code;
  return kind === "proposal" && match?.[1] ? `제안 ${Number(match[1])}의 ${media} 후보 ${index}번` : `타임라인 ${media} 배치 ${index}번`;
}

export function MediaReferenceBadge({ code, kind }: Props) {
  return <span aria-label={koreanLabel(code, kind)} data-reference-kind={kind}>{code}</span>;
}
