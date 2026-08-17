import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const dir = process.argv[2];
mkdirSync(dir, { recursive: true });
const P = "my-project";
const pages = [
  ["01-projects", `/projects`, null],
  ["02-library", `/library`, null],
  ["03-footage", `/footage`, null],
  ["04-settings", `/settings/general?project_id=${P}`, null],
  ["05-plan", `/projects/${P}/plan`, null],
  ["06-assets-videos", `/projects/${P}/assets`, null],
  ["07-assets-music", `/projects/${P}/assets`, "음악"],
  ["08-assets-sfx", `/projects/${P}/assets`, "효과음"],
  ["09-assets-narration", `/projects/${P}/assets`, "내레이션"],
  ["10-assets-import", `/projects/${P}/assets`, "가져오기"],
  ["11-editor", `/projects/${P}/editor`, null],
  ["12-review-output", `/projects/${P}/review`, null],
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const problems = [];
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 120)}`); });

for (const [name, path, tab] of pages) {
  try {
    await page.goto(`http://127.0.0.1:5173${path}`, { waitUntil: "networkidle", timeout: 30000 });
    if (tab) { await page.getByRole("tab", { name: tab }).click(); await page.waitForTimeout(1500); }
    await page.waitForTimeout(1200);
    const over = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    if (over) problems.push(`${name}: 가로 넘침`);
    await page.screenshot({ path: `${dir}/${name}.png`, fullPage: true });
    console.log(`${name} ok${over ? " (넘침)" : ""}`);
  } catch (error) {
    problems.push(`${name}: ${String(error).slice(0, 100)}`);
    console.log(`${name} FAILED`);
  }
}
console.log("--- 문제 ---");
console.log(problems.length ? problems.join("\n") : "없음");
await browser.close();
