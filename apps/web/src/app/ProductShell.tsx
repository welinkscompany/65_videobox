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

import { api, type HomeSummary, type Project } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../components/ui/empty";
import { localDeploymentCapabilities } from "./deploymentCapabilities";
import { type NavigationContext, type WorkspaceSection } from "./routeManifest";
import { JobRecovery } from "../features/jobs/JobRecovery";
import { HermesYujinStatus } from "../features/jobs/HermesYujinStatus";
import { ConversationCleanup } from "../features/settings/ConversationCleanup";
import { HomeYujinChat } from "../features/home/HomeYujinChat";
import { StartChooser } from "../features/home/StartChooser";
import { TopBar } from "../features/shell/TopBar";
import { ShellCanvasProvider, useShellCanvas } from "../features/shell/shellCanvas";

// 프로젝트에 매이지 않는 전역 목적지도 껍데기 안에서 그린다(owner 지적
// 2026-08-19). 띠가 **어느 화면인지** 말해야 하므로 이름을 따로 갖는다 --
// `home`으로 뭉뚱그리면 라이브러리에서도 `홈`이라고 나온다.
type ShellSection = WorkspaceSection | "media" | "outputs" | "library" | "footage";
type SettingsSection = "general" | "appearance" | "ai-privacy" | "voice" | "output" | "conversations";
type SettingsState = { compact: boolean; reducedMotion: boolean };
const settingsKey = "videobox.settings";
const defaultSettings: SettingsState = { compact: false, reducedMotion: false };
function readSettings(): SettingsState { try { const stored = JSON.parse(window.localStorage.getItem(settingsKey) ?? "{}"); return { ...defaultSettings, ...stored }; } catch { return defaultSettings; } }
/** 저장 성공 여부를 돌려준다. 사생활 모드·용량 초과에서는 localStorage 쓰기가
 *  던지는데, 조용히 삼키면 토글이 켜진 것처럼 보이고 다음에 열면 원래대로다. */
function saveSettings(next: SettingsState): boolean {
  try {
    window.localStorage.setItem(settingsKey, JSON.stringify(next));
    return true;
  } catch {
    return false;
  }
}

export type ProductShellProps = {
  projectId: string;
  projects: Project[];
  section: ShellSection;
  onNavigate: (projectId: string, section: WorkspaceSection) => void;
  onOpenSettings: () => void;
  navigation?: NavigationContext;
  onBack?: () => void;
  /** 전역 화면으로 앱 안에서 이동한다. 없으면 링크가 페이지를 통째로 새로 연다. */
  onNavigateGlobal?: (destination: "projects" | "library" | "footage") => void;
  /** 마지막으로 편집하던 곳으로 돌아간다. 돌아갈 곳을 모르면 넘기지 않는다. */
  onResumeEditor?: () => void;
  children: ReactNode;
};

/** 껍데기는 화면 비율을 **스스로 알아내지 않는다.** 그 값은 열려 있는 초안에만
 *  있고, 껍데기가 프로젝트마다 그것을 물어보면 모든 화면에 요청이 하나씩 는다 --
 *  이 껍데기는 작업 목록조차 다이얼로그를 열 때만 부르도록 못박혀 있다.
 *  대신 **아는 화면이 알려 주고**(`usePublishShellCanvas`) 띠가 받아 적는다. */
export function ProductShell(props: ProductShellProps) {
  return <ShellCanvasProvider><ProductShellFrame {...props} /></ShellCanvasProvider>;
}

function ProductShellFrame({ projectId, projects, section, onNavigate, onOpenSettings, onNavigateGlobal, onResumeEditor, navigation, onBack, children }: ProductShellProps) {
  const canvas = useShellCanvas();
  const [jobDialogOpen, setJobDialogOpen] = useState(false);
  const [jobRecoveryBusy, setJobRecoveryBusy] = useState(false);
  const setJobDialogOpenSafely = (open: boolean) => {
    if (!open && jobRecoveryBusy) return;
    setJobDialogOpen(open);
  };
  // These two settings used to write to localStorage and change nothing else,
  // so the toggle flipped its own label while the screen stayed identical.
  // The shell now carries them and the stylesheet reads them.
  const display = readSettings();
  // 단계 단추가 켜져 있으면 그것이 곧 "여기가 어디인지"다. 단계가 없는 화면
  // (내 라이브러리·촬영본 정리·설정·프로젝트 목록)에서만 띠가 이름으로 말한다.
  const screenName = section === "home" ? "홈" : section === "create" ? "이야기" : section === "media" ? "미디어" : section === "settings" ? "설정" : section === "library" ? "내 라이브러리" : section === "footage" ? "촬영본 정리" : section === "outputs" || section === "timeline" || section === "review" ? "확인과 내보내기" : "편집";
  return (
    <div
      className="vb-product-shell"
      // 편집 구간일 때만 화면 전체가 어둡다(승인 2026-08-20). 껍데기가
      // 흰 채로 남으면 검은 편집판을 흰 액자가 감싸는 모양이 된다.
      data-shell-section={section}
      data-vb-desktop-shell
      data-compact={String(display.compact)}
      data-reduced-motion={String(display.reducedMotion)}
    >
      {/* 왼쪽 기둥은 없앴다 -- 캡컷과 같은 배치로, 위 띠 하나가 그 일을 전부 받는다
          (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`, owner 승인 2026-08-21).
          프로젝트 관리(이름 바꾸기·보관·영구 삭제·보관함)는 기둥이 아니라 `프로젝트`
          목록 화면에 산다 -- 띠는 **고르는 것만** 맡는다. */}
      <TopBar
        projectId={projectId}
        projects={projects}
        section={section}
        screenName={screenName}
        canvas={canvas}
        navigation={navigation}
        onBack={onBack}
        onNavigate={onNavigate}
        onSelectProject={(nextProjectId) => onNavigate(nextProjectId, "editing")}
        onOpenSettings={onOpenSettings}
        onNavigateGlobal={onNavigateGlobal}
        onResumeEditor={onResumeEditor}
      >
        <small className="vb-top-bar__note">{localDeploymentCapabilities.aiExecution === "local" ? "이 기기에서 작업" : "AI 기능 끔"}</small>
        <Dialog open={jobDialogOpen} onOpenChange={setJobDialogOpenSafely}><DialogTrigger asChild><Button variant="outline">작업 상태</Button></DialogTrigger><DialogContent className="vb-dialog-content" showCloseButton={!jobRecoveryBusy} onEscapeKeyDown={(event) => { if (jobRecoveryBusy) event.preventDefault(); }} onPointerDownOutside={(event) => { if (jobRecoveryBusy) event.preventDefault(); }} onInteractOutside={(event) => { if (jobRecoveryBusy) event.preventDefault(); }}><DialogHeader><DialogTitle>작업 상태</DialogTitle><DialogDescription>로컬 작업 상태를 확인하고 실패한 작업을 다시 시작할 수 있어요.</DialogDescription></DialogHeader>{jobDialogOpen ? <HermesYujinStatus /> : null}<JobRecovery projectId={projectId} onBusyChange={setJobRecoveryBusy} /></DialogContent></Dialog>
      </TopBar>
      <main className="vb-product-main"><div className="vb-product-content">{children}</div></main>
    </div>
  );
}

export function HomePage({ projectId, onNavigate }: { projectId: string; onNavigate: (projectId: string, section: WorkspaceSection) => void }) {
  // Task 35: all three cards used to state their text unconditionally, so each
  // one could be false -- "완성된 영상이 아직 없어요" stayed on screen after the
  // owner finished a render. Home still must not poll the job list
  // (ProductShell.test pins that to the job dialog), so it asks one dedicated
  // endpoint that counts server-side. If that call fails the cards fall back to
  // saying nothing about state rather than guessing, and stay clickable.
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [summaryError, setSummaryError] = useState(false);
  const [summaryRequest, setSummaryRequest] = useState(0);
  useEffect(() => {
    let active = true;
    setSummary(null);
    setSummaryError(false);
    void api.getHomeSummary(projectId)
      .then((next) => { if (active) setSummary(next); })
      .catch(() => { if (active) setSummaryError(true); });
    return () => { active = false; };
  }, [projectId, summaryRequest]);
  const draftText = summaryError ? "상태 확인 실패" : summary === null ? "상태 확인 중"
    : summary.has_draft ? "초안 있음" : "초안 없음";
  const finishedText = summaryError ? "상태 확인 실패" : summary === null ? "상태 확인 중"
    : `${summary.finished_video_count}개`;
  const assetText = summaryError ? "상태 확인 실패" : summary === null ? "상태 확인 중"
    : summary.asset_gap_count > 0 ? `부족 ${summary.asset_gap_count}곳` : "준비 완료";

  // The cards are ordered the way the work actually runs: bring footage in,
  // edit it, then take it out. The old order opened with editing, which is
  // the middle of the job.
  //
  // "다음 할 일" used to state its fact three times: a keyword line here, a
  // checklist under it, and again on whichever card matched. The three cards
  // below already say each fact exactly once, so this section now only names
  // and acts on the next step -- one button, no restated heading or list.
  // owner: "어떤 버튼을 눌러야 할지 하나도 모르겠어." 여기에 `다음에 할 일`처럼
  // 보이는 단추가 다섯 개 있었다 -- 새 영상 만들기, 다음 할 일, 그리고 카드 세
  // 개의 단추. 다 그럴듯해서 어느 것이 지금 할 일인지 화면이 말해 주지 않았다.
  //
  // 이제 **들어가는 길을 먼저 고르게** 한다(Vrew 방식, owner 지시 2026-08-21).
  // 아래 상태 카드는 남기되 **단추를 뗐다** -- 각 화면으로 가는 길은 메뉴에 이미
  // 있고, 여기서는 사실만 한 번씩 말한다.
  return <section className="vb-home" data-testid="product-home">
    {/* 이어서 하기를 뺀 세 길(대본·찍어 둔 영상·유진에게 부탁)은 **같은 화면**으로
        간다. 이야기 화면이 대본을 받는 자리(붙여넣기·파일·영상·유진)를 모두 갖고
        있어서, 길마다 화면을 따로 두면 같은 것을 네 벌 관리하게 된다. */}
    <StartChooser hasDraft={summary?.has_draft === true} onStart={(path) => onNavigate(projectId, path === "continue" ? "editing" : "create")} />
    <div className="vb-home-grid"><HomeCard title="미디어" description={assetText} /><HomeCard title="편집" description={draftText} /><HomeCard title="완성본" description={finishedText} /></div>
    {summaryError ? <Button variant="outline" onClick={() => setSummaryRequest((value) => value + 1)}>상태 다시 확인</Button> : null}
    <HomeYujinChat projectId={projectId} />
  </section>;
}
/** 상태만 말한다. 단추를 달면 첫 화면에 "다음에 할 일"로 보이는 것이 또 늘어난다 --
 *  각 화면으로 가는 길은 왼쪽 메뉴에 이미 있다. */
function HomeCard({ title, description }: { title: string; description: string }) { return <Card><CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader></Card>; }

export function SettingsPage({ section, onNavigate, projectId }: { section: SettingsSection; onNavigate: (section: SettingsSection) => void; projectId: string }) {
  const [settings, setSettings] = useState(readSettings);
  const [saveFailed, setSaveFailed] = useState(false);
  const persistedOnce = useRef(false);
  // 이번 세션에는 적용하되, 기기에 남지 않았다는 사실은 말한다. 저장은 상태가
  // 실제로 바뀐 뒤 한 번만 한다 -- updater 안에서 저장하면 StrictMode가 두 번
  // 부르고, 닫힌 변수로 계산하면 같은 batch의 두 번째 토글이 첫 번째를 지운다.
  useEffect(() => {
    if (!persistedOnce.current) { persistedOnce.current = true; return; }
    setSaveFailed(!saveSettings(settings));
  }, [settings]);
  const update = (patch: Partial<SettingsState>) => setSettings((previous) => ({ ...previous, ...patch }));
  const labels: Record<SettingsSection, string> = { general: "일반", appearance: "화면", "ai-privacy": "AI·개인정보", voice: "내 목소리", output: "출력", conversations: "유진 대화" };
  return <section className="vb-settings" data-testid="settings-page"><p className="vb-eyebrow">설정</p><h1>{labels[section]}</h1><div className="vb-settings-nav">{(Object.keys(labels) as SettingsSection[]).map((key) => <Button key={key} variant={key === section ? "default" : "outline"} onClick={() => onNavigate(key)}>{labels[key]}</Button>)}</div><p>이 기기에 저장되는 작업 환경을 조절합니다.</p><p className="vb-setting-note">설정은 이 기기에서만 관리됩니다.</p>{saveFailed ? <p role="status" className="vb-setting-note">설정을 이 기기에 저장하지 못했어요. 브라우저 저장 공간을 확인한 뒤 다시 눌러 주세요.</p> : null}{/* `시작할 때 마지막 프로젝트 열기`는 없앴다(owner 결정 2026-08-28) --
        `/`가 이제 항상 프로젝트 목록이라 이 토글이 가리키던 동작 자체가
        없어졌다. 지금은 이 자리에 조절할 항목이 없다. */}{section === "general" && <div className="vb-setting-control"><span>지금은 이 자리에 따로 조절할 항목이 없어요.</span></div>}{section === "appearance" && <><SettingToggle label="조밀한 화면" checked={settings.compact} onChange={(checked) => update({ compact: checked })} /><SettingToggle label="움직임 줄이기" checked={settings.reducedMotion} onChange={(checked) => update({ reducedMotion: checked })} /></>}{/* Not a switch: VideoBox has no non-local mode to turn this off into. */}
      {section === "ai-privacy" && <div className="vb-setting-control"><span>모든 처리는 이 기기 안에서만 이뤄집니다.</span></div>}{section === "voice" && <div className="vb-setting-control"><span>내 목소리 등록과 내레이션 만들기는 미디어 단계의 내레이션에서 합니다.</span><a className="vb-action-link" href={`/projects/${encodeURIComponent(projectId)}/assets`}>내레이션 열기</a></div>}{section === "output" && <div className="vb-setting-control"><span>완성본은 MP4(H.264)로 만듭니다.</span></div>}{section === "conversations" && <ConversationCleanup key={projectId} projectId={projectId} />}</section>;
}
export function ProductEmptyPage({ title, description, action, onClick }: { title: string; description: string; action: string; onClick: () => void }) { return <Empty><EmptyHeader><EmptyTitle>{title}</EmptyTitle><EmptyDescription>{description}</EmptyDescription></EmptyHeader><Button onClick={onClick}>{action}</Button></Empty>; }
function SettingToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) { return <Button variant="outline" className="vb-setting-control" aria-pressed={checked} onClick={() => onChange(!checked)}>{label}: {checked ? "켜짐" : "꺼짐"}</Button>; }
