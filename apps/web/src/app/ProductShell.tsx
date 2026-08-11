// Source-preservation header: shadcn-admin@e16c87f213a5ba5e45964e9b67c792105ec74d26
// Structural reference: src/components/layout/authenticated-layout.tsx and app-sidebar.tsx
// License: MIT (see THIRD_PARTY_NOTICES.md). VideoBox adapts the layout only;
// upstream authentication, team, and administration behavior is intentionally excluded.
// After any content change to this file, update its two normalized_sha256
// entries in docs/oss/editor-ui-source-map.json (`hashlib.sha256(open(path,
// "rb").read()).hexdigest()`) -- tests/test_editor_ui_source_provenance.py
// enforces this and only runs in the full backend suite, not the frontend
// one, so a frontend-only PR can pass CI locally and still break this pin.

import { type ReactNode, useEffect, useRef, useState } from "react";
import { ClipboardCheck, Download, FilePlus2, Home, Images, MoreHorizontal, PanelLeftClose, Scissors, Settings, Video } from "lucide-react";

import { api, type HomeSummary, type Project } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../components/ui/empty";
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger } from "../components/ui/sidebar";
import { localDeploymentCapabilities } from "./deploymentCapabilities";
import { resolveWorkspaceLocation, type WorkspaceSection } from "./routeManifest";
import { JobRecovery } from "../features/jobs/JobRecovery";
import { HermesYujinStatus } from "../features/jobs/HermesYujinStatus";
import { ConversationCleanup } from "../features/settings/ConversationCleanup";
import { VoiceTtsSettings } from "../features/settings/VoiceTtsSettings";
import { HomeYujinChat } from "../features/home/HomeYujinChat";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../components/ui/dropdown-menu";

type ShellSection = WorkspaceSection | "media" | "outputs";
/** Task 32: archiving used to be a one-way door -- the project left the sidebar
 * and nothing called the restore endpoint. Grouped so the shell's call sites
 * stay readable. */
export type ProjectArchiveControls = Readonly<{
  archivedProjects: Project[];
  load: () => void | Promise<void>;
  restore: (projectId: string) => void | Promise<void>;
}>;
type SettingsSection = "general" | "appearance" | "ai-privacy" | "voice" | "output" | "conversations";
type SettingsState = { compact: boolean; reducedMotion: boolean; openLastProject: boolean };
const settingsKey = "videobox.settings";
const defaultSettings: SettingsState = { compact: false, reducedMotion: false, openLastProject: true };
function readSettings(): SettingsState { try { const stored = JSON.parse(window.localStorage.getItem(settingsKey) ?? "{}"); return { ...defaultSettings, ...stored, openLastProject: stored.openLastProject ?? stored.storageHint ?? true }; } catch { return defaultSettings; } }
function saveSettings(next: SettingsState) { window.localStorage.setItem(settingsKey, JSON.stringify(next)); }
export function opensLastProjectOnStart() { return readSettings().openLastProject; }

export function ProductShell({ projectId, projects, archive, section, onNavigate, onOpenSettings, onArchiveProject, onDeleteProjectPermanently, children, forceCollapsed = false }: { projectId: string; projects: Project[]; archive?: ProjectArchiveControls; section: ShellSection; onNavigate: (projectId: string, section: WorkspaceSection) => void; onOpenSettings: () => void; onArchiveProject?: (projectId: string) => void | Promise<void>; onDeleteProjectPermanently?: (projectId: string) => void | Promise<void>; children: ReactNode; forceCollapsed?: boolean }) {
  // Task 32: archived projects are loaded only when the owner opens the
  // archive, so the common path keeps its single project request.
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(forceCollapsed);
  const [jobDialogOpen, setJobDialogOpen] = useState(false);
  const [jobRecoveryBusy, setJobRecoveryBusy] = useState(false);
  const [archiveConfirmId, setArchiveConfirmId] = useState<string | null>(null);
  // Permanent delete needs two separate confirmations (owner decision,
  // 2026-08-06) -- stage 1 warns it's irreversible, stage 2 asks once more
  // before the actual call. Enforced again server-side (routers/projects.py
  // requires ?confirm=true) so this UI gate isn't the only thing standing
  // between a stray click and real data loss.
  const [deleteConfirmStage, setDeleteConfirmStage] = useState<{ projectId: string; stage: 1 | 2 } | null>(null);
  const previousForceCollapsed = useRef(forceCollapsed);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  if (forceCollapsed && !previousForceCollapsed.current) {
    previousForceCollapsed.current = true;
    if (!collapsed) setCollapsed(true);
  } else if (!forceCollapsed) previousForceCollapsed.current = false;
  const current = projects.find((project) => project.project_id === projectId) ?? projects[0];
  const nav = [["홈", "home", Home], ["새 영상 만들기", "create", FilePlus2], ["편집", "editing", Scissors], ["검토", "review", ClipboardCheck], ["자산", "media", Images], ["출력", "outputs", Download]] as const;
  const go = (next: string) => { if (window.innerWidth < 768) document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); onNavigate(projectId, next as WorkspaceSection); };
  const setJobDialogOpenSafely = (open: boolean) => {
    if (!open && jobRecoveryBusy) return;
    setJobDialogOpen(open);
  };
  useEffect(() => { const restoreMobileTrigger = (event: KeyboardEvent) => { if (event.key === "Escape" && window.innerWidth < 768) queueMicrotask(() => mobileTriggerRef.current?.focus()); }; document.addEventListener("keydown", restoreMobileTrigger); return () => document.removeEventListener("keydown", restoreMobileTrigger); }, []);
  // These two settings used to write to localStorage and change nothing else,
  // so the toggle flipped its own label while the screen stayed identical.
  // The shell now carries them and the stylesheet reads them.
  const display = readSettings();
  return <SidebarProvider open={!collapsed} onOpenChange={(open) => setCollapsed(!open)}>
    <div
      className="vb-product-shell"
      data-vb-desktop-shell
      data-compact={String(display.compact)}
      data-reduced-motion={String(display.reducedMotion)}
    >
    <Sidebar collapsible="icon" className="vb-product-sidebar" aria-label="프로젝트와 화면">
      <SidebarHeader>
      <div className="vb-shell-brand"><Video aria-hidden="true" /><span className="group-data-[collapsible=icon]:hidden">VideoBox</span></div>
      <div className="vb-project-switcher group-data-[collapsible=icon]:hidden" aria-label="프로젝트 전환"><p>현재 프로젝트</p>{projects.map((project) => <div key={project.project_id} className="vb-project-row" data-testid={`project-row-${project.project_id}`}>
        <Button variant="ghost" aria-label={project.name} aria-pressed={project.project_id === projectId} onClick={() => onNavigate(project.project_id, "home")}>{project.name}</Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button className="vb-project-more" variant="ghost" size="icon" aria-label={`${project.name} 더보기`}><MoreHorizontal aria-hidden="true" /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {onArchiveProject ? (archiveConfirmId === project.project_id ? (
              <DropdownMenuItem onSelect={(event) => { event.preventDefault(); setArchiveConfirmId(null); void onArchiveProject(project.project_id); }}>보관 확인</DropdownMenuItem>
            ) : (
              <DropdownMenuItem onSelect={(event) => { event.preventDefault(); setArchiveConfirmId(project.project_id); }}>보관하기</DropdownMenuItem>
            )) : null}
            {onDeleteProjectPermanently ? <>
              <DropdownMenuSeparator />
              {deleteConfirmStage?.projectId === project.project_id && deleteConfirmStage.stage === 2 ? (
                <DropdownMenuItem variant="destructive" onSelect={(event) => { event.preventDefault(); setDeleteConfirmStage(null); void onDeleteProjectPermanently(project.project_id); }}>영구 삭제 · 한 번 더 확인할게요</DropdownMenuItem>
              ) : deleteConfirmStage?.projectId === project.project_id && deleteConfirmStage.stage === 1 ? (
                <DropdownMenuItem onSelect={(event) => { event.preventDefault(); setDeleteConfirmStage({ projectId: project.project_id, stage: 2 }); }}>삭제 1차 확인 · 되돌릴 수 없어요</DropdownMenuItem>
              ) : (
                <DropdownMenuItem variant="destructive" onSelect={(event) => { event.preventDefault(); setDeleteConfirmStage({ projectId: project.project_id, stage: 1 }); }}>완전 삭제</DropdownMenuItem>
              )}
            </> : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>)}
      {archive ? (archiveOpen ? (
        <div className="vb-project-archive">
          <p>보관함</p>
          {archive.archivedProjects.length === 0 ? <p>보관한 프로젝트가 없어요.</p> : archive.archivedProjects.map((project) => (
            <div key={project.project_id} style={{ display: "flex", alignItems: "center", gap: ".25rem" }}>
              <span>{project.name}</span>
              <Button variant="outline" aria-label={`${project.name} 되돌리기`} onClick={() => void archive.restore(project.project_id)}>되돌리기</Button>
            </div>
          ))}
          <Button variant="ghost" onClick={() => setArchiveOpen(false)}>보관함 닫기</Button>
        </div>
      ) : (
        <Button variant="ghost" onClick={() => { setArchiveOpen(true); void archive.load(); }}>보관함 보기</Button>
      )) : null}</div>
      </SidebarHeader><SidebarContent><nav aria-label="영상 제작" className="vb-product-nav"><SidebarMenu>{nav.map(([label, target, Icon]) => <SidebarMenuItem key={target}><SidebarMenuButton aria-label={label} isActive={section === target || (target === "review" && section === "timeline")} tooltip={label} onClick={() => go(target)}><Icon aria-hidden="true" /><span className="vb-nav-label group-data-[collapsible=icon]:hidden">{label}</span></SidebarMenuButton></SidebarMenuItem>)}</SidebarMenu></nav></SidebarContent><SidebarFooter><div className="vb-sidebar-footer"><Button variant="ghost" onClick={onOpenSettings}><Settings aria-hidden="true" /> <span className="group-data-[collapsible=icon]:hidden">설정</span></Button><small className="group-data-[collapsible=icon]:hidden">{localDeploymentCapabilities.aiExecution === "local" ? "이 기기에서 작업" : "AI 기능 끔"}</small></div></SidebarFooter><SidebarRail aria-label="화면 목록 접기" title="화면 목록 접기" />
    </Sidebar>
    <SidebarInset className="vb-product-main"><header className="vb-product-header"><SidebarTrigger ref={mobileTriggerRef} className="vb-mobile-menu" aria-label="메뉴 열기" /><Button variant="ghost" size="icon" aria-label="사이드바 접기" onClick={() => setCollapsed((value) => !value)} className="vb-collapse"><PanelLeftClose /></Button><div><p>{current?.name ?? "프로젝트"}</p><strong>{section === "home" ? "홈" : section === "create" ? "새 영상 만들기" : section === "media" ? "자산" : section === "outputs" ? "출력" : section === "settings" ? "설정" : section === "timeline" || section === "review" ? "검토" : "편집"}</strong></div><Dialog open={jobDialogOpen} onOpenChange={setJobDialogOpenSafely}><DialogTrigger asChild><Button variant="outline">작업 상태</Button></DialogTrigger><DialogContent className="vb-dialog-content" showCloseButton={!jobRecoveryBusy} onEscapeKeyDown={(event) => { if (jobRecoveryBusy) event.preventDefault(); }} onPointerDownOutside={(event) => { if (jobRecoveryBusy) event.preventDefault(); }} onInteractOutside={(event) => { if (jobRecoveryBusy) event.preventDefault(); }}><DialogHeader><DialogTitle>작업 상태</DialogTitle><DialogDescription>로컬 작업 상태를 확인하고 실패한 작업을 다시 시작할 수 있어요.</DialogDescription></DialogHeader>{jobDialogOpen ? <HermesYujinStatus /> : null}<JobRecovery projectId={projectId} onBusyChange={setJobRecoveryBusy} /></DialogContent></Dialog></header><div className="vb-product-content">{children}</div></SidebarInset>
    </div>
  </SidebarProvider>;
}

export function HomePage({ projectId, onNavigate }: { projectId: string; onNavigate: (projectId: string, section: WorkspaceSection) => void }) {
  // Task 35: all three cards used to state their text unconditionally, so each
  // one could be false -- "완성된 영상이 아직 없어요" stayed on screen after the
  // owner finished a render. Home still must not poll the job list
  // (ProductShell.test pins that to the job dialog), so it asks one dedicated
  // endpoint that counts server-side. If that call fails the cards fall back to
  // saying nothing about state rather than guessing, and stay clickable.
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  useEffect(() => {
    let active = true;
    setSummary(null);
    void api.getHomeSummary(projectId)
      .then((next) => { if (active) setSummary(next); })
      .catch(() => { /* a home that cannot count still navigates */ });
    return () => { active = false; };
  }, [projectId]);
  const draftText = summary === null ? "이어 할 작업을 선택해 편집을 계속하세요."
    : summary.has_draft ? "이어서 편집할 작업이 있어요." : "아직 시작한 작업이 없어요.";
  const finishedText = summary === null ? "출력 화면에서 완성한 영상을 확인할 수 있어요."
    : summary.finished_video_count > 0 ? `완성한 영상이 ${summary.finished_video_count}개 있어요.` : "아직 완성한 영상이 없어요.";
  const assetText = summary === null ? "대본에 맞는 사진·영상·소리를 추가해 주세요."
    : summary.asset_gap_count > 0 ? `채울 자리가 ${summary.asset_gap_count}곳 남았어요.` : "필요한 자산이 모두 준비됐어요.";
  const nextTask = summary?.has_draft
    ? { label: "편집 계속하기", section: "editing" as WorkspaceSection, description: "저장된 초안에서 다음 장면을 이어서 완성하세요." }
    : summary && summary.asset_gap_count > 0
      ? { label: "자산 준비하기", section: "media" as WorkspaceSection, description: `아직 채워야 할 자산이 ${summary.asset_gap_count}곳 있어요.` }
      : { label: "새 영상 시작하기", section: "create" as WorkspaceSection, description: "대본을 넣고 첫 영상을 시작해 보세요." };
  // The cards are ordered the way the work actually runs: bring footage in,
  // edit it, then take it out. The old order opened with editing, which is
  // the middle of the job.
  return <section className="vb-home" data-testid="product-home"><div><p className="vb-eyebrow">영상 만들기</p><h1>다음 장면을 이어서 만들어 볼까요?</h1><p>대본과 자산을 준비하면, 필요한 순서대로 바로 시작할 수 있어요.</p><Button onClick={() => onNavigate(projectId, "create")}>새 영상 만들기</Button></div><section className="vb-home-next" aria-labelledby="home-next-heading"><div><p className="vb-eyebrow">다음 할 일</p><h2 id="home-next-heading">{nextTask.label}</h2><p>{summary === null ? "현재 프로젝트 상태를 확인하는 중이에요." : nextTask.description}</p></div><Button variant="outline" onClick={() => onNavigate(projectId, nextTask.section)}>{nextTask.label}</Button><ul aria-label="진행 상황"><li>{summary?.has_draft ? "초안 있음" : "초안 없음"}</li><li>{summary ? `자산 ${summary.asset_gap_count > 0 ? `부족 ${summary.asset_gap_count}곳` : "준비됨"}` : "자산 상태 확인 중"}</li><li>{summary ? `완성본 ${summary.finished_video_count}개` : "완성본 확인 중"}</li></ul></section><div className="vb-home-grid"><HomeCard title="촬영본 가져오기" description={assetText} action="자산 준비하기" onClick={() => onNavigate(projectId, "media")} /><HomeCard title="작업 중인 초안 계속하기" description={draftText} action="편집 열기" onClick={() => onNavigate(projectId, "editing")} /><HomeCard title="최근 완성본" description={finishedText} action="출력 확인" onClick={() => onNavigate(projectId, "outputs")} /></div><HomeYujinChat projectId={projectId} /></section>;
}
function HomeCard({ title, description, action, onClick }: { title: string; description: string; action: string; onClick: () => void }) { return <Card><CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader><CardContent><Button variant="outline" onClick={onClick}>{action}</Button></CardContent></Card>; }

export function SettingsPage({ section, onNavigate, projectId }: { section: SettingsSection; onNavigate: (section: SettingsSection) => void; projectId: string }) {
  const [settings, setSettings] = useState(readSettings); const update = (patch: Partial<SettingsState>) => setSettings((previous) => { const next = { ...previous, ...patch }; saveSettings(next); return next; });
  const labels: Record<SettingsSection, string> = { general: "일반", appearance: "화면", "ai-privacy": "AI·개인정보", voice: "내 목소리", output: "출력", conversations: "유진 대화" };
  return <section className="vb-settings" data-testid="settings-page"><p className="vb-eyebrow">설정</p><h1>{labels[section]}</h1><div className="vb-settings-nav">{(Object.keys(labels) as SettingsSection[]).map((key) => <Button key={key} variant={key === section ? "default" : "outline"} onClick={() => onNavigate(key)}>{labels[key]}</Button>)}</div><p>이 기기에 저장되는 작업 환경을 조절합니다.</p><p className="vb-setting-note">설정은 이 기기에서만 관리됩니다.</p>{section === "general" && <SettingToggle label="시작할 때 마지막 프로젝트 열기" checked={settings.openLastProject} onChange={(checked) => update({ openLastProject: checked })} />}{section === "appearance" && <><SettingToggle label="조밀한 화면" checked={settings.compact} onChange={(checked) => update({ compact: checked })} /><SettingToggle label="움직임 줄이기" checked={settings.reducedMotion} onChange={(checked) => update({ reducedMotion: checked })} /></>}{/* Not a switch: VideoBox has no non-local mode to turn this off into. */}
      {section === "ai-privacy" && <div className="vb-setting-control"><span>모든 처리는 이 기기 안에서만 이뤄집니다.</span></div>}{section === "voice" && <VoiceTtsSettings key={projectId} projectId={projectId} />}{section === "output" && <div className="vb-setting-control"><span>완성본은 MP4(H.264)로 만듭니다.</span></div>}{section === "conversations" && <ConversationCleanup key={projectId} projectId={projectId} />}</section>;
}
export function ProductEmptyPage({ title, description, action, onClick }: { title: string; description: string; action: string; onClick: () => void }) { return <Empty><EmptyHeader><EmptyTitle>{title}</EmptyTitle><EmptyDescription>{description}</EmptyDescription></EmptyHeader><Button onClick={onClick}>{action}</Button></Empty>; }
function SettingToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) { return <Button variant="outline" className="vb-setting-control" aria-pressed={checked} onClick={() => onChange(!checked)}>{label}: {checked ? "켜짐" : "꺼짐"}</Button>; }
