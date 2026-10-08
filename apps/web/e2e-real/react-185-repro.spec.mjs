import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";

// 2026-10-08 점검 §3-6: 내보내기를 누르자 React #185(최대 갱신 깊이)로 편집기 영역이 영어 오류 화면이 된 일이 한 번 있었다.
// 개발 서버라 React 오류가 풀어서 나온다. 클립 고르기·분할(Ctrl+B)·되돌리기(Ctrl+Z)를 섞은 뒤 내보내기를 여러 번 열어 본다.
for (const key of ["clean", "duplicatedOverlays"]) {
  test(`${key}: 섞어 편집한 뒤 내보내기를 열어도 편집기가 멈추지 않고 편집 대상이 부풀지 않는다`, async ({ page }) => {
    const messages = [];
    page.on("console", (message) => { if (message.type() === "error") messages.push(`console: ${message.text()}`); });
    page.on("pageerror", (error) => messages.push(`pageerror: ${error.message}`));
    await openEditor(page, readFixture()[key]);
    const clips = page.getByRole("button", { name: /^영상 \d+번째 장면(?!.*이동$)/ });
    const clipCount = await clips.count();
    expect(clipCount).toBeGreaterThan(0);
    for (let step = 0; step < 12; step += 1) {
      await clips.nth(step % clipCount).click();
      if (step % 3 === 1) await page.keyboard.press("Control+b");
      if (step % 3 === 2) await page.keyboard.press("Control+z");
      await page.waitForTimeout(150);
    }
    for (let round = 0; round < 3; round += 1) {
      await page.getByRole("button", { name: "내보내기" }).first().click();
      await page.waitForTimeout(400);
      await page.keyboard.press("Escape");
    }
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/Something went wrong|Maximum update depth|Show Error/);
    expect(messages.filter((line) => /Maximum update depth|#185/.test(line))).toEqual([]);
    const select = page.getByRole("combobox", { name: "편집 대상" });
    if (await select.count()) {
      const values = await select.locator("option").evaluateAll((options) => options.map((option) => option.value));
      expect(values.length).toBeLessThanOrEqual(new Set(values).size);
    }
  });
}
