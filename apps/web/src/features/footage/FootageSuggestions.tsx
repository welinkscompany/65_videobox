const starters = ["장면 변화로 나누기", "출근 과정만 고르기", "흔들린 구간 찾기", "짧은 영상 묶기", "세로 장면 고르기", "30초 묶음 만들기"];

type Props = { value: string; onChange: (value: string) => void };

export function FootageSuggestions({ value, onChange }: Props) {
  return <aside className="vb-footage-pane vb-footage-suggestions" data-testid="footage-suggestions"><div className="vb-footage-pane__heading"><div><p className="vb-eyebrow">SUGGESTIONS</p><h2>정리 도우미</h2></div></div><label className="vb-footage-request">정리 요청<Input aria-label="정리 요청" value={value} onChange={(event) => onChange(event.target.value)} placeholder="원하는 정리 방법을 적어보세요" /></label><div className="vb-footage-starters"><p>빠른 시작</p>{starters.map((starter) => <Button key={starter} type="button" variant="outline" onClick={() => onChange(starter)}>{starter}</Button>)}</div><p className="vb-footage-helper">제안은 원본을 바꾸지 않아요. 결과를 확인한 뒤 적용할 수 있어요.</p></aside>;
}
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
