import { useState, type ReactNode } from "react";
import { ChevronLeft, ClipboardCheck, Images, Menu, Scissors, Settings as SettingsIcon, Video } from "lucide-react";

import { type NavigationContext } from "../../app/routeManifest";
import { Button } from "../../components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/ui/tooltip";
import { shellCanvasLabel, type ShellCanvas } from "./shellCanvas";

/** 캡컷 배치의 위 띠. 왼쪽 기둥을 대신한다
 *  (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`).
 *
 *  **여기에는 우리가 실제로 하는 일만 올린다.** 캡컷과 똑같이 생긴 자리를 만들어
 *  두고 없는 기능을 걸어 두면 배치가 거짓말을 한다 — 익숙해서 쉬운 게 아니라
 *  익숙해서 더 헷갈리게 된다.
 *
 *  왼쪽 기둥이 없어지면서 거기 있던 것(단계 이동·프로젝트 전환·설정)이 조용히
 *  사라지지 않도록 전부 이리로 옮긴다. */
export type ShellSection = "create" | "media" | "editing" | "review";

type ShellProject = { project_id: string; name: string };

//: 일이 실제로 흐르는 순서. 대본을 쓰고, 재료를 모으고, 붙이고, 내보낸다.
const STAGES: ReadonlyArray<readonly [string, ShellSection, typeof Video]> = [
  ["이야기", "create", Video],
  ["재료", "media", Images],
  ["편집", "editing", Scissors],
  ["확인과 내보내기", "review", ClipboardCheck],
];

function CompactTooltip({ label, children }: { label: string; children: ReactNode }) {
  return <Tooltip>
    <TooltipTrigger asChild>{children}</TooltipTrigger>
    <TooltipContent side="bottom" sideOffset={6}>{label}</TooltipContent>
  </Tooltip>;
}

export function TopBar({
  projectId,
  projects,
  section,
  screenName,
  canvas,
  navigation,
  onBack,
  onNavigate,
  onSelectProject,
  onOpenSettings,
  children,
}: {
  projectId: string;
  projects: readonly ShellProject[];
  section: string;
  /** 지금 만들고 있는 초안의 크기. 아는 화면만 알려 주고, 모르면 비운다.
   *
   *  캡컷 위 툴바의 **화면 비율** 자리다. 다만 우리 것은 고르는 자리가 아니라
   *  **말하는 자리**다 -- 비율은 기획 화면에서 초안을 만들 때 정해지고 그 뒤로
   *  바꾸는 길이 없다. 자세한 이유는 `shellCanvas.tsx`. */
  canvas?: ShellCanvas | null;
  /** 어느 화면에서나 같은 방식으로 보이는 현재 위치와, 이력이 없을 때의 대체
   * 목적지다. 실제 뒤로가기는 껍데기가 받아 라우터에서 수행한다. */
  navigation?: NavigationContext;
  onBack?: () => void;
  /** 단계로 표시되지 않는 화면(내 라이브러리·촬영본 정리·설정·프로젝트 목록)에서
   *  **여기가 어디인지** 말하는 이름. 왼쪽 기둥 시절에는 머리말이 이걸 맡았고,
   *  전부 `홈`이라고 적혀 있으면 돌아갈 길이 있어도 자기 위치를 알 수 없다. */
  screenName?: string;
  onNavigate: (projectId: string, section: ShellSection) => void;
  onSelectProject: (projectId: string) => void;
  onOpenSettings: () => void;
  /** 작업 상태처럼 띠 오른쪽에 붙는 것. 껍데기가 그 내용을 알 필요는 없다. */
  children?: ReactNode;
}) {
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const current = projects.find((project) => project.project_id === projectId);
  const hasProject = Boolean(current);
  const others = projects.filter((project) => project.project_id !== projectId);
  const canvasLabel = shellCanvasLabel(canvas);

  // 한 단계가 여러 주소를 갖는다 -- 검토와 내보내기는 한 단계이고, 홈은 이야기에 속한다.
  const activeStage: ShellSection | null =
    section === "create" || section === "home" ? "create"
    : section === "media" ? "media"
    : section === "editing" || section === "editor" ? "editing"
    : section === "review" || section === "timeline" || section === "outputs" ? "review"
    : null;

  return <TooltipProvider delayDuration={350}>
    <header className="vb-top-bar">
      {navigation && onBack ? <CompactTooltip label="방금 보던 화면으로 돌아가기">
        <Button type="button" variant="outline" size="icon-sm" className="vb-top-bar__compact-control" aria-label="이전 화면" onClick={onBack}>
          <ChevronLeft aria-hidden="true" />
        </Button>
      </CompactTooltip> : null}
      {/* 기둥 머리에 있던 이름표. 캡컷도 여기에 로고를 둔다. */}
      <a className="vb-top-bar__brand" href="/projects" aria-label="프로젝트 목록으로">
        <Video aria-hidden="true" /><span>VideoBox</span>
      </a>

      {navigation ? <nav className="vb-top-bar__breadcrumb" aria-label="현재 위치">
        {navigation.crumbs.map((crumb, index) => <span key={`${crumb.label}:${index}`} className="vb-top-bar__breadcrumb-item">
          {crumb.href && index < navigation.crumbs.length - 1
            ? <a href={crumb.href}>{crumb.label}</a>
            : <span aria-current={index === navigation.crumbs.length - 1 ? "page" : undefined}>{crumb.label}</span>}
        </span>)}
      </nav> : null}

      {hasProject ? (
        <div className="vb-top-bar__project">
          <CompactTooltip label="다른 프로젝트 고르기">
            <Button type="button" variant="outline" size="sm" className="vb-top-bar__compact-control" aria-expanded={switcherOpen} onClick={() => setSwitcherOpen((open) => !open)}>
            {current?.name}
            </Button>
          </CompactTooltip>
          {switcherOpen && others.length ? (
            <div className="vb-top-bar__switcher" role="group" aria-label="다른 프로젝트">
              {others.map((project) => (
                <Button
                  key={project.project_id}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => { setSwitcherOpen(false); onSelectProject(project.project_id); }}
                >
                  {project.name}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {hasProject ? (
        <nav aria-label="프로젝트 단계" className="vb-top-bar__stages">
          {STAGES.map(([label, target, Icon]) => (
            <Button
              key={target}
              type="button"
              variant={activeStage === target ? "default" : "outline"}
              size="sm"
              className="vb-top-bar__compact-control"
              aria-current={activeStage === target ? "page" : undefined}
              onClick={() => onNavigate(projectId, target)}
            >
              <Icon aria-hidden="true" />
              {label}
            </Button>
          ))}
        </nav>
      ) : null}

      {/* 단계가 그려지지 않거나 어느 단계도 아닌 화면에서만 이름을 말한다. 단계가
          보일 때는 켜진 단계 단추가 이미 그 말을 하고 있고, 같은 사실을 두 번
          적으면 첫 화면에 "누를 것처럼 보이는 것"이 또 하나 늘어난다. */}
      {screenName && (!hasProject || activeStage === null) ? (
        <strong className="vb-top-bar__screen">{screenName}</strong>
      ) : null}

      <div className="vb-top-bar__end">
        {/* 캡컷 위 툴바의 화면 비율 자리. **단추가 아니라 글자다** -- 우리는 여기서
            비율을 바꾸지 않는다. 지금 이 초안이 어떤 모양으로 나오는지만 말한다.
            `top-bar.test.tsx`가 이게 단추가 되지 않도록 잡고 있다. */}
        {canvasLabel ? <small className="vb-top-bar__canvas">{canvasLabel}</small> : null}
        {children}
        {/* 왼쪽 기둥에 있던 **전체 메뉴 4개**가 여기로 온다. 빼먹으면 내 라이브러리와
            촬영본 정리가 갈 수 없는 곳이 된다 -- 기둥을 없애는 변경에서 가장 흔한 사고다.
            띠에 네 개를 그대로 늘어놓으면 다시 목록이 되므로 한 겹 접어 둔다. */}
        <div className="vb-top-bar__menu">
          <CompactTooltip label="프로젝트와 도구 메뉴 열기">
            <Button type="button" variant="outline" size="icon-sm" className="vb-top-bar__compact-control" aria-expanded={menuOpen} aria-label="전체 메뉴" onClick={() => setMenuOpen((open) => !open)}>
              <Menu aria-hidden="true" />
            </Button>
          </CompactTooltip>
          {menuOpen ? (
            <nav aria-label="전체 메뉴" className="vb-top-bar__menu-list">
              <a href="/projects">프로젝트</a>
              <a href="/library">내 라이브러리</a>
              <a href="/footage">촬영본 정리</a>
              <Button type="button" variant="outline" size="sm" onClick={() => { setMenuOpen(false); onOpenSettings(); }}>
                <SettingsIcon aria-hidden="true" />
                설정
              </Button>
            </nav>
          ) : null}
        </div>
      </div>
    </header>
  </TooltipProvider>;
}
