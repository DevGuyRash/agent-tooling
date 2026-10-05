/** Line diff for comparing two texts, such as two arms' instructions. */
export interface DiffLine { op: "same" | "add" | "del"; text: string }

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split("\n"), b = after.split("\n");
  return [...a.map(text => ({ op: "del" as const, text })), ...b.map(text => ({ op: "add" as const, text }))];
}
