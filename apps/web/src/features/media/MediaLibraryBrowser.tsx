import { useEffect, useState } from "react";

import { api, type MediaLibraryAsset } from "../../api";
import { Button } from "../../components/ui/button";

type Filter = "all" | "music" | "sfx";

const filters: readonly { value: Filter; label: string }[] = [
  { value: "all", label: "전체 보기" },
  { value: "music", label: "음악만 보기" },
  { value: "sfx", label: "효과음만 보기" },
];

/** Browse the music and effects library, hear one, and keep the good ones.
 *
 * The library, its favourites and its preview URL all existed; nothing on
 * screen used them. With 130 assets installed, choosing meant reading
 * filenames and guessing.
 */
export function MediaLibraryBrowser({ projectId }: { projectId: string }) {
  const [assets, setAssets] = useState<readonly MediaLibraryAsset[]>([]);
  const [favourites, setFavourites] = useState<readonly string[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    setReady(false);
    void Promise.all([api.listMediaLibraryAssets(), api.listMediaLibraryFavorites()])
      .then(([library, favourite]) => {
        if (!active) return;
        setAssets(library.assets);
        setFavourites(favourite.asset_ids);
      })
      .catch(() => { /* an unreadable library must not break the assets screen */ })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, [projectId]);

  const toggle = async (libraryAssetId: string, enabled: boolean) => {
    // Show the change now; the list re-sorts on the server's answer.
    setFavourites((current) => enabled
      ? [...current, libraryAssetId]
      : current.filter((item) => item !== libraryAssetId));
    try {
      const saved = await api.setMediaLibraryFavorite(libraryAssetId, enabled);
      setFavourites(saved.asset_ids);
    } catch {
      setFavourites((current) => enabled
        ? current.filter((item) => item !== libraryAssetId)
        : [...current, libraryAssetId]);
    }
  };

  // 팩이 주는 `asset_id`는 내부 슬러그다(`music-005`). owner에게 보일 이름은
  // 종류별 고정 순서로 매긴 번호로 만든다 -- 즐겨찾기가 위로 올라가도 같은
  // 곡이 같은 번호를 유지해야 한다.
  const displayNames = new Map<string, string>();
  for (const kind of ["music", "sfx"] as const) {
    const label = kind === "music" ? "음악" : "효과음";
    assets
      .filter((item) => item.media_type === kind)
      .slice()
      .sort((left, right) => left.asset_id.localeCompare(right.asset_id))
      .forEach((item, index) => displayNames.set(item.library_asset_id, `${label} ${index + 1}`));
  }

  const visible = assets
    .filter((item) => filter === "all" || item.media_type === filter)
    // Favourites first: the point of marking one is not to hunt for it again.
    .slice()
    .sort((left, right) => {
      const loved = Number(favourites.includes(right.library_asset_id))
        - Number(favourites.includes(left.library_asset_id));
      return loved !== 0 ? loved : left.asset_id.localeCompare(right.asset_id);
    });

  if (!ready) return null;
  return (
    <section className="vb-media-library" aria-labelledby="media-library-heading">
      <h2 id="media-library-heading">음악과 효과음</h2>
      <p>들어보고 마음에 드는 것은 즐겨찾기에 담아 두세요.</p>
      <div className="vb-media-library__filters">
        {filters.map((item) => (
          <Button
            key={item.value}
            type="button"
            variant="outline"
            aria-pressed={filter === item.value}
            onClick={() => setFilter(item.value)}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {visible.length ? visible.map((item) => {
        const loved = favourites.includes(item.library_asset_id);
        const name = displayNames.get(item.library_asset_id) ?? item.asset_id;
        return (
          <article key={item.library_asset_id} aria-label={`${name} 항목`}>
            <p>
              <strong>{name}</strong>
              {" · "}
              {item.media_type === "music" ? "음악" : "효과음"}
              {" · "}
              {`${Math.round(item.duration_seconds)}초`}
            </p>
            <audio
              controls
              preload="none"
              aria-label={`${name} 미리 듣기`}
              src={api.mediaLibraryPreviewUrl(item.library_asset_id)}
            />
            <Button
              type="button"
              variant="outline"
              aria-label={`${name} 즐겨찾기${loved ? " 해제" : ""}`}
              onClick={() => void toggle(item.library_asset_id, !loved)}
            >
              {loved ? "즐겨찾기 해제" : "즐겨찾기"}
            </Button>
          </article>
        );
      }) : <p>아직 준비된 음악과 효과음이 없어요.</p>}
    </section>
  );
}
