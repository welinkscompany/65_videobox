import { useCallback, useEffect, useRef, useState } from "react";

import { api, type LibraryAsset, type LibraryMediaType } from "../../../api";
import { Button } from "../../../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { LibraryResults } from "../../library/LibraryResults";
import { LibrarySidebar, type LibraryFilter } from "../../library/LibrarySidebar";
import "./libraryPickerDialog.css";

function matchesFilter(asset: LibraryAsset, filter: LibraryFilter) {
  if (filter === "all") return asset.lifecycle !== "trashed";
  if (filter === "trash") return asset.lifecycle === "trashed";
  if (filter === "favorites") return Boolean(asset.user_metadata?.favorite);
  return asset.media_type === filter && asset.lifecycle !== "trashed";
}

/** 여러 프로젝트가 함께 쓰는 라이브러리에서 자산 하나를 골라 이 프로젝트로
 *  들여온다 -- **편집기를 떠나지 않는다.**
 *
 *  **새로 그리지 않는다.** 필터(`LibrarySidebar`)와 검색+목록(`LibraryResults`)은
 *  `/library` 화면이 쓰는 것을 그대로 가져다 쓴다. 이 팝업은 "고르기"만 한다 --
 *  휴지통·복원·사용처 확인(`LibraryPreviewPane`) 같은 관리 기능은 넣지 않는다.
 *  관리는 실수로 지우기 쉬운 동작이라 스쳐 지나가는 팝업에 두면 위험하다.
 *  → `docs/superpowers/specs/2026-08-27-library-footage-projects-redesign-plan.ko.md` §1.3, §1.5
 *
 *  `/library`의 3단 그리드(`library.css`)는 도크 폭(220~400px)에 맞지 않는다.
 *  컴포넌트는 그대로 두고, 배치만 `libraryPickerDialog.css`로 따로 짰다 --
 *  `/library` 자체 화면의 3단 레이아웃은 건드리지 않는다.
 */
export function LibraryPickerDialog({
  open,
  onOpenChange,
  projectId,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  onImported?: () => void | Promise<void>;
}) {
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [activeFilter, setActiveFilter] = useState<LibraryFilter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LibraryAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<"semantic" | "word" | null>(null);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const epoch = useRef(0);

  const load = useCallback(async () => {
    const currentEpoch = ++epoch.current;
    setLoading(true); setError(null);
    try {
      const semanticEligible = Boolean(search.trim()) && (activeFilter === "broll" || activeFilter === "music" || activeFilter === "sfx" || activeFilter === "image");
      let nextAssets: LibraryAsset[];
      if (semanticEligible) {
        const result = await api.searchLibraryAssets(search.trim(), activeFilter as LibraryMediaType, undefined);
        if (currentEpoch !== epoch.current) return;
        const seenIds = new Set<string>();
        const usable = result.matches.filter((match) => {
          const identity = String(match.library_asset_id ?? "");
          if (!identity || seenIds.has(identity)) return false;
          seenIds.add(identity);
          return true;
        });
        nextAssets = usable;
        setSearchMode(result.semantic && usable.some((match) => match.semantic_match) ? "semantic" : "word");
      } else {
        const result = await api.listLibraryAssets({ includeTrashed: false, q: search || undefined, limit: 500 });
        if (currentEpoch !== epoch.current) return;
        nextAssets = result.assets;
        setSearchMode(null);
      }
      setAssets(nextAssets);
    } catch {
      if (currentEpoch === epoch.current) setError("라이브러리를 불러오지 못했어요.");
    } finally { if (currentEpoch === epoch.current) setLoading(false); }
  }, [activeFilter, search]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => void load(), search ? 180 : 0);
    return () => window.clearTimeout(timer);
  }, [open, load, search]);

  // 팝업을 새로 열 때마다 지난번 검색·선택이 남아 있으면 안 된다.
  useEffect(() => {
    if (open) return;
    setActiveFilter("all"); setSearch(""); setSelected(null); setMessage(null);
  }, [open]);

  const visible = assets.filter((asset) => matchesFilter(asset, activeFilter));
  const counts = {
    all: assets.filter((item) => item.lifecycle !== "trashed").length,
    broll: assets.filter((item) => item.media_type === "broll" && item.lifecycle !== "trashed").length,
    music: assets.filter((item) => item.media_type === "music" && item.lifecycle !== "trashed").length,
    sfx: assets.filter((item) => item.media_type === "sfx" && item.lifecycle !== "trashed").length,
    image: assets.filter((item) => item.media_type === "image" && item.lifecycle !== "trashed").length,
    favorites: assets.filter((item) => Boolean(item.user_metadata?.favorite)).length,
    trash: 0,
  };

  async function confirmImport() {
    if (!selected || importing) return;
    setImporting(true);
    setMessage(null);
    try {
      await api.materializeLibraryAsset(selected.library_asset_id, projectId);
      await onImported?.();
      onOpenChange(false);
    } catch {
      setMessage("가져오지 못했어요. 다시 시도해 주세요.");
    } finally {
      setImporting(false);
    }
  }

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="vb-dialog-content vb-library-picker">
      <DialogHeader>
        <DialogTitle>자료실에서 가져오기</DialogTitle>
        <DialogDescription>여러 프로젝트가 함께 쓰는 자료실에서 골라 이 프로젝트로 가져옵니다.</DialogDescription>
      </DialogHeader>
      <div className="vb-library-picker__body">
        <LibrarySidebar activeFilter={activeFilter} onFilter={(filter) => { setActiveFilter(filter); setSelected(null); }} counts={counts} />
        <LibraryResults
          assets={visible}
          activeFilter={activeFilter}
          search={search}
          onSearch={setSearch}
          selectedId={selected?.library_asset_id}
          onSelect={setSelected}
          loading={loading}
          error={error}
          searchMode={searchMode}
        />
      </div>
      {message ? <p role="status">{message}</p> : null}
      <div className="vb-library-picker__footer">
        <Button type="button" disabled={!selected || importing} onClick={() => void confirmImport()}>
          {importing ? "가져오는 중" : "가져오기"}
        </Button>
      </div>
    </DialogContent>
  </Dialog>;
}
