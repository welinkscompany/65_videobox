import { useState, type ReactNode } from "react";
import { ClipboardCheck, Images, Menu, Scissors, Settings as SettingsIcon, Video } from "lucide-react";

import { Button } from "../../components/ui/button";

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

export function TopBar({
  projectId,
  projects,
  section,
  onNavigate,
  onSelectProject,
  onOpenSettings,
  children,
}: {
  projectId: string;
  projects: readonly ShellProject[];
  section: string;
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

  // 한 단계가 여러 주소를 갖는다 -- 검토와 내보내기는 한 단계이고, 홈은 이야기에 속한다.
  const activeStage: ShellSection | null =
    section === "create" || section === "home" ? "create"
    : section === "media" ? "media"
    : section === "editing" || section === "editor" ? "editing"
    : section === "review" || section === "timeline" || section === "outputs" ? "review"
    : null;

  return (
    <header className="vb-top-bar">
      {hasProject ? (
        <div className="vb-top-bar__project">
          <Button type="button" variant="outline" aria-expanded={switcherOpen} onClick={() => setSwitcherOpen((open) => !open)}>
            {current?.name}
          </Button>
          {switcherOpen && others.length ? (
            <div className="vb-top-bar__switcher" role="group" aria-label="다른 프로젝트">
              {others.map((project) => (
                <Button
                  key={project.project_id}
                  type="button"
                  variant="outline"
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
              aria-current={activeStage === target ? "page" : undefined}
              onClick={() => onNavigate(projectId, target)}
            >
              <Icon aria-hidden="true" />
              {label}
            </Button>
          ))}
        </nav>
      ) : null}

      <div className="vb-top-bar__end">
        {children}
        {/* 왼쪽 기둥에 있던 **전체 메뉴 4개**가 여기로 온다. 빼먹으면 내 라이브러리와
            촬영본 정리가 갈 수 없는 곳이 된다 -- 기둥을 없애는 변경에서 가장 흔한 사고다.
            띠에 네 개를 그대로 늘어놓으면 다시 목록이 되므로 한 겹 접어 둔다. */}
        <div className="vb-top-bar__menu">
          <Button type="button" variant="outline" aria-expanded={menuOpen} aria-label="전체 메뉴" onClick={() => setMenuOpen((open) => !open)}>
            <Menu aria-hidden="true" />
          </Button>
          {menuOpen ? (
            <nav aria-label="전체 메뉴" className="vb-top-bar__menu-list">
              <a href="/projects">프로젝트</a>
              <a href="/library">내 라이브러리</a>
              <a href="/footage">촬영본 정리</a>
              <Button type="button" variant="outline" onClick={() => { setMenuOpen(false); onOpenSettings(); }}>
                <SettingsIcon aria-hidden="true" />
                설정
              </Button>
            </nav>
          ) : null}
        </div>
      </div>
    </header>
  );
}
