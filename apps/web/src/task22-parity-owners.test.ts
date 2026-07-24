import { existsSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";

import {
  ScriptKind,
  ScriptTarget,
  createSourceFile,
  forEachChild,
  isIdentifier,
  isJsxAttribute,
  isJsxElement,
  isJsxSelfClosingElement,
  isStringLiteral,
} from "typescript";
import { describe, expect, it } from "vitest";

const sourceRoot = import.meta.dirname;
const webRoot = resolve(sourceRoot, "..");
const entrypoint = resolve(sourceRoot, "main.tsx");
const importPattern = /\b(?:import|export)\s+(?:type\s+)?(?:[^"'`;]*?\s+from\s+)?["'](\.[^"']+)["']/g;

function resolveTypeScriptImport(importer: string, specifier: string) {
  const base = resolve(dirname(importer), specifier);
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    resolve(base, "index.ts"),
    resolve(base, "index.tsx"),
  ];
  return candidates.find((candidate) => /\.(?:ts|tsx)$/.test(candidate) && existsSync(candidate)) ?? null;
}

function reachableTypeScriptModules(entry: string) {
  const reachable = new Set<string>();
  const pending = [entry];
  while (pending.length > 0) {
    const file = pending.pop()!;
    if (reachable.has(file)) continue;
    reachable.add(file);
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(importPattern)) {
      const dependency = resolveTypeScriptImport(file, match[1]);
      if (dependency && !reachable.has(dependency)) pending.push(dependency);
    }
  }
  return reachable;
}

function sourcePath(file: string) {
  return relative(sourceRoot, file).replaceAll("\\", "/");
}

function nativeControlSignatures(file: string) {
  const source = readFileSync(file, "utf8");
  const sourceFile = createSourceFile(file, source, ScriptTarget.Latest, true, ScriptKind.TSX);
  const signatures: string[] = [];
  const nativeControls = new Set(["button", "input", "select", "textarea", "dialog"]);

  function visit(node: Parameters<typeof forEachChild>[0]): void {
    const openingElement = isJsxElement(node)
      ? node.openingElement
      : isJsxSelfClosingElement(node)
        ? node
        : null;
    const tagName = openingElement?.tagName;
    if (openingElement && tagName && isIdentifier(tagName) && nativeControls.has(tagName.text)) {
      const marker = openingElement.attributes.properties.find(
        (property) => isJsxAttribute(property) && property.name.text === "data-native-control",
      );
      const markerValue = marker && isJsxAttribute(marker) && marker.initializer && isStringLiteral(marker.initializer)
        ? marker.initializer.text
        : "<missing>";
      signatures.push(`${tagName.text}:${markerValue}`);
    }
    forEachChild(node, visit);
  }

  visit(sourceFile);
  return signatures.sort();
}

const nativeControlAllowlist = {
  "features/director/AssetPreviewPlayer.tsx": {
    controls: ["button:candidate-preview", "button:narration-mute", "button:narration-solo"],
    reason: "Media audition transport directly coordinates the owned audio and video elements.",
  },
  "features/editor/preview/preview-stage.tsx": {
    controls: ["button:audition-source", "button:refresh-exact", "button:return-exact", "button:toggle-playback"],
    reason: "The one-player preview transport directly owns playback and audition state.",
  },
  "features/editor/timeline/TimelineDock.tsx": {
    controls: [
      "button:placement-move",
      "button:placement-trim-end",
      "button:placement-trim-start",
      "button:timeline-clip-select",
      "button:timeline-reorder",
      "button:timeline-trim-end",
      "button:timeline-trim-start",
    ],
    reason: "Timeline drag, trim, and keyboard interaction requires direct pointer and focus ownership.",
  },
} as const;

describe("Task 22 canonical production owners", () => {
  it("removes retired legacy shell owners, styles, adapters, and fast-path references", () => {
    const retiredFiles = [
      "App.tsx",
      "app.test.tsx",
      "app/LegacyWorkspacePage.tsx",
      "legacy-baseline.test.tsx",
      "legacy-output-api.ts",
      "styles/legacy.css",
      "app/ProjectWorkspaceProvider.tsx",
      "app/ProjectWorkspaceProvider.test.tsx",
      "features/editor/legacySessionProjection.ts",
      "features/editor/legacySessionProjection.test.ts",
      "features/media/ManualMediaLibrary.tsx",
      "features/media/manual-media-library.test.tsx",
      "features/media/MediaAnalysisPanel.tsx",
      "features/media/media-analysis-panel.test.tsx",
      "features/director/DirectorWorkspacePanel.tsx",
      "features/director/DirectorWorkspacePanel.test.tsx",
      "features/director/DirectorWorkspace.tsx",
      "features/director/director-workspace.test.tsx",
      "features/director/DirectorContextBar.tsx",
      "features/director/DirectorContextBar.test.tsx",
      "features/director/ProposalCandidateCard.tsx",
      "features/director/ProposalCandidateCard.test.tsx",
      "features/director/ProposalComparisonTray.tsx",
      "features/director/proposal-comparison-tray.test.tsx",
      "features/director/DirectorHistoryControls.tsx",
      "features/director/director-history-controls.test.tsx",
      "features/director/director-apply-scope.ts",
      "features/director/director-apply-scope.test.ts",
      "features/director/directorTypes.ts",
      "features/director/useResponsiveDirector.ts",
      "features/director/responsive-director.test.tsx",
      "features/director/useEditingShortcuts.ts",
      "features/director/editing-shortcuts.test.tsx",
    ];
    for (const retiredFile of retiredFiles) {
      expect(existsSync(resolve(sourceRoot, retiredFile)), `${retiredFile} must be removed`).toBe(false);
    }

    const references = [
      readFileSync(resolve(sourceRoot, "styles/index.css"), "utf8"),
      readFileSync(resolve(sourceRoot, "ui-system.test.tsx"), "utf8"),
      readFileSync(resolve(sourceRoot, "user-copy-policy.test.ts"), "utf8"),
      readFileSync(resolve(webRoot, "package.json"), "utf8"),
      readFileSync(resolve(webRoot, "../../scripts/dev-fast-path.ps1"), "utf8"),
      readFileSync(resolve(webRoot, "../../scripts/review-action-fast-path.ps1"), "utf8"),
    ].join("\n");
    expect(references).not.toMatch(/(?:src\/)?app\.test\.tsx|@import\s+["']\.\/legacy\.css|readFileSync\([^)]*legacy\.css|legacy-output-api/);
  });

  it("keeps legacy output calls and their legacy UI owners unreachable from main.tsx", () => {
    const reachable = reachableTypeScriptModules(entrypoint);
    const paths = [...reachable].map(sourcePath);
    const endpointStrings = ["/jobs/preview-render", "/jobs/capcut-export"];

    expect(paths).not.toContain("App.tsx");
    expect(paths).not.toContain("app/LegacyWorkspacePage.tsx");

    for (const file of reachable) {
      const source = readFileSync(file, "utf8");
      expect(source, `${sourcePath(file)} references a legacy output mutation`).not.toMatch(/\b(?:renderPreview|exportCapcut)\b/);
      for (const endpoint of endpointStrings) expect(source, `${sourcePath(file)} contains ${endpoint}`).not.toContain(endpoint);
    }
  });

  it("keeps the canonical production graph free of retired legacy class owners", () => {
    const retiredClassPattern = /(?:\bvb-legacy\b|\baction-button\b|\btab-button\b|\berror-banner\b|\bsection-kicker\b|\bmeta-copy\b|\brecommendation-evidence\b|className=["'](?:field|panel|content)["'])/;
    for (const file of reachableTypeScriptModules(entrypoint)) {
      if (!file.endsWith(".tsx")) continue;
      expect(readFileSync(file, "utf8"), `${sourcePath(file)} retains a legacy class owner`).not.toMatch(retiredClassPattern);
    }
  });

  it("keeps native controls on an explicit reachable AST allowlist", () => {
    const observed = new Map<string, string[]>();
    for (const file of reachableTypeScriptModules(entrypoint)) {
      if (!file.endsWith(".tsx") || sourcePath(file).startsWith("components/ui/")) continue;
      const signatures = nativeControlSignatures(file);
      if (signatures.length > 0) observed.set(sourcePath(file), signatures);
    }

    for (const [file, signatures] of observed) {
      const entry = nativeControlAllowlist[file as keyof typeof nativeControlAllowlist];
      expect(entry, `${file} needs a documented native-control exception`).toBeDefined();
      expect(signatures, `${file} native-control inventory drifted`).toEqual(entry?.controls);
      expect(entry?.reason.trim().length, `${file} needs an exception reason`).toBeGreaterThan(20);
    }
    for (const file of Object.keys(nativeControlAllowlist)) {
      expect(observed.has(file), `${file} is an unused native-control exception`).toBe(true);
    }
  });

  it("retains the persisted preview and export compatibility readers without restoring mutations", () => {
    const client = readFileSync(resolve(sourceRoot, "api.ts"), "utf8");
    expect(client).toMatch(/getPreview:[\s\S]{0,180}\/previews\/\$\{jobId\}/);
    expect(client).toMatch(/getExport:[\s\S]{0,180}\/exports\/\$\{jobId\}/);
    expect(client).not.toMatch(/\b(?:renderPreview|exportCapcut)\s*:/);
  });

  it("keeps every retained workspace section on its canonical component owner", () => {
    const router = readFileSync(resolve(sourceRoot, "app/AppRouter.tsx"), "utf8");
    const owners = [
      [/normalizedSection === "home"/, /<HomePage\b/],
      [/normalizedSection === "create"/, /<CreationInterview\b/],
      [/normalizedSection === "media"/, /<MediaWorkspacePage\b/],
      [/normalizedSection === "outputs"/, /<OutputsPage\b/],
      [/normalizedSection === "timeline" \|\| normalizedSection === "review"/, /<TimelineReviewPage\b/],
      [/section === "editor"/, /<EditorWorkbenchRoute\b/],
    ] as const;

    for (const [routeGuard, owner] of owners) {
      expect(router).toMatch(routeGuard);
      expect(router).toMatch(owner);
    }
    expect(router).toMatch(/params\.section === "settings"/);
    expect(router).toMatch(/\/settings\/general/);
    expect(router).toMatch(/<SettingsPage\b/);
  });

  it("keeps the canonical output acceptance path on exact preview, current render, draft, and explicit stale recovery", () => {
    const outputs = readFileSync(resolve(sourceRoot, "app/OutputsPage.tsx"), "utf8");
    const outputTests = readFileSync(resolve(sourceRoot, "app/OutputsPage.test.tsx"), "utf8");
    const e2e = readFileSync(resolve(sourceRoot, "../e2e/z-script-first-vertical.spec.mjs"), "utf8");

    expect(outputs).toContain("getEditorPlaybackManifest");
    expect(outputs).toContain("exactPreviewState");
    expect(outputs).toContain("편집에서 미리보기 열기");
    expect(outputTests).toContain("does not let a delayed project A exact-preview response replace project B");
    expect(outputTests).toContain("keeps retained final output visible when the exact-preview status read fails");
    expect(e2e).toContain("/exact-previews/exact-e2e-");
    expect(e2e).toContain("__e2e/mark-outputs-stale");
    expect(e2e).toContain("실제 CapCut Desktop에서 열기와 가져오기는 별도로 확인해야 해요.");
  });

  it("keeps every Task 22 parity row mapped to a canonical route, component test, and E2E owner", () => {
    const router = readFileSync(resolve(sourceRoot, "app/AppRouter.tsx"), "utf8");
    const shell = readFileSync(resolve(sourceRoot, "app/ProductShell.tsx"), "utf8");
    const rows = [
      {
        capability: "project create/select and source ingest",
        ownerSource: router, owner: /normalizedSection === "create"[\s\S]{0,240}<CreationInterview\b/,
        componentEvidence: [["project-onboarding.test.tsx", "registers narration plus script from local paths"], ["features/creation/CreationInterview.test.tsx", "uploads a supported creator script"]],
        e2eEvidence: ["z-script-first-vertical.spec.mjs", "ready-assets approval uses returned IDs"],
      },
      {
        capability: "media list and recovery",
        ownerSource: router, owner: /normalizedSection === "media"[\s\S]{0,800}<MediaWorkspacePage\b/,
        componentEvidence: [["features/media/MediaWorkspacePage.test.tsx", "supports cancel, retry, and review"]],
        e2eEvidence: ["media-recovery.spec.mjs", "recovers local analysis with authoritative refreshes"],
      },
      {
        capability: "current/global job recovery",
        ownerSource: shell, owner: /<JobRecovery projectId=\{projectId\}/,
        componentEvidence: [["features/jobs/JobRecovery.test.tsx", "retries a global row with its own project and job IDs"]],
        e2eEvidence: ["job-recovery.spec.mjs", "lazily retries a global row"],
      },
      {
        capability: "script draft and atomic creation",
        ownerSource: router, owner: /normalizedSection === "create"[\s\S]{0,240}<CreationInterview\b/,
        componentEvidence: [["features/creation/CreationInterview.test.tsx", "requires an explicit creator confirmation"]],
        e2eEvidence: ["z-script-first-vertical.spec.mjs", "gap-only approval preserves returned gap IDs"],
      },
      {
        capability: "timeline and review",
        ownerSource: router, owner: /normalizedSection === "timeline" \|\| normalizedSection === "review"[\s\S]{0,500}<TimelineReviewPage\b/,
        componentEvidence: [["features/review/TimelineReviewPage.test.tsx", "links an exact segment to the pinned editor"]],
        e2eEvidence: ["review-to-editor.spec.mjs", "opens the pinned editor"],
      },
      {
        capability: "editor workbench",
        ownerSource: router, owner: /section === "editor"[\s\S]{0,300}<EditorWorkbenchRoute\b/,
        componentEvidence: [["features/editor/workbench/editor-workbench-route.test.tsx", "publishes nothing until the matching manifest and session arrive together"]],
        e2eEvidence: ["exact-preview.spec.mjs", "current exact proxy plays a valid local MP4"],
      },
      {
        capability: "settings and voice review",
        ownerSource: router, owner: /path: "\/settings\/\$section"[\s\S]{0,180}component: SettingsRoutePage/,
        componentEvidence: [["features/settings/VoiceTtsSettings.test.tsx", "creates and reviews candidates"]],
        e2eEvidence: ["voice-tts-settings.spec.mjs", "canonical settings route"],
      },
      {
        capability: "canonical outputs",
        ownerSource: router, owner: /normalizedSection === "outputs"[\s\S]{0,240}<OutputsPage\b/,
        componentEvidence: [["app/OutputsPage.test.tsx", "owns the current exact-preview reference"]],
        e2eEvidence: ["z-script-first-vertical.spec.mjs", "current-revision playback and CapCut smoke"],
      },
    ] as const;

    for (const row of rows) {
      expect(row.ownerSource, `${row.capability} canonical owner`).toMatch(row.owner);
      for (const [componentTest, marker] of row.componentEvidence) {
        const componentPath = resolve(sourceRoot, componentTest);
        expect(existsSync(componentPath), `${row.capability} component owner ${componentTest}`).toBe(true);
        expect(readFileSync(componentPath, "utf8"), `${row.capability} component assertion ${marker}`).toContain(marker);
      }
      const [e2eFile, e2eMarker] = row.e2eEvidence;
      const e2ePath = resolve(webRoot, "e2e", e2eFile);
      expect(existsSync(e2ePath), `${row.capability} E2E owner ${e2eFile}`).toBe(true);
      expect(readFileSync(e2ePath, "utf8"), `${row.capability} E2E assertion ${e2eMarker}`).toContain(e2eMarker);
    }

    const recoveryRows = [
      {
        route: "project create and source ingest",
        ownerSource: router,
        owner: /normalizedSection === "create"[\s\S]{0,240}<CreationInterview\b/,
        componentEvidence: [
          ["project-onboarding.test.tsx", "keeps the created project and retries only the failed narration ingest"],
          ["features/creation/CreationInterview.test.tsx", "keeps a failed durable answer on the same question with an actionable retry"],
          ["app/AppRouter.test.tsx", "does not let a late A workspace response overwrite the currently routed B workspace"],
        ],
        e2eEvidence: ["product-shell.spec.mjs", "다시 준비"],
      },
      {
        route: "media",
        ownerSource: router,
        owner: /normalizedSection === "media"[\s\S]{0,800}<MediaWorkspacePage\b/,
        componentEvidence: [
          ["features/media/MediaWorkspacePage.test.tsx", "shows loading, empty, failure, and refresh recovery"],
          ["features/media/MediaWorkspacePage.test.tsx", "discards late project A results after switching to project B"],
        ],
        e2eEvidence: ["media-recovery.spec.mjs", "recovers local analysis with authoritative refreshes"],
      },
      {
        route: "current and global jobs",
        ownerSource: shell,
        owner: /<JobRecovery projectId=\{projectId\}/,
        componentEvidence: [
          ["features/jobs/JobRecovery.test.tsx", "recovers list errors"],
          ["features/jobs/JobRecovery.test.tsx", "discards a late current-project response after A changes to B"],
        ],
        e2eEvidence: ["job-recovery.spec.mjs", "refreshes global truth"],
      },
      {
        route: "timeline and review",
        ownerSource: router,
        owner: /normalizedSection === "timeline" \|\| normalizedSection === "review"[\s\S]{0,500}<TimelineReviewPage\b/,
        componentEvidence: [
          ["features/review/TimelineReviewPage.test.tsx", "shows no-session, no-exact-match, load error, and an explicit successful refresh"],
          ["features/review/TimelineReviewPage.test.tsx", "fences a late project A detail response after switching to B"],
        ],
        e2eEvidence: ["review-to-editor.spec.mjs", "review route recovers an initial load error with an explicit authoritative refresh"],
      },
      {
        route: "editor",
        ownerSource: router,
        owner: /section === "editor"[\s\S]{0,300}<EditorWorkbenchRoute\b/,
        componentEvidence: [
          ["features/editor/workbench/editor-workbench-route.test.tsx", "publishes nothing until the matching manifest and session arrive together"],
          ["features/editor/workbench/editor-workbench-route.test.tsx", "keeps the manifest editor usable when an asset list fails and gives contained retry-safe guidance"],
          ["features/editor/workbench/editor-workbench-route.test.tsx", "ignores a stale A asset load after route navigation to B"],
        ],
        e2eEvidence: ["exact-preview.spec.mjs", "failed proxy retry requests the current revision and refreshes the surfaced status"],
      },
      {
        route: "voice settings",
        ownerSource: router,
        owner: /path: "\/settings\/\$section"[\s\S]{0,180}component: SettingsRoutePage/,
        componentEvidence: [
          ["features/settings/VoiceTtsSettings.test.tsx", "shows recoverable load errors and keeps list requests single-flight"],
          ["features/settings/VoiceTtsSettings.test.tsx", "fences late project A responses after switching to project B"],
        ],
        e2eEvidence: ["voice-tts-settings.spec.mjs", "목소리 목록을 새로 불러왔어요."],
      },
      {
        route: "outputs",
        ownerSource: router,
        owner: /normalizedSection === "outputs"[\s\S]{0,240}<OutputsPage\b/,
        componentEvidence: [
          ["app/OutputsPage.test.tsx", "keeps a failed status read recoverable without offering output mutations"],
          ["app/OutputsPage.test.tsx", "does not let a delayed project A status response replace project B"],
        ],
        e2eEvidence: ["z-script-first-vertical.spec.mjs", "__e2e/mark-outputs-stale"],
      },
      {
        route: "unknown project",
        ownerSource: router,
        owner: /notFoundComponent: RecoveryPage/,
        componentEvidence: [["app/AppRouter.test.tsx", "renders recovery for an unknown project"]],
        e2eEvidence: ["product-shell.spec.mjs", "unknown project route offers canonical recovery"],
      },
    ] as const;

    expect(recoveryRows).toHaveLength(8);
    for (const recovery of recoveryRows) {
      expect(recovery.ownerSource, `${recovery.route} recovery owner`).toMatch(recovery.owner);
      for (const [componentTest, marker] of recovery.componentEvidence) {
        const componentPath = resolve(sourceRoot, componentTest);
        expect(existsSync(componentPath), `${recovery.route} recovery component ${componentTest}`).toBe(true);
        expect(readFileSync(componentPath, "utf8"), `${recovery.route} recovery assertion ${marker}`).toContain(marker);
      }
      const [e2eFile, e2eMarker] = recovery.e2eEvidence;
      const e2ePath = resolve(webRoot, "e2e", e2eFile);
      expect(existsSync(e2ePath), `${recovery.route} recovery E2E ${e2eFile}`).toBe(true);
      expect(readFileSync(e2ePath, "utf8"), `${recovery.route} recovery E2E assertion ${e2eMarker}`).toContain(e2eMarker);
    }
  });
});
