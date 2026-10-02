// Plain-text tables: columns two spaces apart, each as wide as its widest cell, no trailing spaces.

export type Align = 'left' | 'right';

/** Lay out rows (the first is usually a header) with each column aligned as `align` says. */
export function renderTable(rows: string[][], align: Align[]): string[] {
  const widths = align.map((_, c) => Math.max(0, ...rows.map((row) => (row[c] ?? '').length)));
  return rows.map((row) =>
    align
      .map((a, c) => {
        const cell = row[c] ?? '';
        return a === 'right' ? cell.padStart(widths[c]) : cell.padEnd(widths[c]);
      })
      .join('  ')
      .trimEnd(),
  );
}
