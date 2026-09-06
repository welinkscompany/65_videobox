import { useState, type MouseEvent } from "react";
import { Clapperboard, FolderOpen, Library, Mic, Music, Settings, Video } from "lucide-react";

import { resolveLibraryKind, type LibraryKind } from "../../app/routeManifest";
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

/** **`내 자산` 구역**(owner 승인 2026-09-04
 *  `docs/decisions/2026-09-04-capcut-shell-with-my-assets.ko.md` §2,
 *  착수 지시 2026-09-07). 캡컷 왼쪽의 `AI로 만들기` 자리다.
 *
 *  승인 문서는 `내 B-roll`이라고 적었지만 **낱말은 나중 승인을 따른다** --
 *  2026-09-07에 화면에서 `B-roll`을 없애고 `영상`으로 통일하는 것이 승인됐고
 *  (`109e75b19`), 자료실 분류 목록도 이미 `영상`이다. 승인된 구조는 그대로다.
 *
 *  **여기에 새 화면은 없다.** 세 자리 중 둘은 자료실(`/library`)을 종류를
 *  정한 채로 여는 문이다 -- 새 화면을 만들면 의미검색·휴지통·사용처 검사를
 *  또 만들어야 하고, 그 순간 자료실과 여기가 다른 곳이 된다.
 *
 *  **`자료실`은 위에 그대로 둔다.** 여기 둘은 자료실의 갈래일 뿐이고,
 *  그림·즐겨찾기·휴지통과 파일을 넣는 자리는 자료실에만 있다. 이름도 한
 *  화면에서 하나씩만 쓴다 -- `자료실`은 `자료실`, 갈래는 자료실 분류 목록과
 *  같은 말(`영상`·`음악·효과음`)로 부른다.
 */
const ASSET_ITEMS: ReadonlyArray<readonly [LibraryKind, string, typeof FolderOpen]> = [
  ["broll", "내 영상", Video],
  ["audio", "음악·효과음", Music],
];

/** 목소리 보관함 뒷단은 아직 만드는 중이다. 자리는 승인된 구조대로 두되
 *  **못 쓴다는 것을 눌러 보기 전에 말한다** -- 아무 일도 안 일어나는 단추가
 *  이 저장소가 이미 한 번 고친 결함이다. 개발 용어는 쓰지 않는다(`§8`). */
const VOICE_NOTE = "내 목소리 보관함은 아직 준비 중이에요. 준비되면 여기에서 바로 열 수 있어요.";

/** 평범한 왼쪽 클릭만 가로챈다. 주소는 남겨 둔다 -- 북마크하고 새 창으로
 *  열 수 있어야 한다. 앱 안에서 옮기지 않으면 페이지가 통째로 새로 열리고,
 *  그때 앱이 들고 있던 이력이 날아가 `이전 화면` 단추가 사라진다
 *  (owner 신고 2026-08-27). */
function isPlainLeftClick(event: MouseEvent) {
  if (event.defaultPrevented || event.button !== 0) return false;
  return !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey);
}

export function SideNav({
  current,
  assetKind = null,
  onNavigateGlobal,
  onOpenSettings,
}: {
  /** 지금 보고 있는 자리. 해당하는 것이 없으면 아무것도 표시하지 않는다. */
  current: SideNavDestination | "settings" | null;
  /** 자료실을 갈래로 열었으면 그 갈래. **한 자리만 "여기"라고 말하기 위해**
   *  필요하다 -- 이게 없으면 `자료실`과 `내 영상`이 동시에 선택돼 보인다. */
  assetKind?: LibraryKind | null;
  onNavigateGlobal?: (destination: SideNavDestination, kind?: LibraryKind) => void;
  onOpenSettings: () => void;
}) {
  const [voiceNoteOpen, setVoiceNoteOpen] = useState(false);
  return (
    <nav aria-label="화면 이동" className="vb-side-nav">
      {ITEMS.map(([destination, label, Icon]) => (
        <a
          key={destination}
          aria-current={current === destination && !(destination === "library" && assetKind) ? "page" : undefined}
          className="vb-side-nav__item"
          href={`/${destination}`}
          onClick={(event) => {
            if (!onNavigateGlobal) return;
            if (!isPlainLeftClick(event)) return;
            event.preventDefault();
            onNavigateGlobal(destination);
          }}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </a>
      ))}
      <div className="vb-side-nav__group" role="group" aria-label="내 자산">
        {/* 구역 이름은 읽는 자리 이름이 이미 `내 자산`이라 화면에만 남긴다 --
            소리로 두 번 읽으면 항목마다 `내 자산 내 영상`이 된다. */}
        <p aria-hidden="true" className="vb-side-nav__group-label">내 자산</p>
        {ASSET_ITEMS.map(([kind, label, Icon]) => (
          <a
            key={kind}
            aria-current={current === "library" && assetKind === kind ? "page" : undefined}
            className="vb-side-nav__item"
            href={resolveLibraryKind(kind)}
            onClick={(event) => {
              if (!onNavigateGlobal) return;
              if (!isPlainLeftClick(event)) return;
              event.preventDefault();
              onNavigateGlobal("library", kind);
            }}
          >
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </a>
        ))}
        <Button
          aria-disabled="true"
          className="vb-side-nav__item vb-side-nav__item--waiting"
          onClick={() => setVoiceNoteOpen(true)}
          type="button"
          variant="ghost"
        >
          <Mic aria-hidden="true" />
          <span>내 목소리</span>
          <small className="vb-side-nav__waiting-badge">준비 중</small>
        </Button>
        {voiceNoteOpen ? <p className="vb-side-nav__note" role="status">{VOICE_NOTE}</p> : null}
      </div>
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
