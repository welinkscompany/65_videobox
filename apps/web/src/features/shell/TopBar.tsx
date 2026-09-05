import { useState, type KeyboardEvent, type ReactNode } from "react";
import { ChevronLeft, ClipboardCheck, Menu, Scissors, Settings as SettingsIcon, Video } from "lucide-react";

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

const globalMenuItems: ReadonlyArray<readonly ["projects" | "library" | "footage", string]> = [
  ["projects", "프로젝트"],
  // **전체 메뉴만 새 이름(owner 결정 2026-08-29).** 프로젝트 넘나드는 공용
  // 라이브러리라 프로젝트 단계 탭·편집기 도크 탭의 "미디어"와 한 화면에 같이
  // 보이면 다시 헷갈린다 -- 그 둘은 그대로 "미디어"로 두고 이 자리만 바꾼다.
  ["library", "자료실"],
  ["footage", "촬영본 정리"],
];

//: 일이 실제로 흐르는 순서. 대본을 쓰고, 붙이고, 내보낸다.
//
//  **"미디어" 단계 단추는 뺐다(2026-09-01).** 독립 미디어 화면이 편집기
//  도크 탭으로 접히면서(2026-08-27 결정 §순서 2 실행) 더는 따로 갈 화면이
//  아니다 -- 편집기를 열면 그 도크가 이미 미디어 탭 기본값이다. 캡컷에도
//  이런 중간 단계가 없다.
//  → `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md`
//  → `docs/decisions/2026-08-30-capcut-button-level-parity.ko.md` 9단계
const STAGES: ReadonlyArray<readonly [string, ShellSection, typeof Video]> = [
  ["이야기", "create", Video],
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
  onNavigateGlobal,
  hideGlobalMenu = false,
  onResumeEditor,
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
  /** 전역 화면으로 앱 안에서 이동한다. 없으면 주소 링크가 그대로 동작한다. */
  onNavigateGlobal?: (destination: "projects" | "library" | "footage") => void;
  /** 왼쪽 세로 띠가 같은 자리를 이미 보여 주는 화면에서는 접는다 --
   *  같은 기능이 화면에 둘 있으면 낭독기가 두 번 읽고, 눌러 보고 다른 것인 줄 안다. */
  hideGlobalMenu?: boolean;
  /** 마지막으로 편집하던 곳으로 돌아간다. **돌아갈 곳을 모르면 주지 않는다** --
   *  없는 길을 흉내 내면 눌렀을 때 빈 화면이 뜬다. */
  onResumeEditor?: () => void;
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
  // `media`는 이제 단계 띠에 없다(2026-09-01, 독립 화면이 편집기로 접혔다) --
  // 여전히 `DraftGapMedia`(갭 채우기 흐름)가 이 section을 쓰지만, 그 화면은
  // 더 이상 단계 하나가 아니라서 어떤 단추도 켜지 않는다(아래 `screenName`이
  // 대신 "미디어"라고 말해 준다).
  const activeStage: ShellSection | null =
    section === "create" || section === "home" ? "create"
    : section === "editing" || section === "editor" ? "editing"
    : section === "review" || section === "timeline" || section === "outputs" ? "review"
    : null;
  const closeOverlaysOnEscape = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Escape") return;
    // 접힌 목록은 열기만큼 닫기도 한 번에 되어야 한다. 메뉴 안의 링크를 눌러
    // 이동하지 않고 둘러본 창작자도 키보드로 현재 화면으로 돌아올 수 있다.
    if (!menuOpen && !switcherOpen) return;
    event.preventDefault();
    setMenuOpen(false);
    setSwitcherOpen(false);
  };

  return <TooltipProvider delayDuration={350}>
    <header className="vb-top-bar" onKeyDown={closeOverlaysOnEscape}>
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
      {screenName && !navigation && (!hasProject || activeStage === null) ? (
        <strong className="vb-top-bar__screen">{screenName}</strong>
      ) : null}

      {/* **편집기로 돌아가는 길(owner 결정 2026-08-27).**
          > "그리고 편집기 화면 바로가기가 없고"

          프로젝트에 매이지 않는 화면(`/projects`·`/library`·`/footage`)에서는 단계
          단추가 안 그려진다. 그래서 편집기로 돌아가려면 프로젝트 카드를 다시 찾아
          눌러야 했다. 캡컷도 편집기가 중심이라 한 번에 돌아갈 수 있어야 한다.

          **프로젝트 안에서는 두지 않는다** -- 단계의 `편집`이 이미 그 일을 하고,
          같은 곳으로 가는 문이 둘이 되면 owner를 막았던 문제를 띠에서 되풀이한다. */}
      {!hasProject && onResumeEditor ? <CompactTooltip label="마지막으로 편집하던 곳으로">
        <Button type="button" variant="outline" size="sm" className="vb-top-bar__compact-control" aria-label="편집기로 돌아가기" onClick={onResumeEditor}>
          <Scissors aria-hidden="true" />
        </Button>
      </CompactTooltip> : null}

      <div className="vb-top-bar__end">
        {/* 캡컷 위 툴바의 화면 비율 자리. **단추가 아니라 글자다** -- 우리는 여기서
            비율을 바꾸지 않는다. 지금 이 초안이 어떤 모양으로 나오는지만 말한다.
            `top-bar.test.tsx`가 이게 단추가 되지 않도록 잡고 있다. */}
        {canvasLabel ? <small className="vb-top-bar__canvas">{canvasLabel}</small> : null}
        {children}
        {/* 왼쪽 기둥에 있던 **전체 메뉴 4개**가 여기로 온다. 빼먹으면 내 라이브러리와
            촬영본 정리가 갈 수 없는 곳이 된다 -- 기둥을 없애는 변경에서 가장 흔한 사고다.
            띠에 네 개를 그대로 늘어놓으면 다시 목록이 되므로 한 겹 접어 둔다. */}
        {hideGlobalMenu ? null : <div className="vb-top-bar__menu">
          <CompactTooltip label="프로젝트와 도구 메뉴 열기">
            <Button type="button" variant="outline" size="icon-sm" className="vb-top-bar__compact-control" aria-expanded={menuOpen} aria-label="전체 메뉴" onClick={() => setMenuOpen((open) => !open)}>
              <Menu aria-hidden="true" />
            </Button>
          </CompactTooltip>
          {menuOpen ? (
            <nav aria-label="전체 메뉴" className="vb-top-bar__menu-list">
              {/* **앱 안에서 이동한다(owner 신고 2026-08-27).**
                  > "프로젝트 메뉴나 다른메뉴에 들어가면 다시 설정 버튼을 누르지
                  >  않는이상 뒤로가기가 안되"

                  맨 `<a href>`라 눌리면 페이지를 통째로 새로 열었고, 그때 앱이
                  들고 있던 이력이 날아가 `이전 화면` 단추가 **아예 사라졌다**
                  (실측: `/projects`에서 단추 없음, 브라우저 이력은 4개).
                  설정만 멀쩡했던 이유도 같다 -- 그것만 콜백으로 이동했다.

                  **주소는 그대로 둔다.** 사람이 북마크하고 새 창으로 열 수 있어야
                  하므로 `href`는 남기고, 평범한 왼쪽 클릭만 가로채 라우터에 넘긴다.
                  새 창(Ctrl/Cmd·가운데 클릭)은 브라우저가 하던 대로 둔다. */}
              {globalMenuItems.map(([destination, label]) => (
                <a
                  key={destination}
                  href={`/${destination}`}
                  onClick={(event) => {
                    if (!onNavigateGlobal) return;
                    if (event.defaultPrevented || event.button !== 0) return;
                    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                    event.preventDefault();
                    setMenuOpen(false);
                    onNavigateGlobal(destination);
                  }}
                >
                  {label}
                </a>
              ))}
              <Button type="button" variant="outline" size="sm" onClick={() => { setMenuOpen(false); onOpenSettings(); }}>
                <SettingsIcon aria-hidden="true" />
                설정
              </Button>
            </nav>
          ) : null}
        </div>}
      </div>
    </header>
  </TooltipProvider>;
}
