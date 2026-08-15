import { useMemo, useState } from "react";

import { Button } from "../../components/ui/button";
import {
  getYujinStarters,
  readYujinStarterUsage,
  recordYujinStarterUse,
  type YujinStarter,
  type YujinStarterContext,
} from "./starterRegistry";

const PAGE_SIZE = 4;

export type YujinStartersProps = Readonly<{
  context: YujinStarterContext;
  onSelect: (starter: YujinStarter) => void;
  disabled?: boolean;
  heading?: string;
  className?: string;
  showAllByDefault?: boolean;
}>;

export function YujinStarters({
  context,
  onSelect,
  disabled = false,
  heading = "무엇을 도와드릴까요?",
  className = "",
  showAllByDefault = false,
}: YujinStartersProps) {
  const [page, setPage] = useState(0);
  const [showAll, setShowAll] = useState(showAllByDefault);
  const [usageVersion, setUsageVersion] = useState(0);
  const starters = useMemo(() => getYujinStarters({
    ...context,
    includeRelated: true,
    recentUsage: {
      ...readYujinStarterUsage(),
      ...context.recentUsage,
    },
  }), [context, usageVersion]);
  if (!starters.length) return null;

  const maxPage = Math.max(0, Math.ceil(starters.length / PAGE_SIZE) - 1);
  const visibleStarters = showAll
    ? starters
    : starters.slice((page % (maxPage + 1)) * PAGE_SIZE, (page % (maxPage + 1)) * PAGE_SIZE + PAGE_SIZE);

  const choose = (starter: YujinStarter) => {
    recordYujinStarterUse(starter.id);
    setUsageVersion((version) => version + 1);
    onSelect(starter);
  };

  return (
    <div role="group" aria-label="대화 스타터" className={`vb-yujin-starters ${className}`.trim()}>
      <h3>{heading}</h3>
      <span>스타터를 누르면 요청 문장이 입력창에 채워져요.</span>
      <div className="vb-yujin-starters__list">
        {visibleStarters.map((starter) => (
          <Button
            key={starter.id}
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() => choose(starter)}
          >{starter.label}</Button>
        ))}
      </div>
      <div className="vb-yujin-starters__controls">
        <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={() => {
          setShowAll(false);
          setPage((current) => (current + 1) % (maxPage + 1));
        }}>다른 예시</Button>
        <Button type="button" variant="ghost" size="sm" disabled={disabled} aria-expanded={showAll} onClick={() => setShowAll((current) => !current)}>
          {showAll ? "간단히 보기" : "전체 보기"}
        </Button>
      </div>
    </div>
  );
}
