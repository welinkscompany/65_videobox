// Source-preservation header: shadcn-admin@e16c87f213a5ba5e45964e9b67c792105ec74d26
// Structural reference: src/components/layout/authenticated-layout.tsx and app-sidebar.tsx
// License: MIT (see THIRD_PARTY_NOTICES.md). VideoBox adapts the layout only;
// upstream authentication, team, and administration behavior is intentionally excluded.

import { type ReactNode, useEffect, useRef, useState } from "react";
import { Menu, PanelLeftClose, Settings, Video } from "lucide-react";

import type { Project } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../components/ui/empty";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../components/ui/dropdown-menu";
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger } from "../components/ui/sidebar";
import { localDeploymentCapabilities } from "./deploymentCapabilities";
import { resolveWorkspaceLocation, type WorkspaceSection } from "./routeManifest";

type ShellSection = WorkspaceSection | "media" | "outputs";
type SettingsSection = "general" | "appearance" | "ai-privacy" | "storage" | "output";
type SettingsState = { compact: boolean; reducedMotion: boolean; aiEnabled: boolean; openLastProject: boolean; storageAlert: boolean; exportFormat: "mp4" | "mov" };
const settingsKey = "videobox.settings";
const defaultSettings: SettingsState = { compact: false, reducedMotion: false, aiEnabled: true, openLastProject: true, storageAlert: true, exportFormat: "mp4" };
function readSettings(): SettingsState { try { const stored = JSON.parse(window.localStorage.getItem(settingsKey) ?? "{}"); return { ...defaultSettings, ...stored, openLastProject: stored.openLastProject ?? stored.storageHint ?? true, storageAlert: stored.storageAlert ?? true }; } catch { return defaultSettings; } }
function saveSettings(next: SettingsState) { window.localStorage.setItem(settingsKey, JSON.stringify(next)); }
export function opensLastProjectOnStart() { return readSettings().openLastProject; }

export function ProductShell({ projectId, projects, section, onNavigate, onOpenSettings, children, forceCollapsed = false }: { projectId: string; projects: Project[]; section: ShellSection; onNavigate: (projectId: string, section: WorkspaceSection) => void; onOpenSettings: () => void; children: ReactNode; forceCollapsed?: boolean }) {
  const [collapsed, setCollapsed] = useState(forceCollapsed);
  const previousForceCollapsed = useRef(forceCollapsed);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  if (forceCollapsed && !previousForceCollapsed.current) {
    previousForceCollapsed.current = true;
    if (!collapsed) setCollapsed(true);
  } else if (!forceCollapsed) previousForceCollapsed.current = false;
  const current = projects.find((project) => project.project_id === projectId) ?? projects[0];
  const nav = [["홈", "home"], ["새 영상 만들기", "create"], ["편집", "editing"], ["자산", "media"], ["출력", "outputs"]] as const;
  const go = (next: string) => { if (window.innerWidth < 768) document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); onNavigate(projectId, next as WorkspaceSection); };
  useEffect(() => { const restoreMobileTrigger = (event: KeyboardEvent) => { if (event.key === "Escape" && window.innerWidth < 768) queueMicrotask(() => mobileTriggerRef.current?.focus()); }; document.addEventListener("keydown", restoreMobileTrigger); return () => document.removeEventListener("keydown", restoreMobileTrigger); }, []);
  return <SidebarProvider open={!collapsed} onOpenChange={(open) => setCollapsed(!open)}>
    <div className="vb-product-shell">
    <Sidebar collapsible="icon" className="vb-product-sidebar" aria-label="프로젝트와 화면">
      <SidebarHeader>
      <div className="vb-shell-brand"><Video aria-hidden="true" /><span>VideoBox</span></div>
      <div className="vb-project-switcher" aria-label="프로젝트 전환"><p>현재 프로젝트</p>{projects.map((project) => <Button key={project.project_id} variant="ghost" aria-label={project.name} aria-pressed={project.project_id === projectId} onClick={() => onNavigate(project.project_id, "home")}>{project.name}</Button>)}</div>
      </SidebarHeader><SidebarContent><nav aria-label="영상 제작" className="vb-product-nav"><SidebarMenu>{nav.map(([label, target]) => <SidebarMenuItem key={target}><SidebarMenuButton isActive={section === target} tooltip={label} onClick={() => go(target)}>{label}</SidebarMenuButton></SidebarMenuItem>)}</SidebarMenu></nav></SidebarContent><SidebarFooter><div className="vb-sidebar-footer"><Button variant="ghost" onClick={onOpenSettings}><Settings aria-hidden="true" /> <span>설정</span></Button><small>{localDeploymentCapabilities.aiExecution === "local" ? "이 기기에서 작업" : "AI 기능 끔"}</small></div></SidebarFooter><SidebarRail />
    </Sidebar>
    <SidebarInset className="vb-product-main"><header className="vb-product-header"><SidebarTrigger ref={mobileTriggerRef} className="vb-mobile-menu" aria-label="메뉴 열기" /><Button variant="ghost" size="icon" aria-label="사이드바 접기" onClick={() => setCollapsed((value) => !value)} className="vb-collapse"><PanelLeftClose /></Button><div><p>{current?.name ?? "프로젝트"}</p><strong>{section === "home" ? "홈" : section === "create" ? "새 영상 만들기" : section === "media" ? "자산" : section === "outputs" ? "출력" : section === "settings" ? "설정" : "편집"}</strong></div><DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline">작업 상태</Button></DropdownMenuTrigger><DropdownMenuContent><DropdownMenuItem disabled>진행 중인 작업이 없어요</DropdownMenuItem></DropdownMenuContent></DropdownMenu><Button onClick={() => onNavigate(projectId, "create")}>새 영상 만들기</Button></header><div className="vb-product-content">{children}</div></SidebarInset>
    </div>
  </SidebarProvider>;
}

export function HomePage({ projectId, onNavigate }: { projectId: string; onNavigate: (projectId: string, section: WorkspaceSection) => void }) {
  return <section className="vb-home" data-testid="product-home"><div><p className="vb-eyebrow">영상 만들기</p><h1>다음 장면을 이어서 만들어 볼까요?</h1><p>대본과 자산을 준비하면, 필요한 순서대로 바로 시작할 수 있어요.</p><Button onClick={() => onNavigate(projectId, "create")}>새 영상 만들기</Button></div><div className="vb-home-grid"><HomeCard title="작업 중인 초안 계속하기" description="이어 할 작업을 선택해 편집을 계속하세요." action="편집 열기" onClick={() => onNavigate(projectId, "editing")} /><HomeCard title="최근 완성본" description="완성된 영상이 아직 없어요." action="출력 확인" onClick={() => onNavigate(projectId, "outputs")} /><HomeCard title="자산 준비가 필요한 프로젝트" description="대본에 맞는 사진·영상·소리를 추가해 주세요." action="자산 준비하기" onClick={() => onNavigate(projectId, "media")} /></div></section>;
}
function HomeCard({ title, description, action, onClick }: { title: string; description: string; action: string; onClick: () => void }) { return <Card><CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader><CardContent><Button variant="outline" onClick={onClick}>{action}</Button></CardContent></Card>; }

export function SettingsPage({ section, onNavigate }: { section: SettingsSection; onNavigate: (section: SettingsSection) => void }) {
  const [settings, setSettings] = useState(readSettings); const update = (patch: Partial<SettingsState>) => setSettings((previous) => { const next = { ...previous, ...patch }; saveSettings(next); return next; });
  const labels: Record<SettingsSection, string> = { general: "일반", appearance: "화면", "ai-privacy": "AI·개인정보", storage: "저장공간", output: "출력" };
  return <section className="vb-settings" data-testid="settings-page"><p className="vb-eyebrow">설정</p><h1>{labels[section]}</h1><div className="vb-settings-nav">{(Object.keys(labels) as SettingsSection[]).map((key) => <Button key={key} variant={key === section ? "default" : "outline"} onClick={() => onNavigate(key)}>{labels[key]}</Button>)}</div><p>이 기기에 저장되는 작업 환경을 조절합니다.</p><p className="vb-setting-note">설정은 이 기기에서만 관리됩니다.</p>{section === "general" && <SettingToggle label="시작할 때 마지막 프로젝트 열기" checked={settings.openLastProject} onChange={(checked) => update({ openLastProject: checked })} />}{section === "appearance" && <><SettingToggle label="조밀한 화면" checked={settings.compact} onChange={(checked) => update({ compact: checked })} /><SettingToggle label="움직임 줄이기" checked={settings.reducedMotion} onChange={(checked) => update({ reducedMotion: checked })} /></>}{section === "ai-privacy" && <SettingToggle label="이 기기에서만 처리" checked={settings.aiEnabled} onChange={(checked) => update({ aiEnabled: checked })} />}{section === "storage" && <SettingToggle label="저장 공간 알림" checked={settings.storageAlert} onChange={(checked) => update({ storageAlert: checked })} />}{section === "output" && <div className="vb-setting-control"><span>기본 파일 형식</span><Button variant={settings.exportFormat === "mp4" ? "default" : "outline"} onClick={() => update({ exportFormat: "mp4" })}>MP4</Button><Button variant={settings.exportFormat === "mov" ? "default" : "outline"} onClick={() => update({ exportFormat: "mov" })}>MOV</Button></div>}</section>;
}
export function ProductEmptyPage({ title, description, action, onClick }: { title: string; description: string; action: string; onClick: () => void }) { return <Empty><EmptyHeader><EmptyTitle>{title}</EmptyTitle><EmptyDescription>{description}</EmptyDescription></EmptyHeader><Button onClick={onClick}>{action}</Button></Empty>; }
function SettingToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) { return <Button variant="outline" className="vb-setting-control" aria-pressed={checked} onClick={() => onChange(!checked)}>{label}: {checked ? "켜짐" : "꺼짐"}</Button>; }
