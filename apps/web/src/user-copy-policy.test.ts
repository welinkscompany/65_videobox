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
  "App.tsx",
  "ErrorBoundary.tsx",
  "features/director/AssetPreviewPlayer.tsx",
  "ProjectOnboarding.tsx",
  "features/director/DirectorWorkspace.tsx",
  "features/director/DirectorWorkspacePanel.tsx",
  "features/director/ProposalComparisonTray.tsx",
  "features/director/DirectorHistoryControls.tsx",
  "features/director/MediaReferenceBadge.tsx",
  "features/director/ProposalCandidateCard.tsx",
  "features/media/ManualMediaLibrary.tsx",
  "features/media/MediaAnalysisPanel.tsx",
];

function renderedCopy(source: string): string {
  const copy: string[] = [];
  const sourceFile = createSourceFile("Dashboard.tsx", source, ScriptTarget.Latest, true, ScriptKind.TSX);

  function collectExpressionCopy(node: Parameters<typeof forEachChild>[0]): void {
    if (isConditionalExpression(node)) {
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

describe("user-facing dashboard copy", () => {
  it("includes Director candidate and media-reference copy while ignoring implementation props", () => {
    expect(uiFiles).toEqual(expect.arrayContaining([
      "features/director/MediaReferenceBadge.tsx",
      "features/director/ProposalCandidateCard.tsx",
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

  it("uses Lumi in rendered UI", () => {
    expect(dashboardCopy()).toContain("루미");
  });

  for (const forbiddenTerm of ["Local Media Director", "immutable preflight diff", "revision"]) {
    it(`does not expose ${forbiddenTerm} in rendered UI`, () => {
      expect(dashboardCopy()).not.toMatch(new RegExp(`\\b${forbiddenTerm}\\b`, "i"));
    });
  }
});
