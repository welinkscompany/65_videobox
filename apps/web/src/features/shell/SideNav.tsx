import { FolderOpen, Library, Settings, Clapperboard } from "lucide-react";

import { Button } from "../../components/ui/button";

/** 왼쪽 세로 메뉴 — 화면을 옮기는 자리 (owner 지시 2026-09-05).
 *
 *  2026-08-21에 왼쪽 기둥을 없애고 상단 띠 하나로 모았다. 2026-09-05에 캡컷과
 *  다시 대조해 보니 캡컷은 첫 화면 왼쪽에 메뉴가 **상시** 보이는데, 우리는
 *  상단의 접힌 `전체 메뉴` 하나뿐이었다 -- 자료실과 촬영본이 한 번 접힌 뒤에
 *  있었다.
 *
 *  **캡컷에 있는 항목을 흉내 내지 않는다**(`CLAUDE.md` §2.1). 캡컷 왼쪽에는
 *  `AI로 만들기`·`템플릿`·`공간` 같은 12항목이 있지만, 우리에게 실제로 있는
 *  자리는 넷이다. 없는 기능의 자리를 만들면 눌러 보고 아무 일도 안 일어난다.
 *
 *  **편집기에서는 이 띠를 그리지 않는다.** 그 자리는 편집 도구 띠(미디어·
 *  오디오·텍스트·캡션·전환)가 이미 쓰고 있고, 캡컷도 편집기에서는 화면 이동
 *  메뉴를 접는다. 두 줄이 나란히 서면 어느 쪽이 이동인지 알 수 없다.
 */
export type SideNavDestination = "projects" | "library" | "footage";

const ITEMS: ReadonlyArray<readonly [SideNavDestination, string, typeof FolderOpen]> = [
  ["projects", "프로젝트", FolderOpen],
  // 이름은 상단 `전체 메뉴`와 같은 것을 쓴다(owner 결정 2026-08-29) -- 한
  // 화면에서 같은 곳을 두 이름으로 부르면 다른 곳인 줄 안다.
  ["library", "자료실", Library],
  ["footage", "촬영본 정리", Clapperboard],
];

export function SideNav({
  current,
  onNavigateGlobal,
  onOpenSettings,
}: {
  /** 지금 보고 있는 자리. 해당하는 것이 없으면 아무것도 표시하지 않는다. */
  current: SideNavDestination | "settings" | null;
  onNavigateGlobal?: (destination: SideNavDestination) => void;
  onOpenSettings: () => void;
}) {
  return (
    <nav aria-label="화면 이동" className="vb-side-nav">
      {ITEMS.map(([destination, label, Icon]) => (
        <a
          key={destination}
          aria-current={current === destination ? "page" : undefined}
          className="vb-side-nav__item"
          href={`/${destination}`}
          onClick={(event) => {
            // **앱 안에서 이동한다**(owner 신고 2026-08-27). 맨 `<a href>`는
            // 페이지를 통째로 새로 열고, 그때 앱이 들고 있던 이력이 날아가
            // `이전 화면` 단추가 사라진다. 주소는 남겨 둔다 -- 북마크하고 새
            // 창으로 열 수 있어야 하므로, 평범한 왼쪽 클릭만 가로챈다.
            if (!onNavigateGlobal) return;
            if (event.defaultPrevented || event.button !== 0) return;
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            onNavigateGlobal(destination);
          }}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </a>
      ))}
      {/* 설정은 주소가 아니라 서랍이라 단추다. 아래로 밀어 두는 것은 캡컷과
          같은 무늬다 -- 자주 가는 곳이 위, 어쩌다 가는 곳이 아래. */}
      <Button
        aria-current={current === "settings" ? "page" : undefined}
        className="vb-side-nav__item vb-side-nav__item--settings"
        onClick={onOpenSettings}
        type="button"
        variant="ghost"
      >
        <Settings aria-hidden="true" />
        <span>설정</span>
      </Button>
    </nav>
  );
}
