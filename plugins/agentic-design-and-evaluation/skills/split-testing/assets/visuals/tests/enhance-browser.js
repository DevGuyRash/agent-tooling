// Scenarios for test_browser.py. The test prefixes this file with
// `const SCENARIO = "<name>";`, embeds it in an assembled report as a data:
// script (the report's CSP allows only those), and reads the JSON this writes
// into <pre id="av-test-out"> from Chrome's --dump-dom. Synthetic key events
// reach the report's own handlers; native defaults (Tab, a button's Enter)
// do not run, so focus moves and clicks are made directly.
/* global SCENARIO */
(function () {
  "use strict";
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const key = (el, k) => el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  const shown = el => el.getClientRects().length > 0;
  const live = () => $$("[data-av-live]").map(el => el.textContent).join(" | ");
  const drawerHead = () => ($(".av-drawer-head .av-eyebrow") || {}).textContent || "";
  const visibleRows = () => $$("table.av-ledger tbody tr[data-run]").filter(r => !r.hidden);

  /** Elements a Tab press would stop on, in a rendered report. */
  function tabStops() {
    return $$("a[href], button, input, select, textarea, summary, [tabindex]").filter(el => {
      if (el.disabled || el.tabIndex < 0 || !shown(el)) return false;
      if (el.closest("dialog:not([open])") || el.closest("[inert]")) return false;
      return true;
    });
  }

  const scenarios = {
    async "deep-run"() {
      const dialog = $("[data-av-drawer]");
      const out = { open: dialog.open, head: drawerHead(), title: $("#av-drawer-title")?.textContent, hash: location.hash, copyLink: !!$("[data-av-copy-link]", dialog), why: ($(".av-drawer-why", dialog) || {}).textContent || "" };
      out.focusInDrawer = dialog.contains(document.activeElement);
      key(document.activeElement, "ArrowRight");
      await sleep(150);
      out.afterNext = { head: drawerHead(), hash: location.hash, live: live() };
      $("[data-av-nav=\"next\"]", dialog).click();
      out.focusOnNext = document.activeElement?.matches("[data-av-nav=\"next\"]") || false;
      $(".av-drawer-close", dialog).click();
      for (let i = 0; i < 20 && dialog.open; i++) await sleep(25);
      out.closed = !dialog.open;
      out.hashAfterClose = location.hash;
      return out;
    },

    async "deep-section"() {
      await sleep(200);
      const section = $(`#${CSS.escape(decodeURIComponent(location.hash.slice(1)))}`);
      return { id: section?.id, focused: document.activeElement === $(".av-section-title", section), top: Math.round(section.getBoundingClientRect().top), scrolled: window.scrollY > 0 };
    },

    async "deep-filters"() {
      const tools = $("[data-av-ledger-tools]");
      return {
        rows: visibleRows().map(r => ({ outcome: r.dataset.outcome, text: r.textContent })),
        pressed: $$("[data-outcome]", tools).filter(b => b.getAttribute("aria-pressed") === "true").map(b => b.dataset.outcome),
        search: $('[data-filter="text"]', tools).value, scrolled: window.scrollY > 0, count: $(".av-ledger-count").textContent,
      };
    },

    async ledger() {
      const tools = $("[data-av-ledger-tools]"), total = $$("table.av-ledger tbody tr[data-run]").length;
      const out = { total, invalidDisabled: $('[data-outcome="invalid"]', tools).disabled, clearHiddenAtStart: $("[data-av-clear]").hidden };
      out.tabbableRows = $$("table.av-ledger tbody tr[data-run]").filter(r => r.tabIndex === 0).length;
      $('[data-outcome="fail"]', tools).click();
      out.failRows = visibleRows().map(r => r.dataset.outcome);
      out.hashAfterFail = location.hash;
      out.clearShownWhenFiltered = !$("[data-av-clear]").hidden;
      await sleep(700);
      out.liveAfterFail = live();
      const search = $('[data-filter="text"]', tools);
      search.value = "no run says this"; search.dispatchEvent(new Event("input", { bubbles: true }));
      const empty = $("tr[data-av-empty]");
      out.emptyShown = !!empty && !empty.hidden && shown(empty);
      out.emptyText = empty?.textContent || "";
      $("button", empty).click();
      out.afterClear = { rows: visibleRows().length, hash: location.hash, search: search.value, emptyHidden: empty.hidden };
      // Roving rows: one tab stop, arrows move.
      const first = visibleRows()[0];
      first.focus(); key(first, "ArrowDown");
      out.arrowMoved = document.activeElement === visibleRows()[1];
      out.tabbableAfterMove = $$("table.av-ledger tbody tr[data-run]").filter(r => r.tabIndex === 0).length;
      out.describedBy = !!first.getAttribute("aria-describedby") && !!document.getElementById(first.getAttribute("aria-describedby"));
      key(document.activeElement, "Enter");
      out.enterOpened = $("[data-av-drawer]").open;
      $("[data-av-drawer]").close();
      // Sorting by a numeric column keeps rows and the select in step.
      const timeHead = $$("table.av-ledger th[data-sortable=\"num\"]").find(th => th.dataset.col === "time");
      timeHead.click(); timeHead.click();
      const times = visibleRows().map(r => Number(r.cells[timeHead.cellIndex].dataset.sort));
      out.sortedDescending = times.every((t, i) => i === 0 || times[i - 1] >= t);
      out.sortSelect = $("[data-av-sort]")?.value || "";
      // "/" from outside a field goes to the search.
      document.body.focus(); key(document.body, "/");
      out.slashFocusedSearch = document.activeElement === search;
      return out;
    },

    async export() {
      const blobs = [], names = [];
      URL.createObjectURL = blob => { blobs.push(blob); return "blob:av-test"; };
      URL.revokeObjectURL = () => {};
      HTMLAnchorElement.prototype.click = function () { names.push(this.download); };
      const tools = $("[data-av-ledger-tools]");
      $('[data-outcome="fail"]', tools).click();
      const shownRuns = visibleRows().length;
      $('[data-av-export="csv"]').click();
      $('[data-av-export="json"]').click();
      const csv = await blobs[0].text(), json = JSON.parse(await blobs[1].text());
      return {
        names, shownRuns, csvLines: csv.replace(/^\uFEFF/, "").trim().split("\r\n"), csvType: blobs[0].type,
        jsonRuns: json.runs.length, status: $(".av-ledger-export + .av-export-status")?.textContent || "",
        label: $(".av-ledger-export-what")?.textContent || "", footerButton: !!$('[data-av-export="json-footer"]'),
      };
    },

    async keyboard() {
      const out = { tabStops: tabStops().length, sections: $$(".av-section[id]").length };
      // The first case dossier: its runs are one roving group, a row per arm.
      const block = $(".av-block--cases [data-av-roving]");
      const marks = $$("button[data-run]", block);
      out.marks = marks.length;
      out.markStops = marks.filter(m => m.tabIndex === 0).length;
      out.titles = $$("button[data-run][title]").length;
      const first = marks.find(m => m.tabIndex === 0);
      first.focus();
      const tip = $(".av-tip");
      out.tip = { shown: tip?.hasAttribute("data-show") || false, text: tip?.textContent || "", label: first.getAttribute("aria-label") };
      key(first, "ArrowRight");
      const second = document.activeElement;
      out.rightMoved = second !== first && marks.includes(second);
      out.stopFollows = second.tabIndex === 0 && first.tabIndex === -1;
      key(second, "ArrowDown");
      const below = document.activeElement;
      out.downRow = below !== second && marks.includes(below) && below.closest("[data-av-row]") !== second.closest("[data-av-row]");
      key(below, "End");
      out.endIsLast = document.activeElement === marks[marks.length - 1];
      key(document.activeElement, "Home");
      out.homeIsFirst = document.activeElement === marks[0];
      const opener = document.activeElement;
      opener.click();
      const dialog = $("[data-av-drawer]");
      out.opened = dialog.open;
      out.hashOpen = location.hash;
      out.tipHiddenWhenOpen = !tip.hasAttribute("data-show");
      dialog.close();
      for (let i = 0; i < 20 && (document.activeElement !== opener || location.hash); i++) await sleep(25);
      out.focusReturned = document.activeElement === opener;
      out.hashClosed = location.hash;
      // Section links and the second skip link.
      out.anchors = $$(".av-section[id]").every(s => $(".av-anchor", s)?.getAttribute("href") === `#${s.id}`);
      out.skipLedger = $("[data-av-skip-ledger]")?.getAttribute("href") || "";
      return out;
    },

    async print() {
      // A callout's tone class decides its color (the default never outranks it).
      const callout = $(".av-callout-box.av-tone--warn"), probe = document.createElement("span");
      probe.style.color = "var(--av-warn)"; document.body.appendChild(probe);
      const tone = { callout: callout ? getComputedStyle(callout).borderLeftColor : null, warn: getComputedStyle(probe).color };
      probe.remove();
      const closed = $$("details:not([open])").filter(d => !d.closest("dialog")).length;
      window.dispatchEvent(new Event("beforeprint"));
      const during = { theme: document.documentElement.getAttribute("data-theme"), closed: $$("details:not([open])").filter(d => !d.closest("dialog")).length };
      window.dispatchEvent(new Event("afterprint"));
      return { tone, closedBefore: closed, during, after: { theme: document.documentElement.getAttribute("data-theme"), closed: $$("details:not([open])").filter(d => !d.closest("dialog")).length } };
    },

    async drawers() {
      const dialog = $("[data-av-drawer]"), n = $$("table.av-ledger tbody tr[data-run]").length, seen = [];
      for (let i = 1; i <= n; i++) {
        location.hash = `#run-${i}`;
        await sleep(30);
        seen.push({ open: dialog.open, head: drawerHead(), why: ($(".av-drawer-why", dialog) || {}).textContent || "", hostile: $$("x-hostile").length });
      }
      dialog.close();
      return { runs: n, seen };
    },
  };

  const write = value => {
    const pre = document.createElement("pre");
    pre.id = "av-test-out";
    pre.textContent = JSON.stringify(value);
    document.body.appendChild(pre);
  };
  const start = () => {
    if (!document.querySelector("[data-av-ready]")) { setTimeout(start, 25); return; }
    setTimeout(() => {
      Promise.resolve().then(() => scenarios[SCENARIO]()).then(write, error => write({ error: String(error && error.stack || error) }));
    }, 150);
  };
  start();
})();
