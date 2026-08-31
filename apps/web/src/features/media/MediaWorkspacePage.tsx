import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { api, type BrollAsset, type MediaAnalysis, type MediaInboxAsset } from "../../api";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { filterEditorAssets, projectEditorAssets } from "../editor/assets/editorAssetProjection";
import { MediaLibraryBrowser } from "./MediaLibraryBrowser";
import { VoiceMaterialPanel } from "./VoiceMaterialPanel";

// 내레이션도 영상·음악·효과음과 같은 미디어다. 2026-08-16까지 목소리만 설정 서랍에
// 있었고, 그래서 미디어 단계에서 사람 목소리가 빠져 보였다.
type MediaTab = "videos" | "music" | "sfx" | "narration" | "import";

/** 보관함은 오래된 것부터 도착한다(`local_project_store.list_assets`가 `created_at ASC`). */
type ProjectSort = "recent" | "name";

const projectSorts: readonly { value: ProjectSort; label: string }[] = [
  { value: "recent", label: "최근 순" },
  { value: "name", label: "이름 순" },
];

type MediaState = {
  projectId: string;
  assets: BrollAsset[];
  analyses: MediaAnalysis[];
  collection: MediaInboxAsset[];
};

type MediaActionToken = {
  id: number;
  key: string;
  projectId: string;
  generation: number;
};

const analysisStatusCopy: Record<string, string> = {
  queued: "분석을 기다리고 있어요",
  running: "미디어를 살펴보고 있어요",
  succeeded: "준비가 끝났어요",
  needs_review: "확인이 필요해요",
  failed: "분석을 마치지 못했어요",
  blocked: "분석을 진행할 수 없어요",
  cancelled: "분석을 멈췄어요",
};

function fileSizeLabel(bytes: number) {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)}GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)}MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${bytes}B`;
}

function assetTitle(asset: BrollAsset | undefined, index: number) {
  const title = asset?.metadata?.title;
  return typeof title === "string" && title.trim() ? title.trim() : `미디어 ${index + 1}`;
}

export function MediaWorkspacePage({ projectId }: { projectId: string }) {
  const [state, setState] = useState<MediaState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ assetId: string; durationSec?: number } | null>(null);
  const [tags, setTags] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<MediaTab>("videos");
  const [projectQuery, setProjectQuery] = useState("");
  const [projectSort, setProjectSort] = useState<ProjectSort>("recent");
  const tabRefs = useRef<Partial<Record<MediaTab, HTMLButtonElement>>>({});
  const currentContext = useRef({ projectId, generation: 0 });
  const loadEpoch = useRef(0);
  const actionSequence = useRef(0);
  const actionInFlight = useRef<MediaActionToken | null>(null);

  if (currentContext.current.projectId !== projectId) {
    currentContext.current = {
      projectId,
      generation: currentContext.current.generation + 1,
    };
    actionInFlight.current = null;
  }

  const load = useCallback(async () => {
    const loadProjectId = projectId;
    const loadGeneration = currentContext.current.generation;
    const epoch = ++loadEpoch.current;
    setLoading(true);
    setError(null);
    try {
      const [assets, analysisResponse, collection] = await Promise.all([
        api.listBrollAssets(loadProjectId),
        api.listMediaAnalysis(loadProjectId),
        api.listMediaInboxAssets(),
      ]);
      const current = currentContext.current;
      if (current.projectId !== loadProjectId || current.generation !== loadGeneration || loadEpoch.current !== epoch) return false;
      setState({
        projectId: loadProjectId,
        assets: assets.filter((item) => item.asset_type === "broll_video"),
        analyses: analysisResponse.items,
        collection,
      });
      return true;
    } catch {
      const current = currentContext.current;
      if (current.projectId !== loadProjectId || current.generation !== loadGeneration || loadEpoch.current !== epoch) return false;
      setState(null);
      setError("미디어를 불러오지 못했어요. 다시 시도해 주세요.");
      return false;
    } finally {
      const current = currentContext.current;
      if (current.projectId === loadProjectId && current.generation === loadGeneration && loadEpoch.current === epoch) {
        setLoading(false);
      }
    }
  }, [projectId]);

  useEffect(() => {
    setState(null);
    setPreview(null);
    setTags({});
    setMessage(null);
    setBusyKey(null);
    setActiveTab("videos");
    setProjectQuery("");
    void load();
    return () => {
      loadEpoch.current += 1;
    };
  }, [load]);

  function beginAction(key: string) {
    if (actionInFlight.current !== null) return null;
    const context = currentContext.current;
    const token: MediaActionToken = {
      id: ++actionSequence.current,
      key,
      projectId: context.projectId,
      generation: context.generation,
    };
    actionInFlight.current = token;
    setBusyKey(key);
    setError(null);
    setMessage(null);
    return token;
  }

  function isCurrentAction(token: MediaActionToken) {
    const active = actionInFlight.current;
    const context = currentContext.current;
    return active?.id === token.id
      && context.projectId === token.projectId
      && context.generation === token.generation;
  }

  function finishAction(token: MediaActionToken) {
    if (actionInFlight.current?.id !== token.id) return;
    actionInFlight.current = null;
    setBusyKey(null);
  }

  async function runAction(key: string, mutation: () => Promise<unknown>) {
    const token = beginAction(key);
    if (!token) return;
    try {
      await mutation();
      if (!isCurrentAction(token)) return;
      const refreshed = await load();
      if (refreshed && isCurrentAction(token)) setMessage("변경 내용을 확인했어요.");
    } catch {
      if (!isCurrentAction(token)) return;
      await load();
      if (isCurrentAction(token)) {
        setMessage("지금은 이 작업을 마칠 수 없어요. 직접 선택하거나 다시 시도해 주세요.");
      }
    } finally {
      finishAction(token);
    }
  }

  async function uploadFiles(files: FileList) {
    if (files.length === 0) return;
    const token = beginAction("upload");
    if (!token) return;
    let succeeded = 0; let failed = 0;
    try {
      const batch = await api.ingestLibraryAssets(Array.from(files), "broll", `project-${token.projectId}-${token.id}`);
      for (const item of batch.items) {
        if (!item.library_asset_id || (item.state !== "ready" && item.state !== "duplicate")) { failed += 1; continue; }
        try { await api.materializeLibraryAsset(item.library_asset_id, token.projectId); succeeded += 1; } catch { failed += 1; }
      }
    } catch {
      failed = files.length;
    }
    if (!isCurrentAction(token)) return;
    if (succeeded > 0) await load();
    if (!isCurrentAction(token)) return;
    if (succeeded > 0 && failed === 0) {
      setMessage(`영상 ${succeeded}개를 추가했어요.`);
    } else if (succeeded > 0 && failed > 0) {
      setMessage(`영상 ${succeeded}개를 추가했어요. ${failed}개를 추가하지 못했어요. 파일을 확인한 뒤 다시 시도해 주세요.`);
    } else {
      setMessage("영상을 추가하지 못했어요. 파일을 확인한 뒤 다시 시도해 주세요.");
    }
    finishAction(token);
  }

  async function importFromCollection(filename: string) {
    const token = beginAction(`import:${filename}`);
    if (!token) return;
    try {
      await api.importMediaInboxAsset(token.projectId, filename);
      if (!isCurrentAction(token)) return;
      await load();
      if (isCurrentAction(token)) setMessage(`「${filename}」을 이 프로젝트로 가져왔어요.`);
    } catch {
      if (isCurrentAction(token)) {
        await load();
        if (isCurrentAction(token)) setMessage("이 영상을 가져오지 못했어요. 다시 시도해 주세요.");
      }
    } finally {
      finishAction(token);
    }
  }

  async function removeProjectReference(asset: BrollAsset) {
    const sourceLibraryAssetId = asset.metadata?.source_library_asset_id;
    if (typeof sourceLibraryAssetId !== "string" || !sourceLibraryAssetId) {
      setMessage("이 프로젝트 전용 영상은 여기에서 뺄 수 없어요.");
      return;
    }
    const usage = await api.getLibraryAssetUsage(sourceLibraryAssetId);
    const reference = usage.locations.find((location) => location.project_id === projectId && location.materialized_asset_id === asset.asset_id);
    if (!reference?.reference_id) {
      setMessage("프로젝트 참조 위치를 찾지 못했어요. 자료실에서 상태를 확인해 주세요.");
      return;
    }
    await api.removeLibraryReference(sourceLibraryAssetId, reference.reference_id);
  }

  async function showPreview(item: MediaAnalysis) {
    const key = `preview:${item.analysis_id}`;
    const token = beginAction(key);
    if (!token) return;
    try {
      const response = await api.mediaAnalysisPreview(token.projectId, item.asset_id);
      if (!isCurrentAction(token)) return;
      const raw = response.preview as { duration_sec?: unknown } | null;
      setPreview({
        assetId: item.asset_id,
        durationSec: typeof raw?.duration_sec === "number" ? raw.duration_sec : undefined,
      });
    } catch {
      if (isCurrentAction(token)) {
        setPreview(null);
        setMessage("미리보기를 준비하지 못했어요. 다시 시도해 주세요.");
      }
    } finally {
      finishAction(token);
    }
  }

  const currentState = state?.projectId === projectId ? state : null;
  const assetById = new Map(currentState?.assets.map((item) => [item.asset_id, item]) ?? []);
  // 번호는 좁히기 전에 매긴다. 검색어를 칠 때마다 이름이 바뀌면 같은 영상을 놓친다.
  const allProjectCards = currentState
    ? projectEditorAssets({ projectId, brollAssets: currentState.assets, libraryAssets: [] })
    : [];
  const orderedProjectCards = projectSort === "name"
    ? allProjectCards.slice().sort((left, right) => left.title.localeCompare(right.title, "ko"))
    : allProjectCards.slice().reverse();
  const projectCards = filterEditorAssets(orderedProjectCards, { type: "all", query: projectQuery });

  const tabs: readonly { value: MediaTab; label: string }[] = [
    { value: "videos", label: "내 영상" },
    { value: "music", label: "음악" },
    { value: "sfx", label: "효과음" },
    { value: "narration", label: "내레이션" },
    { value: "import", label: "가져오기" },
  ];

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, value: MediaTab) {
    const index = tabs.findIndex((tab) => tab.value === value);
    if (index < 0 || !["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + tabs.length) % tabs.length;
    const next = tabs[nextIndex].value;
    setActiveTab(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <section data-project-id={projectId} data-testid="media-workspace-page" aria-labelledby="media-workspace-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 id="media-workspace-heading">미디어</h1>
          <p>영상 · 분석 상태</p>
        </div>
        <Button type="button" variant="outline" disabled={loading || busyKey !== null} onClick={() => void load()}>
          새로고침
        </Button>
      </div>

      {loading && !currentState ? <p role="status">미디어를 불러오고 있어요.</p> : null}
      {error ? <div role="alert"><p>{error}</p><Button type="button" onClick={() => void load()}>다시 불러오기</Button></div> : null}
      {message ? <p role="status">{message}</p> : null}

      <div role="tablist" aria-label="미디어 종류" className="vb-media-workspace__tabs">
        {tabs.map((tab) => (
          <Button
            key={tab.value}
            type="button"
            variant={activeTab === tab.value ? "default" : "outline"}
            role="tab"
            aria-selected={activeTab === tab.value}
            aria-controls={activeTab === tab.value ? `media-panel-${tab.value}` : undefined}
            tabIndex={activeTab === tab.value ? 0 : -1}
            ref={(element) => {
              tabRefs.current[tab.value] = element ?? undefined;
            }}
            onKeyDown={(event) => handleTabKeyDown(event, tab.value)}
            onClick={() => setActiveTab(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {activeTab === "import" ? <div id="media-panel-import" role="tabpanel" aria-label="가져오기" className="grid gap-4">
        <section aria-labelledby="media-upload-heading">
          <h2 id="media-upload-heading">새 파일 추가</h2>
          <p className="sr-only">영상 올리기</p>
          <p>여러 개 한 번에 · 보관함에 쌓임</p>
          <label htmlFor="media-broll-upload">장면 영상 파일 추가</label>
          <Input
            id="media-broll-upload"
            type="file"
            accept="video/*,.mp4,.mov,.webm,.mkv"
            multiple
            disabled={busyKey !== null}
            onChange={(event) => {
              const files = event.target.files;
              event.target.value = "";
              if (files && files.length > 0) void uploadFiles(files);
            }}
          />
        </section>
        {currentState ? <section aria-labelledby="media-collection-heading">
            <h2 id="media-collection-heading">촬영본 가져오기</h2>
            <p className="sr-only">따로 모아둔 영상 가져오기</p>
            <p>따로 모아둔 영상에서 고르기</p>
            {currentState.collection.length === 0 ? <p>아직 따로 모아둔 영상이 없어요.</p> : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {currentState.collection.map((item) => (
                  <Card key={item.filename}>
                    <CardHeader>
                      <CardTitle>{item.filename}</CardTitle>
                      <CardDescription>{fileSizeLabel(item.size_bytes)}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Button
                        type="button"
                        variant="outline"
                        aria-label={`${item.filename} 가져오기`}
                        disabled={busyKey !== null}
                        onClick={() => void importFromCollection(item.filename)}
                      >
                        가져오기
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
        </section> : null}
      </div> : null}

      {activeTab === "music" ? <div id="media-panel-music" role="tabpanel" aria-label="음악"><h2>자료실에서 찾기</h2><MediaLibraryBrowser projectId={projectId} fixedFilter="music" /></div> : null}
      {activeTab === "sfx" ? <div id="media-panel-sfx" role="tabpanel" aria-label="효과음"><h2>자료실에서 찾기</h2><MediaLibraryBrowser projectId={projectId} fixedFilter="sfx" /></div> : null}
      {activeTab === "narration" ? <div id="media-panel-narration" role="tabpanel" aria-label="내레이션"><VoiceMaterialPanel projectId={projectId} /></div> : null}

      {activeTab === "videos" && currentState ? (
        <div id="media-panel-videos" role="tabpanel" aria-label="내 영상" className="grid gap-4">
          <section aria-labelledby="media-assets-heading">
            <h2>이 프로젝트의 미디어</h2>
            <h2 id="media-assets-heading">내 영상</h2>
            {allProjectCards.length > 0 ? (
              <div className="vb-media-library__toolbar">
                <label htmlFor="media-project-search">프로젝트 영상 이름으로 찾기</label>
                <Input
                  id="media-project-search"
                  type="search"
                  value={projectQuery}
                  placeholder="이름 일부를 적어 보세요"
                  onChange={(event) => setProjectQuery(event.target.value)}
                />
                <div role="group" aria-label="프로젝트 영상 정렬 순서" className="vb-media-library__filters">
                  {projectSorts.map((item) => (
                    <Button
                      key={item.value}
                      type="button"
                      variant={projectSort === item.value ? "default" : "outline"}
                      aria-pressed={projectSort === item.value}
                      aria-label={`프로젝트 영상 ${item.label}`}
                      onClick={() => setProjectSort(item.value)}
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}
            {projectCards.length === 0 ? <p>{allProjectCards.length > 0
              ? "찾는 이름과 맞는 영상이 없어요."
              : "아직 준비한 영상이 없어요. 가져오기 탭에서 영상을 추가해 보세요."}</p> : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {projectCards.map((card) => (
                  <Card key={card.id} className="vb-media-project-card" aria-label={`${card.title} 미디어`}>
                    {card.thumbnailUrl ? <img className="vb-editor-assets__thumb" src={card.thumbnailUrl} alt={`${card.title} 미리보기`} loading="lazy" /> : null}
                    <CardHeader>
                      <CardTitle title={card.title}>{card.title}</CardTitle>
                      <CardDescription>{card.durationLabel === "길이 정보 없음" ? card.durationLabel : `길이 ${card.durationLabel}`}</CardDescription>
                      <CardDescription>{card.orientation ?? "방향 확인 중"}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <p>{card.audioPresence}</p>
                      <p>{card.status}</p>
                      {(() => {
                        const projectAsset = currentState.assets.find((item) => item.asset_id === card.assetId);
                        const sourceLibraryAssetId = projectAsset?.metadata?.source_library_asset_id;
                        return typeof sourceLibraryAssetId === "string" && sourceLibraryAssetId ? (
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busyKey !== null}
                            aria-label={`${card.title} 프로젝트에서 빼기`}
                            onClick={() => {
                              if (!projectAsset) return;
                              void runAction(`remove:${projectAsset.asset_id}`, () => removeProjectReference(projectAsset));
                            }}
                          >
                            프로젝트에서 빼기
                          </Button>
                        ) : null;
                      })()}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>

          <section aria-labelledby="media-library-heading">
            <MediaLibraryBrowser projectId={projectId} fixedFilter="broll" onMaterialized={() => void load()} />
          </section>

          <section aria-labelledby="media-analysis-heading">
            <h2 id="media-analysis-heading">분석 상태</h2>
            {currentState.analyses.length === 0 ? <p>확인할 분석이 없어요.</p> : (
              <div className="grid gap-3">
                {currentState.analyses.map((item, index) => {
                  const label = assetTitle(assetById.get(item.asset_id), index);
                  const actionDisabled = busyKey !== null;
                  return (
                    <Card key={item.analysis_id} role="article" aria-label={`${label} 분석`}>
                      <CardHeader>
                        <CardTitle>{label}</CardTitle>
                        <CardDescription>
                          {analysisStatusCopy[item.status] ?? "상태를 확인하고 있어요"} · {item.progress_percent}%
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="grid gap-2">
                        {item.error_message ? <p>분석을 마치지 못했어요. 직접 선택하거나 다시 시도해 주세요.</p> : null}
                        {(item.status === "succeeded" || item.status === "needs_review") ? (
                          <Button type="button" variant="outline" disabled={actionDisabled} onClick={() => void showPreview(item)}>
                            미리보기
                          </Button>
                        ) : null}
                        {preview?.assetId === item.asset_id ? (
                          <p>{preview.durationSec === undefined ? "미리보기가 준비됐어요." : `미리보기 길이 ${preview.durationSec}초`}</p>
                        ) : null}
                        {(item.status === "queued" || item.status === "running") ? (
                          <Button type="button" variant="outline" disabled={actionDisabled} onClick={() => void runAction(
                            `cancel:${item.analysis_id}`,
                            () => api.cancelMediaAnalysis(projectId, item.analysis_id),
                          )}>
                            분석 멈추기
                          </Button>
                        ) : null}
                        {(item.status === "failed" || item.status === "blocked") ? (
                          <Button type="button" variant="outline" disabled={actionDisabled} onClick={() => void runAction(
                            `retry:${item.analysis_id}`,
                            () => api.retryMediaAnalysis(projectId, item.analysis_id),
                          )}>
                            다시 분석하기
                          </Button>
                        ) : null}
                        {item.status === "needs_review" ? (
                          <form onSubmit={(event) => {
                            event.preventDefault();
                            const place = (tags[item.analysis_id] ?? "").split(",").map((tag) => tag.trim()).filter(Boolean);
                            void runAction(
                              `review:${item.analysis_id}`,
                              () => api.reviewMediaAnalysis(projectId, item.analysis_id, { place }),
                            );
                          }}>
                            <label>
                              미디어 {index + 1} 태그
                              <Input
                                aria-label={`미디어 ${index + 1} 태그`}
                                value={tags[item.analysis_id] ?? ""}
                                onChange={(event) => setTags((current) => ({ ...current, [item.analysis_id]: event.target.value }))}
                              />
                            </label>
                            <Button type="submit" disabled={actionDisabled}>태그 확인</Button>
                          </form>
                        ) : null}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
