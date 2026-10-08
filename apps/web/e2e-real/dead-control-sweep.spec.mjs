// 편집기 죽은 단추 재고 조사 (계획 H Task 2). 이것은 측정이다 -- 시험은 항상 통과하고 결과를 JSON으로 쓴다.
// 진짜 백엔드의 고정 시험 프로젝트(임시 데이터 폴더)에서만 누른다. 소유자의 실제 스택(5173/8000)에는 닿지 않는다.
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

import { test } from "@playwright/test";

import { classifyControl } from "./support/controlCensus.mjs";
import { readFixture } from "./support/realFlow.mjs";

const OUTPUT = path.resolve("../../docs/superpowers/audit-evidence/2026-10-08-editor-ui/dead-controls.json");
const LIST_ONLY = process.env.CENSUS_LIST_ONLY === "1";
const STATES = ["no-selection", "clip-selected"];
const CHUNK = 10;
const SETTLE_MS = 800;

// 누르지 않는 목록. 되돌릴 수 없거나 바깥으로 나가거나 비싼 일을 시작하는 조작이다.
const SKIP_RULES = [
  { pattern: /완성본 만들기/, reason: "완성본 렌더 시작(오래 걸리고 파일을 만든다)" },
  { pattern: /업로드|올리기/, reason: "바깥(유튜브 등)으로 올리는 일" },
  { pattern: /지우기|삭제|보관/, reason: "지우기·보관(되돌릴 수 없는 저장 변경)" },
  { pattern: /내보내기 시작/, reason: "내보내기 시작(파일 생성)" },
  { pattern: /캡컷/, reason: "캡컷 내보내기(파일 생성, 선택적 호환 경로)" },
  { pattern: /받아쓰기/, reason: "말 받아쓰기 작업 시작(음성 인식 모델을 올리는 무거운 일)" },
  { pattern: /추천받기|요청 보내기/, reason: "유진 대화 호출(언어 모델 호출 -- 소유자 GPU를 쓸 수 있음)" },
];

function skipReason(name) {
  return SKIP_RULES.find((rule) => rule.pattern.test(name))?.reason ?? null;
}

// 페이지 쪽 도우미. 새로 열릴 때마다 심는다.
const PAGE_HELPERS = () => {
  const SELECTOR =
    "summary, button, [role=button], [role=tab], [role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], [role=switch], [role=checkbox], select, a[href]";
  const SCOPES = ".vb-editor-workbench, [role=dialog], [role=menu], [role=listbox], [data-radix-popper-content-wrapper]";
  const nameOf = (el) =>
    (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 80) ||
    el.getAttribute("title") ||
    el.getAttribute("data-native-control") ||
    "(이름 없음)";
  const roleOf = (el) =>
    el.getAttribute("role") || (el.tagName === "SELECT" ? "combobox" : el.tagName === "A" ? "link" : el.tagName === "SUMMARY" ? "summary" : "button");
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (!(rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none")) return false;
    // 닫힌 <details> 안쪽은 크기가 있어도 보이지 않는다(content-visibility). 접힌 곳 속 단추를 센 적이 있다.
    if (typeof el.checkVisibility === "function") return el.checkVisibility({ visibilityProperty: true, contentVisibilityAuto: true });
    return true;
  };
  const isDisabled = (el) =>
    el.disabled === true || el.getAttribute("aria-disabled") === "true" || el.hasAttribute("data-disabled");
  const HANDLERS = ["onClick", "onPointerDown", "onMouseDown", "onChange", "onKeyDown", "onSelect"];
  const propsOf = (el) => {
    const key = Object.keys(el).find((k) => k.startsWith("__reactProps$"));
    return key ? el[key] : null;
  };
  const ownHandler = (el) => {
    const props = propsOf(el);
    return props ? HANDLERS.some((name) => typeof props[name] === "function") : false;
  };
  // <summary>는 브라우저가 알아서 펼친다. 손잡이가 없어도 살아 있다.
  const hasHandlerFor = (el) => ownHandler(el) || el.tagName === "SUMMARY";
  // 이미 골라져 있어서 눌러도 달라질 것이 없는 조작인가.
  const isActive = (el) =>
    el.getAttribute("aria-selected") === "true" ||
    el.getAttribute("aria-pressed") === "true" ||
    el.getAttribute("aria-checked") === "true" ||
    ["active", "on", "checked"].includes(el.getAttribute("data-state") ?? "") ||
    (el.getAttribute("aria-current") ?? "false") !== "false";
  // 같은 묶음에서 안 골라진 형제(없으면 null) -- 먼저 눌러 상태를 바꿔 놓는 데 쓴다.
  const stateAttr = (el) => ["aria-selected", "aria-pressed", "aria-checked"].find((name) => el.hasAttribute(name)) ?? null;
  const inactiveSibling = (el) => {
    const attr = stateAttr(el);
    if (!attr) return null; // 켜짐/꺼짐을 aria로 드러내지 않는 조작은 '형제'를 알 수 없다

    const group = el.closest("[role=tablist], [role=radiogroup], [role=group], [role=toolbar]") ?? el.parentElement;
    if (!group) return null;
    const sameRole = (other) => other !== el && other.tagName === el.tagName && other.getAttribute("role") === el.getAttribute("role") && other.hasAttribute(attr);
    const sibling = [...group.querySelectorAll(SELECTOR)].find((other) => sameRole(other) && visible(other) && !isActive(other) && !isDisabled(other));
    if (!sibling) return null;
    sibling.scrollIntoView({ block: "center", inline: "center" });
    const rect = sibling.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, name: nameOf(sibling) };
  };
  const ancestorHandler = (el) => {
    for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) {
      if (ownHandler(node)) return true;
    }
    return false;
  };
  const collect = () => {
    const found = new Set();
    for (const scope of document.querySelectorAll(SCOPES)) {
      if (scope.matches(SELECTOR)) found.add(scope);
      for (const el of scope.querySelectorAll(SELECTOR)) found.add(el);
    }
    const seen = new Map();
    const result = [];
    for (const el of found) {
      if (!visible(el)) continue;
      const base = `${roleOf(el)}|${nameOf(el)}`;
      const occ = seen.get(base) ?? 0;
      seen.set(base, occ + 1);
      result.push({ el, key: base, occ });
    }
    return result;
  };
  const describe = (el) => {
    if (!el) return null;
    const label = el.getAttribute("aria-label") ?? el.getAttribute("data-native-control") ?? "";
    const cls = typeof el.className === "string" && el.className ? "." + el.className.split(" ")[0] : "";
    return el.tagName.toLowerCase() + cls + (label ? "[" + label.slice(0, 40) + "]" : "");
  };
  const ariaSnapshot = (el) =>
    ["aria-pressed", "aria-expanded", "aria-selected", "aria-checked", "aria-current", "data-state", "disabled", "aria-disabled"]
      .map((name) => name + "=" + el.getAttribute(name))
      .join(";");
  const overlays = () => document.querySelectorAll("[role=dialog], [role=menu], [role=listbox]").length;
  const find = (key, occ) => collect().find((item) => item.key === key && item.occ === occ) ?? null;
  const summarize = () =>
    collect().map(({ el, key, occ }) => ({
      key,
      occ,
      native: el.getAttribute("data-native-control"),
      disabled: isDisabled(el),
      title: el.getAttribute("title"),
      describedBy: (el.getAttribute("aria-describedby") ?? "")
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent?.trim())
        .filter(Boolean)
        .join(" / "),
      ownHandler: hasHandlerFor(el),
      ancestorHandler: ancestorHandler(el),
      isLink: el.tagName === "A" && el.hasAttribute("href"),
      isFormSubmit: el.tagName === "BUTTON" && el.type === "submit" && Boolean(el.form),
      isSelect: el.tagName === "SELECT",
      active: isActive(el),
    }));
  // 눌러 볼 준비: 클릭 지점, 가려짐 여부.
  const prepare = (key, occ) => {
    const item = find(key, occ);
    if (!item) return null;
    const { el } = item;
    el.scrollIntoView({ block: "center", inline: "center" });
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const hit = document.elementFromPoint(x, y);
    return {
      x,
      y,
      hitSelf: Boolean(hit) && (hit === el || el.contains(hit)),
      hit: describe(hit),
      disabled: isDisabled(el),
      active: isActive(el),
      sibling: isActive(el) ? inactiveSibling(el) : null,
      isSelect: el.tagName === "SELECT",
      pointerHandler: (() => {
        const props = propsOf(el);
        return Boolean(props && (typeof props.onPointerDown === "function" || typeof props.onMouseDown === "function"));
      })(),
      selectValues: el.tagName === "SELECT" ? [...el.options].map((option) => option.value) : [],
      selectValue: el.tagName === "SELECT" ? el.value : null,
    };
  };
  const observe = (key, occ) => {
    const item = find(key, occ);
    const state = { count: 0, startUrl: location.href, key, occ };
    state.observer = new MutationObserver((records) => {
      state.count += records.length;
    });
    state.observer.observe(document.body, { subtree: true, attributes: true, childList: true, characterData: true });
    state.before = {
      active: document.activeElement,
      aria: item ? ariaSnapshot(item.el) : "",
      overlays: overlays(),
    };
    state.el = item?.el ?? null;
    window.__censusObs = state;
  };
  const baselineCount = () => {
    const count = window.__censusObs.count;
    window.__censusObs.count = 0;
    return count;
  };
  const finish = () => {
    const state = window.__censusObs;
    state.observer.disconnect();
    const el = state.el;
    const connected = Boolean(el && el.isConnected);
    const active = document.activeElement;
    return {
      mutations: state.count,
      focusMoved: active !== state.before.active && active !== el && active !== document.body,
      ariaChanged: connected ? ariaSnapshot(el) !== state.before.aria : true,
      dialogOpened: overlays() > state.before.overlays,
      urlChanged: location.href !== state.startUrl,
      elementGone: !connected,
    };
  };
  window.__census = { summarize, prepare, observe, baselineCount, finish, collect, find, overlays };
};

test("편집기 조작 전부를 진짜 백엔드에서 눌러 죽은 단추를 센다", async ({ page, context }) => {
  test.setTimeout(60 * 60 * 1000);
  const { clean } = readFixture();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript("(" + PAGE_HELPERS.toString() + ")()");
  // 접힘·열림 같은 화면 상태가 저장소에 남아 다음 열기에 새는 것을 막는다. 문서가 새로 열릴 때마다 비운다.
  await page.addInitScript(() => {
    try {
      window.localStorage.clear();
      window.sessionStorage.clear();
    } catch {
      /* 저장소를 못 쓰는 환경 */
    }
  });

  const requests = [];
  const noisySignatures = new Set();
  const pageErrors = [];
  const mutatingRequests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    const signature = request.method() + " " + url.pathname;
    requests.push({ t: Date.now(), signature });
    if (request.method() !== "GET" && url.pathname.startsWith("/api/")) {
      mutatingRequests.push({ t: Date.now(), signature });
    }
  });
  page.on("pageerror", (error) => pageErrors.push({ t: Date.now(), message: String(error.message).slice(0, 160) }));
  const fileChoosers = [];
  page.on("filechooser", (chooser) => {
    fileChoosers.push(Date.now());
    void chooser.setFiles([]).catch(() => {});
  });
  page.on("dialog", (dialog) => void dialog.dismiss().catch(() => {}));
  context.on("page", (popup) => void popup.close().catch(() => {}));

  const editorPath = `/projects/${clean.projectId}/editor?session_id=${clean.sessionId}`;
  const observations = []; // 한 번 누른(또는 누르지 않은) 기록
  const restores = [];

  // 서버를 바꾸는 편집이 누적되면 뒤 조작의 전제(장면 수 등)가 달라진다. 시드 직후 폴더를 되돌려 놓는다.
  const dataRootsDir = path.resolve("test-results/real-flow-data");
  const newestRoot = () => {
    const names = readdirSync(dataRootsDir).sort();
    return path.join(dataRootsDir, names[names.length - 1]);
  };
  const projectDir = () => path.join(newestRoot(), "projects", "projects", clean.projectId);
  const pristineDir = path.resolve("test-results/census-pristine");
  let restoreChecked = 0;
  function snapshotProject() {
    rmSync(pristineDir, { recursive: true, force: true });
    cpSync(projectDir(), pristineDir, { recursive: true });
  }
  async function sessionRevision() {
    const response = await page.request.get(`/api/projects/${clean.projectId}/editing-sessions/${clean.sessionId}?include_history=false`);
    const body = await response.json().catch(() => ({}));
    return body.session_revision ?? body.revision ?? `status ${response.status()}`;
  }
  async function restoreIfMutated() {
    // 편집판·세션을 바꾸는 요청만 되돌릴 이유가 된다(미리보기 만들기·환경설정은 편집이 아니다).
    const edits = mutatingRequests.filter((request) => request.t > restoreChecked && /\/editing-sessions\/[^/]+\/(?!exact-preview|selected-range-preview|caption-style\/preflight)|\/timelines\//.test(request.signature));
    if (!edits.length) return false;
    restoreChecked = Date.now();
    // 서버가 열어 둔 파일이 있어 폴더째 지우면 윈도우가 거절한다. 시드 파일을 위에 덮어쓴다(편집이 쓰는 것은 세션·편집판 JSON).
    cpSync(pristineDir, projectDir(), { recursive: true, force: true, filter: (source) => !/\.(mp4|wav|png|jpe?g)$/i.test(source) });
    restores.push({ at: new Date().toISOString(), revisionAfterRestore: await sessionRevision() });
    return true;
  }
  snapshotProject();
  const seedRevision = await sessionRevision();

  async function openState(state) {
    await restoreIfMutated();
    await page.goto(editorPath);
    await page.getByRole("region", { name: "타임라인" }).waitFor({ state: "visible" });
    await page.waitForTimeout(1500);
    if (state === "clip-selected") {
      await page.getByRole("button", { name: /^영상 1번째/ }).first().click();
      await page.waitForTimeout(800);
    }
    // 가만히 있어도 나가는 요청(폴링)을 배운다. 그것은 단추 반응이 아니다.
    const from = Date.now();
    await page.waitForTimeout(2200);
    for (const request of requests) if (request.t >= from) noisySignatures.add(request.signature);
  }

  const summary = () => page.evaluate(() => window.__census.summarize());

  async function measure(state, item, parentChain) {
    const base = {
      state,
      key: item.key,
      occ: item.occ,
      native: item.native,
      parent: parentChain ?? null,
      ownHandler: item.ownHandler,
      ancestorHandler: item.ancestorHandler,
      isLink: item.isLink,
      isFormSubmit: item.isFormSubmit,
    };
    const name = item.key.split("|").slice(1).join("|");
    const reason = skipReason(parentChain ? parentChain + " " + name : name);
    if (reason) return { ...base, skipped: true, skipReason: reason };
    const disabledResult = () => ({
      ...base,
      disabled: true,
      disabledReason: [item.title, item.describedBy].filter(Boolean).join(" | ") || null,
    });
    if (item.disabled) return disabledResult();
    const prep = await page.evaluate(([key, occ]) => window.__census.prepare(key, occ), [item.key, item.occ]);
    if (!prep) return { ...base, missing: true };
    if (prep.disabled) return disabledResult();
    // 이미 골라진 조작은 눌러도 달라질 게 없다. 같은 묶음의 다른 형제를 먼저 눌러 상태를 바꿔 놓고 잰다.
    let preFlipped = null;
    if (prep.active && prep.sibling) {
      await page.mouse.click(prep.sibling.x, prep.sibling.y);
      await page.waitForTimeout(600);
      preFlipped = prep.sibling.name;
      const again = await page.evaluate(([key, occ]) => window.__census.prepare(key, occ), [item.key, item.occ]);
      if (!again) return { ...base, missing: true, preFlipped };
      Object.assign(prep, again);
    }
    // 고를 수 있는 값이 하나뿐인 선택 상자도 바꿔 볼 수 없다.
    const untestableActive = (prep.active && !prep.sibling) || (prep.isSelect && new Set(prep.selectValues).size < 2);
    await page.mouse.move(prep.x, prep.y);
    await page.waitForTimeout(150);
    await page.evaluate(([key, occ]) => window.__census.observe(key, occ), [item.key, item.occ]);
    await page.waitForTimeout(400);
    const baseline = await page.evaluate(() => window.__census.baselineCount());
    const beforeKeys = new Set((await summary()).map((control) => control.key + "#" + control.occ));
    const clickedAt = Date.now();
    // 선택 상자는 고른 값이 그대로 남으면(제어 컴포넌트가 되돌리지 않으면) 반응한 것이다 -- 값 자체가 화면에 보이는 변화다.
    let selectHeld = false;
    if (prep.isSelect) {
      const target = prep.selectValues.find((value) => value !== prep.selectValue);
      const handle = await page.evaluateHandle(([key, occ]) => window.__census.find(key, occ)?.el ?? null, [item.key, item.occ]);
      const element = handle.asElement();
      if (element && target !== undefined) {
        await element.selectOption(target).catch(() => {});
        await page.waitForTimeout(150);
        selectHeld = await element.evaluate((el, wanted) => el.value === wanted, target).catch(() => false);
      }
    } else {
      await page.mouse.click(prep.x, prep.y);
    }
    await page.waitForTimeout(SETTLE_MS);
    const after = await page.evaluate(() => window.__census.finish()).catch(() => ({
      mutations: 0,
      focusMoved: false,
      ariaChanged: false,
      dialogOpened: false,
      urlChanged: true,
      elementGone: true,
    }));
    const chooserOpened = fileChoosers.some((t) => t >= clickedAt);
    const seen = requests.filter((request) => request.t >= clickedAt && !noisySignatures.has(request.signature));
    const errors = pageErrors.filter((error) => error.t >= clickedAt);
    const newControls = (await summary().catch(() => []))
      .filter((control) => !beforeKeys.has(control.key + "#" + control.occ))
      .filter((control) => control.key !== item.key);
    const currentPath = new URL(page.url()).pathname + new URL(page.url()).search;
    const reaction = {
      domMutations: Math.max(0, after.mutations - Math.round(baseline * 2)),
      requests: seen.length,
      focusMoved: after.focusMoved,
      ariaChanged: after.ariaChanged || selectHeld,
      dialogOpened: after.dialogOpened || chooserOpened,
      urlChanged: currentPath !== editorPath || after.urlChanged,
    };
    let retriedWithDrag = false;
    const quietNow = !reaction.domMutations && !reaction.requests && !reaction.focusMoved && !reaction.ariaChanged && !reaction.dialogOpened && !reaction.urlChanged;
    if (quietNow && prep.hitSelf && prep.pointerHandler && !prep.isSelect && !(await page.evaluate(() => window.__census.overlays()).catch(() => 0))) {
      // 끌어서 쓰는 조작(재생 위치·손잡이)은 눌러서는 반응이 없다. 끌어 본다.
      retriedWithDrag = true;
      await page.evaluate(([key, occ]) => window.__census.observe(key, occ), [item.key, item.occ]).catch(() => {});
      const dragAt = Date.now();
      await page.mouse.move(prep.x, prep.y);
      await page.mouse.down();
      await page.mouse.move(prep.x + 60, prep.y, { steps: 6 });
      await page.mouse.up();
      await page.waitForTimeout(SETTLE_MS);
      const dragAfter = await page.evaluate(() => window.__census.finish()).catch(() => null);
      if (dragAfter) {
        const dragSeen = requests.filter((request) => request.t >= dragAt && !noisySignatures.has(request.signature));
        reaction.domMutations = Math.max(0, dragAfter.mutations - Math.round(baseline * 2));
        reaction.requests = dragSeen.length;
        reaction.focusMoved = dragAfter.focusMoved;
        reaction.ariaChanged = dragAfter.ariaChanged;
      }
    }
    return {
      ...base,
      clicked: true,
      retriedWithDrag,
      reaction,
      hitSelf: prep.hitSelf,
      hit: prep.hitSelf ? null : prep.hit,
      fileChooser: chooserOpened,
      preFlipped,
      untestableActive,
      baselineMutations: baseline,
      rawMutations: after.mutations,
      requestSignatures: [...new Set(seen.map((request) => request.signature))].slice(0, 4),
      pageErrors: errors.map((error) => error.message).slice(0, 2),
      newControls,
    };
  }

  async function sweepList(state, items, parentChain, replay, sink = { results: [], children: [] }) {
    const { results, children } = sink;
    let sinceOpen = CHUNK; // 처음부터 새로 연다
    let needReopen = true;
    const reopen = async () => {
      await openState(state);
      if (replay) await replay();
      sinceOpen = 0;
      needReopen = false;
    };
    for (const item of items) {
      if (needReopen || sinceOpen >= CHUNK) await reopen();
      let result = await measure(state, item, parentChain);
      if (result.missing) {
        await reopen();
        result = { ...(await measure(state, item, parentChain)), retried: true };
      }
      results.push(result);
      if (result.clicked) {
        sinceOpen += 1;
        if (result.newControls.length) children.push({ item, result });
        await page.keyboard.press("Escape").catch(() => {});
        await page.waitForTimeout(150);
        const stillOpen = await page.evaluate(() => window.__census.overlays()).catch(() => 99);
        if (result.reaction.urlChanged || result.pageErrors.length || stillOpen > 0) needReopen = true;
      }
    }
    return { results, children };
  }

  for (const state of STATES) {
    await openState(state);
    const items = await summary();
    const baseKeys = new Set(items.map((control) => control.key + "#" + control.occ));
    console.log(`[${state}] 후보 ${items.length}개`);
    if (LIST_ONLY) {
      for (const item of items) {
        console.log(`  ${item.key}#${item.occ} disabled=${item.disabled} own=${item.ownHandler} native=${item.native ?? ""}`);
      }
      continue;
    }
    const sink = { results: [], children: [] };
    try {
      await sweepList(state, items, null, null, sink);
    } catch (error) {
      console.log(`[${state}] 훑기 중단: ${String(error).slice(0, 200)}`);
    }
    const { results, children } = sink;
    observations.push(...results);
    // 한 단계 아래: 누르자 새로 나타난 조작(열린 창·메뉴)을 다시 누른다.
    for (const { item, result } of children) {
      // 처음부터 있던 조작(다른 창·탭을 눌러 도로 나타난 것)은 이미 위에서 쟀다.
      const childItems = result.newControls.filter((control) => !baseKeys.has(control.key + "#" + control.occ)).slice(0, 40);
      if (!childItems.length) continue;
      const parentName = item.key.split("|").slice(1).join("|");
      const replay = async () => {
        const prep = await page.evaluate(([key, occ]) => window.__census.prepare(key, occ), [item.key, item.occ]);
        if (prep && !prep.disabled) {
          await page.mouse.click(prep.x, prep.y);
          await page.waitForTimeout(700);
        }
      };
      const subSink = { results: [], children: [] };
      try {
        await sweepList(state, childItems, parentName, replay, subSink);
      } catch (error) {
        console.log(`[${state}] ${parentName} 아래 훑기 중단: ${String(error).slice(0, 200)}`);
      }
      observations.push(...subSink.results);
    }
  }

  if (LIST_ONLY) return;

  // ---- 합치기: 같은 (부모 › 이름·역할)을 한 줄로 ----
  const groups = new Map();
  for (const obs of observations) {
    const name = obs.key.split("|").slice(1).join("|");
    const role = obs.key.split("|")[0];
    const fullName = obs.parent ? obs.parent + " › " + name : name;
    const groupKey = role + "|" + fullName;
    if (!groups.has(groupKey)) groups.set(groupKey, { role, name: fullName, slots: new Map() });
    const group = groups.get(groupKey);
    const slot = group.slots.get(obs.occ) ?? [];
    slot.push(obs);
    group.slots.set(obs.occ, slot);
  }

  const RANK = { silent: 5, "no-handler": 4, "always-disabled": 3, "skipped-side-effect": 2, ok: 1 };
  const controls = [];
  for (const group of groups.values()) {
    const slotResults = [];
    for (const [occ, slotObs] of group.slots) {
      const clicked = slotObs.filter((obs) => obs.clicked);
      const states = [...new Set(slotObs.map((obs) => obs.state))];
      const merged = {
        domMutations: Math.max(0, ...clicked.map((obs) => obs.reaction.domMutations)),
        requests: Math.max(0, ...clicked.map((obs) => obs.reaction.requests)),
        focusMoved: clicked.some((obs) => obs.reaction.focusMoved),
        ariaChanged: clicked.some((obs) => obs.reaction.ariaChanged),
        dialogOpened: clicked.some((obs) => obs.reaction.dialogOpened),
        urlChanged: clicked.some((obs) => obs.reaction.urlChanged),
      };
      const skipped = slotObs.some((obs) => obs.skipped);
      const disabledEverywhere = !skipped && slotObs.every((obs) => obs.disabled);
      // 어느 상태에서도 눌러 보지 못한 것(없어짐 등)은 'unmeasured'로 따로 적고 ok로 세지 않는다.
      const unmeasured = !skipped && !disabledEverywhere && clicked.length === 0;
      const observation = {
        role: group.role,
        name: group.name,
        disabledInAllStates: disabledEverywhere,
        hasHandler: slotObs.some((obs) => obs.ownHandler),
        isLink: slotObs.some((obs) => obs.isLink),
        isFormSubmit: slotObs.some((obs) => obs.isFormSubmit),
        skipped,
        // 한 번이라도 가려지지 않고 눌린 상태가 있으면 눌린다고 본다. 눌러 본 적이 없으면 undefined.
        hitSelf: clicked.length ? clicked.some((obs) => obs.hitSelf) : undefined,
        reaction: merged,
      };
      let cls = unmeasured ? "unmeasured" : classifyControl(observation);
      // 이미 골라져 있고 바꿀 형제도 없어서 눌러도 달라질 수 없는 것은 재지 못한 것이다. 죽었다고 하지 않는다.
      const unverifiedActive = cls === "silent" && clicked.length > 0 && clicked.every((obs) => obs.untestableActive);
      if (unverifiedActive) cls = "ok";
      slotResults.push({
        occ,
        unverified: unverifiedActive ? "이미 선택된 상태라 눌러도 변화가 없고 상태를 바꿀 형제가 없다(재지 못함)" : undefined,
        class: cls,
        states,
        native: slotObs[0].native,
        detail: slotObs.map((obs) => ({
          state: obs.state,
          ...(obs.skipped ? { skipped: obs.skipReason } : {}),
          ...(obs.disabled ? { disabled: true, reason: obs.disabledReason } : {}),
          ...(obs.missing ? { missing: true } : {}),
          ...(obs.preFlipped ? { preFlippedSibling: obs.preFlipped } : {}),
          ...(obs.untestableActive ? { untestableActive: true } : {}),
          ...(obs.fileChooser ? { fileChooser: true } : {}),
          ...(obs.retriedWithDrag ? { retriedWithDrag: true } : {}),
          ...(obs.clicked
            ? {
                reaction: obs.reaction,
                hitSelf: obs.hitSelf,
                ...(obs.hit ? { coveredBy: obs.hit } : {}),
                ...(obs.baselineMutations ? { baselineMutations: obs.baselineMutations } : {}),
                ...(obs.requestSignatures.length ? { requests: obs.requestSignatures } : {}),
                ...(obs.pageErrors.length ? { pageErrors: obs.pageErrors } : {}),
              }
            : {}),
          ownHandler: obs.ownHandler,
          ...(obs.ancestorHandler && !obs.ownHandler ? { ancestorHandler: true } : {}),
        })),
      });
    }
    const worst = slotResults.reduce((a, b) => ((RANK[b.class] ?? 6) > (RANK[a.class] ?? 6) ? b : a));
    const mixed = new Set(slotResults.map((slot) => slot.class)).size > 1;
    controls.push({
      name: group.name,
      role: group.role,
      nativeControl: slotResults.find((slot) => slot.native)?.native ?? null,
      states: [...new Set(slotResults.flatMap((slot) => slot.states))],
      class: worst.class,
      evidence: {
        occurrences: slotResults.length,
        mixed,
        perOccurrence: slotResults.map((slot) => ({ occ: slot.occ, class: slot.class, ...(slot.unverified ? { unverified: slot.unverified } : {}), detail: slot.detail })),
      },
    });
  }

  mkdirSync(path.dirname(OUTPUT), { recursive: true });
  writeFileSync(
    OUTPUT,
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        fixture: "clean",
        viewport: "1440x900",
        seed_revision: seedRevision,
        restores,
        controls,
        mutating_requests_seen: mutatingRequests.map((request) => request.signature),
      },
      null,
      2,
    ),
    "utf-8",
  );
  const counts = { ok: 0, silent: 0, "no-handler": 0, "always-disabled": 0, "skipped-side-effect": 0 };
  for (const control of controls) counts[control.class] = (counts[control.class] ?? 0) + 1;
  console.log(JSON.stringify(counts));
});
