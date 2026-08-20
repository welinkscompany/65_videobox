import { useEffect, useState } from "react";

import { api, type CaptionFont } from "../../../api";
import { Button } from "../../../components/ui/button";
import { orderByFavouriteThenRecent } from "../../../lib/pickerOrder";

/** 설치된 글꼴 중에서 고른다.
 *
 * 예전에는 자유 입력이었다. owner가 아무 이름이나 칠 수 있었고, 없는 글꼴이면
 * 완성본이 조용히 다른 글꼴로 나왔다 -- 화면 기본값 `Pretendard`가 실제로
 * 그랬다. 목록은 백엔드가 아는 것 하나뿐이고 화면은 따로 들고 있지 않는다.
 *
 * 정렬은 자막 모양 고르기와 같은 규칙을 쓴다(`orderByFavouriteThenRecent`).
 * 즐겨찾기가 맨 위, 그다음이 최근에 쓴 것이다.
 */
export function CaptionFontPicker({
  value,
  onSelect,
  disabled,
}: {
  /** 지금 잡혀 있는 글꼴. */
  value: string;
  onSelect: (family: string) => void;
  disabled?: boolean;
}) {
  const [fonts, setFonts] = useState<readonly CaptionFont[]>([]);
  const [favourites, setFavourites] = useState<readonly string[]>([]);
  const [recents, setRecents] = useState<readonly string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    // 목록·즐겨찾기·최근이 한 번에 온다. 나눠 부르면 그중 하나만 실패해도
    // 글꼴을 아예 못 고른다.
    void api.listCaptionFonts()
      .then((library) => {
        if (!active) return;
        setFonts(library.fonts);
        setFavourites(library.favorites);
        setRecents(library.recents);
      })
      .catch(() => { /* 목록을 못 읽어도 편집 자체를 막지 않는다 */ });
    return () => { active = false; };
  }, []);

  const choose = (family: string) => {
    onSelect(family);
    // 최근에 쓴 것을 남기는 것은 고르기를 되돌릴 이유가 아니다.
    void api.markRecentCaptionFont(family)
      .then((updated) => setRecents(updated.recents))
      .catch(() => { /* 다음 순서만 덜 똑똑해진다 */ });
  };

  const toggle = async (family: string, enabled: boolean) => {
    const previous = favourites;
    setError(null);
    setFavourites((current) =>
      enabled ? [...current, family] : current.filter((item) => item !== family),
    );
    try {
      await api.toggleCaptionFontFavorite(family, enabled);
    } catch {
      setFavourites(previous);
      setError("즐겨찾기를 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    }
  };

  // 목록을 못 읽었어도 지금 쓰는 글꼴은 보여 준다. 빈 화면은 owner에게
  // "글꼴이 사라졌다"로 보인다.
  const visible = orderByFavouriteThenRecent(
    fonts.length ? fonts : [{ family: value, label: value, group: "" }],
    (font) => font.family,
    favourites,
    recents,
  );

  return (
    <section className="vb-caption-fonts" aria-labelledby="caption-fonts-heading">
      <h3 id="caption-fonts-heading">글꼴</h3>
      {error ? <p role="status">{error}</p> : null}
      <ul>
        {visible.map((font) => {
          const loved = favourites.includes(font.family);
          const chosen = font.family === value;
          return (
            <li key={font.family}>
              <span>{font.label}</span>
              {font.group ? <span>{font.group}</span> : null}
              {chosen ? <span>지금 쓰는 글꼴</span> : null}
              {!loved && recents.includes(font.family) ? <span>최근에 썼어요</span> : null}
              <Button
                disabled={disabled}
                onClick={() => choose(font.family)}
                type="button"
                variant="outline"
              >
                {`${font.label} 고르기`}
              </Button>
              {fonts.length ? (
                <Button
                  disabled={disabled}
                  onClick={() => void toggle(font.family, !loved)}
                  type="button"
                  variant="outline"
                >
                  {loved ? `${font.label} 즐겨찾기 해제` : `${font.label} 즐겨찾기`}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
