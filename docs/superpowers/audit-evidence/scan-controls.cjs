// 계획 I Task 0 Step 4 (a): 단추 정적 점검. 사용법: cd apps/web && node ../../docs/superpowers/audit-evidence/scan-controls.cjs src
// TypeScript 컴파일러 API로 .tsx(시험 제외)의 <Button>/<button> 여는 태그를 훑어 셋을 파일:줄로 낸다.
//  (1) 손잡이 없음  (2) 조건 때문에 disabled인데 이유(title/aria-describedby) 없음  (3) 아이콘 단추인데 이름(aria-label/title) 없음
const fs = require("node:fs");
const path = require("node:path");
const ts = require(path.resolve("node_modules/typescript"));

const HANDLERS = new Set(["onClick", "onPointerDown", "onMouseDown", "onKeyDown", "onSelect", "asChild", "form"]);
const BUSY = /busy|pending|saving|loading|starting|submitting|running|sending|uploading|recording/i;

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (entry.name !== "node_modules") walk(full, out); }
    else if (full.endsWith(".tsx") && !/\.test\.tsx$/.test(full)) out.push(full);
  }
  return out;
}

const root = process.argv[2] ?? "src";
const noHandler = [], noReason = [], noName = [];
for (const file of walk(root)) {
  const source = ts.createSourceFile(file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const visit = (node) => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(source);
      if (tag === "Button" || tag === "button") {
        const attrs = new Map();
        let spread = false;
        for (const attr of node.attributes.properties) {
          if (ts.isJsxSpreadAttribute(attr)) { spread = true; continue; }
          attrs.set(attr.name.getText(source), attr.initializer ? attr.initializer.getText(source) : "true");
        }
        const where = `${file.split(path.sep).join("/")}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
        const submit = /submit/.test(attrs.get("type") ?? "");
        if (!spread && !submit && ![...attrs.keys()].some((k) => HANDLERS.has(k))) noHandler.push(where);
        if (attrs.has("disabled") && !attrs.has("title") && !attrs.has("aria-describedby")) {
          const expr = attrs.get("disabled").replace(/^\{|\}$/g, "").replace(/^!+/, "").trim();
          const lastWord = expr.split(".").pop();
          const single = /^[A-Za-z_$][\w$.?]*$/.test(expr) && BUSY.test(lastWord);
          if (!single) noReason.push(`${where}  disabled=${attrs.get("disabled")}`);
        }
        if (/^"?\{?"?icon/.test(attrs.get("size") ?? "") && !attrs.has("aria-label") && !attrs.has("title")) noName.push(where);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}
const byFile = (list) => { const m = {}; for (const w of list) { const f = w.split(":")[0]; m[f] = (m[f] ?? 0) + 1; } return Object.entries(m).sort((a, b) => b[1] - a[1]); };
console.log(`== (1) 손잡이 없는 단추: ${noHandler.length}`); noHandler.forEach((w) => console.log(w));
console.log(`== (2) 조건 비활성인데 이유 없음: ${noReason.length}곳 / ${byFile(noReason).length}파일`);
byFile(noReason).slice(0, 12).forEach(([f, n]) => console.log(`${n}\t${f}`));
if (process.env.SCAN_VERBOSE) noReason.forEach((w) => console.log(w));
console.log(`== (3) 이름 없는 아이콘 단추: ${noName.length}`); noName.forEach((w) => console.log(w));
