/** A tiny prelude the assembler places in the document head: it applies a
 * reader's stored theme before first paint, so a dark-theme reader never sees
 * a light flash. It reads one storage key and fails silently without storage. */
export function startupPrelude(): string {
  function begin(): void {
    if (typeof document === "undefined") return;
    try {
      const theme = window.localStorage.getItem("av-theme");
      if (theme === "light" || theme === "dark") document.documentElement.setAttribute("data-theme", theme);
    } catch { /* storage unavailable: the system preference applies */ }
  }
  return "// Generated from src/startup.ts by build.mjs.\n(" + begin.toString() + ")();\n";
}
