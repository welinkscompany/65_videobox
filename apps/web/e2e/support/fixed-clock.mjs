export const fixedClockEpochMs = 0;

export function fixedClockInit(epochMs) {
  const NativeDate = globalThis.Date;
  class FixedDate extends NativeDate {
    constructor(...args) {
      super(...(args.length ? args : [epochMs]));
    }

    static now() {
      return epochMs;
    }
  }
  Object.setPrototypeOf(FixedDate, NativeDate);
  globalThis.Date = FixedDate;
}

export async function installFixedClock(page) {
  await page.addInitScript(fixedClockInit, fixedClockEpochMs);
}

export async function waitForStableCapture(page) {
  await page.evaluate(async () => {
    await document.fonts?.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
}

export function playwrightSnapshotOptions(path, shouldWrite = process.env.VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS === "1") {
  return {
    ...(shouldWrite ? { path } : {}),
    animations: "disabled",
    caret: "hide",
  };
}
