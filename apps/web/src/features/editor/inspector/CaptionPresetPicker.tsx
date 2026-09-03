import { useEffect, useState } from "react";

import { api, type CaptionStyleSnapshot, type EditorPreset } from "../../../api";
import { Button } from "../../../components/ui/button";
import { orderByFavouriteThenRecent } from "../../../lib/pickerOrder";

/** 저장된 모양을 화면 값으로 옮긴다.
 *
 * 두 가지 스냅샷 이름을 안다: 내장 프리셋의 짧은 이름(`font_size`)과, 편집본·
 * 저장한 포맷이 그대로 떠 오는 정본 이름(`font_size_px` 같은 `_px`·`_percent`).
 * 정본 이름을 모르면 포맷을 적용해도 글자 크기·두께·위치가 조용히 빠진다.
 * 그 밖의 모르는 것은 버린다 -- 지어내면 owner가 고르지 않은 모양이 적용된다.
 */
export function fromSnapshot(style: CaptionStyleSnapshot): Partial<Record<string, string | number | boolean>> {
  const numbers: Readonly<Record<string, string>> = {
    font_size: "fontSizePx",
    font_size_px: "fontSizePx",
    outline_width: "outlineWidthPx",
    outline_width_px: "outlineWidthPx",
    position_x: "positionXPercent",
    position_x_percent: "positionXPercent",
    position_y: "positionYPercent",
    position_y_percent: "positionYPercent",
    shadow_blur_px: "shadowBlurPx",
    letter_spacing_px: "letterSpacingPx",
  };
  const strings: Readonly<Record<string, string>> = {
    font_family: "fontFamily",
    text_color: "textColor",
    outline_color: "outlineColor",
    background_color: "backgroundColor",
    horizontal_align: "horizontalAlign",
  };
  const booleans: Readonly<Record<string, string>> = {
    safe_area_enabled: "safeAreaEnabled",
    bold: "bold",
    italic: "italic",
  };
  const mapped: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(style ?? {})) {
    if (key in numbers && typeof value === "number" && Number.isFinite(value)) {
      mapped[numbers[key]] = value;
    } else if (key in strings && typeof value === "string" && value) {
      // 백엔드는 정렬을 left·center·right만 받는다. 다른 값을 화면에 넣으면
      // 다음 저장이 422로 거부돼 되돌릴 길이 없다.
      if (key === "horizontal_align" && !["left", "center", "right"].includes(value)) continue;
      mapped[strings[key]] = value;
    } else if (key in booleans && typeof value === "boolean") {
      mapped[booleans[key]] = value;
    }
  }
  return mapped;
}

/** 즐겨찾기가 되는 모양인지.
 *
 * 저장소는 `project:` 또는 `pack:` 으로 시작하는 것만 받는다. 내장 모양에
 * 버튼을 띄우면 눌러도 422로 실패한다 -- 화면이 못 하는 일을 권하는 셈이다.
 */
export function canFavourite(presetId: string, projectId: string): boolean {
  return presetId.startsWith(`project:${projectId}:`) || presetId.startsWith("pack:");
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
  currentStyle,
}: {
  projectId: string;
  onApply: (style: CaptionStyleSnapshot) => void | Promise<void>;
  /** 지금 화면에 잡혀 있는 모양. 이것을 저장해야 즐겨찾기가 걸 것이 생긴다. */
  currentStyle?: CaptionStyleSnapshot;
}) {
  const [presets, setPresets] = useState<readonly EditorPreset[]>([]);
  const [favourites, setFavourites] = useState<readonly string[]>([]);
  const [recents, setRecents] = useState<readonly string[]>([]);
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
    // 최근 쓴 모양은 이미 적용할 때마다 기록되고 있었는데 아무도 다시 읽지
    // 않았다. 못 읽더라도 즐겨찾기 정렬은 그대로 돌아야 한다.
    void api.listRecentEditorPresetIds(projectId)
      .then((recent) => { if (active) setRecents(recent); })
      .catch(() => { /* 순서만 덜 똑똑해질 뿐이다 */ });
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
      setRecents(await api.markRecentEditorPreset(projectId, preset.preset_id));
    } catch { /* 기록 실패가 적용을 되돌리지 않는다 */ }
  };

  // 지금 모양을 프리셋으로 남긴다. **`project:`로 시작해야** 즐겨찾기를 걸 수
  // 있다(`canFavourite`). 이 한 칸이 없어서 프리셋이 내장 둘로 고정돼 있었고,
  // 즐겨찾기 기능 전체가 걸 대상 없이 놀고 있었다.
  const keepCurrent = async () => {
    if (!currentStyle) return;
    setError(null);
    const ordinal = presets.filter((preset) => preset.preset_id.startsWith(`project:${projectId}:`)).length + 1;
    try {
      // 스냅샷 이름 그대로 저장한다. 화면 이름(camelCase)으로 바꿔 저장하면
      // 적용할 때 `fromSnapshot`이 아무것도 알아보지 못해 왕복이 끊긴다.
      const saved = await api.saveEditorPreset(projectId, `project:${projectId}:${ordinal}`, {
        name: `내 모양 ${ordinal}`,
        style: currentStyle as Record<string, unknown>,
      });
      setPresets((current) => [...current.filter((preset) => preset.preset_id !== saved.preset_id), saved]);
    } catch {
      setError("이 모양을 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    }
  };

  // 즐겨찾기가 위로, 그다음이 최근에 쓴 것. 자주 쓰는 모양을 매번 찾아
  // 내려가지 않게 하는 것이 뜻이다.
  const visible = orderByFavouriteThenRecent(
    presets,
    (preset) => preset.preset_id,
    favourites,
    recents,
  );

  if (!ready) return null;
  return (
    <section className="vb-caption-presets" aria-labelledby="caption-presets-heading">
      <h3 id="caption-presets-heading">자막 모양</h3>
      {error ? <p role="status">{error}</p> : null}
      {currentStyle ? <Button type="button" variant="outline" onClick={() => void keepCurrent()}>이 모양 저장해 두기</Button> : null}
      {visible.length ? visible.map((preset) => {
        const loved = favourites.includes(preset.preset_id);
        return (
          <article key={preset.preset_id} aria-label={`${preset.name} 자막 모양`}>
            <strong>{preset.name}</strong>
            {!loved && recents.includes(preset.preset_id) ? <span>최근에 썼어요</span> : null}
            <Button type="button" variant="outline" onClick={() => void apply(preset)}>
              {`${preset.name} 적용`}
            </Button>
            {canFavourite(preset.preset_id, projectId) ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => void toggle(preset.preset_id, !loved)}
              >
                {loved ? `${preset.name} 즐겨찾기 해제` : `${preset.name} 즐겨찾기`}
              </Button>
            ) : null}
          </article>
        );
      }) : <p>아직 저장된 자막 모양이 없어요.</p>}
    </section>
  );
}
