// The holds export's CSV: comma-separated, fields in double quotes when they hold a comma, a quote, or a line
// break, and "" for a quote inside quotes. Lines end in LF or CRLF.

export interface Record {
  line: number; // the line the record starts on, from 1
  fields: string[];
}

export class CsvError extends Error {}

export function parseCsv(text: string): Record[] {
  const records: Record[] = [];
  let fields: string[] = [];
  let field = '';
  let quoted = false;
  let line = 1;
  let start = 1;
  let atStart = true; // nothing of the current record read yet
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
      } else {
        if (c === '\n') line++;
        field += c;
      }
      continue;
    }
    if (c === '"' && field === '') {
      quoted = true;
      atStart = false;
    } else if (c === ',') {
      fields.push(field);
      field = '';
      atStart = false;
    } else if (c === '\n' || (c === '\r' && text[i + 1] === '\n')) {
      if (c === '\r') i++;
      if (!(atStart && field === '')) {
        fields.push(field);
        records.push({ line: start, fields });
      }
      fields = [];
      field = '';
      atStart = true;
      line++;
      start = line;
    } else {
      field += c;
      atStart = false;
    }
  }
  if (quoted) throw new CsvError(`line ${start}: unterminated quoted field`);
  if (!(atStart && field === '')) {
    fields.push(field);
    records.push({ line: start, fields });
  }
  return records;
}
