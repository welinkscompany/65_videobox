import { useEffect, useState } from "react";

import { api, type CaptionStyleSnapshot, type EditorPreset } from "../../../api";
import { Button } from "../../../components/ui/button";

/** 저장된 모양을 화면 값으로 옮긴다.
 *
 * 백엔드 프리셋은 `font_size`, `text_color`, `font_family`로 온다. 아는 것만
 * 옮기고 나머지는 버린다 -- 지어내면 owner가 고르지 않은 모양이 적용된다.
 */
export function fromSnapshot(style: CaptionStyleSnapshot): Partial<Record<string, string | number>> {
  const numbers: Readonly<Record<string, string>> = {
    font_size: "fontSizePx",
    outline_width: "outlineWidthPx",
    position_x: "positionXPercent",
    position_y: "positionYPercent",
  };
  const strings: Readonly<Record<string, string>> = {
    font_family: "fontFamily",
    text_color: "textColor",
    outline_color: "outlineColor",
    background_color: "backgroundColor",
  };
  const mapped: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(style ?? {})) {
    if (key in numbers && typeof value === "number" && Number.isFinite(value)) {
      mapped[numbers[key]] = value;
    } else if (key in strings && typeof value === "string" && value) {
      mapped[strings[key]] = value;
    }
  }
  return mapped;
}

/** 저장된 자막 모양을 고르고, 자주 쓰는 것은 위에 둔다.
 *
 * 프리셋과 즐겨찾기 계약은 백엔드에 다 있었는데 부르는 화면이 없었다 --
 * `api.ts` 147개 메서드 중 31개가 화면 코드에 이름조차 없던 것 중 다섯 개가
 * 여기에 속한다.
 */
export function CaptionPresetPicker({
  projectId,
  onApply,
}: {
  projectId: string;
  onApply: (style: CaptionStyleSnapshot) => void | Promise<void>;
}) {
  const [presets, setPresets] = useState<readonly EditorPreset[]>([]);
  const [favourites, setFavourites] = useState<readonly string[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setReady(false);
    void Promise.all([api.listEditorPresets(projectId), api.listEditorFavorites(projectId)])
      .then(([list, favourite]) => {
        if (!active) return;
        setPresets(list);
        setFavourites(
          favourite.filter((item) => item.favorite_type === "preset").map((item) => item.favorite_id),
        );
      })
      .catch(() => { /* 모양을 못 읽어도 편집 자체를 막지 않는다 */ })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [projectId]);

  const toggle = async (presetId: string, enabled: boolean) => {
    const previous = favourites;
    setError(null);
    setFavourites((current) =>
      enabled ? [...current, presetId] : current.filter((item) => item !== presetId),
    );
    try {
      await api.toggleEditorFavorite(projectId, presetId, { favorite_type: "preset", enabled });
    } catch {
      setFavourites(previous);
      setError("즐겨찾기를 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    }
  };

  const apply = async (preset: EditorPreset) => {
    await onApply(preset.style);
    // 최근 쓴 것을 남기는 것은 편집을 막을 이유가 없다.
    try {
      await api.markRecentEditorPreset(projectId, preset.preset_id);
    } catch { /* 기록 실패가 적용을 되돌리지 않는다 */ }
  };

  // 즐겨찾기가 위로. 자주 쓰는 모양을 매번 찾아 내려가지 않게 하는 것이 뜻이다.
  const visible = presets.slice().sort((left, right) =>
    Number(favourites.includes(right.preset_id)) - Number(favourites.includes(left.preset_id)),
  );

  if (!ready) return null;
  return (
    <section className="vb-caption-presets" aria-labelledby="caption-presets-heading">
      <h3 id="caption-presets-heading">자막 모양</h3>
      {error ? <p role="status">{error}</p> : null}
      {visible.length ? visible.map((preset) => {
        const loved = favourites.includes(preset.preset_id);
        return (
          <article key={preset.preset_id} aria-label={`${preset.name} 자막 모양`}>
            <strong>{preset.name}</strong>
            <Button type="button" variant="outline" onClick={() => void apply(preset)}>
              {`${preset.name} 적용`}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => void toggle(preset.preset_id, !loved)}
            >
              {loved ? `${preset.name} 즐겨찾기 해제` : `${preset.name} 즐겨찾기`}
            </Button>
          </article>
        );
      }) : <p>아직 저장된 자막 모양이 없어요.</p>}
    </section>
  );
}
