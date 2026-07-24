import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  ScriptKind,
  ScriptTarget,
  SyntaxKind,
  createSourceFile,
  forEachChild,
  isBinaryExpression,
  isConditionalExpression,
  isJsxAttribute,
  isJsxElement,
  isJsxExpression,
  isJsxFragment,
  isJsxSelfClosingElement,
  isJsxText,
  isStringLiteral,
} from "typescript";
import { describe, expect, it } from "vitest";

const uiFiles = [
  "ErrorBoundary.tsx",
  "ProjectOnboarding.tsx",
  "app/AppRouter.tsx",
  "app/OutputsPage.tsx",
  "app/ProductShell.tsx",
  "features/creation/CreationInterview.tsx",
  "features/director/AssetPreviewPlayer.tsx",
  "features/director/MediaReferenceBadge.tsx",
  "features/editor/assets/EditorAssetBrowser.tsx",
  "features/editor/inspector/InspectorControls.tsx",
  "features/editor/preview/preview-stage.tsx",
  "features/editor/timeline/TimelineDock.tsx",
  "features/editor/transcript/CaptionLane.tsx",
  "features/editor/transcript/TranscriptPanel.tsx",
  "features/editor/workbench/EditorWorkbench.tsx",
  "features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx",
  "features/editor/workbench/EditorWorkbenchRoute.tsx",
  "features/editor/workbench/RightDock.tsx",
  "features/jobs/JobRecovery.tsx",
  "features/media/DraftGapMedia.tsx",
  "features/media/MediaWorkspacePage.tsx",
  "features/review/TimelineReviewPage.tsx",
  "features/settings/VoiceTtsSettings.tsx",
];

function renderedCopy(source: string): string {
  const copy: string[] = [];
  const sourceFile = createSourceFile("Dashboard.tsx", source, ScriptTarget.Latest, true, ScriptKind.TSX);

  function collectExpressionCopy(node: Parameters<typeof forEachChild>[0]): void {
    if (isConditionalExpression(node)) {
      if (node.condition.kind === SyntaxKind.TrueKeyword) {
        collectExpressionCopy(node.whenTrue);
        return;
      }
      if (node.condition.kind === SyntaxKind.FalseKeyword) {
        collectExpressionCopy(node.whenFalse);
        return;
      }
      collectExpressionCopy(node.whenTrue);
      collectExpressionCopy(node.whenFalse);
      return;
    }
    if (isBinaryExpression(node) && [SyntaxKind.AmpersandAmpersandToken, SyntaxKind.BarBarToken].includes(node.operatorToken.kind)) {
      collectExpressionCopy(node.right);
      return;
    }
    if (isStringLiteral(node)) {
      copy.push(node.text);
      return;
    }
    if (isJsxElement(node) || isJsxFragment(node) || isJsxSelfClosingElement(node)) {
      visit(node);
    }
  }

  function visit(node: Parameters<typeof forEachChild>[0]): void {
    if (isJsxText(node)) {
      copy.push(node.getText(sourceFile));
    }
    if (isJsxAttribute(node) && ["aria-label", "aria-description", "placeholder", "title"].includes(node.name.text) && node.initializer) {
      if (isStringLiteral(node.initializer)) {
        copy.push(node.initializer.text);
      } else if (isJsxExpression(node.initializer) && node.initializer.expression) {
        collectExpressionCopy(node.initializer.expression);
      }
    }
    if (isJsxExpression(node)) {
      if (node.expression && (isJsxElement(node.parent) || isJsxFragment(node.parent))) {
        collectExpressionCopy(node.expression);
      }
      return;
    }
    forEachChild(node, visit);
  }

  visit(sourceFile);
  return copy.join("\n");
}

function dashboardCopy(): string {
  return uiFiles
    .map((file) => renderedCopy(readFileSync(resolve(import.meta.dirname, file), "utf8")))
    .join("\n");
}

function containsForbiddenDashboardCopy(copy: string, forbiddenTerm: string): boolean {
  if (/[가-힣]/u.test(forbiddenTerm)) {
    return copy.includes(forbiddenTerm);
  }
  const escapedTerm = forbiddenTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escapedTerm}\\b`, "i").test(copy);
}

describe("user-facing dashboard copy", () => {
  it("includes the retained media-reference copy while ignoring implementation props", () => {
    expect(uiFiles).toEqual(expect.arrayContaining([
      "features/director/MediaReferenceBadge.tsx",
      "features/editor/workbench/RightDock.tsx",
    ]));

    const copy = renderedCopy('<section data-state="Local Media Director">revision</section>');

    expect(copy).toMatch(/\brevision\b/i);
    expect(copy).not.toContain("Local Media Director");
  });

  it("ignores implementation-only JSX props", () => {
    const copy = renderedCopy('<section className="revision" data-state={"revision"} data-testid={"Local Media Director"}>루미</section>');

    expect(copy).toBe("루미");
  });

  it("ignores implementation-only props inside nested child JSX", () => {
    const copy = renderedCopy('<div>{true ? <section className="revision" data-state="revision">루미</section> : null}</div>');

    expect(copy).toBe("루미");
  });

  it("collects conditional child text without collecting condition state", () => {
    const copy = renderedCopy('<div>{mode === "revision" ? "루미" : null}</div>');

    expect(copy).toBe("루미");
  });

  it("collects literal accessible labels from JSX expressions", () => {
    const copy = renderedCopy('<button aria-label={"루미"} data-state={"revision"} />');

    expect(copy).toBe("루미");
  });

  it("collects conditional accessible-label branches without collecting condition state", () => {
    const copy = renderedCopy('<button aria-label={ready ? "revision" : "루미"} />');

    expect(copy).toBe("revision\n루미");
  });

  it("collects only value-producing logical accessible-label operands", () => {
    const copy = renderedCopy('<button aria-label={mode === "revision" && "루미"} title={status === "revision" || "준비"} />');

    expect(copy).toBe("루미\n준비");
  });

  it("does not collect source-only literals nested in formatter calls or objects", () => {
    const copy = renderedCopy('<div>{formatStatus("revision")}{lookup({ fallback: "revision" })}</div>');

    expect(copy).toBe("");
  });

  it("uses Eugene and creator-language guidance in rendered UI", () => {
    const copy = dashboardCopy();

    expect(copy).toContain("유진");
    expect(copy).toContain("유진 대화");
    expect(copy).toMatch(/영상|편집|대본|자막/);
    expect(copy).not.toContain("루미");
  });

  it("detects Korean forbidden dashboard copy", () => {
    const copy = "시스템 개발 안내는 루미가 도와드려요.";

    for (const forbiddenTerm of ["시스템", "개발", "루미"]) {
      expect(containsForbiddenDashboardCopy(copy, forbiddenTerm)).toBe(true);
    }
    expect(containsForbiddenDashboardCopy("modeling a scene", "model")).toBe(false);
    expect(containsForbiddenDashboardCopy("model choice", "model")).toBe(true);
  });

  for (const forbiddenTerm of [
    "Local Media Director",
    "immutable preflight diff",
    "revision",
    "provider",
    "runtime",
    "fallback",
    "loopback",
    "API key",
    "model",
    "context",
    "pipeline",
    "Inspector",
    "job",
    "로컬 검수",
    "등록된 job 없음",
    "시스템",
    "개발",
    "런타임",
    "공급자",
    "제공자",
    "모델",
    "API 키",
    "루프백",
    "폴백",
    "컨텍스트",
    "리비전",
    "파이프라인",
  ]) {
    it(`does not expose ${forbiddenTerm} in rendered UI`, () => {
      expect(containsForbiddenDashboardCopy(dashboardCopy(), forbiddenTerm)).toBe(false);
    });
  }
});
