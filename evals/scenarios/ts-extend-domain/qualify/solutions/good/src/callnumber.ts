// Call numbers in the library's house scheme (docs/callnumbers.md): reading, checking, and shelf order.

const COLLECTIONS = new Map<string, [number, string]>([
  ['', [0, 'Adult']], ['J', [1, "Children's"]], ['YA', [2, 'Young adult']], ['REF', [3, 'Reference']],
  ['OS', [4, 'Oversize']],
]);
// Word classes stand after every Dewey number of their collection, in this order.
const WORD_CLASSES = new Map<string, [number, string]>([['B', [1, 'Biography']], ['GN', [2, 'Graphic novels']],
  ['FIC', [3, 'Fiction']]]);
const DEWEY = /^(\d{3})(?:\.(\d+))?$/;
const CUTTER = /^([A-Z]{1,3})(\d*)$/;
const NAME = /^[A-Z][A-Z'-]*$/;
const YEAR = /^(?:1[5-9]|20)\d\d$/;
const VOLUME = /^V\.([1-9]\d{0,2})$/;
const COPY = /^C\.([1-9]\d{0,2})$/;

export class CallNumberError extends Error {}

export interface CallNumber {
  collection: string; // '' (adult), 'J', 'YA', 'REF', or 'OS'
  klass: string; // a Dewey number as written, or a word class
  mark: string; // the Cutter or the name, as written
  year?: number;
  volume?: number;
  copy?: number;
}

/** Upper case, surrounding space removed, every run of white space made one space. */
export function normalize(text: string): string {
  return text.toUpperCase().split(/\s+/).filter(Boolean).join(' ');
}

export function parse(text: string): CallNumber {
  const words = normalize(text).split(' ').filter(Boolean);
  if (words.length === 0) throw new CallNumberError('no call number');
  let collection = '';
  if (words[0] !== '' && COLLECTIONS.has(words[0])) {
    collection = words.shift()!;
    if (words.length === 0) throw new CallNumberError(`no class after '${collection}'`);
  }
  const klass = words.shift()!;
  let what: string, pattern: RegExp;
  if (/^[0-9]/.test(klass)) {
    if (!DEWEY.test(klass)) throw new CallNumberError(`bad class number '${klass}'`);
    [what, pattern] = ['cutter', CUTTER];
  } else if (WORD_CLASSES.has(klass)) {
    [what, pattern] = ['name', NAME];
  } else {
    throw new CallNumberError(`unknown class '${klass}'`);
  }
  if (words.length === 0) throw new CallNumberError(`no ${what} after '${klass}'`);
  const mark = words.shift()!;
  if (!pattern.test(mark)) throw new CallNumberError(`bad ${what} '${mark}'`);
  const cn: CallNumber = { collection, klass, mark };
  let stage = 0;
  for (const word of words) {
    let m: RegExpExecArray | null;
    if (stage < 1 && YEAR.test(word)) {
      cn.year = Number(word);
      stage = 1;
    } else if (stage < 2 && (m = VOLUME.exec(word))) {
      cn.volume = Number(m[1]);
      stage = 2;
    } else if (stage < 3 && (m = COPY.exec(word))) {
      cn.copy = Number(m[1]);
      stage = 3;
    } else {
      throw new CallNumberError(`unexpected '${word}'`);
    }
  }
  return cn;
}

/** The call number written out: capitals, single spaces. */
export function format(cn: CallNumber): string {
  return [cn.collection, cn.klass, cn.mark, cn.year ? String(cn.year) : '', cn.volume ? `V.${cn.volume}` : '',
    cn.copy ? `C.${cn.copy}` : ''].filter(Boolean).join(' ');
}

/** The heading a shelf list puts over this call number's section. */
export function section(cn: CallNumber): string {
  const name = WORD_CLASSES.get(cn.klass)?.[1] ?? `${cn.klass[0]}00s`;
  return `${COLLECTIONS.get(cn.collection)![1]} · ${name}`;
}

function cmp(a: string | number, b: string | number): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Shelf order (docs/callnumbers.md): negative when a stands before b, 0 when they stand together. */
export function compare(a: CallNumber, b: CallNumber): number {
  return cmp(COLLECTIONS.get(a.collection)![0], COLLECTIONS.get(b.collection)![0])
    || compareClassAndMark(a, b)
    || cmp(a.year ?? 0, b.year ?? 0)
    || cmp(a.volume ?? 0, b.volume ?? 0)
    || cmp(a.copy ?? 0, b.copy ?? 0);
}

function compareClassAndMark(a: CallNumber, b: CallNumber): number {
  const kindA = WORD_CLASSES.get(a.klass)?.[0] ?? 0;
  const kindB = WORD_CLASSES.get(b.klass)?.[0] ?? 0;
  if (kindA !== kindB) return cmp(kindA, kindB);
  if (kindA !== 0) return cmp(a.mark.replace(/['-]/g, ''), b.mark.replace(/['-]/g, ''));
  const [, wholeA, fracA = ''] = DEWEY.exec(a.klass)!;
  const [, wholeB, fracB = ''] = DEWEY.exec(b.klass)!;
  const [, lettersA, digitsA] = CUTTER.exec(a.mark)!;
  const [, lettersB, digitsB] = CUTTER.exec(b.mark)!;
  // Fractions and Cutter digits are decimal fractions: compared digit by digit, trailing zeros dropped.
  return cmp(Number(wholeA), Number(wholeB))
    || cmp(fracA.replace(/0+$/, ''), fracB.replace(/0+$/, ''))
    || cmp(lettersA, lettersB)
    || cmp(digitsA.replace(/0+$/, ''), digitsB.replace(/0+$/, ''));
}
