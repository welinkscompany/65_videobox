import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { YujinStarters } from "../yujin/YujinStarters";

type Props = { value: string; onChange: (value: string) => void; onInterpret: () => void; disabled?: boolean };

export function FootageSuggestions({ value, onChange, onInterpret, disabled }: Props) {
  return <aside className="vb-footage-pane vb-footage-suggestions" data-testid="footage-suggestions"><div className="vb-footage-pane__heading"><div><p className="vb-eyebrow">유진 도움</p><h2>정리 도우미</h2></div></div><label className="vb-footage-request">정리 요청<Input className="vb-footage-request__input h-8 rounded-2xl border-transparent bg-input/50 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30" aria-label="정리 요청" value={value} onChange={(event) => onChange(event.target.value)} placeholder="원하는 정리 방법을 적어보세요" /></label><Button className="vb-footage-yujin-request" type="button" variant="outline" onClick={onInterpret} disabled={disabled || !value.trim()}>유진에게 제안 요청</Button><YujinStarters className="vb-footage-starters" context={{ surface: "footage", selection: "none" }} heading="빠른 시작" showAllByDefault onSelect={(starter) => onChange(starter.label)} /><p className="vb-footage-helper">제안은 원본을 바꾸지 않아요. 결과를 확인한 뒤 적용할 수 있어요.</p></aside>;
}
