import { useEffect, useState } from "react";

import { api, type CaptionFont } from "../../../api";
import { Button } from "../../../components/ui/button";
import { NativeSelect } from "../../../components/ui/native-select";
import { orderByFavouriteThenRecent } from "../../../lib/pickerOrder";

/** 설치된 글꼴 중에서 고른다.
 *
 * 예전에는 자유 입력이었다. owner가 아무 이름이나 칠 수 있었고, 없는 글꼴이면
 * 완성본이 조용히 다른 글꼴로 나왔다 -- 화면 기본값 `Pretendard`가 실제로
 * 그랬다. 목록은 백엔드가 아는 것 하나뿐이고 화면은 따로 들고 있지 않는다.
 *
 * 그 목록에는 **글꼴 파일이 실제로 있는 것만** 담겨 온다. 그래서 지금 쓰는
 * 글꼴이 목록에 없다면 그건 이 컴퓨터에 없다는 뜻이고, 그대로 두면 완성본만
 * 조용히 다른 글꼴로 나온다. 그때는 화면이 먼저 말한다.
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

  // 목록을 받아 왔는데 지금 쓰는 글꼴이 그 안에 없다 -- 이 컴퓨터에 그 글꼴이
  // 없다는 뜻이다. 말해 주지 않으면 owner는 완성본을 보고서야 알게 된다.
  const missingHere = fonts.length > 0 && !fonts.some((font) => font.family === value);
  // 즐겨찾기 단추가 부를 이름. 목록에 없는 글꼴이면 단추 자체를 안 만든다.
  const chosenFont = visible.find((font) => font.family === value) ?? null;

  return (
    <section className="vb-caption-fonts" aria-labelledby="caption-fonts-heading">
      <h3 id="caption-fonts-heading">글꼴</h3>
      {missingHere ? (
        <p role="status">지금 쓰는 글꼴이 이 컴퓨터에 없어요. 아래에서 하나 골라 주세요.</p>
      ) : null}
      {error ? <p role="status">{error}</p> : null}
      {/* **드롭다운 하나**(owner 지시 2026-09-04: "글자폰트도 다양한 무료
          폰트를 드롭다운으로 만들라고 했는데도 무시하고"). 예전에는 글꼴마다
          `고르기`·`즐겨찾기` 단추가 하나씩 붙어서, 실기에서 글꼴 15개에
          단추 30개·세로 260px을 먹고 있었다. 캡컷도 글꼴은 드롭다운이다.

          순서(즐겨찾기 → 최근 → 나머지)는 `orderByFavouriteThenRecent`가
          그대로 정한다 -- 드롭다운 안에서도 자주 쓰는 것이 위에 온다. */}
      {/* 이름은 위 h3가 이미 `글꼴`이라고 말한다. 숨김 라벨을 또 두면
          화면 낭독기가 같은 말을 두 번 하고, 시험에서도 어느 쪽인지 못 가린다. */}
      <div className="vb-caption-fonts__field">
        <NativeSelect
          aria-label="글꼴"
          disabled={disabled}
          onChange={(event) => choose(event.target.value)}
          value={value}
        >
          {visible.map((font) => (
            <option key={font.family} value={font.family}>
              {font.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      {/* 즐겨찾기는 **지금 고른 글꼴 하나**에만 붙인다. 목록이 드롭다운으로
          접히면서 글꼴마다 두던 단추는 갈 자리가 없어졌고, 실제로 즐겨찾기를
          누르는 순간은 "방금 고른 이것을 다음에도 위에 두고 싶다"일 때다. */}
      {fonts.length && chosenFont ? (
        <Button
          disabled={disabled}
          onClick={() => void toggle(chosenFont.family, !favourites.includes(chosenFont.family))}
          type="button"
          variant="outline"
        >
          {favourites.includes(chosenFont.family)
            ? `${chosenFont.label} 즐겨찾기 해제`
            : `${chosenFont.label} 즐겨찾기`}
        </Button>
      ) : null}
    </section>
  );
}
