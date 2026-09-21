/** The assembler places this tiny, generated prelude before reader content.
 * It never reads or writes reader records. A bounded visibility gate prevents
 * authored defaults from flashing before the controllers restore owned state.
 */
export function startupPrelude(): string {
  function begin(): void {
    if(typeof document==='undefined'||typeof window==='undefined')return;
    const doc = document, host = doc.documentElement;
    if(!host||!doc.head)return;
    if (host.hasAttribute('data-av-starting')) return;
    const style = doc.createElement('style');
    style.textContent = '[data-av-starting] .av-workspace:not([data-av-ready]) { visibility: hidden; }';
    doc.head.appendChild(style); host.setAttribute('data-av-starting', '');
    let complete = false, claimed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const release = () => {
      if (complete) return; complete = true; clearTimeout(timer);
      host.removeAttribute('data-av-starting'); style.remove();
      doc.removeEventListener('av-report-ready', check);
      doc.removeEventListener('DOMContentLoaded', loaded);
      doc.removeEventListener('av-report-initializing', initializing);
      window.removeEventListener('error', release);
    };
    const check = () => {
      if (doc.readyState !== 'loading' && !doc.querySelector('.av-workspace:not([data-av-ready])')) release();
    };
    // Missing enhancement, blocked storage, or a failed author script must
    // never leave the evidence invisible. No-JavaScript documents never gate.
    // The missing-author budget begins after parsing, not before a large
    // offline bundle has even loaded. An actual controller owns bounded
    // storage reads (open + transaction watchdogs); allow those to settle
    // instead of showing a partly restored theme and a different section.
    const arm = () => { clearTimeout(timer); timer = setTimeout(release, claimed ? 12000 : 2000); };
    const initializing = () => { if (complete || claimed) return; claimed = true; if (doc.readyState !== 'loading') arm(); };
    const loaded = () => { check(); if (!complete) arm(); };
    doc.addEventListener('av-report-ready', check);
    doc.addEventListener('av-report-initializing', initializing);
    doc.addEventListener('DOMContentLoaded', loaded);
    if (doc.readyState !== 'loading') loaded();
    window.addEventListener('error', release);
  }
  return '// Generated from src/startup.ts by build.mjs.\n(' + begin.toString() + ')();\n';
}
/** Readiness is separate from whenIdle: later edits do not delay first paint. */
export function notifyReportReady(document: Document): void {
  const Constructor = document.defaultView?.Event;
  if (Constructor) document.dispatchEvent(new Constructor('av-report-ready'));
}

/** Claim the bounded initial-restore phase before synchronous enhancement. */
export function notifyReportInitializing(document: Document): void {
  const Constructor = document.defaultView?.Event;
  if (Constructor) document.dispatchEvent(new Constructor('av-report-initializing'));
}
