import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";

// 스파이크 H-e: 눈금 글자가 붙지 않는다. 고정 프로젝트는 3.75초라서 재생 목록의 길이만 120초로 바꿔 받는다
// (점검 그림 10의 742e1924 전체 보기와 같은 조건). 글자 상자를 재서 간격을 확인한다.
const SHOT_DIR = path.resolve("../../.superpowers/sdd/2026-10-08-editor-core-repair-h.ko/task-10-shots");
const MIN_GAP_PX = 120;

async function stretchTo120(page) {
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.output.duration_sec = 120;
    await route.fulfill({ response, json: body });
  });
}

const measure = (page) => page.evaluate(() => {
  const majors = [...document.querySelectorAll(".vb-ruler-major")].map((el) => {
    const r = el.getBoundingClientRect();
    return { label: el.textContent, left: r.left, right: r.right, labelWidth: el.scrollWidth };
  });
  const minors = document.querySelectorAll(".vb-ruler-minor").length;
  const pps = Number(document.querySelector('[data-pixels-per-second]').getAttribute("data-pixels-per-second"));
  const list = document.querySelector('[aria-label="시간 눈금"]').getBoundingClientRect();
  return { majors, minors, pps, listLeft: list.left, listRight: list.right };
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }, { width: 375, height: 812 }]) {
  test(`120초 전체 보기 눈금이 붙지 않는다 (${viewport.width}px)`, async ({ page }) => {
    mkdirSync(SHOT_DIR, { recursive: true });
    const { clean } = readFixture();
    await stretchTo120(page);
    await openEditor(page, clean, viewport);
    await page.getByRole("button", { name: "타임라인 전체 보기" }).click();
    await page.waitForTimeout(300);
    const m = await measure(page);
    console.log("RULER", viewport.width, JSON.stringify({ pps: m.pps, count: m.majors.length, minors: m.minors, labels: m.majors.map((x) => x.label), lefts: m.majors.map((x) => Math.round(x.left * 10) / 10) }));
    expect(m.majors.length).toBeGreaterThanOrEqual(2);
    expect(m.majors.length).toBeLessThanOrEqual(10); // 121개가 아니다
    const gaps = m.majors.slice(1).map((mark, i) => mark.left - m.majors[i].left);
    console.log("GAPS", viewport.width, JSON.stringify(gaps.map((g) => Math.round(g * 10) / 10)));
    for (const gap of gaps) expect(gap).toBeGreaterThanOrEqual(MIN_GAP_PX - 1);
    // 글자 상자는 서로 겹치지 않는다(다음 눈금 선보다 오른쪽 끝이 앞에 있다).
    m.majors.slice(1).forEach((mark, i) => expect(m.majors[i].right).toBeLessThanOrEqual(mark.left + 0.5));
    await page.getByRole("region", { name: "타임라인" }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOT_DIR, `ruler-120s-${viewport.width}.png`), fullPage: true });
  });
}

test("처음 화면(60초가 보이는 배율)과 3.75초 고정 프로젝트도 간격을 지킨다", async ({ page }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  const m = await measure(page);
  console.log("RULER-FIXTURE", JSON.stringify({ pps: m.pps, labels: m.majors.map((x) => x.label) }));
  const gaps = m.majors.slice(1).map((mark, i) => mark.left - m.majors[i].left);
  for (const gap of gaps) expect(gap).toBeGreaterThanOrEqual(MIN_GAP_PX - 1);
  await expect(page.getByLabel("눈금 0초")).toBeVisible();
});
